#!/usr/bin/env python3
"""
Mole FM — YouTube Video Generator
===================================
Zero-cost pipeline that converts each hourly newscast MP3 into a
broadcast-quality YouTube video ready for admin approval.

Stack (all free):
  - FFmpeg        — audio/video assembly + text overlays (drawtext filter)
  - Pillow        — background frame & graphic rendering
  - numpy         — pixel manipulation for smooth gradients
  - Python stdlib — no paid APIs used

Output: MP4 (1080x1920 portrait for YouTube Shorts / Reels) or
        1920x1080 landscape for standard YouTube — configurable.

Usage:
  python3 video_generator.py                  # latest newscast
  python3 video_generator.py --all            # all unapproved newscasts
  python3 video_generator.py --file <mp3>     # specific file

Admin approval queue:
  /home/user/workspace/molefm/videos/queue/   ← generated, awaiting review
  /home/user/workspace/molefm/videos/approved/ ← admin-moved here = OK to upload
  /home/user/workspace/molefm/videos/rejected/ ← skip

Approval flow:
  1. Cron generates video → drops to queue/
  2. Cron sends Telegram notification with preview info
  3. Admin replies /approve <filename> or /reject <filename> to JUNO bot
  4. Upload cron moves approved → YouTube via yt-dlp upload (or manual)
"""

import os, json, glob, subprocess, textwrap, datetime, sys, re, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.join(os.path.dirname(__file__), "..")
AUDIO_DIR   = os.path.join(BASE_DIR, "audio")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
VIDEO_DIR   = os.path.join(BASE_DIR, "videos")
QUEUE_DIR   = os.path.join(VIDEO_DIR, "queue")
APPROVED_DIR= os.path.join(VIDEO_DIR, "approved")
REJECTED_DIR= os.path.join(VIDEO_DIR, "rejected")
FONTS_DIR   = os.path.join(BASE_DIR, "assets", "fonts")
LOGO_PATH   = os.path.join(BASE_DIR, "reader", "webapp", "sponsors", "mathurin_beach.jpg")
APPROVAL_LOG= os.path.join(VIDEO_DIR, "approval_log.json")

for d in [QUEUE_DIR, APPROVED_DIR, REJECTED_DIR, FONTS_DIR]:
    os.makedirs(d, exist_ok=True)

# ── Video config ──────────────────────────────────────────────────────────────
# Shorts (9:16) = maximum reach on mobile; change to (1920,1080) for landscape
VIDEO_W, VIDEO_H = 1080, 1920
FORMAT = "shorts"   # "shorts" | "landscape"

# Brand colours
COLOR_BG_TOP    = (15,  23,  42)   # deep navy
COLOR_BG_MID    = (30,  58,  138)  # indigo
COLOR_BG_BOT    = (7,   15,  35)   # near black
COLOR_ACCENT    = (41,  200, 239)  # Mole FM cyan #29C8EF
COLOR_ACCENT2   = (79,  110, 247)  # Mole FM indigo #4F6EF7
COLOR_WHITE     = (255, 255, 255)
COLOR_WHITE_70  = (255, 255, 255, 178)
COLOR_GOLD      = (251, 191, 36)

# ── Font helpers ──────────────────────────────────────────────────────────────
def _font(size, bold=False):
    """Return a PIL font. Falls back to default if custom font unavailable."""
    candidates = [
        os.path.join(FONTS_DIR, "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

# ── Background frame renderer ─────────────────────────────────────────────────
def render_background_frame(slide_index: int, total_slides: int) -> Image.Image:
    """
    Renders a full 1080×1920 (or landscape) background frame.
    Uses numpy gradient + Pillow drawing — zero external calls.
    """
    W, H = VIDEO_W, VIDEO_H
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # Vertical gradient
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    for y in range(H):
        t = y / H
        if t < 0.5:
            # top → mid
            tt = t / 0.5
            r = int(COLOR_BG_TOP[0] + (COLOR_BG_MID[0] - COLOR_BG_TOP[0]) * tt)
            g = int(COLOR_BG_TOP[1] + (COLOR_BG_MID[1] - COLOR_BG_TOP[1]) * tt)
            b = int(COLOR_BG_TOP[2] + (COLOR_BG_MID[2] - COLOR_BG_TOP[2]) * tt)
        else:
            tt = (t - 0.5) / 0.5
            r = int(COLOR_BG_MID[0] + (COLOR_BG_BOT[0] - COLOR_BG_MID[0]) * tt)
            g = int(COLOR_BG_MID[1] + (COLOR_BG_BOT[1] - COLOR_BG_MID[1]) * tt)
            b = int(COLOR_BG_MID[2] + (COLOR_BG_BOT[2] - COLOR_BG_MID[2]) * tt)
        arr[y, :] = [r, g, b]
    img = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(img, "RGBA")

    # Radial glow top-left
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for radius in range(400, 0, -20):
        alpha = int(30 * (1 - radius / 400))
        gd.ellipse([-radius//2, -radius//2, radius*1.2, radius*1.2],
                   fill=(*COLOR_ACCENT, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Subtle grid lines (editorial/broadcast feel)
    for x in range(0, W, 120):
        draw.line([(x, 0), (x, H)], fill=(255, 255, 255, 8), width=1)
    for y in range(0, H, 120):
        draw.line([(0, y), (W, y)], fill=(255, 255, 255, 8), width=1)

    # Progress bar at very bottom (slide N of total)
    bar_h = 6
    bar_w = int(W * (slide_index + 1) / max(total_slides, 1))
    draw.rectangle([0, H - bar_h, W, H], fill=COLOR_BG_BOT)
    draw.rectangle([0, H - bar_h, bar_w, H], fill=COLOR_ACCENT)

    return img


def render_slide(
    title: str,
    source: str,
    verification: str,
    slide_index: int,
    total_slides: int,
    broadcast_hour: str,
    story_number: int,
    confidence: int = 75,
) -> Image.Image:
    """
    Renders a complete news slide as a PIL Image.
    Layout (top to bottom):
      - Mole FM logo text + radio icon
      - Haiti live bar (date/time)
      - Separator accent line
      - Story number badge
      - Headline (wrapped, large bold)
      - Source attribution + verification badge
      - Footer: molefm.com
    """
    W, H = VIDEO_W, VIDEO_H
    img = render_background_frame(slide_index, total_slides)
    draw = ImageDraw.Draw(img)

    # ── Logo zone (top 140px) ──────────────────────────────────────────────
    logo_font    = _font(52, bold=True)
    sub_font     = _font(26)
    badge_font   = _font(22, bold=True)
    headline_font= _font(68, bold=True)
    source_font  = _font(32)
    footer_font  = _font(28)
    story_num_f  = _font(38, bold=True)
    time_font    = _font(30)

    pad = 60  # side padding

    # Radio icon (drawn as unicode symbol since we don't have icon files)
    draw.text((pad, 55), "📻", font=_font(48), fill=COLOR_WHITE)
    draw.text((pad + 70, 60), "MOLE FM", font=logo_font, fill=COLOR_WHITE)
    draw.text((pad + 72, 118), "94.5 · Radio Communautaire Haïtienne", font=sub_font, fill=(*COLOR_ACCENT, 220))

    # ── Accent separator ──────────────────────────────────────────────────
    sep_y = 168
    draw.rectangle([pad, sep_y, W - pad, sep_y + 3], fill=COLOR_ACCENT)
    # Second thin line
    draw.rectangle([pad, sep_y + 8, W // 3, sep_y + 10], fill=COLOR_ACCENT2)

    # ── Date/time bar ─────────────────────────────────────────────────────
    now_ht = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    date_str = now_ht.strftime("%A %d %B %Y · %H:%M").capitalize()
    draw.text((pad, sep_y + 20), date_str, font=time_font, fill=(*COLOR_WHITE, 160))

    # ── BULLETIN D'INFORMATION header ─────────────────────────────────────
    bul_y = sep_y + 70
    draw.text((pad, bul_y), "BULLETIN D'INFORMATION", font=badge_font,
              fill=(*COLOR_ACCENT, 230))
    draw.text((pad, bul_y + 36), broadcast_hour, font=badge_font, fill=(*COLOR_GOLD, 200))

    # ── Story number bubble ───────────────────────────────────────────────
    num_y = bul_y + 100
    bubble_r = 44
    bubble_x = pad + bubble_r
    bubble_y = num_y + bubble_r
    draw.ellipse(
        [bubble_x - bubble_r, bubble_y - bubble_r, bubble_x + bubble_r, bubble_y + bubble_r],
        fill=COLOR_ACCENT2
    )
    num_str = str(story_number)
    nb = draw.textbbox((0, 0), num_str, font=story_num_f)
    draw.text(
        (bubble_x - (nb[2]-nb[0])//2 - 1, bubble_y - (nb[3]-nb[1])//2 - 2),
        num_str, font=story_num_f, fill=COLOR_WHITE
    )

    # ── Headline (the big text) ────────────────────────────────────────────
    headline_y = num_y + bubble_r * 2 + 30
    # Wrap headline to fit width
    max_chars = 28  # for 68px font at 1080px width
    wrapped = textwrap.wrap(title, width=max_chars)[:5]  # max 5 lines

    line_h = 82
    for i, line in enumerate(wrapped):
        # Shadow
        draw.text((pad + 2, headline_y + i * line_h + 2), line,
                  font=headline_font, fill=(0, 0, 0, 80))
        # Text
        draw.text((pad, headline_y + i * line_h), line,
                  font=headline_font, fill=COLOR_WHITE)

    text_block_h = len(wrapped) * line_h

    # ── Source attribution ─────────────────────────────────────────────────
    src_y = headline_y + text_block_h + 40

    # Pill background for source
    src_text = f"  {source}  "
    src_bb = draw.textbbox((0, 0), src_text, font=source_font)
    src_w = src_bb[2] - src_bb[0] + 20
    src_h = src_bb[3] - src_bb[1] + 14
    draw.rounded_rectangle(
        [pad - 8, src_y - 4, pad + src_w, src_y + src_h],
        radius=12, fill=(*COLOR_ACCENT2, 180)
    )
    draw.text((pad + 2, src_y), src_text, font=source_font, fill=COLOR_WHITE)

    # Verification badge
    v_x = pad + src_w + 20
    if "CONFIRMED" in (verification or ""):
        v_label = "✓ VÉRIFIÉ"
        v_color = (16, 185, 129)   # green
    else:
        v_label = "⏳ EN COURS"
        v_color = (245, 158, 11)   # amber

    vb = draw.textbbox((0, 0), v_label, font=badge_font)
    vw = vb[2] - vb[0] + 20
    vh = vb[3] - vb[1] + 12
    draw.rounded_rectangle(
        [v_x - 8, src_y - 2, v_x + vw, src_y + vh],
        radius=10, fill=(*v_color, 180)
    )
    draw.text((v_x + 2, src_y + 1), v_label, font=badge_font, fill=COLOR_WHITE)

    # Confidence bar
    conf_y = src_y + src_h + 22
    bar_total_w = min(confidence * 4, W - pad * 2 - 40)  # scale 0-100 to 0-~960px
    draw.rounded_rectangle(
        [pad, conf_y, W - pad - 40, conf_y + 10],
        radius=5, fill=(255, 255, 255, 30)
    )
    conf_color = (16, 185, 129) if confidence >= 80 else (245, 158, 11) if confidence >= 65 else (156, 163, 175)
    draw.rounded_rectangle(
        [pad, conf_y, pad + bar_total_w, conf_y + 10],
        radius=5, fill=(*conf_color, 220)
    )
    draw.text((W - pad - 35, conf_y - 4), f"{confidence}%", font=_font(24), fill=(*COLOR_WHITE, 160))

    # ── Footer ────────────────────────────────────────────────────────────
    footer_y = H - 120
    draw.line([(pad, footer_y - 20), (W - pad, footer_y - 20)], fill=(*COLOR_ACCENT, 60), width=1)
    draw.text((pad, footer_y), "🌐 molefm.com", font=footer_font, fill=(*COLOR_WHITE, 180))
    draw.text((W - pad - 160, footer_y), "#MoleFM94", font=footer_font, fill=(*COLOR_ACCENT, 200))

    # ── Slide counter ─────────────────────────────────────────────────────
    counter_text = f"{slide_index + 1}/{total_slides}"
    cb = draw.textbbox((0, 0), counter_text, font=badge_font)
    draw.text(
        (W - pad - (cb[2]-cb[0]) - 4, 70),
        counter_text, font=badge_font, fill=(*COLOR_WHITE, 120)
    )

    return img


def render_cover_slide(broadcast_hour: str, story_count: int) -> Image.Image:
    """
    Opening title card — plays for first 3 seconds.
    """
    W, H = VIDEO_W, VIDEO_H
    img = render_background_frame(0, 1)
    draw = ImageDraw.Draw(img)

    pad = 60

    # Central glow circle
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = W // 2, H // 2 - 80
    for r in range(320, 0, -16):
        alpha = int(25 * (1 - r / 320))
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*COLOR_ACCENT2, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Big radio icon
    icon_font = _font(160, bold=True)
    icon_bb = draw.textbbox((0, 0), "📻", font=icon_font)
    draw.text(
        ((W - (icon_bb[2]-icon_bb[0])) // 2, H // 2 - 340),
        "📻", font=icon_font, fill=COLOR_WHITE
    )

    # MOLE FM title
    title_font = _font(110, bold=True)
    tb = draw.textbbox((0, 0), "MOLE FM", font=title_font)
    # Shadow
    draw.text(
        ((W - (tb[2]-tb[0])) // 2 + 3, H // 2 - 100 + 3),
        "MOLE FM", font=title_font, fill=(0, 0, 0, 100)
    )
    draw.text(
        ((W - (tb[2]-tb[0])) // 2, H // 2 - 100),
        "MOLE FM", font=title_font, fill=COLOR_WHITE
    )

    # 94.5
    sub_font = _font(52, bold=True)
    sub_text = "94.5 · Radio Haïtienne"
    sb = draw.textbbox((0, 0), sub_text, font=sub_font)
    draw.text(
        ((W - (sb[2]-sb[0])) // 2, H // 2 + 40),
        sub_text, font=sub_font, fill=(*COLOR_ACCENT, 230)
    )

    # Bulletin label
    bul_font = _font(40)
    bul_text = f"BULLETIN · {broadcast_hour.upper()}"
    bb2 = draw.textbbox((0, 0), bul_text, font=bul_font)
    draw.text(
        ((W - (bb2[2]-bb2[0])) // 2, H // 2 + 130),
        bul_text, font=bul_font, fill=(*COLOR_GOLD, 220)
    )

    # Story count pill
    count_font = _font(34, bold=True)
    count_text = f"  {story_count} informations vérifiées  "
    ctb = draw.textbbox((0, 0), count_text, font=count_font)
    cw = ctb[2] - ctb[0] + 20
    ch = ctb[3] - ctb[1] + 16
    cx2 = (W - cw) // 2
    cy2 = H // 2 + 215
    draw.rounded_rectangle([cx2 - 10, cy2 - 4, cx2 + cw + 10, cy2 + ch], radius=24,
                            fill=(*COLOR_ACCENT, 200))
    draw.text((cx2 + 2, cy2), count_text, font=count_font, fill=COLOR_WHITE)

    # Date
    now_ht = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    date_str = now_ht.strftime("%A %d %B %Y").capitalize()
    df = _font(32)
    db = draw.textbbox((0, 0), date_str, font=df)
    draw.text(((W - (db[2]-db[0])) // 2, H // 2 + 310),
              date_str, font=df, fill=(*COLOR_WHITE, 140))

    # Footer
    footer_font = _font(28)
    draw.text((pad, H - 100), "🌐 molefm.com", font=footer_font, fill=(*COLOR_WHITE, 160))
    draw.text((W - pad - 170, H - 100), "#MoleFM94", font=footer_font, fill=(*COLOR_ACCENT, 180))

    return img


# ── Parse stories from newscast JSON ─────────────────────────────────────────
def extract_stories_from_json(json_path: str) -> tuple[list[dict], str]:
    """Returns (stories_list, broadcast_hour_label)."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    broadcast_hour = data.get("broadcast_hour", "")
    stories = []

    # Pull from verification log for best story metadata
    vlog_path = os.path.join(BASE_DIR, "research", "verification_log.json")
    try:
        with open(vlog_path, "r", encoding="utf-8") as f:
            vlog = json.load(f)
        if vlog:
            latest = vlog[-1]
            for s in latest.get("stories", []):
                stories.append({
                    "title":        s.get("title", "")[:120],
                    "source":       s.get("source", "Mole FM"),
                    "verification": s.get("verification", "SINGLE-SOURCE"),
                    "confidence":   s.get("confidence", 65),
                    "link":         s.get("link", ""),
                    "all_sources":  s.get("all_sources", []),
                })
    except Exception:
        pass

    # Fallback: parse title numbers from NEWS_MAIN segment text
    if not stories:
        for seg in data.get("segments", []):
            if seg.get("segment") in ("NEWS_MAIN", "NEWS"):
                text = seg.get("text", "")
                for m in re.finditer(r"Titre \d+ : (.+?)(?=Titre \d+|$)", text, re.DOTALL):
                    title = m.group(1).strip()[:120]
                    src_m = re.search(r"Selon ([^—]+)\s*—", title)
                    src = src_m.group(1).strip() if src_m else "Mole FM"
                    clean = re.sub(r"Selon [^—]+\s*—\s*", "", title).strip()
                    stories.append({
                        "title": clean or title,
                        "source": src,
                        "verification": "CONFIRMED" if " et " in src else "SINGLE-SOURCE",
                        "confidence": 80 if " et " in src else 65,
                        "link": "",
                    })

    return stories, broadcast_hour


# ── Core video assembly ───────────────────────────────────────────────────────
def generate_video(mp3_path: str, json_path: str) -> str | None:
    """
    Main function: renders all slides as PNG frames, then uses FFmpeg to:
      1. Tile the static PNG over the audio duration per slide
      2. Concatenate all slide clips
      3. Mux with original MP3 audio
    Returns output path or None on failure.
    """
    ts = os.path.basename(mp3_path).replace("newscast_", "").replace(".mp3", "")
    out_path = os.path.join(QUEUE_DIR, f"molefm_news_{ts}.mp4")

    if os.path.exists(out_path):
        print(f"  [SKIP] Already generated: {out_path}")
        return out_path

    print(f"\n[VIDEO] Generating: {os.path.basename(mp3_path)}")

    # Step 1 — Parse stories
    stories, broadcast_hour = extract_stories_from_json(json_path)
    if not stories:
        print("  [WARN] No stories found — skipping")
        return None

    print(f"  Stories: {len(stories)} | Broadcast: {broadcast_hour}")

    # Step 2 — Get audio duration
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", mp3_path],
        capture_output=True, text=True
    )
    duration_secs = 0.0
    try:
        probe = json.loads(result.stdout)
        duration_secs = float(probe["format"]["duration"])
    except Exception:
        duration_secs = 300.0  # 5min fallback
    print(f"  Audio duration: {duration_secs:.1f}s")

    # Step 3 — Calculate time per slide
    cover_duration = 3.0   # opening card
    outro_duration = 4.0   # sign-off card
    news_duration  = duration_secs - cover_duration - outro_duration
    per_story_secs = max(news_duration / len(stories), 8.0)

    # Step 4 — Render PNG frames
    tmp_dir = f"/tmp/molefm_video_{ts}"
    os.makedirs(tmp_dir, exist_ok=True)

    slides = []  # (image_path, duration_secs)

    # Cover slide
    cover_img = render_cover_slide(broadcast_hour, len(stories))
    cover_path = os.path.join(tmp_dir, "slide_00_cover.png")
    cover_img.save(cover_path)
    slides.append((cover_path, cover_duration))

    # News slides
    total_slides = len(stories) + 2  # cover + stories + outro
    for i, story in enumerate(stories):
        print(f"  Rendering slide {i+1}/{len(stories)}: {story['title'][:50]}...")
        slide_img = render_slide(
            title=story["title"],
            source=story["source"],
            verification=story["verification"],
            slide_index=i + 1,
            total_slides=total_slides,
            broadcast_hour=broadcast_hour,
            story_number=i + 1,
            confidence=story.get("confidence", 65),
        )
        slide_path = os.path.join(tmp_dir, f"slide_{i+1:02d}.png")
        slide_img.save(slide_path)
        slides.append((slide_path, per_story_secs))

    # Outro slide (reuse cover with "Merci" text)
    outro_img = render_background_frame(total_slides - 1, total_slides)
    od = ImageDraw.Draw(outro_img)
    mf = _font(90, bold=True)
    mb = od.textbbox((0,0), "Merci !", font=mf)
    od.text(((VIDEO_W-(mb[2]-mb[0]))//2, VIDEO_H//2 - 120), "Merci !", font=mf, fill=COLOR_WHITE)
    sf = _font(44)
    st = "Restez informés sur molefm.com"
    sb = od.textbbox((0,0), st, font=sf)
    od.text(((VIDEO_W-(sb[2]-sb[0]))//2, VIDEO_H//2 + 10), st, font=sf, fill=(*COLOR_ACCENT, 220))
    ht = _font(36)
    hh = "#MoleFM94   molefm.com"
    hb = od.textbbox((0,0), hh, font=ht)
    od.text(((VIDEO_W-(hb[2]-hb[0]))//2, VIDEO_H//2 + 100), hh, font=ht, fill=(*COLOR_GOLD, 200))
    outro_path = os.path.join(tmp_dir, f"slide_{len(stories)+1:02d}_outro.png")
    outro_img.save(outro_path)
    slides.append((outro_path, outro_duration))

    # Step 5 — Build FFmpeg concat input
    # Each slide becomes a silent video clip, then we overlay the real audio
    concat_list = os.path.join(tmp_dir, "concat.txt")
    clip_paths = []

    for idx, (img_path, dur) in enumerate(slides):
        clip_path = os.path.join(tmp_dir, f"clip_{idx:02d}.mp4")
        cmd = [
            "ffmpeg", "-y", "-loop", "1",
            "-i", img_path,
            "-vf", f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
                   f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2",
            "-t", str(dur),
            "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-an",  # no audio in individual clips
            clip_path
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            print(f"  [ERR] Slide {idx} render failed: {result.stderr.decode()[-200:]}")
            continue
        clip_paths.append(clip_path)

    if not clip_paths:
        print("  [ERROR] No clips generated")
        return None

    # Write concat file
    with open(concat_list, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp}'\n")

    # Step 6 — Concatenate video clips
    video_only = os.path.join(tmp_dir, "video_only.mp4")
    cmd_concat = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        video_only
    ]
    result = subprocess.run(cmd_concat, capture_output=True)
    if result.returncode != 0:
        print(f"  [ERR] Concat failed: {result.stderr.decode()[-300:]}")
        return None

    # Step 7 — Mux with original audio
    # Trim video to match audio, fade audio out at end
    cmd_mux = [
        "ffmpeg", "-y",
        "-i", video_only,
        "-i", mp3_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-af", f"afade=type=out:start_time={duration_secs-3}:duration=3",
        "-shortest",
        "-movflags", "+faststart",  # web optimized
        out_path
    ]
    result = subprocess.run(cmd_mux, capture_output=True)
    if result.returncode != 0:
        print(f"  [ERR] Mux failed: {result.stderr.decode()[-300:]}")
        return None

    # Step 8 — Log to approval queue
    log_entry = {
        "file":        os.path.basename(out_path),
        "path":        out_path,
        "mp3":         mp3_path,
        "timestamp":   datetime.datetime.now().isoformat(),
        "broadcast_hour": broadcast_hour,
        "stories":     len(stories),
        "duration_secs": duration_secs,
        "status":      "PENDING",
        "story_titles": [s["title"][:80] for s in stories],
    }
    _append_approval_log(log_entry)

    file_size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"  ✓ Video ready: {out_path} ({file_size_mb:.1f} MB)")
    print(f"  Status: PENDING APPROVAL")

    # Cleanup tmp
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return out_path


# ── Approval log helpers ──────────────────────────────────────────────────────
def _append_approval_log(entry: dict):
    log = []
    try:
        with open(APPROVAL_LOG, "r") as f:
            log = json.load(f)
    except Exception:
        pass
    log.append(entry)
    log = log[-200:]
    with open(APPROVAL_LOG, "w") as f:
        json.dump(log, f, indent=2, default=str)


def approve_video(filename: str) -> bool:
    """Move a video from queue/ to approved/ and update log."""
    src = os.path.join(QUEUE_DIR, filename)
    if not os.path.exists(src):
        print(f"  [ERR] Not found in queue: {filename}")
        return False
    dst = os.path.join(APPROVED_DIR, filename)
    os.rename(src, dst)
    _update_log_status(filename, "APPROVED")
    print(f"  ✓ Approved: {filename}")
    return True


def reject_video(filename: str) -> bool:
    """Move a video from queue/ to rejected/ and update log."""
    src = os.path.join(QUEUE_DIR, filename)
    if not os.path.exists(src):
        print(f"  [ERR] Not found in queue: {filename}")
        return False
    dst = os.path.join(REJECTED_DIR, filename)
    os.rename(src, dst)
    _update_log_status(filename, "REJECTED")
    print(f"  ✗ Rejected: {filename}")
    return True


def _update_log_status(filename: str, status: str):
    try:
        with open(APPROVAL_LOG, "r") as f:
            log = json.load(f)
        for entry in log:
            if entry.get("file") == filename:
                entry["status"] = status
                entry["reviewed_at"] = datetime.datetime.now().isoformat()
        with open(APPROVAL_LOG, "w") as f:
            json.dump(log, f, indent=2, default=str)
    except Exception as e:
        print(f"  [WARN] Log update: {e}")


def list_queue() -> list[dict]:
    """Return all videos currently awaiting approval."""
    try:
        with open(APPROVAL_LOG, "r") as f:
            log = json.load(f)
        return [e for e in log if e.get("status") == "PENDING"]
    except Exception:
        return []


# ── Find matching JSON for an MP3 ────────────────────────────────────────────
def find_json_for_mp3(mp3_path: str) -> str | None:
    ts = os.path.basename(mp3_path).replace("newscast_", "").replace(".mp3", "")
    json_path = os.path.join(SCRIPTS_DIR, f"newscast_{ts}.json")
    if os.path.exists(json_path):
        return json_path
    # Try any JSON with timestamp overlap
    jsons = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "newscast_*.json")))
    if jsons:
        return jsons[-1]  # fallback to latest
    return None


# ── CLI entrypoint ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Mole FM Video Generator")
    parser.add_argument("--all",      action="store_true", help="Generate videos for all unapproved newscasts")
    parser.add_argument("--file",     type=str,            help="Specific MP3 path to process")
    parser.add_argument("--approve",  type=str,            help="Approve a video by filename")
    parser.add_argument("--reject",   type=str,            help="Reject a video by filename")
    parser.add_argument("--queue",    action="store_true", help="List pending approval queue")
    args = parser.parse_args()

    if args.approve:
        approve_video(args.approve)
        return

    if args.reject:
        reject_video(args.reject)
        return

    if args.queue:
        pending = list_queue()
        if not pending:
            print("Approval queue is empty.")
        else:
            print(f"Pending approval ({len(pending)} videos):")
            for e in pending:
                print(f"  {e['file']}  [{e['broadcast_hour']}]  {e['stories']} stories")
        return

    # Determine which MP3s to process
    if args.file:
        mp3s = [args.file] if os.path.exists(args.file) else []
    elif args.all:
        mp3s = sorted(glob.glob(os.path.join(AUDIO_DIR, "newscast_*.mp3")))
        # Filter out already-generated
        already = {
            e["mp3"] for e in (
                json.load(open(APPROVAL_LOG)) if os.path.exists(APPROVAL_LOG) else []
            )
        }
        mp3s = [m for m in mp3s if m not in already]
    else:
        # Default: latest newscast only
        all_mp3s = sorted(glob.glob(os.path.join(AUDIO_DIR, "newscast_*.mp3")))
        mp3s = [all_mp3s[-1]] if all_mp3s else []

    if not mp3s:
        print("No new newscasts to process.")
        return

    generated = []
    for mp3_path in mp3s:
        json_path = find_json_for_mp3(mp3_path)
        if not json_path:
            print(f"  [SKIP] No JSON found for {os.path.basename(mp3_path)}")
            continue
        out = generate_video(mp3_path, json_path)
        if out:
            generated.append(out)

    print(f"\n{'─'*50}")
    print(f"Generated {len(generated)} video(s) → {QUEUE_DIR}")
    print(f"Run with --queue to see pending approvals.")
    print(f"Approve: python3 video_generator.py --approve <filename>")


if __name__ == "__main__":
    main()
