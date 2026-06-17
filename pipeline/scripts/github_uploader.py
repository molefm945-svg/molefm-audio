#!/usr/bin/env python3
"""
Mole FM — GitHub Audio Uploader
Pushes MP3 files to the molefm-audio GitHub repo as git objects.
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
import shutil
import subprocess
import datetime

REPO_URL = "https://git-agent-proxy.perplexity.ai/molefm945-svg/molefm-audio.git"
REPO_DIR = "/tmp/molefm-audio-repo"
GIT_USER_EMAIL = "molefm945@gmail.com"
GIT_USER_NAME = "Mole FM"
RAW_BASE = "https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main"


# Path to the git proxy config (written by pplx credential injector)
GIT_PROXY_CONFIG = "/home/user/.gitconfig-proxy"


def _git_env():
    """Build env dict with git credentials and author info."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = GIT_USER_NAME
    env["GIT_AUTHOR_EMAIL"] = GIT_USER_EMAIL
    env["GIT_COMMITTER_NAME"] = GIT_USER_NAME
    env["GIT_COMMITTER_EMAIL"] = GIT_USER_EMAIL
    # Always force the proxy gitconfig so the credential helper is available
    # (contains: credential helper using $GH_ENTERPRISE_TOKEN, and insteadOf rule)
    if os.path.exists(GIT_PROXY_CONFIG):
        env["GIT_CONFIG_GLOBAL"] = GIT_PROXY_CONFIG
        env["GH_HOST"] = "git-agent-proxy.perplexity.ai"
    # Propagate the enterprise token so the credential helper can read it
    token = os.environ.get("GH_ENTERPRISE_TOKEN", "")
    if token:
        env["GH_ENTERPRISE_TOKEN"] = token
    return env


def run_git(args, cwd=REPO_DIR, capture=True):
    """Run a git command in the repo directory."""
    env = _git_env()
    result = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=capture, text=True, env=env
    )
    if result.returncode != 0 and capture:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip() if capture else None


def _git_clone():
    """Clone using the git-agent-proxy URL (no gh CLI needed)."""
    result = subprocess.run(
        ["git", "clone", "--depth=1", REPO_URL, REPO_DIR],
        capture_output=True, text=True, env=_git_env()
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()[:400]}")


def _is_valid_git_repo(path):
    """Return True if path is a valid git repo (git rev-parse succeeds)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path, capture_output=True, text=True, env=_git_env()
        )
        return result.returncode == 0
    except Exception:
        return False


def ensure_repo():
    """Clone or pull the molefm-audio repo to /tmp."""
    git_dir = os.path.join(REPO_DIR, ".git")

    # Pre-flight: verify the repo is actually valid before attempting pull
    if os.path.exists(git_dir) and _is_valid_git_repo(REPO_DIR):
        # Valid repo — pull latest
        try:
            run_git(["pull", "origin", "main", "--rebase"])
        except Exception as e:  # broad catch: RuntimeError, FileNotFoundError, OSError, etc.
            # Pull failed for any reason — nuke and reclone
            print(f"  [GitHub] Pull failed ({e}), re-cloning...")
            shutil.rmtree(REPO_DIR, ignore_errors=True)
            _git_clone()
    else:
        # .git missing, invalid, or partial directory structure (e.g. from
        # content_pack_generator.py writing to /tmp/molefm-audio-repo/public/
        # before a clone happens) — remove everything and clone fresh
        if os.path.exists(REPO_DIR):
            print(f"  [GitHub] Stale or corrupt repo dir detected, removing...")
            shutil.rmtree(REPO_DIR, ignore_errors=True)
        _git_clone()

    # Always set git config after clone/pull
    run_git(["config", "user.email", GIT_USER_EMAIL])
    run_git(["config", "user.name", GIT_USER_NAME])
    # Ensure push remote is using the proxy URL
    run_git(["remote", "set-url", "origin", REPO_URL])


def upload_audio(audio_type, mp3_path):
    """
    Upload an MP3 to GitHub and return its permanent public URL.
    audio_type: 'newscast' or 'podcast'
    """
    if not os.path.exists(mp3_path):
        raise FileNotFoundError(f"MP3 not found: {mp3_path}")

    filename = os.path.basename(mp3_path)
    size_kb = os.path.getsize(mp3_path) // 1024

    # Determine subfolder
    subfolder = "audio" if audio_type == "newscast" else "podcasts"
    dest_dir = os.path.join(REPO_DIR, subfolder)
    dest_path = os.path.join(dest_dir, filename)

    print(f"  [GitHub] Syncing repo...")
    ensure_repo()

    os.makedirs(dest_dir, exist_ok=True)

    # Check if file already exists with same size (skip redundant push)
    if os.path.exists(dest_path) and os.path.getsize(dest_path) == os.path.getsize(mp3_path):
        print(f"  [GitHub] Already uploaded: {filename}")
        url = f"{RAW_BASE}/{subfolder}/{filename}"
        print(f"  [GitHub] ✓ URL: {url}")
        return url

    # Copy file into repo
    shutil.copy2(mp3_path, dest_path)

    # Commit and push
    run_git(["add", os.path.join(subfolder, filename)])

    # Check if there's anything to commit
    status = run_git(["status", "--porcelain"])
    if not status.strip():
        print(f"  [GitHub] No changes to commit (already up to date)")
    else:
        commit_msg = f"Add {audio_type}: {filename} ({size_kb}KB)"
        run_git(["commit", "-m", commit_msg])
        print(f"  [GitHub] Pushing {filename} ({size_kb} KB)...")
        run_git(["push", "origin", "main"])

    url = f"{RAW_BASE}/{subfolder}/{filename}"
    print(f"  [GitHub] ✓ URL: {url}")
    return url


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


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python github_uploader.py [newscast|podcast] /path/to/file.mp3")
        sys.exit(1)

    audio_type = sys.argv[1]
    mp3_path = sys.argv[2]

    if audio_type not in ("newscast", "podcast"):
        print(f"Unknown type: {audio_type}. Use 'newscast' or 'podcast'")
        sys.exit(1)

    url = upload_audio(audio_type, mp3_path)
    filename = os.path.basename(mp3_path)
    save_url_to_registry(audio_type, filename, url)
    print(f"  [Registry] Saved to audio_registry.json")
    # Print URL as final line (parsed by run_pipeline.py)
    print(url)
