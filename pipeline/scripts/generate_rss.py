#!/usr/bin/env python3
"""
Mole FM — Podcast RSS Feed Generator
Builds a standards-compliant RSS 2.0 + iTunes feed from the GitHub audio archive.
Output: feed.xml (served via GitHub Pages at https://molefm945-svg.github.io/molefm-audio/feed.xml)

This feed is submitted to:
- Spotify for Podcasters: https://podcasters.spotify.com
- Apple Podcasts: https://podcastsconnect.apple.com
- Google Podcasts / YouTube Music
- Pocket Casts, Overcast, etc.

Run: python3 generate_rss.py
"""

import os
import json
import datetime
import subprocess
import glob
from email.utils import formatdate
import time

# === CONFIG ===
REPO = "molefm945-svg/molefm-audio"
GITHUB_RAW = "https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main"
GITHUB_PAGES = "https://molefm945-svg.github.io/molefm-audio"
FEED_URL = f"{GITHUB_PAGES}/feed.xml"
PODCAST_DIR = "/home/user/workspace/molefm/audio/podcasts"
REGISTRY_PATH = "/home/user/workspace/molefm/config/audio_registry.json"
OUTPUT_PATH = "/tmp/molefm-audio-repo/feed.xml"

SHOW = {
    "title": "Mole FM 94.5 — Nouvèl Ayiti",
    "description": (
        "Le podcast quotidien de référence sur l'actualité haïtienne pour la diaspora. "
        "Analyses approfondies, nouvelles vérifiées, voix de Haïti. "
        "Format The Daily × BBC Global News — en français. "
        "Mole FM 94.5, Môle-Saint-Nicolas, Haïti."
    ),
    "author": "Mole FM 94.5",
    "email": "molefm945@gmail.com",
    "website": "https://www.molefm.com",
    "language": "fr",
    "category": "News",
    "subcategory": "Daily News",
    "explicit": "false",
    "image": f"{GITHUB_PAGES}/cover.jpg",
    "copyright": f"© {datetime.datetime.now().year} Mole FM 94.5",
}


def get_mp3_duration_seconds(path):
    """Get MP3 duration using mutagen or ffprobe."""
    try:
        from mutagen.mp3 import MP3
        audio = MP3(path)
        return int(audio.info.length)
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        return int(float(data["format"]["duration"]))
    except Exception:
        return 1140  # default 19 min


def format_duration(seconds):
    """Format seconds as HH:MM:SS for iTunes."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_pubdate(filename):
    """
    Parse pubDate from filename like podcast_fr_20260616_2048.mp3
    Returns RFC 2822 date string.
    """
    try:
        parts = filename.replace(".mp3", "").split("_")
        # podcast_fr_YYYYMMDD_HHMM
        date_str = parts[-2]  # YYYYMMDD
        time_str = parts[-1]  # HHMM
        dt = datetime.datetime(
            int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]),
            int(time_str[:2]), int(time_str[2:4]),
            tzinfo=datetime.timezone(datetime.timedelta(hours=-4))  # Haiti UTC-4
        )
        return formatdate(dt.timestamp())
    except Exception:
        return formatdate(time.time())


def slot_label_from_filename(filename):
    """Map time to slot label."""
    try:
        time_str = filename.replace(".mp3", "").split("_")[-1]
        hour = int(time_str[:2])
        # Haiti time (UTC-4): UTC 01 = 21h Haiti, UTC 16 = 12h Haiti, UTC 19 = 15h Haiti
        if hour == 1 or (20 <= hour <= 22):
            return "Soir"
        elif hour == 16 or (11 <= hour <= 13):
            return "Midi"
        elif hour == 19 or (14 <= hour <= 16):
            return "Après-midi"
        else:
            return "Édition spéciale"
    except Exception:
        return "Édition"


def build_episode_item(filename, url, file_size_bytes, duration_seconds, pubdate):
    """Build an RSS <item> block for one episode."""
    slug = filename.replace(".mp3", "").replace("_", "-")
    slot = slot_label_from_filename(filename)

    # Parse date for title
    try:
        parts = filename.replace(".mp3", "").split("_")
        date_str = parts[-2]
        day = date_str[6:8]
        month_names = ["", "janvier", "février", "mars", "avril", "mai", "juin",
                       "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        month = month_names[int(date_str[4:6])]
        year = date_str[:4]
        date_display = f"{int(day)} {month} {year}"
    except Exception:
        date_display = "2026"

    title = f"Mole FM — {slot} — {date_display}"
    description = (
        f"Émission quotidienne Mole FM 94.5 — {date_display}. "
        f"Analyse approfondie des actualités d'Haïti avec Denise et Henri. "
        f"Nouvelles vérifiées, météo, sports. "
        f"Format The Daily × BBC Global News × Hugo Décrypte. "
        f"Durée : {format_duration(duration_seconds)}."
    )
    dur_fmt = format_duration(duration_seconds)

    return f"""    <item>
      <title>{title}</title>
      <description><![CDATA[{description}]]></description>
      <link>{SHOW['website']}/podcasts</link>
      <guid isPermaLink="false">molefm-{slug}</guid>
      <pubDate>{pubdate}</pubDate>
      <enclosure url="{url}" length="{file_size_bytes}" type="audio/mpeg"/>
      <itunes:title>{title}</itunes:title>
      <itunes:summary><![CDATA[{description}]]></itunes:summary>
      <itunes:duration>{dur_fmt}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
    </item>"""


def generate_feed():
    """Build the complete RSS feed XML."""
    print("  [RSS] Scanning podcast archive...")

    # Collect all podcasts from the local archive
    podcast_files = sorted(
        glob.glob(os.path.join(PODCAST_DIR, "podcast_fr_*.mp3")),
        reverse=True  # newest first
    )

    # Also check registry for any uploaded ones
    registry_podcasts = []
    try:
        with open(REGISTRY_PATH) as f:
            registry = json.load(f)
            registry_podcasts = registry.get("podcasts", [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Build registry lookup: filename -> url
    registry_lookup = {e["filename"]: e["url"] for e in registry_podcasts}

    items = []
    for mp3_path in podcast_files[:30]:  # max 30 episodes in feed
        filename = os.path.basename(mp3_path)

        # Get public URL (from registry or construct from GitHub raw)
        url = registry_lookup.get(filename,
              f"{GITHUB_RAW}/podcasts/{filename}")

        # File metadata
        file_size = os.path.getsize(mp3_path)
        duration = get_mp3_duration_seconds(mp3_path)
        pubdate = format_pubdate(filename)

        item = build_episode_item(filename, url, file_size, duration, pubdate)
        items.append(item)
        print(f"  [RSS] + {filename} ({duration//60}m{duration%60:02d}s)")

    if not items:
        print("  [RSS] No podcast files found — feed will be empty")

    now_rfc = formatdate(time.time())
    items_xml = "\n".join(items)

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{SHOW['title']}</title>
    <link>{SHOW['website']}</link>
    <language>{SHOW['language']}</language>
    <copyright>{SHOW['copyright']}</copyright>
    <description><![CDATA[{SHOW['description']}]]></description>
    <lastBuildDate>{now_rfc}</lastBuildDate>
    <atom:link href="{FEED_URL}" rel="self" type="application/rss+xml"/>

    <itunes:author>{SHOW['author']}</itunes:author>
    <itunes:owner>
      <itunes:name>{SHOW['author']}</itunes:name>
      <itunes:email>{SHOW['email']}</itunes:email>
    </itunes:owner>
    <itunes:image href="{SHOW['image']}"/>
    <itunes:category text="{SHOW['category']}">
      <itunes:category text="{SHOW['subcategory']}"/>
    </itunes:category>
    <itunes:explicit>{SHOW['explicit']}</itunes:explicit>
    <itunes:summary><![CDATA[{SHOW['description']}]]></itunes:summary>
    <itunes:type>episodic</itunes:type>

{items_xml}
  </channel>
</rss>"""

    return feed, len(items)


def save_and_push_feed(feed_xml):
    """Save feed.xml to the GitHub repo and push."""
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(feed_xml)

    print(f"  [RSS] feed.xml written ({len(feed_xml)//1024}KB)")

    # Push to GitHub
    repo_dir = "/tmp/molefm-audio-repo"
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_NAME": "Mole FM", "GIT_AUTHOR_EMAIL": "molefm945@gmail.com",
                "GIT_COMMITTER_NAME": "Mole FM", "GIT_COMMITTER_EMAIL": "molefm945@gmail.com"})

    subprocess.run(["git", "add", "feed.xml"], cwd=repo_dir, env=env, check=True)

    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_dir,
                           capture_output=True, text=True, env=env).stdout.strip()
    if status:
        subprocess.run(["git", "commit", "-m", "Update: podcast RSS feed"], cwd=repo_dir,
                      env=env, check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", "main"], cwd=repo_dir,
                      env=env, check=True, capture_output=True)
        print("  [RSS] ✓ feed.xml pushed to GitHub")
    else:
        print("  [RSS] feed.xml unchanged — no push needed")

    return f"{GITHUB_PAGES}/feed.xml"


if __name__ == "__main__":
    print("\n=== Mole FM RSS Feed Generator ===")
    feed_xml, episode_count = generate_feed()
    feed_url = save_and_push_feed(feed_xml)
    print(f"\n  ✓ Feed ready: {feed_url}")
    print(f"  ✓ Episodes: {episode_count}")
    print(f"\n  Submit to Spotify: https://podcasters.spotify.com/pod/show/submit")
    print(f"  Submit to Apple:   https://podcastsconnect.apple.com")
    print(f"  Feed URL to paste: {feed_url}")
