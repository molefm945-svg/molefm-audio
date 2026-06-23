#!/usr/bin/env python3
"""
Mole FM hourly source-backed news worker.

This script is the CI-safe entry point for producing the actual top-of-hour
French news bulletin. It fetches live RSS stories, requires source attribution,
generates a natural edge-tts MP3, updates the public registry, and rebuilds the
24-hour content pack that molefm.com reads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = REPO_ROOT / "pipeline"
RUNTIME_DIR = PIPELINE_DIR / "runtime"
SCRIPTS_DIR = RUNTIME_DIR / "scripts"
RESEARCH_DIR = PIPELINE_DIR / "research"
CONFIG_DIR = PIPELINE_DIR / "config"
AUDIO_DIR = REPO_ROOT / "audio"
PLAYLISTS_DIR = REPO_ROOT / "playlists"
PUBLIC_GENERATED_DIR = REPO_ROOT / "public" / "radio" / "generated"
REGISTRY_PATH = CONFIG_DIR / "audio_registry.json"
ROOT_REGISTRY_PATH = REPO_ROOT / "registry.json"
RAW_BASE = "https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main"
HAITI_TZ = dt.timezone(dt.timedelta(hours=-4), name="HT")


def configure_runtime_paths() -> None:
    os.environ.setdefault("TZ", "UTC")
    if hasattr(time, "tzset"):
        time.tzset()

    os.environ.setdefault("MOLEFM_WORKSPACE", str(REPO_ROOT))
    os.environ.setdefault("MOLEFM_NEWS_SCRIPTS_DIR", str(SCRIPTS_DIR))
    os.environ.setdefault("MOLEFM_SEEN_TITLES_FILE", str(RUNTIME_DIR / "seen_titles.json"))
    os.environ.setdefault(
        "MOLEFM_AUTOSEARCH_SOURCES_FILE",
        str(RUNTIME_DIR / "autosearch_sources.json"),
    )
    os.environ.setdefault("MOLEFM_VERIFICATION_LOG_FILE", str(RESEARCH_DIR / "verification_log.json"))
    os.environ.setdefault("MOLEFM_AUDIO_DIR", str(AUDIO_DIR))
    os.environ.setdefault("MOLEFM_PLAYLISTS_DIR", str(PLAYLISTS_DIR))
    os.environ.setdefault("MOLEFM_CONFIG_DIR", str(CONFIG_DIR))
    os.environ.setdefault("MOLEFM_OUTPUT_DIR", str(RESEARCH_DIR))
    os.environ.setdefault("MOLEFM_AUDIO_REPO_DIR", str(REPO_ROOT))

    for path in (SCRIPTS_DIR, RESEARCH_DIR, AUDIO_DIR, PLAYLISTS_DIR, PUBLIC_GENERATED_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parse_script_datetime(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except Exception:
        parsed = dt.datetime.now(dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_pub_date(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def story_link(story: dict[str, Any]) -> str:
    return str(story.get("link") or story.get("source_url") or "").strip()


def validate_source_backing(
    script: dict[str, Any],
    *,
    min_stories: int,
    min_fresh_stories: int,
    max_source_age_hours: float,
) -> dict[str, Any]:
    stories = script.get("source_backed_stories") or []
    if len(stories) < min_stories:
        raise RuntimeError(
            f"Only {len(stories)} source-backed stories found; need at least {min_stories}."
        )

    missing_links = [story.get("title", "") for story in stories if not story_link(story)]
    if missing_links:
        raise RuntimeError(
            "Source-backed validation failed: at least one selected story has no link/source_url."
        )

    news_main = " ".join(
        segment.get("text", "")
        for segment in script.get("segments", [])
        if segment.get("segment") == "NEWS_MAIN"
    )
    if "Nous n'avons pas de nouvelles récentes" in news_main:
        raise RuntimeError("Refusing to publish placeholder news as a live hourly bulletin.")

    now_utc = dt.datetime.now(dt.timezone.utc)
    dated_stories = []
    fresh_stories = []
    for story in stories:
        pub_dt = parse_pub_date(str(story.get("pub_date", "")))
        if not pub_dt:
            continue
        age_hours = max(0.0, (now_utc - pub_dt).total_seconds() / 3600)
        dated_stories.append({**story, "_age_hours": round(age_hours, 2)})
        if age_hours <= max_source_age_hours:
            fresh_stories.append({**story, "_age_hours": round(age_hours, 2)})

    if len(fresh_stories) < min_fresh_stories:
        raise RuntimeError(
            f"Only {len(fresh_stories)} fresh dated source stories found; "
            f"need at least {min_fresh_stories} within {max_source_age_hours:g}h."
        )

    return {
        "source_backed": True,
        "story_count": len(stories),
        "dated_story_count": len(dated_stories),
        "fresh_story_count": len(fresh_stories),
        "max_source_age_hours": max_source_age_hours,
        "freshest_story_pub_date": fresh_stories[0].get("pub_date", "") if fresh_stories else "",
        "oldest_selected_age_hours": max(
            (story["_age_hours"] for story in dated_stories),
            default=None,
        ),
    }


def verify_mp3(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"MP3 was not generated: {path}")
    size = path.stat().st_size
    if size < 50_000:
        raise RuntimeError(f"Generated MP3 is too small to be a real bulletin: {size} bytes.")
    with path.open("rb") as handle:
        header = handle.read(3)
    valid_header = header == b"ID3" or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0)
    if not valid_header:
        raise RuntimeError(f"Generated MP3 has an invalid header: {path}")
    return {"path": str(path), "size_bytes": size}


def update_audio_registry(
    *,
    script: dict[str, Any],
    script_path: Path,
    audio_path: Path,
    source_freshness: dict[str, Any],
) -> dict[str, Any]:
    registry = load_json(REGISTRY_PATH, {"newscasts": [], "podcasts": []})
    generated_at = parse_script_datetime(str(script.get("generated_at", "")))
    haiti_dt = generated_at.astimezone(HAITI_TZ)
    filename = audio_path.name
    raw_url = f"{RAW_BASE}/audio/{filename}"
    stories = script.get("source_backed_stories") or []
    title = f"Mole FM Actualités — {haiti_dt.strftime('%d/%m/%Y %Hh%M')} (Haïti)"

    entry = {
        "filename": filename,
        "url": raw_url,
        "title": title,
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "uploaded_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "haiti_hour": haiti_dt.hour,
        "language": "fr",
        "source_backed": True,
        "source_backed_stories": stories,
        "source_story_count": len(stories),
        "source_freshness": source_freshness,
        "script_path": str(script_path.relative_to(REPO_ROOT)),
        "voice_provider": "edge-tts",
        "tts_voices": [
            "fr-CA-ThierryNeural",
            "fr-FR-DeniseNeural",
            "fr-FR-HenriNeural",
            "fr-CA-SylvieNeural",
        ],
        "verification_summary": {
            "confirmed": sum(1 for story in stories if "CONFIRMED" in story.get("verification", "")),
            "single_source": sum(1 for story in stories if story.get("verification") == "SINGLE-SOURCE"),
            "all_story_links_present": all(bool(story_link(story)) for story in stories),
        },
    }

    newscasts = [
        item for item in registry.get("newscasts", [])
        if not isinstance(item, dict) or item.get("filename") != filename
    ]
    newscasts.insert(0, entry)
    registry["newscasts"] = newscasts[:72]
    registry.setdefault("podcasts", [])
    write_json(REGISTRY_PATH, registry)

    root_registry = load_json(ROOT_REGISTRY_PATH, {})
    root_registry["latest_newscast"] = raw_url
    root_registry["latest_source_backed_newscast"] = raw_url
    root_registry["updated_at"] = entry["uploaded_at"]
    root_registry["source_backed"] = True
    root_registry["source_story_count"] = len(stories)
    write_json(ROOT_REGISTRY_PATH, root_registry)
    return entry


def validate_content_pack(pack: dict[str, Any]) -> dict[str, Any]:
    slots = pack.get("slots", [])
    if len(slots) != 24:
        raise RuntimeError(f"Content pack must contain 24 slots; found {len(slots)}.")
    news_slots = [slot for slot in slots if slot.get("kind") == "hourly_news"]
    if not news_slots:
        raise RuntimeError("Content pack has no hourly_news slots.")
    unbacked = [slot.get("id", "") for slot in news_slots if not slot.get("source_backed")]
    if unbacked:
        raise RuntimeError(
            "Content pack contains hourly_news slots without source-backed metadata: "
            + ", ".join(unbacked[:5])
        )
    return {
        "slot_count": len(slots),
        "hourly_news_slots": len(news_slots),
        "source_backed_news_slots": len(news_slots) - len(unbacked),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    configure_runtime_paths()
    sys.path.insert(0, str(REPO_ROOT / "pipeline" / "scripts"))

    from news_fetcher import looks_like_english_headline, run as fetch_news
    from tts_generator import process_script, update_playlist
    from content_pack_generator import run as generate_content_pack

    script_path_raw, _segments = fetch_news()
    script_path = Path(script_path_raw)
    script = load_json(script_path, {})
    english_titles = [
        story.get("title", "")
        for story in script.get("source_backed_stories", [])
        if looks_like_english_headline(str(story.get("title", "")))
    ]
    if english_titles:
        raise RuntimeError(
            "Refusing to publish non-French source headlines in the hourly bulletin: "
            + "; ".join(english_titles[:3])
        )
    non_french_sources = [
        story.get("title", "")
        for story in script.get("source_backed_stories", [])
        if story.get("source_lang", "fr") != "fr"
    ]
    if non_french_sources:
        raise RuntimeError(
            "Refusing to publish non-French source feeds in the hourly bulletin: "
            + "; ".join(non_french_sources[:3])
        )
    source_freshness = validate_source_backing(
        script,
        min_stories=args.min_stories,
        min_fresh_stories=args.min_fresh_stories,
        max_source_age_hours=args.max_source_age_hours,
    )

    audio_path = Path(process_script(str(script_path)))
    audio_health = verify_mp3(audio_path)
    update_playlist(str(audio_path))

    registry_entry = update_audio_registry(
        script=script,
        script_path=script_path,
        audio_path=audio_path,
        source_freshness=source_freshness,
    )
    content_pack = generate_content_pack(dry_run=False)
    pack_health = validate_content_pack(content_pack)

    result = {
        "status": "ok",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "script": str(script_path.relative_to(REPO_ROOT)),
        "audio": str(audio_path.relative_to(REPO_ROOT)),
        "audio_url": registry_entry["url"],
        "registry_entry": registry_entry,
        "source_freshness": source_freshness,
        "audio_health": audio_health,
        "content_pack": pack_health,
    }
    write_json(RESEARCH_DIR / "hourly_news_worker_last_run.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Mole FM source-backed hourly news MP3.")
    parser.add_argument("--min-stories", type=int, default=3)
    parser.add_argument("--min-fresh-stories", type=int, default=1)
    parser.add_argument("--max-source-age-hours", type=float, default=48)
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
