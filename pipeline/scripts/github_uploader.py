#!/usr/bin/env python3
"""
Mole FM — GitHub Audio Uploader (API-based, no git clone)
Uploads MP3 files to molefm-audio via GitHub Contents API.
Returns a permanent public raw.githubusercontent.com URL.

URL format:
  https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main/audio/<filename>
  https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main/podcasts/<filename>

Usage:
  python github_uploader.py newscast /path/to/newscast_20260617_0800.mp3
  python github_uploader.py podcast  /path/to/podcast_fr_20260617_1200.mp3
"""

import os
import sys
import json
import base64
import datetime
import urllib.request
import urllib.error

OWNER      = "molefm945-svg"
REPO       = "molefm-audio"
BRANCH     = "main"
RAW_BASE   = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}"
# Use the git-agent-proxy for API calls (token is a proxy token, not a raw GitHub PAT)
API_HOST   = "https://git-agent-proxy.perplexity.ai/api/v3"
API_BASE   = f"{API_HOST}/repos/{OWNER}/{REPO}/contents"


def _token():
    """Return GitHub token from environment (injected by api_credentials)."""
    tok = os.environ.get("GH_ENTERPRISE_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
    if not tok:
        raise RuntimeError(
            "No GitHub token found. Run with api_credentials=['github'] or set GH_ENTERPRISE_TOKEN."
        )
    return tok


def _api_headers():
    return {
        "Authorization": f"token {_token()}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_file_sha(path_in_repo):
    """Return the blob SHA of an existing file, or None if it doesn't exist."""
    url = f"{API_BASE}/{path_in_repo}?ref={BRANCH}"
    req = urllib.request.Request(url, headers=_api_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
            return data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def upload_file_api(path_in_repo, mp3_path, commit_msg):
    """
    Upload or update a file in the GitHub repo using the Contents API.
    Returns the raw URL.
    """
    with open(mp3_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    sha = _get_file_sha(path_in_repo)  # None if new file, string if update

    payload = {
        "message": commit_msg,
        "content": content_b64,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha  # required for updates

    url = f"{API_BASE}/{path_in_repo}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_api_headers(), method="PUT")

    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.loads(r.read())
        return resp["content"]["download_url"]


def upload_audio(audio_type, mp3_path):
    """
    Upload an MP3 to GitHub and return its permanent public URL.
    audio_type: 'newscast' or 'podcast'
    """
    if not os.path.exists(mp3_path):
        raise FileNotFoundError(f"MP3 not found: {mp3_path}")

    filename  = os.path.basename(mp3_path)
    size_kb   = os.path.getsize(mp3_path) // 1024
    subfolder = "audio" if audio_type == "newscast" else "podcasts"
    path_in_repo = f"{subfolder}/{filename}"

    print(f"  [GitHub API] Checking {path_in_repo}...")
    sha = _get_file_sha(path_in_repo)

    if sha:
        # File already exists — check local size vs remote size to skip if identical
        # (GitHub API doesn't give size easily without another call; just re-upload to be safe
        #  unless the filename already exists — same filename = same content for Mole FM)
        raw_url = f"{RAW_BASE}/{subfolder}/{filename}"
        print(f"  [GitHub API] Already uploaded: {filename}")
        print(f"  [GitHub API] ✓ URL: {raw_url}")
        return raw_url

    print(f"  [GitHub API] Uploading {filename} ({size_kb} KB)...")
    commit_msg = f"Add {audio_type}: {filename} ({size_kb}KB)"
    raw_url = upload_file_api(path_in_repo, mp3_path, commit_msg)

    print(f"  [GitHub API] ✓ Uploaded → {raw_url}")
    return raw_url


def save_url_to_registry(audio_type, filename, url):
    """Save the public URL to a local registry for molefm.com submission."""
    registry_path = "/home/user/workspace/molefm/config/audio_registry.json"
    try:
        with open(registry_path) as f:
            registry = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        registry = {"newscasts": [], "podcasts": []}

    entry = {
        "filename": filename,
        "url": url,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    key = "newscasts" if audio_type == "newscast" else "podcasts"
    registry[key] = [e for e in registry[key] if e["filename"] != filename]
    registry[key].insert(0, entry)
    registry[key] = registry[key][:50]

    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def update_github_registry(audio_type, url):
    """
    Update the public registry.json on GitHub so the reader can detect new broadcasts.
    registry.json: {"latest_newscast": "...", "latest_podcast": "...", "updated_at": "..."}
    """
    import base64 as _b64
    try:
        # Fetch current registry from GitHub
        reg_path = "registry.json"
        sha = _get_file_sha(reg_path)
        if sha:
            reg_url = f"{API_BASE}/{reg_path}?ref={BRANCH}"
            req = urllib.request.Request(reg_url, headers=_api_headers())
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
                current = json.loads(
                    _b64.b64decode(data["content"].replace("\n", "")).decode()
                )
        else:
            current = {}

        field = "latest_newscast" if audio_type == "newscast" else "latest_podcast"
        current[field] = url
        current["updated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")

        content_b64 = _b64.b64encode(
            json.dumps(current, indent=2).encode()
        ).decode()
        payload = {
            "message": f"update: registry.json — {field}",
            "content": content_b64,
            "branch": BRANCH,
        }
        if sha:
            payload["sha"] = sha

        put_url = f"{API_BASE}/{reg_path}"
        req2 = urllib.request.Request(
            put_url,
            data=json.dumps(payload).encode(),
            headers=_api_headers(),
            method="PUT",
        )
        with urllib.request.urlopen(req2, timeout=30) as r:
            pass
        print(f"  [GitHub Registry] \u2713 updated {field}")
    except Exception as e:
        print(f"  [GitHub Registry] non-fatal: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python github_uploader.py [newscast|podcast] /path/to/file.mp3")
        sys.exit(1)

    audio_type = sys.argv[1]
    mp3_path   = sys.argv[2]

    if audio_type not in ("newscast", "podcast"):
        print(f"Unknown type: {audio_type}. Use 'newscast' or 'podcast'")
        sys.exit(1)

    url = upload_audio(audio_type, mp3_path)
    filename = os.path.basename(mp3_path)
    save_url_to_registry(audio_type, filename, url)
    print(f"  [Registry] Saved to audio_registry.json")
    update_github_registry(audio_type, url)
    # Print URL as final line (parsed by run_pipeline.py)
    print(url)
