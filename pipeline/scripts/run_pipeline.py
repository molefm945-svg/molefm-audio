"""
Mole FM Master Pipeline
Runs the full hourly broadcast pipeline:
1. Fetch latest Haiti news
2. Generate broadcast script
3. Convert to MP3 audio
4. Update M3U playlist
5. Optionally upload to AzuraCast streaming server

Run this script every hour via the scheduled task.
"""

import os
import sys
import json
import datetime
import glob

# Add scripts dir to path
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

from news_fetcher import run as fetch_news
from tts_generator import process_script, update_playlist

AUDIO_DIR = "/home/user/workspace/molefm/audio"
PLAYLISTS_DIR = "/home/user/workspace/molefm/playlists"
LOGS_DIR = "/home/user/workspace/molefm/logs"

# Set to True and configure below if you have AzuraCast
AZURACAST_ENABLED = False
AZURACAST_HOST = "https://your-azuracast-server.com"  # e.g. https://radio.molefm.com
AZURACAST_API_KEY = ""
AZURACAST_STATION_ID = "1"

# Live window: newscasts within this many hours stay in /audio/ (active playlist)
LIVE_WINDOW_HOURS = 24
ARCHIVE_DIR = "/home/user/workspace/molefm/audio/archive"


def cleanup_old_audio():
    """
    Move newscasts older than LIVE_WINDOW_HOURS to the archive.
    Files are NEVER deleted — they are preserved in /audio/archive/
    organised by date (YYYY-MM-DD/).
    Segment temp dirs are removed after 24h to save disk space.
    """
    import shutil
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=LIVE_WINDOW_HOURS)
    files = sorted(glob.glob(os.path.join(AUDIO_DIR, "newscast_*.mp3")))
    archived = 0
    for fpath in files:
        # Parse timestamp from filename: newscast_YYYYMMDD_HHMM.mp3
        fname = os.path.basename(fpath)
        try:
            ts_str = fname.replace("newscast_", "").replace(".mp3", "")
            file_dt = datetime.datetime.strptime(ts_str, "%Y%m%d_%H%M")
        except ValueError:
            continue
        if file_dt < cutoff:
            # Organise archive by date folder
            date_dir = os.path.join(ARCHIVE_DIR, file_dt.strftime("%Y-%m-%d"))
            os.makedirs(date_dir, exist_ok=True)
            dest = os.path.join(date_dir, fname)
            if not os.path.exists(dest):
                shutil.move(fpath, dest)
                print(f"  [ARCHIVE] {fname} → archive/{file_dt.strftime('%Y-%m-%d')}/")
                archived += 1
    if archived:
        print(f"  [ARCHIVE] {archived} files archived. Live window: last {LIVE_WINDOW_HOURS}h.")

    # Clean up segment temp dirs older than 24h (these are large and not needed)
    seg_dirs = sorted(glob.glob(os.path.join(AUDIO_DIR, "segments_*")))
    for d in seg_dirs:
        try:
            dname = os.path.basename(d)
            ts_str = dname.replace("segments_", "")
            seg_dt = datetime.datetime.strptime(ts_str, "%Y%m%d_%H%M")
            if seg_dt < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass


def upload_to_azuracast(audio_path):
    """Upload audio file to AzuraCast via REST API."""
    if not AZURACAST_ENABLED or not AZURACAST_API_KEY:
        return False
    
    import urllib.request
    import urllib.parse
    
    filename = os.path.basename(audio_path)
    url = f"{AZURACAST_HOST}/api/station/{AZURACAST_STATION_ID}/files"
    
    try:
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        
        boundary = "MoleFMBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: audio/mpeg\r\n\r\n"
        ).encode() + audio_data + f"\r\n--{boundary}--\r\n".encode()
        
        req = urllib.request.Request(
            url, data=body,
            headers={
                "X-API-Key": AZURACAST_API_KEY,
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"  [AZURACAST] Uploaded: {result.get('path', filename)}")
            return True
    except Exception as e:
        print(f"  [AZURACAST ERROR] {e}")
        return False


def log_run(status, audio_path=None, story_count=0):
    """Write a log entry for this pipeline run."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = os.path.join(LOGS_DIR, "pipeline.log")
    timestamp = datetime.datetime.now().isoformat()
    entry = {
        "timestamp": timestamp,
        "status": status,
        "audio_file": os.path.basename(audio_path) if audio_path else None,
        "stories_fetched": story_count
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def generate_24h_schedule():
    """Generate a daily M3U playlist with all available newscasts + filler content."""
    playlist_path = os.path.join(PLAYLISTS_DIR, "molefm_24h.m3u")
    audio_files = sorted(glob.glob(os.path.join(AUDIO_DIR, "newscast_*.mp3")))
    
    with open(playlist_path, "w") as f:
        f.write("#EXTM3U\n")
        f.write("#EXTINF:-1,Mole FM 24/7 News Radio\n")
        for af in audio_files:
            f.write(f"{af}\n")
    
    print(f"  [SCHEDULE] 24h playlist updated: {len(audio_files)} newscasts")
    return playlist_path


def run():
    print(f"\n{'='*50}")
    print(f"MOLE FM PIPELINE RUN — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(PLAYLISTS_DIR, exist_ok=True)
    
    # Step 1: Fetch news
    print("\n[1/4] Fetching Haiti news...")
    try:
        script_path, script_sections = fetch_news()
        # Count actual news stories: NEWS_MAIN contains "Titre N :" patterns
        news_main = next((s for s in script_sections if s["segment"] == "NEWS_MAIN"), None)
        if news_main:
            import re as _re
            story_count = len(_re.findall(r'Titre \d+', news_main.get("text", "")))
        else:
            story_count = 0
        # Fallback: if regex finds nothing, count NEWS-prefixed segments
        if story_count == 0:
            story_count = sum(1 for s in script_sections if s["segment"].startswith("NEWS"))
        print(f"  Stories: {story_count} verified stories in broadcast")
    except Exception as e:
        print(f"  [ERROR] News fetch failed: {e}")
        log_run("FAILED_FETCH")
        return

    # Step 2: Generate audio
    print("\n[2/4] Generating TTS audio...")
    try:
        audio_path = process_script(script_path)
        if not audio_path:
            raise Exception("Audio generation returned None")
        audio_size = os.path.getsize(audio_path)
        print(f"  Audio: {os.path.basename(audio_path)} ({audio_size//1024}KB)")
    except Exception as e:
        print(f"  [ERROR] TTS failed: {e}")
        log_run("FAILED_TTS")
        return

    # Step 3: Update playlists
    print("\n[3/4] Updating playlists...")
    update_playlist(audio_path)
    generate_24h_schedule()

    # Step 4: Upload to AzuraCast (if configured)
    print("\n[4/5] Streaming server upload...")
    if AZURACAST_ENABLED:
        upload_to_azuracast(audio_path)
    else:
        print("  [SKIP] AzuraCast not configured. Set AZURACAST_ENABLED=True and add credentials.")

    # Step 5: Rebuild reader webapp with fresh audio
    print("\n[5/5] Rebuilding reader webapp...")
    try:
        from build_reader import build as build_reader
        reader_path = build_reader(script_path, audio_path)
        if reader_path:
            print(f"  [OK] Reader rebuilt: {reader_path}")
        else:
            print("  [WARN] Reader build returned None")
    except Exception as e:
        print(f"  [WARN] Reader rebuild failed (non-fatal): {e}")
        import traceback; traceback.print_exc()

    # Cleanup old files
    cleanup_old_audio()

    # Step 6: Upload to GitHub + submit to molefm.com
    print("\n[6/6] Publishing to GitHub + molefm.com...")
    try:
        import subprocess as _sp
        import json as _json
        _script_stem = os.path.basename(script_path).replace('.json', '')
        _parts = _script_stem.split('_')  # ['newscast', 'YYYYMMDD', 'HHMM']
        _date_str = _parts[1] if len(_parts) > 1 else 'unknown'
        _time_str = _parts[2] if len(_parts) > 2 else '0000'
        _title = f"Mole FM Nouvèl — {_date_str[:4]}-{_date_str[4:6]}-{_date_str[6:]} {_time_str[:2]}h{_time_str[2:]} UTC"

        # Build env that carries git proxy credentials into the subprocess
        _git_env = os.environ.copy()
        _proxy_cfg = "/home/user/.gitconfig-proxy"
        if os.path.exists(_proxy_cfg):
            _git_env["GIT_CONFIG_GLOBAL"] = _proxy_cfg
            _git_env["GH_HOST"] = "git-agent-proxy.perplexity.ai"
        # GH_ENTERPRISE_TOKEN is already in os.environ when cron runs with github creds

        # Upload MP3 to GitHub
        _upload_result = _sp.run(
            ["python3", "/home/user/workspace/molefm/scripts/github_uploader.py",
             "newscast", audio_path],
            capture_output=True, text=True, env=_git_env
        )
        if _upload_result.returncode == 0:
            # Extract URL from last line of output
            _github_url = _upload_result.stdout.strip().splitlines()[-1].strip()
            print(f"  [GitHub] ✓ {_github_url}")

            # Submit URL to molefm.com
            _submit_result = _sp.run(
                ["python3", "/home/user/workspace/molefm/scripts/molefm_submitter.py",
                 "newscast", _github_url, _title],
                capture_output=True, text=True
            )
            print(_submit_result.stdout.strip())
            if _submit_result.returncode != 0:
                print(f"  [molefm.com] Non-fatal: {_submit_result.stderr.strip()[:200]}")
        else:
            print(f"  [GitHub] Upload failed (non-fatal): {_upload_result.stderr.strip()[:300]}")
    except Exception as _e:
        print(f"  [WARN] Publish step failed (non-fatal): {_e}")

    # Step 7: Generate molefm.com content pack (updates what the player reads)
    print("\n[7/7] Updating molefm.com content pack...")
    try:
        import sys as _sys
        _sys.path.insert(0, SCRIPTS_DIR)
        from content_pack_generator import run as generate_pack
        content_pack = generate_pack()
        if content_pack:
            print(f"  [ContentPack] ✓ {content_pack['audio_generated_count']} slots generated")
            # Also write to reader webapp so pplx CDN serves fresh content pack
            _reader_pack_dir = os.path.join(
                os.path.dirname(SCRIPTS_DIR), "reader", "webapp", "radio", "generated"
            )
            os.makedirs(_reader_pack_dir, exist_ok=True)
            _reader_pack_path = os.path.join(_reader_pack_dir, "latest-content-pack.json")
            import json as _json2
            with open(_reader_pack_path, "w", encoding="utf-8") as _f:
                _json2.dump(content_pack, _f, ensure_ascii=False, indent=2)
            print(f"  [ContentPack] Written to reader webapp (pplx CDN path)")
        else:
            print("  [ContentPack] Warn: returned None")
    except Exception as _e:
        print(f"  [WARN] Content pack generation failed (non-fatal): {_e}")

    # Step 8: Trigger broadcast interruption on the reader (seamless news → live resume)
    print("\n[8/8] Triggering broadcast automation (interrupt En Direct)...")
    try:
        import urllib.request as _urlreq, json as _bj
        # Use GitHub URL if available, otherwise fall back to local audio path
        try:
            _bc_github_url = _github_url
        except NameError:
            _bc_github_url = ""
        try:
            _bc_title = _title
        except NameError:
            _bc_title = "Journal de l'heure"
        # audioUrl must be non-empty; use GitHub URL or a placeholder that the
        # reader can ignore gracefully (local path signals server-side playback)
        _audio_url = _bc_github_url or f"local:{os.path.basename(audio_path)}"
        _bpayload = _bj.dumps({
            "type": "news",
            "audioUrl": _audio_url,
            "githubUrl": _bc_github_url,
            "title": _bc_title,
            "stories": story_count
        }).encode()
        _breq = _urlreq.Request(
            "http://localhost:5000/api/broadcast/trigger",
            data=_bpayload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with _urlreq.urlopen(_breq, timeout=3) as _br:
            _bres = _bj.loads(_br.read())
            print(f"  [Broadcast] ✓ triggered — id: {_bres.get('id','?')}")
    except Exception as _be:
        print(f"  [Broadcast] Non-fatal (server may not be running): {_be}")

    # Log success
    log_run("SUCCESS", audio_path, story_count)
    
    print(f"\n{'='*50}")
    print(f"PIPELINE COMPLETE")
    print(f"  Script:   {script_path}")
    print(f"  Audio:    {audio_path}")
    print(f"  Playlist: {os.path.join(PLAYLISTS_DIR, 'molefm_24h.m3u')}")
    print(f"  Stories:  {story_count} verified in broadcast")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    run()
