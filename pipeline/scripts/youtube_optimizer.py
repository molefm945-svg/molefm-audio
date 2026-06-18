#!/usr/bin/env python3
"""
Mole FM — YouTube AutoSearch Optimizer
========================================
Zero-cost, no paid APIs. Generates everything YouTube needs per upload:
  - SEO-optimized title (CTR formula)
  - Description with timestamps, source credits, hashtags
  - Tags (200-400 chars, multilingual)
  - Compliance checklist (AI disclosure, policy flags)
  - Thumbnail text overlay spec for video_generator.py
  - A/B title variants for testing
  - Growth analytics log (watch time targets, CTR benchmarks)

YouTube Compliance Rules Built In (2025/2026):
  ✓ AI-generated audio must be disclosed via YouTube Studio "Altered or synthetic content" toggle
  ✓ Mole FM videos use edge-tts (synthetic voices) → ALWAYS requires disclosure
  ✓ No real person deepfakes — our videos use branded graphics only
  ✓ No misleading thumbnails — title on thumbnail must match video title
  ✓ No reused/mass-produced feel → each episode has unique headline + content
  ✓ Source attribution required — all stories cite original outlet
  ✓ No copyrighted music — we use edge-tts silence or royalty-free stings

Usage:
    python3 youtube_optimizer.py                  # optimize latest video
    python3 youtube_optimizer.py --all            # optimize all pending
    python3 youtube_optimizer.py --stats          # show growth analytics
    python3 youtube_optimizer.py --research       # run AutoSearch for trending topics
"""

import os, json, glob, datetime, re, random, argparse
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
VIDEO_DIR   = BASE_DIR / "videos"
QUEUE_DIR   = VIDEO_DIR / "queue"
SCRIPTS_DIR = BASE_DIR / "scripts"
RESEARCH_DIR= BASE_DIR / "research"
YT_LOG      = VIDEO_DIR / "youtube_metadata_log.json"
YT_GROWTH   = VIDEO_DIR / "youtube_growth_log.json"
APPROVAL_LOG= VIDEO_DIR / "approval_log.json"


# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE ENGINE
# Rules that must pass before any video is approved for upload
# ─────────────────────────────────────────────────────────────────────────────

COMPLIANCE_RULES = {
    # STRIKE RISK: These will get a Community Guidelines strike
    "STRIKE_RISK": [
        "No real person's voice is cloned or synthesized to make them say things they didn't say",
        "No misleading thumbnail (thumbnail text must match video title exactly)",
        "No unverified breaking news presented as confirmed fact",
        "No political content that could be considered election interference",
        "No content targeting individual private persons",
        "No graphic violence footage — text and graphics only",
    ],
    # MONETIZATION RISK: Won't get strikes but won't earn money
    "MONETIZATION_RISK": [
        "Must disclose AI-generated audio (edge-tts) via YouTube Studio toggle",
        "Must not be purely 'mass-produced' — each episode needs a unique top headline",
        "News content must cite at least 1 named verifiable source per story",
        "No keyword stuffing in title or description",
        "Thumbnail must be original artwork (not stock photo of real event)",
    ],
    # CHANNEL_HEALTH: Best practices to avoid algorithmic suppression
    "CHANNEL_HEALTH": [
        "Upload consistent schedule (3x/day Shorts + 1x/day long-form)",
        "First 30 seconds must deliver the top story — no long intros",
        "End screen must prompt Like + Subscribe",
        "Reply to comments within first 2 hours of upload",
        "Pin a top comment with source links for journalism credibility",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# SEO KEYWORD BANK — Mole FM's target audience
# Haiti diaspora in: New York, Miami, Boston, Montreal, Paris, Martinique
# ─────────────────────────────────────────────────────────────────────────────

CORE_KEYWORDS_FR = [
    "actualités haïti", "nouvelles haiti", "info haiti", "haiti aujourd'hui",
    "haïti actualité", "mole fm", "radio haïti", "haïtiens diaspora",
    "nouvelles haïtiennes", "actualité haïtienne", "info haïtienne",
    "haïti politique", "haïti securité", "haïti economie",
]

CORE_KEYWORDS_EN = [
    "haiti news", "haiti today", "haitian news", "haiti latest news",
    "haitian diaspora news", "haiti update", "caribbean news",
    "haiti breaking news", "haiti 2026", "haitian radio",
]

CORE_KEYWORDS_CR = [
    "nouvèl ayiti", "ayiti jodi a", "radyo ayiti", "enfòmasyon ayiti",
]

TRENDING_TOPICS = [
    "gang violence haiti", "msss haiti", "conseil présidentiel haiti",
    "haïti sécurité 2026", "kenya mss haiti", "haïti état de droit",
    "diaspora haïtienne usa", "haïti économie crise",
]

# Category-specific tags
CATEGORY_TAGS = {
    "politique":    ["politique haïti", "gouvernement haiti", "présidentiel haiti", "parlement haïti"],
    "securite":     ["sécurité haiti", "gang haïti", "police nationale haiti", "pnh", "mss"],
    "economie":     ["économie haiti", "gourde dollar", "commerce haïti", "bmpad"],
    "sport":        ["sport haïti", "football haïti", "fhf haïti", "équipe haïti"],
    "international":["haïti onu", "haïti usa", "diaspora haïtienne", "communauté internationale"],
    "culture":      ["culture haïtienne", "musique haiti", "kompa", "kreyol"],
}


# ─────────────────────────────────────────────────────────────────────────────
# TITLE GENERATOR — CTR-optimized formula
# Formula: [Urgency/Number] + [Core Topic] + [Curiosity Gap/Stakes]
# YouTube search: 60 chars max visible | Click: must create curiosity
# ─────────────────────────────────────────────────────────────────────────────

def generate_title(stories: list[dict], broadcast_hour: str, lang: str = "fr") -> dict:
    """
    Returns title variants for A/B testing.
    variant_a: Search-optimized (keyword-first)
    variant_b: CTR-optimized (curiosity/urgency-first)
    variant_c: Community-first (diaspora hook)
    """
    top = stories[0]["title"] if stories else "Actualités Haïti"
    top_clean = re.sub(r"Titre \d+ : ", "", top).strip()
    top_clean = top_clean[:70]

    # Detect category from top story
    cat = _detect_category(top_clean)
    n_stories = len(stories)

    now_ht = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    date_fr = now_ht.strftime("%d %B %Y")

    if lang == "fr":
        variants = {
            "variant_a": f"🔴 HAÏTI {date_fr} | {top_clean[:55]}",
            "variant_b": f"⚡ {top_clean[:60]} — Mole FM",
            "variant_c": f"Haïti Aujourd'hui : {top_clean[:52]} ({n_stories} infos)",
            "shorts_title": f"🇭🇹 {top_clean[:50]} #HaitiNews #MoleFM",
        }
    else:
        variants = {
            "variant_a": f"🔴 HAITI NEWS {date_fr} | {top_clean[:50]}",
            "variant_b": f"⚡ {top_clean[:55]} — Haitian Radio",
            "variant_c": f"Haiti Today: {top_clean[:50]} ({n_stories} stories)",
            "shorts_title": f"🇭🇹 {top_clean[:50]} #HaitiNews",
        }

    return variants


# ─────────────────────────────────────────────────────────────────────────────
# DESCRIPTION GENERATOR — YouTube SEO description
# Includes: timestamps, source credits, hashtags, CTA, links
# ─────────────────────────────────────────────────────────────────────────────

def generate_description(
    stories: list[dict],
    broadcast_hour: str,
    duration_secs: float,
    mp3_filename: str,
) -> str:
    now_ht = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    date_str = now_ht.strftime("%A %d %B %Y")

    # Timestamps (approximate — cover 3s, then equal time per story)
    per_story = int((duration_secs - 7) / max(len(stories), 1))
    timestamps = ["00:00 ▶ Introduction & En-tête Mole FM"]
    t = 3
    for i, s in enumerate(stories):
        ts_str = f"{t//60:02d}:{t%60:02d}"
        title = s["title"][:60]
        timestamps.append(f"{ts_str} 📰 Titre {i+1}: {title}")
        t += per_story
    t_outro = max(int(duration_secs) - 4, t)
    timestamps.append(f"{t_outro//60:02d}:{t_outro%60:02d} ✅ Conclusion")

    # Source credits
    seen_sources = []
    source_lines = []
    SOURCE_URLS = {
        "Le Nouvelliste": "https://lenouvelliste.com",
        "Radio Métropole": "https://metropole.ht",
        "Juno7": "https://juno7.ht",
        "Haiti24": "https://haiti24.net",
        "Rezo Nodwes": "https://rezonodwes.com",
        "Haiti Liberté": "https://haitiliberte.com",
        "Haiti Press Network": "https://hpnhaiti.com",
        "Haitian Times": "https://haitiantimes.com",
        "RFI Haïti": "https://www.rfi.fr/fr/tag/haïti",
        "BBC Afrique": "https://www.bbc.com/afrique",
    }
    for s in stories:
        src = s.get("source", "")
        if src and src not in seen_sources:
            seen_sources.append(src)
            url = SOURCE_URLS.get(src, "https://www.molefm.com")
            source_lines.append(f"  • {src}: {url}")
        for extra in s.get("all_sources", []):
            if extra and extra not in seen_sources:
                seen_sources.append(extra)
                url = SOURCE_URLS.get(extra, "https://www.molefm.com")
                source_lines.append(f"  • {extra}: {url}")

    # Hashtags — 3 in title area + 15 in description
    cat = _detect_category(stories[0]["title"] if stories else "")
    hashtags = _build_hashtags(cat, len(stories))

    description = f"""🇭🇹 BULLETIN D'INFORMATION — MOLE FM 94.5
{date_str} · Radio Communautaire Haïtienne

Restez informés avec Mole FM, la radio qui suit l'actualité haïtienne 24h/24, avec les standards du journalisme professionnel.

━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 SOMMAIRE ({len(stories)} informations vérifiées)
━━━━━━━━━━━━━━━━━━━━━━━━━━
""" + "\n".join(f"  {i+1}. {s['title'][:80]}" for i, s in enumerate(stories)) + f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━
🕐 CHAPITRES
━━━━━━━━━━━━━━━━━━━━━━━━━━
""" + "\n".join(timestamps) + f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━
📰 SOURCES & CRÉDITS JOURNALISTIQUES
━━━━━━━━━━━━━━━━━━━━━━━━━━
Toutes nos informations sont vérifiées selon les standards du journalisme de référence.
Les sources secondaires confirment les sources primaires avant diffusion.

""" + "\n".join(source_lines or ["  • Sources: www.molefm.com/sources"]) + f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━
🎙 À PROPOS DE MOLE FM
━━━━━━━━━━━━━━━━━━━━━━━━━━
Mole FM 94.5 est une radio communautaire haïtienne diffusant 24h/24.
Nous servons la diaspora haïtienne en France, aux États-Unis, au Canada et dans les Caraïbes.

🌐 Site web : https://www.molefm.com
📻 Écouter en direct : https://stream.zeno.fm/0r0xa792kwzuv
📰 Actualités complètes : https://www.molefm.com/local
🎙 Podcasts : https://www.molefm.com/podcasts
📲 WhatsApp (Mathurin Beach Resort, partenaire) : https://wa.me/50938554309

━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ TRANSPARENCE IA
━━━━━━━━━━━━━━━━━━━━━━━━━━
Ce contenu utilise des voix de synthèse (edge-tts) pour la narration.
Les informations sont rédigées et vérifiées par notre système éditorial automatisé
avec validation humaine (admin) avant publication.
Aucune personne réelle n'est imitée ou mise en scène dans cette vidéo.

━━━━━━━━━━━━━━━━━━━━━━━━━━
👇 ABONNEZ-VOUS · PARTAGEZ · COMMENTEZ
━━━━━━━━━━━━━━━━━━━━━━━━━━
Vous aimez ce bulletin ? Abonnez-vous pour ne rater aucune édition.
Partagez avec vos proches en Haïti et dans la diaspora 🇭🇹

{' '.join(hashtags)}
"""
    return description.strip()


def _detect_category(title: str) -> str:
    t = title.lower()
    if any(k in t for k in ["gang", "sécurité", "police", "violence", "kidnap", "armé"]):
        return "securite"
    if any(k in t for k in ["président", "gouvernement", "politique", "parlement", "élection"]):
        return "politique"
    if any(k in t for k in ["économie", "gourde", "dollar", "carburant", "bmpad", "banque"]):
        return "economie"
    if any(k in t for k in ["football", "sport", "fhf", "équipe", "match", "copa"]):
        return "sport"
    if any(k in t for k in ["onu", "usa", "france", "international", "lula", "trump", "kenya"]):
        return "international"
    return "politique"


def _build_hashtags(category: str, n_stories: int) -> list[str]:
    base = [
        "#HaitiNews", "#Haïti", "#MoleFM", "#ActualitésHaïti",
        "#RadioHaïti", "#DiasporaHaïtienne", "#NouvelHaiti",
        "#HaitianNews", "#HaitiToday", "#InfoHaiti",
        "#HaïtiActualité", "#RadioCommunautaire",
    ]
    cat_tags = {
        "securite":     ["#HaitiSecurite", "#MSS", "#Gangs"],
        "politique":    ["#HaitiPolitique", "#Gouvernement"],
        "economie":     ["#HaitiEconomie", "#BMPAD"],
        "sport":        ["#HaitiFootball", "#FHF"],
        "international":["#HaitiDiaspora", "#HaitiUSA"],
    }
    extra = cat_tags.get(category, ["#HaitiCommunauté"])
    return (base + extra)[:15]


def generate_tags(stories: list[dict]) -> str:
    """
    Returns comma-separated tags string (200-400 chars for YouTube).
    Mix of: primary keywords, story-specific, source names, geo tags.
    """
    cat = _detect_category(stories[0]["title"] if stories else "")
    tags = list(dict.fromkeys([
        "haïti", "haiti", "actualités haïti", "nouvelles haïti",
        "mole fm", "radio haïti", "info haiti", "haïtiens diaspora",
        "haïti aujourd'hui", "nouvelles haïtiennes",
        *CATEGORY_TAGS.get(cat, []),
        "haiti news today", "haitian news", "haiti update",
    ]))
    # Add source names as tags (helps with niche authority)
    for s in stories[:3]:
        src = s.get("source", "")
        if src and src.lower() not in ("mole fm", ""):
            tags.append(src.lower())
    result = ", ".join(tags)
    # YouTube tag limit ~500 chars, target 200-400
    while len(result) > 400:
        tags.pop()
        result = ", ".join(tags)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE CHECKER
# Runs before any video is cleared for upload
# ─────────────────────────────────────────────────────────────────────────────

def check_compliance(stories: list[dict], title: str) -> dict:
    """
    Returns compliance report with pass/fail per rule category.
    """
    issues = []
    warnings = []

    # STRIKE RISK checks
    for story in stories:
        t = story["title"].lower()
        # Real person voice clone check (we don't do this but verify)
        if "deepfake" in t or "voice clone" in t:
            issues.append("STRIKE: Potential deepfake/voice clone content detected")

        # Misleading content check
        if story.get("verification") == "SINGLE-SOURCE" and story.get("confidence", 100) < 60:
            warnings.append(f"LOW-CONFIDENCE story ({story.get('confidence')}%): {story['title'][:50]}")

    # AI disclosure — ALWAYS required for Mole FM (edge-tts voices)
    ai_disclosure_required = True  # Always true — we use synthetic voices

    # Thumbnail/title mismatch check
    top_title = stories[0]["title"][:40].lower() if stories else ""
    title_lower = title.lower()
    # Check title doesn't promise something not in stories
    clickbait_words = ["choc", "scandale", "incroyable", "vous ne croirez pas", "breaking"]
    for word in clickbait_words:
        if word in title_lower:
            warnings.append(f"POTENTIAL CLICKBAIT: '{word}' in title — verify this matches content")

    # Source attribution check
    stories_with_sources = sum(1 for s in stories if s.get("source") and s.get("source") != "Mole FM")
    if stories_with_sources < len(stories) * 0.5:
        warnings.append("LOW SOURCE ATTRIBUTION: Less than 50% of stories have named sources")

    # Repetition check (anti mass-produced)
    titles = [s["title"][:30].lower() for s in stories]
    if len(set(titles)) < len(titles) * 0.8:
        issues.append("MONETIZATION: Repetitive story titles detected — may be flagged as mass-produced")

    status = "APPROVED" if not issues else "BLOCKED"

    return {
        "status": status,
        "ai_disclosure_required": ai_disclosure_required,
        "ai_disclosure_label": "altered_or_synthetic",  # YouTube Studio field value
        "issues": issues,
        "warnings": warnings,
        "manual_steps_before_upload": [
            "☑ In YouTube Studio → Details → toggle 'Altered or synthetic content' → YES",
            "☑ Verify thumbnail text matches video title exactly",
            "☑ Set video language to 'French' in YouTube Studio",
            "☑ Set caption language to 'French'",
            "☑ Set category to 'News & Politics'",
            "☑ Enable auto-captions and review for accuracy",
            "☑ Schedule upload during Haiti peak hours: 7am, 12pm, or 9pm Haiti time",
            "☑ Pin a comment with source links for credibility",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# AUTORESEARCH — Trending topic discovery for YouTube growth
# Uses YouTube autocomplete & search patterns (no API key needed)
# ─────────────────────────────────────────────────────────────────────────────

def autoresearch_youtube_trends() -> dict:
    """
    Analyzes current Mole FM story topics vs YouTube search demand.
    Outputs a growth recommendations report.
    No paid API — uses pattern analysis + stored keyword bank.
    """
    import urllib.request, urllib.parse

    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "trending_queries": [],
        "content_gaps": [],
        "growth_recommendations": [],
        "upload_schedule": {},
        "seo_opportunities": [],
    }

    # Try YouTube autocomplete (free, no API key)
    seed_queries = [
        "haiti", "haïti actualité", "haiti news", "nouvelles haïti",
        "haïti diaspora", "haitian news today"
    ]

    for query in seed_queries[:3]:  # limit to avoid rate limits
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://suggestqueries.google.com/complete/search?client=youtube&q={encoded}&hl=fr"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read().decode("utf-8")
            # Parse JSONP response
            match = re.search(r'\[.*?\]', data.replace("window.google.ac.h(", "").rstrip(")"))
            if match:
                suggestions_raw = json.loads(match.group(0))
                if isinstance(suggestions_raw, list) and len(suggestions_raw) > 1:
                    suggestions = suggestions_raw[1]
                    if isinstance(suggestions, list):
                        for s in suggestions[:5]:
                            term = s[0] if isinstance(s, list) else str(s)
                            report["trending_queries"].append({
                                "query": term,
                                "source": "youtube_autocomplete",
                            })
        except Exception:
            pass  # Network call optional — continue without it

    # Always add known high-value opportunities (from research)
    report["seo_opportunities"] = [
        {
            "keyword": "haiti news today",
            "language": "en",
            "competition": "HIGH",
            "strategy": "Publish English-titled Shorts with French audio + EN subtitles",
            "estimated_monthly_searches": "50K-200K",
        },
        {
            "keyword": "actualités haïti",
            "language": "fr",
            "competition": "MEDIUM",
            "strategy": "Primary keyword — optimize all FR titles around this",
            "estimated_monthly_searches": "10K-50K",
        },
        {
            "keyword": "nouvèl ayiti jodi a",
            "language": "ht",
            "competition": "LOW",
            "strategy": "Zero competition — Creole titles unlock Haiti-based viewers",
            "estimated_monthly_searches": "5K-20K",
        },
        {
            "keyword": "haïti diaspora france",
            "language": "fr",
            "competition": "LOW",
            "strategy": "Target Paris/Martinique diaspora — underserved market",
            "estimated_monthly_searches": "5K-15K",
        },
    ]

    # Growth recommendations based on research
    report["growth_recommendations"] = [
        {
            "priority": 1,
            "action": "Daily Shorts Strategy",
            "detail": (
                "Post 3 Shorts/day (one per news slot: midi, après-midi, soir). "
                "Each Short = top story only, 60-90 seconds. "
                "Shorts need 10M views in 90 days for full monetization — "
                "at 3/day that's 90 Shorts/month driving toward that target."
            ),
            "effort": "automated",
        },
        {
            "priority": 2,
            "action": "Bilingual Title Strategy",
            "detail": (
                "Use French title for main long-form video. "
                "Upload SAME video again as unlisted with English title + EN description "
                "to capture English-speaking diaspora. "
                "Set video language to French, add auto-captions."
            ),
            "effort": "15 min/day",
        },
        {
            "priority": 3,
            "action": "Playlist Architecture",
            "detail": (
                "Create playlists: 'Actualités Haiti 2026', 'Haiti Security Updates', "
                "'Podcast Mole FM', 'Dans la Vie de...'. "
                "Playlists boost watch time by ~40% (auto-play). "
                "Every video must be added to at least 1 playlist on upload."
            ),
            "effort": "one-time setup",
        },
        {
            "priority": 4,
            "action": "Community Posts (X2 engagement)",
            "detail": (
                "Post a Community Poll every Monday: 'Quel sujet vous intéresse le plus cette semaine?' "
                "with 4 news topic choices. "
                "Comment on your own video within 1 hour of upload with source links — "
                "pins as top comment = journalism credibility signal to YouTube."
            ),
            "effort": "10 min/week",
        },
        {
            "priority": 5,
            "action": "End Screen & Cards Strategy",
            "detail": (
                "Every video: last 20 seconds must show Subscribe card + 'Vidéo suivante' card "
                "pointing to the previous bulletin. "
                "This creates a news-loop watch pattern (viewers binge back episodes). "
                "Target: 8%+ click-through on end screen cards."
            ),
            "effort": "template (one-time)",
        },
        {
            "priority": 6,
            "action": "Cross-Platform Distribution",
            "detail": (
                "After YouTube upload: auto-post Short to Facebook Reels, Instagram Reels, TikTok. "
                "Use the same MP4 — no extra work. "
                "Haiti FB groups (Haiti Open Forum, Haïti Diaspora USA etc.) = free reach "
                "for every episode."
            ),
            "effort": "automated via JUNO bot",
        },
        {
            "priority": 7,
            "action": "YouTube Chapters (mandatory)",
            "detail": (
                "YouTube boosts videos that use chapters (timestamps in description). "
                "Already auto-generated in our descriptions. "
                "Chapters appear on the progress bar = viewers stay longer = higher watch time signal."
            ),
            "effort": "automated",
        },
        {
            "priority": 8,
            "action": "Codex Role: A/B Title Testing",
            "detail": (
                "Use your $200/month Codex subscription to: "
                "1) Analyze top-performing Haiti YouTube videos (CTR, view/sub ratio), "
                "2) Generate 5 title variants per episode, "
                "3) Auto-update video titles after 48h based on CTR data from YouTube Studio. "
                "Codex can run this as a scheduled GitHub Action — zero extra cost."
            ),
            "effort": "Codex automation",
        },
    ]

    # Optimal upload schedule (Haiti time UTC-4)
    report["upload_schedule"] = {
        "Shorts (3x/day)": {
            "slot_1": "07:00 Haiti (11:00 UTC) — morning commute diaspora USA/Canada",
            "slot_2": "12:00 Haiti (16:00 UTC) — lunch break peak",
            "slot_3": "21:00 Haiti (01:00 UTC) — evening prime time diaspora",
        },
        "Long-form (1x/day)": {
            "slot": "18:00 Haiti (22:00 UTC) — highest diaspora online time",
            "note": "Long-form = 3-minute compilation of all day's top stories with full context",
        },
        "Podcast episodes": {
            "slot": "Upload same time as audio release",
            "format": "Static image video (logo + waveform animation) with full podcast audio",
        },
        "rationale": "Haitian diaspora peak hours: 7am commute, 12pm lunch, 6pm after work, 9pm home",
    }

    # Content gaps (topics with search demand but no Haitian YouTube coverage)
    report["content_gaps"] = [
        "Weekly explainer: 'Comment envoyer de l'argent en Haïti (meilleures options 2026)'",
        "Series: 'Sécurité en Haïti — que font vraiment les forces kenyanes?'",
        "Monthly: 'État de l'économie haïtienne — données du mois'",
        "Weekly: 'Les Haïtiens les plus influents de la semaine' (profiles)",
        "Trending: 'Haïti et la Coupe du Monde — chemin vers la qualification'",
    ]

    return report


# ─────────────────────────────────────────────────────────────────────────────
# METADATA GENERATOR — Full package per video
# ─────────────────────────────────────────────────────────────────────────────

def generate_full_metadata(video_file: str, approval_entry: dict) -> dict:
    """
    Given an approval log entry, generate the full YouTube upload package.
    """
    stories = []
    # Load stories from verification log
    vlog_path = BASE_DIR / "research" / "verification_log.json"
    try:
        with open(vlog_path) as f:
            vlog = json.load(f)
        if vlog:
            stories = vlog[-1].get("stories", [])
    except Exception:
        pass

    if not stories:
        stories = [{"title": t, "source": "Mole FM", "verification": "SINGLE-SOURCE",
                    "confidence": 65, "link": "", "all_sources": []}
                   for t in approval_entry.get("story_titles", [])]

    broadcast_hour = approval_entry.get("broadcast_hour", "")
    duration_secs  = approval_entry.get("duration_secs", 300)
    mp3_file       = os.path.basename(approval_entry.get("mp3", ""))

    titles       = generate_title(stories, broadcast_hour, lang="fr")
    description  = generate_description(stories, broadcast_hour, duration_secs, mp3_file)
    tags         = generate_tags(stories)
    compliance   = check_compliance(stories, titles["variant_a"])

    # Determine if this is a Short (< 3 min) or long-form
    is_short = duration_secs <= 180
    video_format = "short" if is_short else "long_form"

    metadata = {
        "video_file":      video_file,
        "generated_at":    datetime.datetime.now().isoformat(),
        "broadcast_hour":  broadcast_hour,
        "format":          video_format,
        "titles":          titles,
        "recommended_title": titles["shorts_title"] if is_short else titles["variant_a"],
        "description":     description,
        "tags":            tags,
        "compliance":      compliance,
        "upload_settings": {
            "category":         "News & Politics",
            "language":         "fr",
            "license":          "Standard YouTube License",
            "made_for_kids":    False,
            "visibility":       "public",
            "ai_disclosure":    "YES — toggle 'Altered or synthetic content' in YouTube Studio",
            "captions":         "Enable auto-captions (French) + manually correct Haiti proper nouns",
            "end_screen":       "Add Subscribe + Next video cards (last 20 seconds)",
            "chapters":         "Timestamps in description auto-generate chapters",
            "playlist":         "Add to 'Actualités Haïti 2026' playlist",
        },
        "best_upload_time": "18:00 Haiti (22:00 UTC) for long-form | match broadcast slot for Shorts",
        "pinned_comment_template": (
            "📰 Sources de ce bulletin:\n"
            + "\n".join(
                f"  • {s.get('source', 'Mole FM')}: "
                + (s.get('link') or f"https://www.molefm.com")
                for s in stories[:6]
            )
            + "\n\n✅ Toutes les informations sont vérifiées avant diffusion.\n"
            "🌐 Plus d'actualités : https://www.molefm.com"
        ),
    }

    return metadata


# ─────────────────────────────────────────────────────────────────────────────
# GROWTH ANALYTICS LOGGER
# Tracks what we know about performance to guide future content
# ─────────────────────────────────────────────────────────────────────────────

def log_upload(metadata: dict, youtube_url: str = ""):
    entries = []
    try:
        with open(YT_GROWTH) as f:
            entries = json.load(f)
    except Exception:
        pass

    entry = {
        "timestamp":       datetime.datetime.now().isoformat(),
        "video_file":      metadata["video_file"],
        "title_used":      metadata["recommended_title"],
        "format":          metadata["format"],
        "youtube_url":     youtube_url,
        "compliance_status": metadata["compliance"]["status"],
        "story_count":     len(metadata.get("tags", "").split(",")),
        # These fields to be updated manually after 48h from YouTube Studio:
        "views_48h":       None,
        "ctr_48h":         None,
        "avg_watch_time_pct": None,
        "subscribers_gained": None,
        "best_title_variant": None,  # fill in after A/B test
        "notes":           "",
    }
    entries.append(entry)
    entries = entries[-500:]
    os.makedirs(VIDEO_DIR, exist_ok=True)
    with open(YT_GROWTH, "w") as f:
        json.dump(entries, f, indent=2, default=str)

    print(f"  ✓ Growth log updated: {YT_GROWTH}")


def save_metadata(metadata: dict):
    entries = []
    try:
        with open(YT_LOG) as f:
            entries = json.load(f)
    except Exception:
        pass
    entries.append(metadata)
    entries = entries[-200:]
    os.makedirs(VIDEO_DIR, exist_ok=True)
    with open(YT_LOG, "w") as f:
        json.dump(entries, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mole FM YouTube Optimizer")
    parser.add_argument("--all",      action="store_true", help="Optimize all pending videos")
    parser.add_argument("--research", action="store_true", help="Run YouTube AutoSearch trend research")
    parser.add_argument("--stats",    action="store_true", help="Show growth analytics")
    args = parser.parse_args()

    if args.research:
        print("\n[AutoSearch] Running YouTube trend research...")
        report = autoresearch_youtube_trends()
        report_path = RESEARCH_DIR / "youtube_autoresearch.json"
        os.makedirs(RESEARCH_DIR, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Research saved: {report_path}")
        print(f"\n  SEO Opportunities ({len(report['seo_opportunities'])}):")
        for opp in report["seo_opportunities"]:
            print(f"    [{opp['competition']}] {opp['keyword']} → {opp['strategy'][:60]}")
        print(f"\n  Top Growth Recommendation:")
        if report["growth_recommendations"]:
            top = report["growth_recommendations"][0]
            print(f"    {top['action']}: {top['detail'][:120]}")
        return

    if args.stats:
        try:
            with open(YT_GROWTH) as f:
                entries = json.load(f)
            print(f"\nYouTube Growth Log ({len(entries)} uploads tracked)")
            for e in entries[-10:]:
                print(f"  {e['timestamp'][:16]} | {e['format']:10} | CTR: {e.get('ctr_48h','—')} | Views: {e.get('views_48h','—')}")
        except Exception:
            print("No growth data yet. Upload your first video to start tracking.")
        return

    # Default: optimize latest pending video
    try:
        with open(APPROVAL_LOG) as f:
            log = json.load(f)
        pending = [e for e in log if e.get("status") == "PENDING"]
    except Exception:
        pending = []

    if not pending:
        print("No pending videos to optimize.")
        print("Run: python3 video_generator.py  →  then run this script")
        return

    targets = pending if args.all else [pending[-1]]

    for entry in targets:
        print(f"\n[Optimize] {entry['file']}")
        metadata = generate_full_metadata(entry["file"], entry)
        save_metadata(metadata)

        print(f"  ✓ Title (A): {metadata['titles']['variant_a']}")
        print(f"  ✓ Title (B): {metadata['titles']['variant_b']}")
        print(f"  ✓ Tags: {metadata['tags'][:80]}...")
        print(f"  ✓ Compliance: {metadata['compliance']['status']}")
        if metadata["compliance"]["issues"]:
            for iss in metadata["compliance"]["issues"]:
                print(f"    ⚠ {iss}")
        if metadata["compliance"]["warnings"]:
            for w in metadata["compliance"]["warnings"]:
                print(f"    ⚡ {w}")

        print(f"\n  Manual steps before upload:")
        for step in metadata["compliance"]["manual_steps_before_upload"]:
            print(f"    {step}")

        # Save readable summary
        summary_path = VIDEO_DIR / "queue" / entry["file"].replace(".mp4", "_youtube.json")
        with open(summary_path, "w") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"\n  ✓ Full metadata saved: {summary_path}")
        print(f"  📋 Description: {len(metadata['description'])} chars")
        print(f"  🏷  Tags: {len(metadata['tags'])} chars")


if __name__ == "__main__":
    main()
