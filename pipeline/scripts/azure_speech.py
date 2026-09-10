"""Authenticated Azure S0 narration with a local, fail-closed usage allowance.

No Edge fallback and no retries. Reservations remain charged to the local
allowance after uncertain failures, since Azure may have processed the request.
The allowance controls this worker only; it is not an Azure billing cap.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

VOICES = {"fr-FR-DeniseNeural", "fr-FR-HenriNeural", "fr-CA-ThierryNeural", "fr-CA-SylvieNeural"}


def tls_context():
    """Honor an operator-configured proxy CA without disabling TLS verification."""
    context = ssl.create_default_context()
    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        bundle = os.environ.get(name, "").strip()
        if bundle:
            # Invalid/missing bundles fail before reserving usage or making a call.
            context.load_verify_locations(cafile=bundle)
    return context


def synthesize(text, voice, output_path, rate="+0%", volume="+0%"):
    if voice not in VOICES or not isinstance(text, str) or not text.strip() or len(text) > 8000:
        raise ValueError("Unsupported voice or invalid narration length (maximum 8000 characters)")
    if not all(re.fullmatch(r"[+-]\d{1,2}%", value) for value in (rate, volume)):
        raise ValueError("Invalid prosody settings")
    now = dt.datetime.now(dt.timezone.utc)
    until = dt.datetime.fromisoformat(os.environ["MOLEFM_AZURE_ENABLED_UNTIL"].replace("Z", "+00:00"))
    if until.tzinfo is None or now >= until:
        raise RuntimeError("Azure narration funding authorization has expired")
    region = os.environ["AZURE_SPEECH_REGION"]
    if not re.fullmatch(r"[a-z0-9]+", region):
        raise ValueError("Invalid Azure region")
    auth_mode = os.environ.get("AZURE_SPEECH_AUTH_MODE", "key")
    key = ""
    if auth_mode == "perplexity-proxy":
        # The platform attaches the named vault credential to this process.
        # Never read its credential token or forward a local key in this mode.
        if not os.environ.get("HTTPS_PROXY", "").strip():
            raise RuntimeError("Perplexity credential proxy is not attached")
    elif auth_mode == "key":
        key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
        if not key:
            key = Path(os.environ["AZURE_SPEECH_KEY_FILE"]).read_text().strip()
        if not key:
            raise RuntimeError("Azure Speech credential missing")
    else:
        raise ValueError("Unsupported Azure authentication mode")
    output = Path(output_path)
    if output.exists():
        raise FileExistsError("Refusing to overwrite existing narration")
    limit = int(os.environ.get("MOLEFM_AZURE_MONTHLY_CHARACTERS", "1000000"))
    if not 1 <= limit <= 1000000:
        raise ValueError("Worker allowance must be between 1 and 1000000 characters")
    context = tls_context()
    ledger = Path(os.environ["MOLEFM_AZURE_USAGE_FILE"])
    ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    month = now.strftime("%Y-%m")
    # Separate lock remains stable while the ledger is replaced atomically.
    with open(str(ledger) + ".lock", "a") as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        usage = json.loads(ledger.read_text()) if ledger.exists() else {}
        spent = usage.get(month, 0)
        if type(spent) is not int or spent < 0 or spent + len(text) > limit:
            raise RuntimeError("Azure worker narration allowance exhausted or invalid")
        usage[month] = spent + len(text)
        temporary = Path(str(ledger) + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(usage, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(ledger)
    locale = voice[:5]
    ssml = (f'<speak version="1.0" xml:lang="{locale}"><voice name="{voice}">'
            f'<prosody rate="{rate}" volume="{volume}">{escape(text)}</prosody></voice></speak>')
    request = Request(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                      data=ssml.encode(), headers={**({"Ocp-Apim-Subscription-Key": key} if key else {}),
                      "Content-Type": "application/ssml+xml",
                      "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                      "User-Agent": "MoleFM-Broadcast"})
    try:
        with urlopen(request, timeout=60, context=context) as response:
            audio = response.read(16000001)
    except Exception:
        raise RuntimeError("Azure synthesis failed; allowance retained; no automatic retry") from None
    if not 1000 <= len(audio) <= 16000000 or not (audio[:3] == b"ID3" or (audio[0] == 255 and audio[1] & 224 == 224)):
        raise RuntimeError("Azure returned invalid or oversized MP3 data")
    with output.open("xb") as stream:
        stream.write(audio)
    receipt = {"provider": "azure-speech", "authentication": auth_mode, "voice": voice, "region": region,
               "generated_at": now.isoformat(), "characters": len(text),
               "script_sha256": hashlib.sha256(text.encode()).hexdigest(),
               "audio_sha256": hashlib.sha256(audio).hexdigest(), "audio_bytes": len(audio)}
    Path(str(output) + ".azure.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt
