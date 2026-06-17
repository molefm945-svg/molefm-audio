"""
Mole FM TTS Audio Generator — French Edition
Uses Microsoft Neural voices via edge-tts (FREE, no API key).
All content is in French, with voices chosen for broadcast character.

Voice map:
  STATION_ID  → fr-CA-ThierryNeural    Warm French-Canadian male
  INTRO       → fr-FR-DeniseNeural     Professional French female
  NEWS_MAIN   → fr-FR-DeniseNeural     Professional French female
  SPORTS      → fr-FR-HenriNeural      Energetic French male
  SIGN_OFF    → fr-CA-SylvieNeural     Warm French-Canadian female
  default     → fr-FR-DeniseNeural
"""

import json
import os
import glob
import asyncio
import datetime
import subprocess
import time
import edge_tts

SCRIPTS_DIR  = "/home/user/workspace/molefm/scripts"
AUDIO_DIR    = "/home/user/workspace/molefm/audio"
PLAYLISTS_DIR = "/home/user/workspace/molefm/playlists"

# ── Voice assignments ────────────────────────────────────────────────────────
VOICE_MAP = {
    "STATION_ID": "fr-CA-ThierryNeural",   # Warm male open
    "SPONSOR":    "fr-FR-DeniseNeural",    # Sponsor read — clear female
    "INTRO":      "fr-FR-DeniseNeural",    # Professional female intro
    "NEWS_MAIN":  "fr-FR-DeniseNeural",    # Main news — clear, authoritative
    "SPORTS":     "fr-FR-HenriNeural",     # Sports — energetic male
    "WEATHER":    "fr-FR-DeniseNeural",    # Weather — clear French female
    "SIGN_OFF":   "fr-CA-SylvieNeural",    # Warm female close
    "default":    "fr-FR-DeniseNeural",
}

# ── Speaking rate per segment ────────────────────────────────────────────────
RATE_MAP = {
    "STATION_ID": "-15%",   # Slower, punchy ID
    "SPONSOR":    "-8%",    # Measured sponsor read
    "INTRO":      "-5%",    # Slightly measured intro
    "NEWS_MAIN":  "+0%",    # Normal broadcast pace
    "SPORTS":     "+5%",    # Slightly faster for energy
    "WEATHER":    "-5%",    # Measured pace for clarity
    "SIGN_OFF":   "-15%",   # Slow warm close
    "default":    "+0%",
}

# ── Volume per segment ───────────────────────────────────────────────────────
VOLUME_MAP = {
    "STATION_ID": "+10%",
    "SIGN_OFF":   "-5%",
    "default":    "+0%",
}


async def synth_async(text, voice, rate, volume, output_path):
    """Async edge-tts synthesis."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    await communicate.save(output_path)
    size = os.path.getsize(output_path)
    print(f"    [OK] {os.path.basename(output_path)} — {voice} ({size//1024} KB)")


def synth(text, segment_name, output_path, max_retries=4):
    """Synthesize one segment to MP3 with exponential-backoff retry.
    edge-tts can return transient 503 / WebSocket errors — retry up to 4x
    with 2s, 4s, 8s, 16s delays before giving up.
    """
    voice  = VOICE_MAP.get(segment_name,  VOICE_MAP["default"])
    rate   = RATE_MAP.get(segment_name,   RATE_MAP["default"])
    volume = VOLUME_MAP.get(segment_name, VOLUME_MAP["default"])

    for attempt in range(1, max_retries + 1):
        try:
            asyncio.run(synth_async(text, voice, rate, volume, output_path))
            return True
        except Exception as e:
            err_str = str(e)
            is_transient = any(x in err_str for x in ["503", "502", "500", "429",
                                                        "ConnectionError", "TimeoutError",
                                                        "Invalid response", "WebSocket",
                                                        "wss://", "Connection"])
            if is_transient and attempt < max_retries:
                wait = 2 ** attempt  # 2, 4, 8, 16 seconds
                print(f"    [RETRY {attempt}/{max_retries}] {segment_name}: {e} — retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"    [ERROR] {segment_name}: {e}")
                return False

    return False


def add_silence(ms, output_path):
    """Generate silence with ffmpeg."""
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(ms / 1000),
        "-acodec", "libmp3lame", "-b:a", "64k",
        output_path
    ], capture_output=True)


def concat_mp3s(files, output_path):
    """Concatenate MP3 list into a single file using ffmpeg."""
    list_file = output_path.replace(".mp3", "_list.txt")
    with open(list_file, "w") as f:
        for fp in files:
            f.write(f"file '{fp}'\n")

    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-acodec", "libmp3lame", "-b:a", "128k",
        "-ar", "44100",
        "-metadata", "title=Mole FM — Journal",
        "-metadata", "artist=Mole FM Radio",
        "-metadata", "language=French",
        output_path
    ], capture_output=True, text=True)

    os.remove(list_file)

    if result.returncode == 0:
        size = os.path.getsize(output_path)
        secs = int(size / (128 * 1024 / 8))
        mins, s = divmod(secs, 60)
        print(f"  [OK] {os.path.basename(output_path)} — {size//1024} KB (~{mins}m{s:02d}s)")
        return True
    else:
        print(f"  [ERROR] ffmpeg: {result.stderr[-300:]}")
        return False


def process_script(script_path):
    """Convert one JSON script into a broadcast MP3."""
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    ts = script.get("generated_at", datetime.datetime.now().isoformat())[:16] \
              .replace(":", "").replace("-", "").replace("T", "_")
    seg_dir = os.path.join(AUDIO_DIR, f"segments_{ts}")
    os.makedirs(seg_dir, exist_ok=True)

    print(f"\n  Script  : {os.path.basename(script_path)}")
    print(f"  Hour    : {script.get('broadcast_hour', '?')}")
    print(f"  Language: {script.get('language', 'fr')}")

    files = []
    for i, seg in enumerate(script["segments"]):
        name = seg["segment"]
        text = seg["text"].strip()
        if len(text) < 5:
            continue

        seg_path = os.path.join(seg_dir, f"{i:02d}_{name}.mp3")
        print(f"    [{name}]")
        ok = synth(text, name, seg_path)
        if ok:
            files.append(seg_path)
            # Pause between segments (longer after station ID, shorter between news)
            pause_ms = 1200 if name in ("STATION_ID", "INTRO") else 700
            sil = os.path.join(seg_dir, f"{i:02d}_pause.mp3")
            add_silence(pause_ms, sil)
            files.append(sil)

    if not files:
        print("  [ERROR] No audio generated.")
        return None

    out = os.path.join(AUDIO_DIR, f"newscast_{ts}.mp3")
    print(f"\n  Assembling {len(files)} files...")
    return out if concat_mp3s(files, out) else None


def process_latest_script():
    scripts = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "newscast_*.json")))
    if not scripts:
        print("[ERROR] No scripts found. Run news_fetcher.py first.")
        return None
    return process_script(scripts[-1])


def update_playlist(audio_path):
    os.makedirs(PLAYLISTS_DIR, exist_ok=True)
    playlist = os.path.join(PLAYLISTS_DIR, "molefm_news.m3u")
    with open(playlist, "a", encoding="utf-8") as f:
        f.write(f"{audio_path}\n")

    # Rebuild 24h playlist
    all_mp3s = sorted(glob.glob(os.path.join(AUDIO_DIR, "newscast_*.mp3")))
    with open(os.path.join(PLAYLISTS_DIR, "molefm_24h.m3u"), "w") as f:
        f.write("#EXTM3U\n")
        for mp3 in all_mp3s:
            f.write(f"{mp3}\n")
    print(f"  [OK] Playlists updated ({len(all_mp3s)} newscasts in 24h list)")
    return playlist


def run():
    print(f"\n=== Mole FM TTS (edge-tts / French / FREE) === "
          f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    os.makedirs(AUDIO_DIR, exist_ok=True)

    audio = process_latest_script()
    if audio:
        update_playlist(audio)
        print(f"\n  Audio : {audio}")
        print(f"  Cost  : $0.00")
        return audio
    print("\n  [FAILED]")
    return None


if __name__ == "__main__":
    run()
