"""
Mole FM Reader Builder
Rebuilds the trilingual literacy reader webapp with the latest newscast audio.
Runs after TTS generation each hour — keeps the reader fresh 24/7.

What it does:
1. Reads the latest newscast audio (FR) and translates to EN + ES
2. Generates word-level timing for all 3 languages
3. Extracts article titles + seek timestamps for the article picker
4. Copies audio_fr.mp3 / audio_en.mp3 / audio_es.mp3 alongside index.html
5. index.html references them as relative URLs — NO base64, NO inline blobs

AUDIO ARCHITECTURE (permanent fix):
  - Audio files served as separate static .mp3 files (not base64 embedded)
  - index.html is ~50KB instead of ~4MB
  - Eliminates Mobile Safari silent failure from >4MB inline <script> blocks
5. Copies to /home/user/workspace/molefm/reader/webapp/index.html
"""

import os
import sys
import json
import re
import asyncio
import datetime
import subprocess
import tempfile
import shutil

READER_DIR   = "/home/user/workspace/molefm/reader"
WEBAPP_DIR   = "/home/user/workspace/molefm/reader/webapp"
SCRIPTS_DIR  = "/home/user/workspace/molefm/scripts"
AUDIO_DIR    = "/home/user/workspace/molefm/audio"
PODCAST_DIR  = "/home/user/workspace/molefm/audio/podcasts"

# Voices for EN and ES TTS
VOICE_EN = "en-GB-SoniaNeural"
VOICE_ES = "es-ES-ElviraNeural"


# ── HELPERS ──────────────────────────────────────────────────────────────────

def copy_audio_to_webapp(src_path, dest_name):
    """Copy an MP3 file to the webapp directory with a fixed name."""
    dest_path = os.path.join(WEBAPP_DIR, dest_name)
    shutil.copy2(src_path, dest_path)
    size_kb = os.path.getsize(dest_path) / 1024
    return dest_path, size_kb


def get_duration_ms(path):
    """Get MP3 duration in milliseconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True
        )
        return int(float(result.stdout.strip()) * 1000)
    except:
        return 0


def interpolate_timing(text, total_ms, lang="fr"):
    """
    Generate word-level timing by linear interpolation across total_ms.
    Real word timing would require forced alignment (WhisperX etc.) but
    linear interpolation is good enough for karaoke highlighting.
    """
    words_raw = text.split()
    # Weight longer words slightly more
    weights = [max(1, len(w)) for w in words_raw]
    total_weight = sum(weights)
    timing = []
    t = 100  # 100ms head start
    for i, (w, wt) in enumerate(zip(words_raw, weights)):
        duration = int((wt / total_weight) * (total_ms - 100))
        timing.append({"word": w, "start_ms": t, "end_ms": t + duration})
        t += duration
    return timing


def translate_text(text, target_lang):
    """Translate French text to EN or ES using deep-translator (free)."""
    try:
        from deep_translator import GoogleTranslator
        # Split into chunks of ~4500 chars to avoid API limits
        chunks = []
        while len(text) > 4000:
            split = text[:4000].rfind('. ')
            if split < 100:
                split = 4000
            chunks.append(text[:split+1])
            text = text[split+1:].strip()
        if text:
            chunks.append(text)
        translated = []
        for chunk in chunks:
            t = GoogleTranslator(source='fr', target=target_lang).translate(chunk)
            translated.append(t)
        return ' '.join(translated)
    except Exception as e:
        print(f"  [WARN] Translation to {target_lang} failed: {e}")
        return text  # fallback: use FR text


async def synth_async(text, voice, output_path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate="+0%", volume="+0%")
    await communicate.save(output_path)


def synth(text, voice, output_path):
    asyncio.run(synth_async(text, voice, output_path))


def get_full_text(script_path):
    """Extract the full broadcast text from a JSON script."""
    with open(script_path) as f:
        script = json.load(f)
    parts = []
    for seg in script["segments"]:
        parts.append(seg["text"])
    return " ".join(parts), script


def parse_articles(news_text, lang):
    """Extract article titles and positions from NEWS_MAIN text."""
    kw = {"fr": "Titre", "en": "Title", "es": "Título"}.get(lang, "Titre")
    pattern = rf'{kw}\s+(\d+)\s*:\s*(.+?)(?={kw}\s+\d+|$)'
    matches = re.findall(pattern, news_text, re.DOTALL)
    articles = []
    for num, body in matches:
        body = body.strip()
        sentences = re.split(r'(?<=[.!?])\s+', body)
        title = sentences[0].rstrip('.').strip()
        if len(title) < 5:
            title = body[:80].rstrip('.')
        articles.append({"num": int(num), "title": title[:90]})
    return articles


def find_article_seek_points(word_timing, articles, lang):
    """Find the timestamp where each article starts in the word timing."""
    kw = {"fr": "Titre", "en": "Title", "es": "Título"}.get(lang, "Titre")
    words = [w["word"] for w in word_timing]
    result = []
    for art in articles:
        target_num = str(art["num"])
        for i, w in enumerate(words):
            if w.rstrip(":") == kw and i + 1 < len(words):
                nw = words[i+1].rstrip(":").strip()
                if nw == target_num:
                    result.append({
                        "num": art["num"],
                        "word_idx": i,
                        "start_ms": word_timing[i]["start_ms"],
                        "title": art["title"]
                    })
                    break
    return result


# ── MAIN BUILD FUNCTION ───────────────────────────────────────────────────────

def build(script_path, audio_fr_path, sponsor_text=None):
    print(f"\n=== Mole FM Reader Builder ===")
    print(f"  Script: {os.path.basename(script_path)}")
    print(f"  Audio:  {os.path.basename(audio_fr_path)}")

    os.makedirs(READER_DIR, exist_ok=True)
    os.makedirs(WEBAPP_DIR, exist_ok=True)

    # ── 1. Get FR text and script data ──────────────────────────────────────
    full_text_fr, script = get_full_text(script_path)
    broadcast_hour = script.get("broadcast_hour", datetime.datetime.now().strftime("%Y-%m-%d %H:00"))
    
    # Inject sponsor into FR text if provided
    if sponsor_text:
        full_text_fr = sponsor_text + " " + full_text_fr

    # ── 2. Translate to EN and ES ────────────────────────────────────────────
    print("  Translating to EN...")
    full_text_en = translate_text(full_text_fr, "en")
    print("  Translating to ES...")
    full_text_es = translate_text(full_text_fr, "es")

    # ── 3. Generate EN and ES audio ──────────────────────────────────────────
    audio_en_path = os.path.join(READER_DIR, "broadcast_en.mp3")
    audio_es_path = os.path.join(READER_DIR, "broadcast_es.mp3")
    shutil.copy(audio_fr_path, os.path.join(READER_DIR, "broadcast_fr.mp3"))

    print("  Generating EN audio...")
    synth(full_text_en, VOICE_EN, audio_en_path)
    print("  Generating ES audio...")
    synth(full_text_es, VOICE_ES, audio_es_path)

    # ── 4. Get durations and build word timing ───────────────────────────────
    dur_fr = get_duration_ms(audio_fr_path)
    dur_en = get_duration_ms(audio_en_path)
    dur_es = get_duration_ms(audio_es_path)

    print(f"  Durations: FR={dur_fr//1000}s EN={dur_en//1000}s ES={dur_es//1000}s")

    wt_fr = interpolate_timing(full_text_fr, dur_fr, "fr")
    wt_en = interpolate_timing(full_text_en, dur_en, "en")
    wt_es = interpolate_timing(full_text_es, dur_es, "es")

    word_timing = {"fr": wt_fr, "en": wt_en, "es": wt_es}

    # ── 5. Extract articles ──────────────────────────────────────────────────
    news_seg = next((s for s in script["segments"] if s["segment"] == "NEWS_MAIN"), None)
    news_fr = news_seg["text"] if news_seg else ""
    news_en = translate_text(news_fr, "en") if news_seg else ""
    news_es = translate_text(news_fr, "es") if news_seg else ""

    articles_fr = parse_articles(news_fr, "fr")
    articles_en = parse_articles(news_en, "en")
    articles_es = parse_articles(news_es, "es")

    # Use FR timing for all seeks (they match the FR broadcast)
    seeks_fr = find_article_seek_points(wt_fr, articles_fr, "fr")
    seeks_en = find_article_seek_points(wt_en, articles_en, "en")
    seeks_es = find_article_seek_points(wt_es, articles_es, "es")

    # Fallback: if EN/ES seek detection fails, scale from FR timestamps
    if not seeks_en and seeks_fr:
        scale = dur_en / max(dur_fr, 1)
        seeks_en = [{"num": a["num"], "word_idx": 0,
                     "start_ms": int(a["start_ms"] * scale),
                     "title": articles_en[i]["title"] if i < len(articles_en) else a["title"]}
                    for i, a in enumerate(seeks_fr)]
    if not seeks_es and seeks_fr:
        scale = dur_es / max(dur_fr, 1)
        seeks_es = [{"num": a["num"], "word_idx": 0,
                     "start_ms": int(a["start_ms"] * scale),
                     "title": articles_es[i]["title"] if i < len(articles_es) else a["title"]}
                    for i, a in enumerate(seeks_fr)]

    articles_data = {"fr": seeks_fr, "en": seeks_en, "es": seeks_es}

    # ── 6. Copy audio files to webapp (served as separate static files) ──────
    print("  Copying audio files to webapp...")
    _, kb_fr = copy_audio_to_webapp(audio_fr_path, "audio_fr.mp3")
    _, kb_en = copy_audio_to_webapp(audio_en_path, "audio_en.mp3")
    _, kb_es = copy_audio_to_webapp(audio_es_path, "audio_es.mp3")
    print(f"  [OK] audio_fr.mp3 ({kb_fr:.0f} KB), audio_en.mp3 ({kb_en:.0f} KB), audio_es.mp3 ({kb_es:.0f} KB)")

    # ── 7. Save data files ────────────────────────────────────────────────────
    with open(os.path.join(READER_DIR, "word_timing.json"), "w") as f:
        json.dump(word_timing, f, ensure_ascii=False)
    with open(os.path.join(READER_DIR, "articles.json"), "w") as f:
        json.dump(articles_data, f, ensure_ascii=False, indent=2)

    trilingual = {
        "station": "Mole FM",
        "broadcast_hour": broadcast_hour,
        "segments": [{"segment": s["segment"], "fr": s["text"],
                       "en": translate_text(s["text"], "en"),
                       "es": translate_text(s["text"], "es")}
                     for s in script["segments"]]
    }
    with open(os.path.join(READER_DIR, "trilingual_content.json"), "w") as f:
        json.dump(trilingual, f, ensure_ascii=False, indent=2)

    # ── 8. Copy all 24h newscast mp3s into webapp/audio/ for archive player ──────
    import glob as _glob
    _webapp_audio_dir = os.path.join(WEBAPP_DIR, "audio")
    os.makedirs(_webapp_audio_dir, exist_ok=True)
    _audio_files = sorted(_glob.glob(os.path.join(AUDIO_DIR, "newscast_*.mp3")))
    _broadcasts = []
    _tz_haiti = datetime.timezone(datetime.timedelta(hours=-4))
    for _af in _audio_files:
        _fname = os.path.basename(_af)
        _dest = os.path.join(_webapp_audio_dir, _fname)
        if not os.path.exists(_dest):
            shutil.copy2(_af, _dest)
        # Parse timestamp and format Haiti-time label
        try:
            _ts_str = _fname.replace("newscast_", "").replace(".mp3", "")
            _dt_utc = datetime.datetime.strptime(_ts_str, "%Y%m%d_%H%M")
            _dt_ht  = _dt_utc.replace(tzinfo=datetime.timezone.utc).astimezone(_tz_haiti)
            _label  = _dt_ht.strftime("%a %d %b · %Hh%M")
            _is_current = (_fname == os.path.basename(audio_fr_path))
        except ValueError:
            _label = _fname
            _is_current = False
        _broadcasts.append({
            "filename": _fname,
            "audio_url": f"audio/{_fname}",
            "label": _label,
            "is_current": _is_current,
        })
    broadcasts_json_str = json.dumps(list(reversed(_broadcasts)), ensure_ascii=False)

    # Auto-advance playlist (all broadcasts, newest first)
    _playlist = []
    for _b in reversed(_broadcasts):
        _playlist.append({
            "audio_fr": _b["audio_url"],
            "audio_en": "audio_en.mp3",
            "audio_es": "audio_es.mp3",
            "broadcast_hour": _b["label"],
            "label": _b["label"],
        })
    playlist_json_str = json.dumps(_playlist, ensure_ascii=False)

    # ── 9. Copy FR podcasts into webapp/podcasts/ and build manifest ──────────────
    _webapp_pod_dir = os.path.join(WEBAPP_DIR, "podcasts")
    os.makedirs(_webapp_pod_dir, exist_ok=True)
    _pod_files = sorted(_glob.glob(os.path.join(PODCAST_DIR, "podcast_fr_*.mp3")), reverse=True)[:12]
    _podcasts = []
    for _pf in _pod_files:
        _pfname = os.path.basename(_pf)
        _pdest = os.path.join(_webapp_pod_dir, _pfname)
        if not os.path.exists(_pdest):
            shutil.copy2(_pf, _pdest)
        try:
            _pts = _pfname.replace("podcast_fr_", "").replace(".mp3", "")
            _pdt_utc = datetime.datetime.strptime(_pts, "%Y%m%d_%H%M")
            _pdt_ht  = _pdt_utc.replace(tzinfo=datetime.timezone.utc).astimezone(_tz_haiti)
            _hr = _pdt_ht.hour
            if   _hr == 12: _slot = "Midi"
            elif _hr == 15: _slot = "Après-midi"
            elif _hr == 21: _slot = "Soir"
            else:           _slot = f"{_hr:02d}h"
            _plabel = f"{_pdt_ht.strftime('%a %d %b')} · {_slot}"
        except ValueError:
            _plabel = _pfname
            _slot = ""
        _dur_kb = os.path.getsize(_pf) // 1024
        _est_min = max(1, round(_dur_kb / 192))
        _podcasts.append({
            "filename": _pfname,
            "audio_url": f"podcasts/{_pfname}",
            "label": _plabel,
            "slot": _slot,
            "est_min": _est_min,
        })
    podcasts_json_str = json.dumps(_podcasts, ensure_ascii=False)

    # ── 9. Build index.html ───────────────────────────────────────────────────
    print("  Building index.html...")
    html = build_html(
        wt_fr=wt_fr, wt_en=wt_en, wt_es=wt_es,
        articles=articles_data,
        broadcast_hour=broadcast_hour,
        trilingual=trilingual,
        sponsor_text=sponsor_text,
        playlist_json=playlist_json_str,
        broadcasts_json=broadcasts_json_str,
        podcasts_json=podcasts_json_str
    )

    out_path = os.path.join(WEBAPP_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  [OK] index.html written — {size_mb:.1f}MB")
    return out_path


def build_html(wt_fr, wt_en, wt_es,
               articles, broadcast_hour, trilingual, sponsor_text=None, playlist_json=None,
               broadcasts_json=None, podcasts_json=None):
    """Generate the full self-contained reader HTML."""

    wt_json = json.dumps({"fr": wt_fr, "en": wt_en, "es": wt_es}, ensure_ascii=False)
    articles_json = json.dumps(articles, ensure_ascii=False)
    if playlist_json is None:
        playlist_json = "[]"
    if broadcasts_json is None:
        broadcasts_json = "[]"
    if podcasts_json is None:
        podcasts_json = "[]"

    # Build trilingual text panels
    def make_words(wt, lang, panel_id):
        parts = []
        for i, w in enumerate(wt):
            parts.append(f'<span class="w" data-i="{i}" onclick="seekW(\'{lang}\',{i})">{w["word"]}</span>')
            if w["word"].rstrip('"\'').endswith(('.', '!', '?')):
                parts.append('<br><br>')
        return f'<div class="lp" id="{panel_id}">' + ' '.join(parts) + '</div>'

    words_fr = make_words(wt_fr, "fr", "wfr")
    words_en = make_words(wt_en, "en", "wen")
    words_es = make_words(wt_es, "es", "wes")
    
    # Triple view word panels
    tw_fr = make_words(wt_fr, "fr", "twfr").replace('class="lp"', 'class="lp twp"')
    tw_en = make_words(wt_en, "en", "twen").replace('class="lp"', 'class="lp twp"')
    tw_es = make_words(wt_es, "es", "twes").replace('class="lp"', 'class="lp twp"')

    # Load active sponsors from config for visual banner
    _spcfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "sponsors.json")
    try:
        with open(_spcfg_path, "r", encoding="utf-8") as _spf:
            _spcfg = json.load(_spf)
        _active_sponsors = [s for s in _spcfg["sponsors"] if s.get("active", False)]
    except Exception:
        _active_sponsors = [{"id":"mathurin_beach","name": "Mathurin Beach Resort", "logo": "sponsors/mathurin_beach.jpg", "tagline":"L'escapade parfaite au nord d'Haïti","cta_label":"Réserver","cta_url":"https://wa.me/50938554309","video_url":""}]
    if not _active_sponsors:
        _active_sponsors = [{"id":"mathurin_beach","name": "Mathurin Beach Resort", "logo": "sponsors/mathurin_beach.jpg", "tagline":"L'escapade parfaite au nord d'Haïti","cta_label":"Réserver","cta_url":"https://wa.me/50938554309","video_url":""}]
    _label = "PARTENAIRE OFFICIEL" if len(_active_sponsors) == 1 else "NOS PARTENAIRES"
    _cards_html = ""
    for _s in _active_sponsors:
        _sn = _s.get("name","")
        _sl = _s.get("logo","")
        _st = _s.get("tagline","")
        _sc = _s.get("cta_label","Visiter")
        _su = _s.get("cta_url","#")
        _sv = _s.get("video_url","")
        _sid = _s.get("id","sp")
        # Abbreviated initials fallback
        _initials = "".join(w[0] for w in _sn.split()[:3]).upper()
        _video_btn = (
            f'<button class="sp-vid-btn" onclick="toggleSpVid(\'{_sid}\')" aria-label="Voir la vidéo">'
            f'<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>'
            f'</button>'
        ) if _sv else ""
        _video_embed = (
            f'<div class="sp-vid" id="spvid-{_sid}" style="display:none">'
            f'<video controls playsinline style="width:100%;border-radius:12px;margin-top:8px">'
            f'<source src="{_sv}" type="video/mp4">'
            f'</video></div>'
        ) if _sv else ""
        _cards_html += (
            f'<div class="sponsor-card">'
            f'<div class="sponsor-card-inner">'
            f'<div class="sp-logo-wrap">'
            f'<img class="sp-logo-img" src="{_sl}" alt="{_sn}" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'" />'
            f'<div class="sp-logo-fallback" style="display:none">{_initials}</div>'
            f'</div>'
            f'<div class="sp-info">'
            f'<p class="sp-badge">{_label}</p>'
            f'<p class="sp-name">{_sn}</p>'
            f'<p class="sp-tagline">{_st}</p>'
            f'</div>'
            f'<div class="sp-actions">'
            f'{_video_btn}'
            f'<a class="sp-cta" href="{_su}" target="_blank" rel="noreferrer">{_sc}</a>'
            f'</div>'
            f'</div>'
            f'{_video_embed}'
            f'</div>'
        )
    sponsor_badge = f'<div class="sponsor-rail">{_cards_html}</div>'


    # Format broadcast date nicely
    try:
        bh_dt = datetime.datetime.strptime(broadcast_hour, "%Y-%m-%d %H:%M")
        JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
        MOIS  = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
        bdate_fr = f"{JOURS[bh_dt.weekday()]} {bh_dt.day} {MOIS[bh_dt.month-1]} {bh_dt.year}".upper()
        btime_fr = bh_dt.strftime("%Hh%M")
    except:
        bdate_fr = broadcast_hour.upper()
        btime_fr = ""

    hspd_btns = ''.join(
        f'<button class="hspd{" on" if s == 1.0 else ""}" data-speed="{s}" onclick="setSpeed({s})">{s}×</button>'
        for s in [0.5, 0.75, 1, 1.25, 1.5, 2, 3]
    )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mole FM — Lecteur Trilingue</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{
  --red:#dc2626;--red-d:#b91c1c;--red-glow:rgba(220,38,38,.15);
  --navy:#020617;--s800:#1e293b;--s700:#334155;--s600:#475569;
  --s500:#64748b;--s400:#94a3b8;--s300:#cbd5e1;--s200:#e2e8f0;
  --s100:#f1f5f9;--white:#ffffff;
  --cfr:#dc2626;--cen:#2563eb;--ces:#16a34a;--pod:#7c3aed;
  --sp1:4px;--sp2:8px;--sp3:12px;--sp4:16px;--sp5:20px;--sp6:24px;--sp8:32px;
  --r-sm:6px;--r-md:8px;--r-lg:12px;--r-xl:16px;--r-full:9999px;
  --font:'Inter',ui-sans-serif,system-ui,-apple-system,sans-serif;
  --tx:11px;--ts:13px;--tb:15px;--tl:17px;--txl:20px;
  --sh-card:0 1px 3px rgba(0,0,0,.08),0 1px 2px rgba(0,0,0,.06);
  --sh-md:0 4px 12px rgba(0,0,0,.1),0 2px 4px rgba(0,0,0,.06);
  --sh-lg:0 8px 24px rgba(0,0,0,.12);
  --ease:.16s cubic-bezier(.4,0,.2,1);
}}
*{{box-sizing:border-box;margin:0;padding:0;border:none;outline:none;}}
html{{height:100%;position:fixed;width:100%;top:0;left:0;}}
body{{
  height:100%;width:100%;
  font-family:var(--font);font-size:var(--tb);
  color:var(--navy);background:var(--s100);
  display:flex;flex-direction:column;overflow:hidden;
  -webkit-font-smoothing:antialiased;
}}
.hdr{{
  display:flex;align-items:center;justify-content:space-between;
  padding:0 var(--sp5);height:56px;
  background:var(--white);box-shadow:0 1px 0 var(--s200);
  flex-shrink:0;gap:var(--sp3);position:relative;z-index:30;
}}
.logo{{display:flex;align-items:center;gap:var(--sp3);flex-shrink:0;text-decoration:none;}}
.logo-mark{{width:36px;height:36px;background:var(--red);border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;}}
.logo-mark svg{{fill:#fff;}}
.logo-name{{font-size:var(--tl);font-weight:800;color:var(--navy);letter-spacing:-.02em;line-height:1;}}
.logo-name span{{color:var(--red);}}
.logo-sub{{font-size:10px;font-weight:600;color:var(--s500);text-transform:uppercase;letter-spacing:.08em;margin-top:2px;}}
.hdr-langs{{display:flex;gap:var(--sp2);align-items:center;}}
.hlt{{
  padding:5px 11px;border-radius:var(--r-full);
  border:1.5px solid var(--s200);font-size:12px;font-weight:700;color:var(--s500);
  background:transparent;cursor:pointer;transition:all var(--ease);white-space:nowrap;min-height:32px;
}}
.hlt:hover{{border-color:var(--s400);color:var(--s700);}}
.hlt:active{{transform:scale(.95);}}
.hlt.afr{{background:var(--cfr);color:#fff;border-color:var(--cfr);}}
.hlt.aen{{background:var(--cen);color:#fff;border-color:var(--cen);}}
.hlt.aes{{background:var(--ces);color:#fff;border-color:var(--ces);}}
.hdr-r{{display:flex;align-items:center;gap:var(--sp2);flex-shrink:0;}}
.hdr-speed{{position:relative;display:flex;align-items:center;}}
.hspd-trigger{{
  display:flex;align-items:center;gap:4px;
  padding:5px 10px;border-radius:var(--r-full);
  border:1.5px solid var(--s200);font-size:12px;font-weight:700;color:var(--s700);
  background:var(--s100);cursor:pointer;transition:all var(--ease);min-height:32px;white-space:nowrap;
}}
.hspd-trigger:hover{{border-color:var(--s400);}}
.hspd-trigger:active{{transform:scale(.95);}}
.hspd-trigger .arrow{{font-size:8px;color:var(--s400);margin-left:2px;transition:transform var(--ease);}}
.hspd-trigger.open .arrow{{transform:rotate(180deg);}}
.hspd-popover{{
  position:absolute;top:calc(100% + 6px);right:0;
  background:var(--white);border:1px solid var(--s200);border-radius:var(--r-lg);
  padding:var(--sp2);display:none;flex-direction:column;gap:3px;
  z-index:200;min-width:76px;box-shadow:var(--sh-lg);
}}
.hspd-popover.open{{display:flex;}}
.hspd{{
  padding:7px 12px;border-radius:var(--r-md);font-size:var(--ts);font-weight:700;color:var(--s500);
  background:transparent;cursor:pointer;transition:all var(--ease);text-align:center;min-height:36px;
}}
.hspd:hover{{background:var(--s100);color:var(--navy);}}
.hspd:active{{transform:scale(.95);}}
.hspd.on{{background:var(--red);color:#fff;}}
.hplay{{
  display:flex;align-items:center;gap:6px;
  padding:0 var(--sp4);height:36px;border-radius:var(--r-full);
  background:var(--red);color:#fff;font-size:12px;font-weight:700;
  cursor:pointer;transition:all var(--ease);box-shadow:0 2px 8px var(--red-glow);
  flex-shrink:0;white-space:nowrap;
}}
.hplay:hover{{background:var(--red-d);}}
.hplay:active{{transform:scale(.95);}}
.hplay.cen{{background:var(--cen);box-shadow:0 2px 8px rgba(37,99,235,.2);}}
.hplay.ces{{background:var(--ces);box-shadow:0 2px 8px rgba(22,163,74,.2);}}
.tbtn{{
  width:34px;height:34px;border-radius:50%;
  border:1.5px solid var(--s200);background:transparent;
  display:flex;align-items:center;justify-content:center;
  color:var(--s500);cursor:pointer;transition:all var(--ease);
}}
.tbtn:hover{{background:var(--s100);border-color:var(--s300);}}
.player{{background:var(--white);border-bottom:1px solid var(--s200);padding:var(--sp4) var(--sp5);flex-shrink:0;}}
.pi{{max-width:960px;margin:0 auto;display:flex;flex-direction:column;gap:var(--sp3);}}
.ltabs{{display:flex;gap:var(--sp2);flex-wrap:wrap;}}
.lt{{
  padding:5px 14px;border-radius:var(--r-full);
  border:1.5px solid var(--s200);font-size:var(--ts);font-weight:700;color:var(--s500);
  background:transparent;cursor:pointer;transition:all var(--ease);
}}
.lt:hover{{border-color:var(--s400);color:var(--s700);}}
.lt.afr{{background:var(--cfr);color:#fff;border-color:var(--cfr);}}
.lt.aen{{background:var(--cen);color:#fff;border-color:var(--cen);}}
.lt.aes{{background:var(--ces);color:#fff;border-color:var(--ces);}}
.ctrl{{display:flex;align-items:center;gap:var(--sp4);}}
.pb{{
  width:48px;height:48px;border-radius:50%;background:var(--red);
  display:flex;align-items:center;justify-content:center;color:#fff;
  flex-shrink:0;cursor:pointer;transition:all var(--ease);box-shadow:0 4px 14px var(--red-glow);
}}
.pb:hover{{background:var(--red-d);transform:scale(1.04);}}
.pb:active{{transform:scale(.92);}}
.pb.cen{{background:var(--cen);box-shadow:0 4px 14px rgba(37,99,235,.2);}}
.pb.ces{{background:var(--ces);box-shadow:0 4px 14px rgba(22,163,74,.2);}}
.pw{{flex:1;display:flex;flex-direction:column;gap:6px;}}
.pbar{{height:6px;background:var(--s200);border-radius:var(--r-full);cursor:pointer;position:relative;padding:8px 0;margin:-8px 0;}}
.pfill{{height:6px;border-radius:var(--r-full);background:var(--red);width:0%;transition:width .1s linear;position:relative;pointer-events:none;}}
.pfill.cen{{background:var(--cen);}}
.pfill.ces{{background:var(--ces);}}
.pthumb{{width:14px;height:14px;border-radius:50%;background:var(--red);position:absolute;right:-7px;top:50%;transform:translateY(-50%);box-shadow:0 1px 4px rgba(0,0,0,.2);}}
.trow{{display:flex;justify-content:space-between;font-size:var(--tx);color:var(--s400);font-variant-numeric:tabular-nums;}}
.ctrl2{{display:flex;align-items:center;gap:var(--sp3);flex-wrap:wrap;}}
.loop-btn{{
  display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:var(--r-full);
  border:1.5px solid var(--s200);font-size:var(--tx);font-weight:600;color:var(--s500);
  cursor:pointer;background:transparent;transition:all var(--ease);white-space:nowrap;min-height:32px;
}}
.loop-btn:hover{{border-color:var(--s400);color:var(--s700);}}
.loop-btn.on{{border-color:var(--red);color:var(--red);background:var(--red-glow);}}
.loop-dot{{width:7px;height:7px;border-radius:50%;background:var(--red);opacity:0;transition:opacity var(--ease);}}
.loop-btn.on .loop-dot{{opacity:1;animation:pulse 1.4s ease-in-out infinite;}}
.vol{{display:flex;align-items:center;gap:var(--sp2);margin-left:auto;}}
.vsl{{width:72px;-webkit-appearance:none;height:4px;border-radius:2px;background:var(--s200);cursor:pointer;}}
.vsl::-webkit-slider-thumb{{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:var(--red);}}
/* ── Sponsor Card (Liquid Glass) ─────────────────────────────── */
.sponsor-rail{{padding:var(--sp3) 0 0;border-top:1px solid var(--s200);margin-top:var(--sp1);display:flex;flex-direction:column;gap:var(--sp2);}}
.sponsor-card{{border-radius:16px;overflow:hidden;
  background:linear-gradient(135deg,rgba(251,191,36,.15) 0%,rgba(245,158,11,.10) 100%);
  backdrop-filter:blur(14px);
  -webkit-backdrop-filter:blur(14px);
  border:1px solid rgba(251,191,36,.35);
  box-shadow:0 4px 20px rgba(245,158,11,.10);
  padding:var(--sp3) var(--sp4);
}}
.sponsor-card-inner{{display:flex;align-items:center;gap:var(--sp3);}}
.sp-logo-wrap{{width:52px;height:52px;border-radius:12px;overflow:hidden;flex-shrink:0;
  background:#fff;border:1.5px solid rgba(245,158,11,.35);
  display:flex;align-items:center;justify-content:center;}}
.sp-logo-img{{width:100%;height:100%;object-fit:contain;display:block;}}
.sp-logo-fallback{{width:100%;height:100%;display:flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:900;color:#fff;
  background:linear-gradient(135deg,#F59E0B,#EF8C0A);}}
.sp-info{{flex:1;min-width:0;}}
.sp-badge{{font-size:9px;font-weight:700;color:#B45309;text-transform:uppercase;letter-spacing:.08em;margin:0 0 2px;}}
.sp-name{{font-size:13px;font-weight:800;color:var(--navy);margin:0 0 1px;line-height:1.2;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.sp-tagline{{font-size:11px;color:var(--s500);margin:0;line-height:1.3;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.sp-actions{{display:flex;align-items:center;gap:var(--sp2);flex-shrink:0;}}
.sp-cta{{display:inline-flex;align-items:center;padding:7px 14px;border-radius:50px;
  font-size:12px;font-weight:700;color:#fff;text-decoration:none;
  background:linear-gradient(135deg,#F59E0B,#EF8C0A);
  box-shadow:0 3px 12px rgba(245,158,11,.35);
  transition:transform .15s ease,box-shadow .15s ease;}}
.sp-cta:hover{{transform:scale(1.04);box-shadow:0 5px 18px rgba(245,158,11,.45);}}
.sp-vid-btn{{width:30px;height:30px;border-radius:50%;border:1.5px solid rgba(245,158,11,.5);
  background:rgba(245,158,11,.12);color:#B45309;
  display:flex;align-items:center;justify-content:center;cursor:pointer;
  transition:background .15s;}}
.sp-vid-btn:hover{{background:rgba(245,158,11,.22);}}
.sp-vid{{margin-top:var(--sp2);}}
/* Legacy sponsor-bar kept for compat */
.sponsor-bar{{display:none;}}
.section-strip{{background:var(--white);border-bottom:1px solid var(--s200);flex-shrink:0;}}
.section-hdr{{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px var(--sp5);cursor:pointer;user-select:none;
  max-width:960px;margin:0 auto;
}}
.section-title{{display:flex;align-items:center;gap:var(--sp2);font-size:12px;font-weight:700;color:var(--s500);text-transform:uppercase;letter-spacing:.06em;}}
.section-chevron{{
  width:26px;height:26px;border-radius:50%;border:1.5px solid var(--s200);background:transparent;
  display:flex;align-items:center;justify-content:center;
  color:var(--s400);cursor:pointer;transition:transform .25s ease;flex-shrink:0;
}}
.section-body{{
  overflow-y:auto;-webkit-overflow-scrolling:touch;
  max-height:42vh;
  transition:max-height .28s ease,opacity .2s ease,padding .28s ease;
  opacity:1;padding:0 var(--sp5) var(--sp3);
}}
.section-body.collapsed{{max-height:0;padding-top:0;padding-bottom:0;opacity:0;overflow:hidden;}}
.pod-mini-player{{
  display:none;align-items:center;gap:var(--sp3);
  padding:var(--sp3) var(--sp5);
  background:rgba(124,58,237,.05);border-bottom:1px solid rgba(124,58,237,.12);
}}
.pod-mini-player.active{{display:flex;}}
.pod-mini-title{{flex:1;font-size:var(--ts);font-weight:600;color:var(--navy);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
.pod-mini-time{{font-size:10px;color:var(--s400);white-space:nowrap;}}
.pod-progress-wrap{{flex:1;display:flex;flex-direction:column;gap:3px;min-width:0;}}
.pod-progress-bar{{width:100%;height:4px;border-radius:2px;background:var(--s200);cursor:pointer;accent-color:var(--pod);}}
.pod-play-btn{{
  width:34px;height:34px;border-radius:50%;background:var(--pod);
  display:flex;align-items:center;justify-content:center;
  color:#fff;cursor:pointer;flex-shrink:0;transition:all var(--ease);
}}
.pod-play-btn:hover{{background:#6d28d9;}}
.card-list{{display:flex;flex-direction:column;gap:var(--sp2);}}
.item-card{{
  display:flex;align-items:center;justify-content:space-between;
  padding:var(--sp3) var(--sp4);border-radius:var(--r-lg);
  border:1.5px solid var(--s200);background:var(--white);
  cursor:pointer;transition:all var(--ease);box-shadow:var(--sh-card);
}}
.item-card:hover{{border-color:var(--s300);box-shadow:var(--sh-md);}}
.item-card:active{{transform:scale(.98);}}
.item-card.active{{border-color:var(--red);background:rgba(220,38,38,.03);}}
.item-card.active-pod{{border-color:var(--pod);background:rgba(124,58,237,.03);}}
.item-card-info{{display:flex;flex-direction:column;gap:2px;}}
.item-card-label{{font-size:var(--ts);color:var(--navy);font-weight:500;}}
.item-card-sub{{font-size:10px;color:var(--s400);}}
.live-dot{{width:8px;height:8px;border-radius:50%;background:var(--red);display:inline-block;animation:blink 1.2s infinite;margin-right:6px;vertical-align:middle;}}
.item-badge{{font-size:10px;font-weight:700;padding:2px 8px;border-radius:var(--r-full);background:var(--red);color:#fff;text-transform:uppercase;}}
.play-circle{{
  width:32px;height:32px;border-radius:50%;background:var(--pod);
  display:flex;align-items:center;justify-content:center;
  color:#fff;flex-shrink:0;transition:all var(--ease);
}}
.play-circle:hover{{transform:scale(1.08);}}
.article-grid{{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
  gap:var(--sp2);overflow-y:auto;-webkit-overflow-scrolling:touch;
  max-height:38vh;
  transition:max-height .28s ease,opacity .2s ease,padding .28s ease;
  opacity:1;padding:0 var(--sp5) var(--sp3);
}}
.article-grid.collapsed{{max-height:0;padding-bottom:0;opacity:0;overflow:hidden;}}
.acard{{
  display:flex;align-items:flex-start;gap:var(--sp3);
  padding:var(--sp3) var(--sp4);border-radius:var(--r-lg);
  border:1.5px solid var(--s200);background:var(--white);
  cursor:pointer;transition:all var(--ease);box-shadow:var(--sh-card);min-height:52px;
}}
.acard:hover{{border-color:var(--s300);box-shadow:var(--sh-md);}}
.acard:active{{transform:scale(.98);}}
.acard.playing{{border-color:var(--cfr);background:rgba(220,38,38,.03);}}
.acard.aen.playing{{border-color:var(--cen);background:rgba(37,99,235,.03);}}
.acard.aes.playing{{border-color:var(--ces);background:rgba(22,163,74,.03);}}
.acard-num{{
  width:26px;height:26px;border-radius:50%;background:var(--red);color:#fff;
  font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0;
}}
.acard.aen .acard-num{{background:var(--cen);}}
.acard.aes .acard-num{{background:var(--ces);}}
.acard-text{{font-size:var(--ts);color:var(--navy);line-height:1.4;font-weight:500;}}
.acard-ts{{font-size:10px;color:var(--s400);margin-top:3px;}}
.scroll-wrap{{
  flex:1;min-height:0;overflow-y:auto;-webkit-overflow-scrolling:touch;
  overscroll-behavior-y:contain;touch-action:pan-y;background:var(--s100);
}}
.main{{max-width:960px;margin:0 auto;padding:var(--sp5) var(--sp5) var(--sp8);width:100%;}}
.transcript-card{{
  background:var(--white);border-radius:var(--r-xl);
  border:1px solid var(--s200);box-shadow:var(--sh-card);
  padding:var(--sp6) var(--sp6) var(--sp8);margin-bottom:var(--sp5);
}}
.ph{{display:flex;align-items:center;gap:var(--sp3);margin-bottom:var(--sp5);padding-bottom:var(--sp4);border-bottom:1px solid var(--s200);}}
.ph-flag{{font-size:1.3rem;line-height:1;}}
.ph-lang{{font-size:var(--tl);font-weight:700;letter-spacing:-.01em;}}
.ph-lang.fr{{color:var(--cfr);}}
.ph-lang.en{{color:var(--cen);}}
.ph-lang.es{{color:var(--ces);}}
.pdate{{margin-left:auto;font-size:var(--tx);color:var(--s400);font-weight:600;text-transform:uppercase;letter-spacing:.06em;}}
.lp{{display:none;animation:fi .2s ease;line-height:2.5;font-size:var(--tl);color:var(--s700);text-align:left;}}
.lp.on{{display:block;}}
.w{{display:inline;border-radius:4px;padding:0 2px;cursor:pointer;transition:background var(--ease),color var(--ease);}}
.w:hover{{background:var(--s200);}}
.w.hl{{background:var(--cfr);color:#fff;border-radius:4px;padding:0 3px;}}
.w.hl-en{{background:var(--cen);color:#fff;}}
.w.hl-es{{background:var(--ces);color:#fff;}}
.triple{{display:none;gap:var(--sp5);}}
.triple.on{{display:grid;grid-template-columns:1fr 1fr 1fr;}}
.tc{{flex:1;}}
.tch{{display:flex;align-items:center;gap:var(--sp2);margin-bottom:var(--sp4);padding-bottom:var(--sp3);border-bottom:1px solid var(--s200);}}
.tch-f{{font-size:1.1rem;}}
.tch-l{{font-size:var(--ts);font-weight:700;}}
.tch-l.fr{{color:var(--cfr);}}
.tch-l.en{{color:var(--cen);}}
.tch-l.es{{color:var(--ces);}}
.twp{{display:block;line-height:2.0;font-size:var(--ts);}}
.loop-banner{{
  display:none;align-items:center;justify-content:center;gap:var(--sp3);
  margin-bottom:var(--sp4);padding:var(--sp3) var(--sp5);
  border-radius:var(--r-lg);background:var(--red-glow);
  border:1px solid rgba(220,38,38,.22);color:var(--red);font-size:var(--ts);font-weight:700;
}}
.loop-banner.show{{display:flex;}}
.loop-spin{{animation:spin 2s linear infinite;display:inline-block;}}
.tip{{
  background:var(--white);border:1px solid var(--s200);border-radius:var(--r-xl);
  box-shadow:var(--sh-card);padding:var(--sp4) var(--sp5);
  display:flex;gap:var(--sp4);align-items:flex-start;position:relative;margin-bottom:var(--sp5);
}}
.tip-close{{position:absolute;top:var(--sp2);right:var(--sp3);background:none;cursor:pointer;color:var(--s400);font-size:14px;padding:4px 8px;border-radius:4px;line-height:1;opacity:.6;min-height:28px;}}
.tip-close:active{{opacity:1;background:var(--s100);}}
.tip-ico{{font-size:1.3rem;flex-shrink:0;}}
.tip-body{{font-size:var(--ts);color:var(--s500);line-height:1.6;}}
.tip-title{{font-weight:700;color:var(--navy);margin-bottom:4px;}}
.kbd-hint{{display:flex;gap:var(--sp4);justify-content:center;flex-wrap:wrap;margin-top:var(--sp6);}}
.kbd{{display:flex;align-items:center;gap:6px;font-size:var(--tx);color:var(--s400);}}
.key{{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:22px;padding:0 6px;border-radius:4px;background:var(--s100);border:1px solid var(--s200);font-size:11px;font-weight:700;color:var(--s500);}}
footer{{text-align:center;padding:var(--sp3) var(--sp5);font-size:var(--tx);color:var(--s400);border-top:1px solid var(--s200);background:var(--white);flex-shrink:0;}}
@keyframes fi{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
@keyframes pulse{{0%,100%{{opacity:.4}}50%{{opacity:1}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
@media(max-width:640px){{
  .hdr{{padding:0 var(--sp4);height:52px;gap:var(--sp2);}}
  .logo-sub{{display:none;}}
  .player{{padding:var(--sp3) var(--sp4);}}
  .ltabs{{display:none;}}
  .vol{{display:none;}}
  .main{{padding:var(--sp4) var(--sp4) var(--sp8);}}
  .transcript-card{{padding:var(--sp4) var(--sp4) var(--sp6);}}
  .kbd-hint{{display:none;}}
  .section-hdr{{padding:10px var(--sp4);}}
  .section-body{{padding:0 var(--sp4) var(--sp3);}}
  .article-grid{{padding:0 var(--sp4) var(--sp3);grid-template-columns:1fr;}}
  .lp{{font-size:var(--tb);line-height:2.3;}}
  .hlt{{padding:4px 9px;font-size:11px;}}
  .hplay span{{display:none;}}
  .hplay{{padding:0 var(--sp3);}}
}}
</style>
</head>
<body>

<audio id="afr" preload="auto"></audio>
<audio id="aen" preload="auto"></audio>
<audio id="aes" preload="auto"></audio>

<header class="hdr">
  <a class="logo" href="#">
    <div class="logo-mark">
      <svg width="20" height="20" viewBox="0 0 24 24"><path d="M12 1C5.9 1 1 5.9 1 12s4.9 11 11 11 11-4.9 11-11S18.1 1 12 1zm0 3c.6 0 1 .4 1 1v5.6l3.4 3.4c.4.4.4 1 0 1.4-.4.4-1 .4-1.4 0l-3.7-3.7c-.2-.2-.3-.4-.3-.7V5c0-.6.4-1 1-1z"/></svg>
    </div>
    <div>
      <div class="logo-name">Môle <span>FM</span></div>
      <div class="logo-sub">Lecteur Trilingue</div>
    </div>
  </a>
  <div class="hdr-langs">
    <button class="hlt afr" id="hlt-fr" data-lang="fr" onclick="switchLang('fr')">🇫🇷 FR</button>
    <button class="hlt" id="hlt-en" data-lang="en" onclick="switchLang('en')">🇬🇧 EN</button>
    <button class="hlt" id="hlt-es" data-lang="es" onclick="switchLang('es')">🇪🇸 ES</button>
  </div>
  <div class="hdr-r">
    <div class="hdr-speed" id="hdrSpeed">
      <div class="hspd-trigger" id="hspdTrigger" onclick="toggleSpeedPopover()">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <span id="hspdLabel">1×</span>
        <span class="arrow">▾</span>
      </div>
      <div class="hspd-popover" id="hspdPopover">{hspd_btns}</div>
    </div>
    <button class="hplay" id="hplaybtn" onclick="togglePlay()" aria-label="Lecture / Pause">
      <svg id="hpico" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
      <span id="hplayLabel">Écouter</span>
    </button>
    <button class="tbtn" id="themeBtn" aria-label="Thème">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
    </button>
  </div>
</header>

<div class="player">
  <div class="pi">
    <div class="ltabs">
      <button class="lt afr" data-lang="fr" onclick="switchLang('fr')">🇫🇷 Français</button>
      <button class="lt" data-lang="en" onclick="switchLang('en')">🇬🇧 English</button>
      <button class="lt" data-lang="es" onclick="switchLang('es')">🇪🇸 Español</button>
    </div>
    <div class="ctrl">
      <button class="pb" id="pbtn" onclick="togglePlay()" aria-label="Lecture / Pause">
        <svg id="pico" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
      </button>
      <div class="pw">
        <div class="pbar" id="pbar" onclick="seekClick(event)">
          <div class="pfill" id="pfill"><div class="pthumb"></div></div>
        </div>
        <div class="trow"><span id="tel">0:00</span><span id="tdur">0:00</span></div>
      </div>
      <div class="vol">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11,5 6,9 2,9 2,15 6,15 11,19"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
        <input type="range" class="vsl" id="vsl" min="0" max="1" step="0.05" value="1" oninput="setVol(this.value)">
      </div>
    </div>
    <div class="ctrl2">
      <button class="loop-btn" id="loopBtn" onclick="toggleLoop()">
        <span class="loop-dot"></span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
        Lecture continue
      </button>
    </div>
    {sponsor_badge}
  </div>
</div>

<div class="section-strip" id="podSection">
  <div class="pod-mini-player" id="podMiniPlayer">
    <div class="pod-progress-wrap">
      <div class="pod-mini-title" id="podMiniTitle">Podcast en cours</div>
      <progress class="pod-progress-bar" id="podProgress" value="0" max="100"></progress>
    </div>
    <span class="pod-mini-time" id="podMiniTime">0:00</span>
    <button class="pod-play-btn" onclick="togglePodPlay()" id="podPlayBtn">
      <svg id="podPlayIcon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
    </button>
  </div>
  <div class="section-hdr" onclick="togglePodPicker()">
    <div class="section-title">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/><path d="M6.3 6.3a8 8 0 0 0 0 11.4M17.7 6.3a8 8 0 0 1 0 11.4"/></svg>
      Podcasts Mole FM
    </div>
    <div class="section-chevron" id="podChevron">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
  </div>
  <div class="section-body collapsed" id="podList"><div class="card-list" id="podCardList"></div></div>
</div>

<div class="section-strip" id="broadcastPicker">
  <div class="section-hdr" onclick="toggleBcastPicker()">
    <div class="section-title">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      Bulletins des 24 dernières heures
    </div>
    <div class="section-chevron" id="bcastChevron">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
  </div>
  <div class="section-body collapsed" id="bcastList"><div class="card-list" id="bcastCardList"></div></div>
</div>

<div class="section-strip" id="articlePicker">
  <div class="section-hdr" onclick="togglePicker()">
    <div class="section-title">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 6h16M4 10h16M4 14h10"/></svg>
      <span id="apickLabel">Articles — Cliquez pour écouter</span>
    </div>
    <div class="section-chevron" id="apickChevron">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
  </div>
  <div class="article-grid collapsed" id="apickList"></div>
</div>

<div class="scroll-wrap" id="scrollWrap">
<main class="main">

  <div class="loop-banner" id="loopBanner">
    <span class="loop-spin">↻</span> Mode boucle actif — lecture en continu
  </div>

  <div id="sv">
    <div class="transcript-card">
      <div class="ph">
        <span class="ph-flag" id="phflag">🇫🇷</span>
        <span class="ph-lang fr" id="phlang">Français</span>
        <span class="pdate" id="bdate">{bdate_fr}</span>
      </div>
      {words_fr}
      {words_en}
      {words_es}
    </div>
  </div>

  <div class="triple" id="tv">
    <div class="tc"><div class="tch"><span class="tch-f">🇫🇷</span><span class="tch-l fr">Français</span></div>{tw_fr}</div>
    <div class="tc"><div class="tch"><span class="tch-f">🇬🇧</span><span class="tch-l en">English</span></div>{tw_en}</div>
    <div class="tc"><div class="tch"><span class="tch-f">🇪🇸</span><span class="tch-l es">Español</span></div>{tw_es}</div>
  </div>

  <div class="tip" id="tipBox">
    <div class="tip-ico">📖</div>
    <div class="tip-body">
      <div class="tip-title">Lecteur de littératie Mole FM</div>
      Suivez le mot en surbrillance pour apprendre à lire tout en restant informé(e). · Follow the highlighted word to build reading skills while staying informed. · Sigue la palabra resaltada para aprender a leer.
    </div>
    <button class="tip-close" onclick="document.getElementById('tipBox').style.display='none'" aria-label="Fermer">✕</button>
  </div>

  <div class="kbd-hint">
    <div class="kbd"><span class="key">Espace</span> Lecture/Pause</div>
    <div class="kbd"><span class="key">←</span><span class="key">→</span> ±5s</div>
    <div class="kbd"><span class="key">L</span> Boucle</div>
    <div class="kbd"><span class="key">+</span><span class="key">−</span> Vitesse</div>
  </div>
</main>
</div>

<footer>Mole FM 94.5 — Môle-Saint-Nicolas · Bulletin généré automatiquement · JUNO RadioOS</footer>
<script>
// ── AUDIO SOURCES (relative URLs — separate static .mp3 files) ──────────────
// PERMANENT FIX: Audio is NOT embedded as base64 in this script.
// Inline base64 audio in a large <script> block causes Mobile Safari to
// silently fail to execute the script, producing no sound.
// The .mp3 files are deployed alongside index.html and served directly.
const AUDIO_URLS={{fr:"audio_fr.mp3",en:"audio_en.mp3",es:"audio_es.mp3"}};
const PLAYLIST={playlist_json};   // ordered list of past newscasts for auto-advance
const BROADCASTS={broadcasts_json}; // full 24h archive manifest (newest first)
const PODCASTS={podcasts_json}; // FR podcast episodes (newest first)

// ── WORD TIMING ──────────────────────────────────────────────────────────────
const WT={wt_json};

// ── ARTICLE DATA ─────────────────────────────────────────────────────────────
const ARTICLES={articles_json};

// ── STATE ────────────────────────────────────────────────────────────────────
let lang='fr', view='single', raf=null;
let loopOn=false, currentSpeed=1.0;
const SPEEDS=[0.5,0.75,1,1.25,1.5,2,3];
let pickerOpen=false;
let userTouching=false;
document.addEventListener('touchstart',()=>userTouching=true,{{passive:true}});
document.addEventListener('touchend',()=>setTimeout(()=>userTouching=false,300),{{passive:true}});

const au=l=>document.getElementById('a'+l);

// ── INIT ──────────────────────────────────────────────────────────────────────
// Audio uses relative URL references to separate .mp3 files alongside index.html.
// PERMANENT FIX: eliminates Mobile Safari silent failure from large inline scripts.
function init(){{
  ['fr','en','es'].forEach(l=>{{
    au(l).src=AUDIO_URLS[l];
    au(l).playbackRate=currentSpeed;
  }});

  // Play button always enabled — mobile browsers (iOS/Safari) require a user gesture
  // before play() works. Disabling until canplaythrough is unreliable on iOS
  // because canplaythrough may never fire until AFTER the user has already tapped.
  const pb=document.getElementById('pbtn');
  const hpb=document.getElementById('hplaybtn');
  if(pb){{pb.disabled=false;pb.style.opacity='1';}}
  if(hpb){{hpb.disabled=false;hpb.style.opacity='1';}}

  // Audio events
  ['fr','en','es'].forEach(l=>{{
    au(l).addEventListener('timeupdate',()=>{{if(lang===l){{upProg(l);updateActiveCard();}}}});
    au(l).addEventListener('ended',()=>{{if(lang===l)onEnd();}});
    au(l).addEventListener('loadedmetadata',()=>{{if(lang===l)upDur(l);}});
  }});

  // Theme
  let th=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
  document.documentElement.setAttribute('data-theme',th);
  document.getElementById('themeBtn').addEventListener('click',()=>{{
    th=th==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',th);
  }});

  // Keyboard shortcuts
  document.addEventListener('keydown',handleKey);

  // Activate default language panel
  document.getElementById('wfr').classList.add('on');
  // Always single view by default (user instruction: only selected language shown)
  setView('single');
  // Keep all pickers collapsed on load
  buildPicker();
  buildBcastPicker();
  buildPodPicker();
}}

// ── PLAY / PAUSE ──────────────────────────────────────────────────────────────
function showPause(){{
  const ico='<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';
  document.getElementById('pico').innerHTML=ico;
  const h=document.getElementById('hpico');if(h)h.innerHTML=ico;
  const hl=document.getElementById('hplayLabel');if(hl)hl.textContent='Pause';
}}
function showPlay(){{
  const ico='<polygon points="5,3 19,12 5,21"/>';
  document.getElementById('pico').innerHTML=ico;
  const h=document.getElementById('hpico');if(h)h.innerHTML=ico;
  const hl=document.getElementById('hplayLabel');if(hl)hl.textContent='Écouter';
}}
function togglePlay(){{
  const a=au(lang);
  if(a.paused){{
    const p=a.play();
    if(p!==undefined){{p.then(()=>{{showPause();startLoop();}}).catch(()=>showPlay());}}
    else{{showPause();startLoop();}}
  }}else{{
    a.pause();showPlay();stopLoop();
  }}
}}

// ── END OF TRACK ──────────────────────────────────────────────────────────────
let _playlistIdx = PLAYLIST.length - 1;  // current index (starts at latest)

function onEnd(){{
  stopLoop();
  clrHL(lang,'w'+lang);
  if(loopOn){{
    // Auto-advance to next newscast in playlist, wrapping around
    if(PLAYLIST && PLAYLIST.length > 1){{
      _playlistIdx = (_playlistIdx - 1 + PLAYLIST.length) % PLAYLIST.length;
      const next = PLAYLIST[_playlistIdx];
      loadNextCast(next);
    }} else {{
      // Single newscast — just replay from start
      const a=au(lang);a.currentTime=0;
      setTimeout(()=>{{
        const p=a.play();
        if(p!==undefined){{p.then(()=>{{showPause();startLoop();}}).catch(()=>showPlay());}}
        else{{showPause();startLoop();}}
      }},400);
    }}
  }}else{{showPlay();}}
}}

function loadNextCast(entry){{
  // Update audio sources to point to next newscast
  if(!entry)return;
  ['fr','en','es'].forEach(l=>{{
    const a=au(l);
    a.pause();
    a.src=entry['audio_'+l] || AUDIO_URLS[l];
    a.load();
  }});
  // Brief pause then play
  setTimeout(()=>{{
    const a=au(lang);
    const p=a.play();
    if(p!==undefined){{p.then(()=>{{showPause();startLoop();}}).catch(()=>showPlay());}}
    else{{showPause();startLoop();}}
  }}, 800);
  // Update broadcast time display if present
  const bd=document.getElementById('bdate');
  if(bd && entry.broadcast_hour)bd.textContent=entry.broadcast_hour.toUpperCase();
}}

// ── LOOP ──────────────────────────────────────────────────────────────────────
function toggleLoop(){{
  loopOn=!loopOn;
  document.getElementById('loopBtn').classList.toggle('on',loopOn);
  document.getElementById('loopBanner').classList.toggle('show',loopOn);
}}

// ── SPEED ─────────────────────────────────────────────────────────────────────
function toggleSpeedPopover(){{
  const trigger=document.getElementById('hspdTrigger');
  const popover=document.getElementById('hspdPopover');
  const isOpen=popover.classList.contains('open');
  popover.classList.toggle('open',!isOpen);
  trigger.classList.toggle('open',!isOpen);
  if(!isOpen){{
    // Close when clicking outside
    const close=(e)=>{{
      if(!trigger.contains(e.target)&&!popover.contains(e.target)){{
        popover.classList.remove('open');
        trigger.classList.remove('open');
        document.removeEventListener('click',close,true);
      }}
    }};
    setTimeout(()=>document.addEventListener('click',close,true),10);
  }}
}}
function toggleSpVid(id){{
  const el=document.getElementById('spvid-'+id);
  if(!el)return;
  const isOpen=el.style.display!=='none';
  el.style.display=isOpen?'none':'block';
  const vid=el.querySelector('video');
  if(vid){{if(isOpen)vid.pause();else vid.play().catch(()=>{{}});}}
}}
function setSpeed(s){{
  currentSpeed=s;
  ['fr','en','es'].forEach(l=>au(l).playbackRate=s);
  // Also apply to podcast audio if it exists and is active
  if(typeof _podAudio!=='undefined'&&_podAudio)_podAudio.playbackRate=s;
  // Sync speed buttons
  document.querySelectorAll('.spd,.hspd').forEach(b=>{{
    b.classList.toggle('on',parseFloat(b.dataset.speed)===s);
  }});
  // Update trigger label and close popover
  const lbl=document.getElementById('hspdLabel');
  if(lbl)lbl.textContent=s+'×';
  const popover=document.getElementById('hspdPopover');
  const trigger=document.getElementById('hspdTrigger');
  if(popover)popover.classList.remove('open');
  if(trigger)trigger.classList.remove('open');
}}

// ── VOLUME ────────────────────────────────────────────────────────────────────
function setVol(v){{['fr','en','es'].forEach(l=>au(l).volume=+v);}}

// ── LANGUAGE SWITCH ───────────────────────────────────────────────────────────
function switchLang(l){{
  const wasPlaying=!au(lang).paused;
  au(lang).pause();clrHL(lang,'w'+lang);stopLoop();lang=l;
  // Always switch to single view when selecting a language
  setView('single');
  const cm={{fr:'',en:'cen',es:'ces'}};
  const cc=cm[l]||'';
  document.getElementById('pbtn').className='pb '+cc;
  document.getElementById('pfill').className='pfill '+cc;
  const hpb=document.getElementById('hplaybtn');
  if(hpb)hpb.className='hplay '+cc;
  // Update all lang button active states
  ['fr','en','es'].forEach(hl=>{{
    const flags=[document.getElementById('hlt-'+hl),...document.querySelectorAll(`.lt[data-lang="${{hl}}"]`)];
    flags.forEach(b=>{{if(b)b.className=b.className.replace(/ *(afr|aen|aes)/g,'')+(hl===l?' a'+hl:'');}});
  }});
  // Update single view panel
  const flags={{fr:'🇫🇷',en:'🇬🇧',es:'🇪🇸'}};
  const names={{fr:'Français',en:'English',es:'Español'}};
  const phf=document.getElementById('phflag');if(phf)phf.textContent=flags[l]||'';
  const phl=document.getElementById('phlang');
  if(phl){{phl.textContent=names[l]||l;phl.className='ph-lang '+l;}}
  document.querySelectorAll('.lp').forEach(p=>p.classList.remove('on'));
  const panel=document.getElementById('w'+l);if(panel)panel.classList.add('on');
  upDur(l);
  if(wasPlaying){{
    const p=au(l).play();
    if(p!==undefined){{p.then(()=>{{showPause();startLoop();}}).catch(()=>showPlay());}}
    else{{showPause();startLoop();}}
  }}
  buildPicker();
}}

// ── VIEW ──────────────────────────────────────────────────────────────────────
function setView(v){{
  view=v;
  const sv=document.getElementById('sv');if(sv)sv.style.display=v==='single'?'':'none';
  const tv=document.getElementById('tv');if(tv)tv.className='triple'+(v==='triple'?' on':'');
  const vsbtn=document.getElementById('vs');if(vsbtn)vsbtn.className='vb'+(v==='single'?' o':'');
  const vtbtn=document.getElementById('vt');if(vtbtn)vtbtn.className='vb'+(v==='triple'?' o':'');
}}

// ── PROGRESS ──────────────────────────────────────────────────────────────────
function upProg(l){{
  const a=au(l);if(!a.duration)return;
  document.getElementById('pfill').style.width=(a.currentTime/a.duration*100)+'%';
  document.getElementById('tel').textContent=fmt(a.currentTime);
}}
function upDur(l){{document.getElementById('tdur').textContent=fmt(au(l).duration||0);}}
function fmt(s){{const m=Math.floor(s/60);return m+':'+String(Math.floor(s%60)).padStart(2,'0');}}
function seekClick(e){{
  const r=document.getElementById('pbar').getBoundingClientRect();
  const ratio=Math.max(0,Math.min(1,(e.clientX-r.left)/r.width));
  au(lang).currentTime=ratio*(au(lang).duration||0);
}}

// ── WORD HIGHLIGHT ────────────────────────────────────────────────────────────
function startLoop(){{
  if(raf)cancelAnimationFrame(raf);
  (function tick(){{
    const ms=au(lang).currentTime*1000;// currentTime already reflects audio position at any playbackRate
    hlAt(lang,ms,'w'+lang);
    if(view==='triple')['fr','en','es'].forEach(ll=>hlAt(ll,ms,'tw'+ll));
    raf=requestAnimationFrame(tick);
  }})();
}}
function stopLoop(){{if(raf){{cancelAnimationFrame(raf);raf=null;}}}}
function hlAt(l,ms,cid){{
  const wts=WT[l];if(!wts)return;
  let idx=-1;
  for(let i=0;i<wts.length;i++){{if(ms>=wts[i].start_ms&&ms<wts[i].end_ms){{idx=i;break;}}}}
  const c=document.getElementById(cid);if(!c)return;
  const active=c.querySelector('.w.hl,.w.hl-en,.w.hl-es');
  if(active)active.className='w';
  if(idx>=0){{
    const w=c.querySelector(`[data-i="${{idx}}"]`);
    if(w){{
      const hlClass=l==='en'?'hl-en':l==='es'?'hl-es':'hl';
      w.className='w '+hlClass;
      // Auto-scroll: only when not touching (avoids hijacking user swipe on iOS)
      if(view==='single'&&lang===l&&!userTouching)w.scrollIntoView({{behavior:'smooth',block:'nearest',inline:'nearest'}});
    }}
  }}
}}
function clrHL(l,cid){{
  const c=document.getElementById(cid);if(!c)return;
  c.querySelectorAll('.w.hl,.w.hl-en,.w.hl-es').forEach(w=>w.className='w');
}}
function seekW(l,i){{
  const wts=WT[l];if(!wts||!wts[i])return;
  au(l).currentTime=wts[i].start_ms/1000;
}}

// ── PODCAST PLAYER ──────────────────────────────────────────────────────────────
let _podAudio = new Audio();
let _podPickerOpen = false;
let _activePodFilename = null;

function buildPodPicker(){{
  const list = document.getElementById('podCardList'); if(!list) return;
  if(!PODCASTS||!PODCASTS.length){{
    list.innerHTML='<div style="padding:var(--sp3);font-size:var(--ts);color:var(--s400);">Aucun podcast disponible pour le moment.</div>';
    return;
  }}
  list.innerHTML = PODCASTS.map((p,i) => {{
    const isActive = _activePodFilename === p.filename;
    return `<div class="item-card ${{isActive?'active-pod':''}}" id="pd-${{i}}" onclick="loadPodcast('${{p.audio_url}}','${{p.filename}}','${{p.label}}','${{p.est_min}}')">
      <div class="item-card-info">
        <div class="item-card-label">${{isActive?'<span class="live-dot"></span>':''}}<strong>${{p.label}}</strong></div>
        <div class="item-card-sub">~${{p.est_min}} min · Français</div>
      </div>
      <div class="play-circle" style="background:${{isActive?'#6d28d9':'#7c3aed'}};">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      </div>
    </div>`;
  }}).join('');
}}

function loadPodcast(audioUrl, filename, label, estMin){{
  _activePodFilename = filename;
  _podAudio.pause();
  _podAudio.src = audioUrl;
  _podAudio.load();
  // Show mini player
  document.getElementById('podMiniTitle').textContent = label;
  document.getElementById('podMiniPlayer').classList.add('active');
  buildPodPicker();
  // Wire up progress
  _podAudio.ontimeupdate = function(){{
    if(!_podAudio.duration) return;
    const pct = (_podAudio.currentTime / _podAudio.duration) * 100;
    document.getElementById('podProgress').value = pct;
    const m = Math.floor(_podAudio.currentTime/60);
    const s = Math.floor(_podAudio.currentTime%60).toString().padStart(2,'0');
    document.getElementById('podMiniTime').textContent = `${{m}}:${{s}}`;
  }};
  _podAudio.onended = function(){{
    document.getElementById('podPlayIcon').innerHTML='<polygon points="5 3 19 12 5 21 5 3"/>';
  }};
  // Auto-play
  setTimeout(()=>{{
    const p=_podAudio.play();
    if(p!==undefined)p.then(()=>{{document.getElementById('podPlayIcon').innerHTML='<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';}}).catch(()=>{{}});
  }}, 300);
  // Collapse picker
  _podPickerOpen = false;
  document.getElementById('podList').classList.add('collapsed');
  const ch = document.getElementById('podChevron');
  if(ch) ch.style.transform = 'rotate(-90deg)';
}}

function togglePodPlay(){{
  if(_podAudio.paused){{
    _podAudio.play().then(()=>{{document.getElementById('podPlayIcon').innerHTML='<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';}});
  }} else {{
    _podAudio.pause();
    document.getElementById('podPlayIcon').innerHTML='<polygon points="5 3 19 12 5 21 5 3"/>';
  }}
}}

function togglePodPicker(){{
  _podPickerOpen = !_podPickerOpen;
  document.getElementById('podList').classList.toggle('collapsed', !_podPickerOpen);
  const ch = document.getElementById('podChevron');
  if(ch) ch.style.transform = _podPickerOpen ? 'rotate(180deg)' : '';
}}

// ── BROADCASTS ARCHIVE PICKER ─────────────────────────────────────────────────────
let _bcastPickerOpen=false;
let _activeBcastFilename=null; // filename of currently loaded broadcast (null=current)

function buildBcastPicker(){{
  const list=document.getElementById('bcastCardList');if(!list)return;
  if(!BROADCASTS||!BROADCASTS.length){{
    list.innerHTML='<div style="padding:var(--sp3);font-size:var(--ts);color:var(--s400);">Aucun bulletin disponible</div>';
    return;
  }}
  list.innerHTML=BROADCASTS.map((b,i)=>{{
    const isCurrent=b.is_current;
    const isActive=_activeBcastFilename===b.filename||(isCurrent&&!_activeBcastFilename);
    return`<div class="item-card ${{isActive?'active':''}}" id="bc-${{i}}" onclick="loadBroadcastFromPicker('${{b.audio_url}}','${{b.filename}}','${{b.label}}')">
      <div class="item-card-info">
        <div class="item-card-label">${{isActive?'<span class="live-dot"></span>':''}}<strong>${{b.label}}</strong></div>
        ${{isCurrent?'<div class="item-card-sub">🔴 En direct</div>':''}}
      </div>
      ${{isCurrent?'<span class="item-badge">Live</span>':''}}
    </div>`;
  }}).join('');
}}

function loadBroadcastFromPicker(audioUrl, filename, label){{
  // Update active state
  _activeBcastFilename=filename;
  // Update FR audio source to the selected broadcast
  const a=au('fr');
  a.pause();
  a.src=audioUrl;
  a.load();
  // EN/ES stay as current broadcast (archive is FR only for past hours)
  // Update broadcast time label
  const bd=document.getElementById('bdate');
  if(bd)bd.textContent=label.toUpperCase();
  // Rebuild picker to update active highlight
  buildBcastPicker();
  // Close the picker and auto-play
  setTimeout(()=>{{
    const p=a.play();
    if(p!==undefined){{p.then(()=>{{showPause();startLoop();}}).catch(()=>showPlay());}}
    else{{showPause();startLoop();}}
  }},400);
  // Collapse picker
  _bcastPickerOpen=false;
  document.getElementById('bcastList').classList.add('collapsed');
  const ch=document.getElementById('bcastChevron');
  if(ch)ch.style.transform='rotate(-90deg)';
}}

function toggleBcastPicker(){{
  _bcastPickerOpen=!_bcastPickerOpen;
  document.getElementById('bcastList').classList.toggle('collapsed',!_bcastPickerOpen);
  const ch=document.getElementById('bcastChevron');
  if(ch)ch.style.transform=_bcastPickerOpen?'rotate(180deg)':'';
}}

// ── ARTICLE PICKER ────────────────────────────────────────────────────────────
function buildPicker(){{
  const list=document.getElementById('apickList');if(!list)return;
  const items=(ARTICLES[lang]||[]);
  const cc={{fr:'',en:'aen',es:'aes'}};
  const labels={{fr:'Articles — Cliquez pour écouter',en:'Articles — Tap to listen',es:'Artículos — Pulsa para escuchar'}};
  const el=document.getElementById('apickLabel');
  if(el)el.textContent=labels[lang]||labels.fr;
  list.innerHTML=items.length?items.map(a=>{{
    const mins=Math.floor(a.start_ms/60000);
    const secs=String(Math.floor((a.start_ms%60000)/1000)).padStart(2,'0');
    return`<div class="acard ${{cc[lang]||''}}" id="ac-${{a.num}}" onclick="jumpArticle(${{a.num}})">
      <div class="acard-num">${{a.num}}</div>
      <div><div class="acard-text">${{a.title}}</div><div class="acard-ts">${{mins}}m${{secs}}s</div></div>
    </div>`;
  }}).join(''):'<div style="padding:var(--sp3);font-size:var(--ts);color:var(--s400);">Aucun article disponible</div>';
}}
function jumpArticle(num){{
  const items=(ARTICLES[lang]||[]);
  const art=items.find(a=>a.num===num);if(!art)return;
  au(lang).currentTime=art.start_ms/1000;
  if(au(lang).paused){{
    const p=au(lang).play();
    if(p!==undefined){{p.then(()=>{{showPause();startLoop();}}).catch(()=>showPlay());}}
    else{{showPause();startLoop();}}
  }}
  document.querySelectorAll('.acard').forEach(c=>c.classList.remove('playing'));
  const card=document.getElementById('ac-'+num);if(card)card.classList.add('playing');
}}
function updateActiveCard(){{
  const ms=au(lang).currentTime*1000;
  const items=(ARTICLES[lang]||[]);
  let active=null;
  for(let i=items.length-1;i>=0;i--){{if(ms>=items[i].start_ms){{active=items[i].num;break;}}}}
  document.querySelectorAll('.acard').forEach(c=>{{
    c.classList.toggle('playing',parseInt(c.id.replace('ac-',''))===active);
  }});
}}
function togglePicker(){{
  pickerOpen=!pickerOpen;
  document.getElementById('apickList').classList.toggle('collapsed',!pickerOpen);
  const ch=document.getElementById('apickChevron');
  if(ch)ch.style.transform=pickerOpen?'rotate(180deg)':'';
}}

// ── KEYBOARD SHORTCUTS ────────────────────────────────────────────────────────
function handleKey(e){{
  if(e.target.tagName==='INPUT')return;
  const a=au(lang);
  switch(e.code){{
    case'Space':e.preventDefault();togglePlay();break;
    case'ArrowRight':e.preventDefault();a.currentTime=Math.min(a.duration||0,a.currentTime+5);break;
    case'ArrowLeft':e.preventDefault();a.currentTime=Math.max(0,a.currentTime-5);break;
    case'KeyL':toggleLoop();break;
    case'Equal':case'NumpadAdd':case'BracketRight':e.preventDefault();{{const n=SPEEDS.find(s=>s>currentSpeed);if(n)setSpeed(n);}}break;
    case'Minus':case'NumpadSubtract':case'BracketLeft':e.preventDefault();{{const n=[...SPEEDS].reverse().find(s=>s<currentSpeed);if(n)setSpeed(n);}}break;
  }}
}}

window.addEventListener('DOMContentLoaded',init);
</script>
</body>
</html>"""



if __name__ == "__main__":
    import sys as _sys
    print("[build_reader] Standalone rebuild starting...")
    # Locate latest script for word timings
    _scripts_dir = os.path.dirname(os.path.abspath(__file__))
    _scripts_out = os.path.join(_scripts_dir, "..", "audio", "scripts")
    _script_file = None
    _audio_file = None
    # Find most recent .json script and matching audio
    if os.path.isdir(_scripts_out):
        _jsons = sorted([f for f in os.listdir(_scripts_out) if f.endswith('.json')], reverse=True)
        if _jsons:
            _script_file = os.path.join(_scripts_out, _jsons[0])
    _audio_dir = os.path.join(_scripts_dir, "..", "reader", "webapp")
    _audio_fr = os.path.join(_audio_dir, "audio_fr.mp3")
    if os.path.exists(_audio_fr):
        _audio_file = _audio_fr
    if _script_file and _audio_file:
        print(f"  Script: {_script_file}")
        print(f"  Audio:  {_audio_file}")
        result = build(_script_file, _audio_file)
        if result:
            print(f"[build_reader] Done → {result}")
        else:
            print("[build_reader] Build returned None — check script/audio files")
    else:
        print(f"[build_reader] Missing script ({_script_file}) or audio ({_audio_file})")
        print("  Run from pipeline: python3 run_pipeline.py")
        _sys.exit(1)
