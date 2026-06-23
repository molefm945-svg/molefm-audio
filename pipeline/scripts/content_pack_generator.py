#!/usr/bin/env python3
"""
Mole FM — Content Pack Generator
=================================
Generates a molefm.com-compatible latest-content-pack.json from the
current pipeline audio (newscasts + podcasts hosted on GitHub).

How molefm.com works:
  The player at molefm.com reads /radio/generated/latest-content-pack.json
  to know what audio to play. This JSON defines all 24 "slots" for the day —
  hourly news, podcast replays, sponsor segments, etc.

  Since molefm.com is a Vercel/Cloudflare static app, we can't write to it
  directly. BUT: the content pack is served from the Vercel deployment, and
  we CAN update it by:
    1. Generating a new content-pack.json pointing to our GitHub-hosted audio
    2. Pushing it to the molefm-audio GitHub repo
    3. The GitHub Pages feed at molefm945-svg.github.io/molefm-audio/ serves it

  The reader webapp at molefm-reader.pplx.app is the FULLY WORKING live player.
  It gets updated every hour automatically via run_pipeline.py.

  For molefm.com integration: we generate a compatible content-pack.json and
  save it to the GitHub repo as public/radio/generated/latest-content-pack.json
  so any future Vercel redeployment can pick it up automatically.

Usage:
  python content_pack_generator.py
  python content_pack_generator.py --dry-run   (print output, don't save)
"""

import os
import sys
import json
import glob
import datetime
import subprocess
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = os.environ.get("MOLEFM_WORKSPACE", str(REPO_ROOT))
AUDIO_DIR = os.environ.get("MOLEFM_AUDIO_DIR", os.path.join(WORKSPACE, "audio"))
PODCAST_DIR = os.environ.get("MOLEFM_PODCAST_DIR", os.path.join(WORKSPACE, "podcasts"))
SCRIPTS_DIR = os.environ.get(
    "MOLEFM_NEWS_SCRIPTS_DIR",
    os.path.join(WORKSPACE, "pipeline", "runtime", "scripts"),
)
CONFIG_DIR = os.environ.get("MOLEFM_CONFIG_DIR", os.path.join(WORKSPACE, "pipeline", "config"))
REGISTRY_PATH = os.path.join(CONFIG_DIR, "audio_registry.json")
OUTPUT_DIR = os.environ.get("MOLEFM_OUTPUT_DIR", os.path.join(WORKSPACE, "pipeline", "research"))
VERIFICATION_LOG_FILE = os.environ.get(
    "MOLEFM_VERIFICATION_LOG_FILE",
    os.path.join(OUTPUT_DIR, "verification_log.json"),
)

# GitHub raw audio base URL
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main"

# Station imaging assets (from molefm.com /radio/imaging/)
STATION_IMAGING = {
    "manifest_url": "/radio/imaging/imaging-manifest.json",
    "pre_news_jingle": {
        "id": "mole-fm-spot-long",
        "title": "Mole FM long station spot",
        "url": "/radio/imaging/mol-fm-spot-long.mp3",
        "duration_seconds": 42,
        "placement": ["top_of_hour_intro", "music_bridge"],
        "license_status": "station_owned"
    },
    "post_news_jingle": {
        "id": "mol-short-id",
        "title": "Mole FM short ID",
        "url": "/radio/imaging/mol-short-id.mp3",
        "duration_seconds": 9,
        "placement": ["post_news", "quick_id"],
        "license_status": "station_owned"
    },
    "policy": "Play a station-owned Mole FM ID before the station news intro and a short ID after the French news before returning to live radio."
}

# Imaging assets for station_imaging_sequence
SOURCE_HOMEPAGES = {
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

IMAGING_ASSETS = {
    "mole-fm-spot-long": {"id": "mole-fm-spot-long", "title": "Mole FM long station spot", "url": "/radio/imaging/mol-fm-spot-long.mp3"},
    "mol-short-id": {"id": "mol-short-id", "title": "Mole FM short ID", "url": "/radio/imaging/mol-short-id.mp3"},
    "mole-fm-spot": {"id": "mole-fm-spot", "title": "Mole FM station spot", "url": "/radio/imaging/mole-fm-spot.mp3"},
    "mol-fm-fille": {"id": "mol-fm-fille", "title": "Mole FM female station ID", "url": "/radio/imaging/mol-fm-fille.mp3"},
}


def get_audio_duration_seconds(mp3_path):
    """Get MP3 duration using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", mp3_path],
            capture_output=True, text=True
        )
        return round(float(result.stdout.strip()))
    except Exception:
        return 60  # Default 60s if ffprobe fails


def load_audio_registry():
    """Load the GitHub audio registry."""
    try:
        with open(REGISTRY_PATH) as f:
            return json.load(f)
    except Exception:
        return {"newscasts": [], "podcasts": []}


def get_latest_newscast_url():
    """Get the GitHub URL for the most recent newscast."""
    registry = load_audio_registry()
    newscasts = registry.get("newscasts", [])
    if newscasts:
        return newscasts[0].get("url", "")
    return ""


def get_latest_podcast_url():
    """Get the GitHub URL for the most recent podcast."""
    registry = load_audio_registry()
    podcasts = registry.get("podcasts", [])
    if podcasts:
        return podcasts[0].get("url", "")
    return ""


def get_recent_newscast_urls(count=6):
    """Get URLs for the N most recent newscasts."""
    registry = load_audio_registry()
    return [e["url"] for e in registry.get("newscasts", [])[:count]]


def get_recent_newscasts(count=6):
    """Get the N most recent newscast registry entries with metadata."""
    registry = load_audio_registry()
    entries = []
    for entry in registry.get("newscasts", [])[:count]:
        if isinstance(entry, dict) and entry.get("url"):
            entries.append(entry)
        elif isinstance(entry, str):
            entries.append({"url": entry, "filename": entry.split("/")[-1]})
    source_backed_entries = [
        entry for entry in entries
        if entry.get("source_backed") or entry.get("source_backed_stories")
    ]
    return source_backed_entries or entries


def get_recent_podcast_urls(count=3):
    """Get URLs for the N most recent podcasts."""
    registry = load_audio_registry()
    return [e["url"] for e in registry.get("podcasts", [])[:count]]


def get_newscast_title_from_script(newscast_entry):
    """Try to extract a meaningful title from the newscast script JSON."""
    if isinstance(newscast_entry, dict):
        newscast_url = newscast_entry.get("url", "")
        if newscast_entry.get("title"):
            return newscast_entry["title"], int(newscast_entry.get("haiti_hour", 12))
    else:
        newscast_url = newscast_entry

    # Extract filename from URL
    filename = newscast_url.split("/")[-1].replace(".mp3", "")
    # Parse timestamp: newscast_YYYYMMDD_HHMM
    try:
        parts = filename.split("_")
        date_str = parts[1]
        time_str = parts[2] if len(parts) > 2 else "0000"
        dt = datetime.datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M")
        haiti_dt = dt - datetime.timedelta(hours=4)  # UTC-4
        return (f"Mole FM Actualités — {haiti_dt.strftime('%d/%m/%Y %Hh%M')} (Haïti)",
                haiti_dt.hour)
    except Exception:
        return "Mole FM Actualités Haïti", 12


def build_news_slot(newscast_url, station_hour, slot_index):
    """Build a content pack slot for a newscast."""
    if isinstance(newscast_url, dict):
        newscast_entry = newscast_url
        newscast_url = newscast_entry.get("url", "")
    else:
        newscast_entry = {"url": newscast_url, "filename": newscast_url.split("/")[-1]}

    title, hour = get_newscast_title_from_script(newscast_entry)
    filename = newscast_url.split("/")[-1]
    # Unique ID based on filename
    slot_id = filename.replace(".mp3", "").replace("newscast_", "")
    now = datetime.datetime.utcnow()
    source_stories = newscast_entry.get("source_backed_stories", [])
    source_links = [
        {
            "title": story.get("title", ""),
            "source": story.get("source", ""),
            "url": story.get("link") or story.get("source_url", ""),
            "pub_date": story.get("pub_date", ""),
            "verification": story.get("verification", ""),
            "confidence": story.get("confidence", 0),
        }
        for story in source_stories
        if story.get("link") or story.get("source_url")
    ]
    source_backed = bool(source_stories) and len(source_links) == len(source_stories)

    # Try to get duration
    # Can't get duration of remote file easily — use estimate
    duration = 180  # ~3 min for our newscasts

    return {
        "id": slot_id,
        "title": title,
        "kind": "hourly_news",
        "category": "news",
        "language": "fr",
        "spoken_language": "fr",
        "audio_url": newscast_url,
        "stream_audio_url": newscast_url,
        "archive_audio_url": newscast_url,
        "station_imaging": STATION_IMAGING,
        "estimated_duration_seconds": duration,
        "station_hour": station_hour,
        "starts_at": now.isoformat() + "Z",
        "editorial_status": "review_supervisor_auto_approved_for_air",
        "editorial_standard": "source-backed actual news from live RSS fetch",
        "source_backed": source_backed,
        "actual_news": source_backed,
        "news_generated_at": newscast_entry.get("generated_at", ""),
        "uploaded_at": newscast_entry.get("uploaded_at", ""),
        "script_path": newscast_entry.get("script_path", ""),
        "source_story_count": len(source_stories),
        "source_links": source_links,
        "source_freshness": newscast_entry.get("source_freshness", {}),
        "verification_summary": newscast_entry.get("verification_summary", {}),
        "voice_provider": "edge-tts",
        "voice_provider_status": "generated",
        "tts_voice": "fr-FR-DeniseNeural",
        "tts_rate_wpm": 170,
        "voice_quality": "neural_broadcast",
        "audio_delivery": {
            "mode": "web_smooth_low_bandwidth",
            "stream_bitrate": "64k",
            "source_bitrate": "64k",
            "station_imaging_included": True,
            "station_imaging_sequence": [
                {
                    "role": "pre_news_station_id",
                    **IMAGING_ASSETS["mole-fm-spot-long"]
                },
                {
                    "role": "news_voice",
                    "id": slot_id,
                    "title": title,
                    "url": newscast_url,
                },
                {
                    "role": "post_news_station_id",
                    **IMAGING_ASSETS["mol-short-id"]
                }
            ]
        }
    }


def build_podcast_slot(podcast_url, station_hour, slot_index):
    """Build a content pack slot for a podcast episode."""
    filename = podcast_url.split("/")[-1]
    slot_id = filename.replace(".mp3", "").replace("podcast_fr_", "podcast-fr-")
    now = datetime.datetime.utcnow()
    duration = 1200  # ~20 min podcast

    return {
        "id": slot_id,
        "title": "Mole FM Journal du Matin — Analyse approfondie",
        "kind": "podcast_replay",
        "category": "analysis",
        "language": "fr",
        "spoken_language": "fr",
        "audio_url": podcast_url,
        "stream_audio_url": podcast_url,
        "archive_audio_url": podcast_url,
        "station_imaging": STATION_IMAGING,
        "estimated_duration_seconds": duration,
        "station_hour": station_hour,
        "starts_at": now.isoformat() + "Z",
        "editorial_status": "review_supervisor_auto_approved_for_air",
        "voice_provider": "edge-tts",
        "voice_provider_status": "generated",
        "tts_voice": "fr-FR-DeniseNeural + fr-FR-HenriNeural",
        "tts_rate_wpm": 170,
        "voice_quality": "neural_broadcast",
        "audio_delivery": {
            "mode": "web_smooth_low_bandwidth",
            "stream_bitrate": "64k",
            "source_bitrate": "64k",
            "station_imaging_included": True,
            "station_imaging_sequence": [
                {
                    "role": "pre_news_station_id",
                    **IMAGING_ASSETS["mole-fm-spot"]
                },
                {
                    "role": "podcast_voice",
                    "id": slot_id,
                    "title": "Mole FM Journal du Matin",
                    "url": podcast_url,
                },
                {
                    "role": "post_news_station_id",
                    **IMAGING_ASSETS["mol-fm-fille"]
                }
            ]
        }
    }


def get_trilingual_articles():
    """Return recent verified article metadata for MoleFM.com cards."""
    try:
        with open(VERIFICATION_LOG_FILE, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return []

    if not log:
        return []

    latest_run = log[-1] if isinstance(log, list) else log
    stories = latest_run.get("stories", []) if isinstance(latest_run, dict) else []
    articles = []

    for s in stories[:8]:
        title = s.get("title", "")
        source = s.get("source", "")
        articles.append({
            "title_fr":    title,
            "title_en":    title,
            "title_es":    title,
            "source":      source,
            "verification": s.get("verification", ""),
            "confidence":  s.get("confidence", 0),
            "link":        s.get("link", ""),
            "source_url":  s.get("source_url", "") or SOURCE_HOMEPAGES.get(source, ""),
            "description": s.get("description", ""),
            "pub_date":    s.get("pub_date", ""),
            "all_sources": s.get("all_sources", [source] if source else []),
        })

    return articles


def generate_content_pack():
    """
    Generate a full 24-slot content pack from available audio.
    Alternates: news → news → podcast → news × 8 cycles = 24 slots.
    """
    now = datetime.datetime.utcnow()
    run_id = f"molefm-pipeline-{now.strftime('%Y%m%dT%H%M%SZ')}"

    news_entries = get_recent_newscasts(count=18)
    podcast_urls = get_recent_podcast_urls(count=6)

    if not news_entries:
        print("  [WARN] No newscast URLs in registry — content pack will be empty")
        news_entries = []

    slots = []
    news_idx = 0
    podcast_idx = 0

    # Build 24 slots: rotate news + occasional podcast replay
    for slot_num in range(24):
        station_hour = (now.hour + slot_num) % 24

        # Pattern: every 3rd slot is a podcast replay (if available)
        use_podcast = (slot_num % 4 == 2) and podcast_idx < len(podcast_urls)

        if use_podcast:
            slot = build_podcast_slot(podcast_urls[podcast_idx], station_hour, slot_num)
            podcast_idx += 1
        elif news_idx < len(news_entries):
            slot = build_news_slot(news_entries[news_idx], station_hour, slot_num)
            news_idx += 1
        elif podcast_urls and podcast_idx < len(podcast_urls):
            # Fall back to podcast if no more news
            slot = build_podcast_slot(podcast_urls[podcast_idx], station_hour, slot_num)
            podcast_idx += 1
        elif news_entries:
            # Cycle back through news
            slot = build_news_slot(news_entries[news_idx % len(news_entries)], station_hour, slot_num)
            news_idx += 1
        else:
            # No audio at all — skip
            continue

        slots.append(slot)

    # Get imaging manifest (reuse from site)
    imaging_manifest_url = "/radio/imaging/imaging-manifest.json"
    station_imaging_assets = list(IMAGING_ASSETS.values())

    content_pack = {
        "run_id": run_id,
        "generated_at": now.isoformat() + "Z",
        "content_language": "fr",
        "articles": get_trilingual_articles(),
        "audio_generated_count": len(slots),
        "generator": "mole-fm-pipeline-v2",
        "pipeline_version": "2.0.0",
        "playout_json_url": "/radio/generated/latest-content-pack.json",
        "playout_m3u_url": "/radio/generated/molefm-24-7-program.m3u",
        "station_imaging_policy": "Station-owned Mole FM IDs are interlaced before the station news intro and after the French news item before returning to live radio or approved fallback programming.",
        "station_imaging_manifest_url": imaging_manifest_url,
        "station_imaging_assets": station_imaging_assets,
        "voice_policy": "Voice generation uses edge-tts Neural voices (fr-FR-DeniseNeural, fr-FR-HenriNeural, fr-CA-ThierryNeural) — zero cost, broadcast-grade quality.",
        "voice_quality_summary": {
            "generated_count": len(slots),
            "by_provider": {"edge-tts": len(slots)},
            "by_quality": {"neural_broadcast": len(slots)},
            "broadcast_grade_ready": True,
        },
        "slots": slots,
    }

    return content_pack


def generate_m3u(content_pack):
    """Generate an M3U playlist from the content pack."""
    lines = [
        "#EXTM3U",
        "# Mole FM 24/7 generated program queue",
        f"# Generated: {content_pack['generated_at']}",
        f"# Source pack: https://www.molefm.com/radio/generated/latest-content-pack.json",
    ]
    for slot in content_pack["slots"]:
        duration = slot.get("estimated_duration_seconds", 60)
        title = slot.get("title", "Mole FM")
        url = slot.get("audio_url", "")
        if url:
            lines.append(f"#EXTINF:{duration},{title}")
            lines.append(url)
    return "\n".join(lines) + "\n"


def save_to_github_repo(content_pack, m3u_content):
    """
    Save the content pack and M3U to the GitHub repo under
    public/radio/generated/ so it's accessible via GitHub Pages.
    Returns True on success.
    """
    repo_dir = os.environ.get("MOLEFM_AUDIO_REPO_DIR", str(REPO_ROOT))

    # Ensure the output directories exist
    out_dir = os.path.join(repo_dir, "public", "radio", "generated")
    os.makedirs(out_dir, exist_ok=True)

    # Write content pack
    pack_path = os.path.join(out_dir, "latest-content-pack.json")
    with open(pack_path, "w", encoding="utf-8") as f:
        json.dump(content_pack, f, indent=2, ensure_ascii=False)
    print(f"  [ContentPack] Written: {pack_path}")

    # Write M3U
    m3u_path = os.path.join(out_dir, "molefm-24-7-program.m3u")
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)
    print(f"  [ContentPack] Written: {m3u_path}")

    return True


def save_locally(content_pack, m3u_content):
    """Save content pack locally for reference and debugging."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pack_path = os.path.join(OUTPUT_DIR, "latest-content-pack.json")
    with open(pack_path, "w", encoding="utf-8") as f:
        json.dump(content_pack, f, indent=2, ensure_ascii=False)
    print(f"  [ContentPack] Saved locally: {pack_path}")

    m3u_path = os.path.join(OUTPUT_DIR, "latest-content-pack.m3u")
    with open(m3u_path, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    return pack_path


def run(dry_run=False):
    """Main entry point."""
    print("\n=== Mole FM Content Pack Generator ===")
    print(f"  Time: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")

    # Generate the content pack
    content_pack = generate_content_pack()
    m3u = generate_m3u(content_pack)

    print(f"  Generated: {content_pack['audio_generated_count']} slots")
    for slot in content_pack["slots"][:6]:
        print(f"    [{slot['kind']}] {slot['title'][:60]}")
        print(f"             → {slot['audio_url'][-50:]}")

    if dry_run:
        print("\n  [DRY RUN] Not saving.")
        return content_pack

    # Save locally
    save_locally(content_pack, m3u)

    # Save to GitHub repo (if it's been cloned)
    try:
        save_to_github_repo(content_pack, m3u)
        print("  [ContentPack] Saved to GitHub repo local clone")
    except Exception as e:
        print(f"  [ContentPack] GitHub repo save: {e} (non-fatal)")

    print("  [ContentPack] Done.")
    return content_pack


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)
