#!/usr/bin/env python3
"""Offline release checks for the generated reader; no synthesis or network calls."""

import argparse
import html as html_module
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


MAX_HTML_BYTES = 1_000_000  # Decimal MB; equality fails as well.
REQUIRED_LANGUAGES = {"fr", "en", "es"}
_JS_TOKEN = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|//[^\n]*|/\*[\s\S]*?\*/''')


class ReaderGuardrailError(ValueError):
    pass


def _without_js_comments(script):
    return _JS_TOKEN.sub(lambda match: " " * len(match[0]) if match[0].startswith(("//", "/*")) else match[0], script)


def _code_mask(script):
    """Keep offsets while ignoring declarations or calls quoted as text."""
    return _JS_TOKEN.sub(lambda match: " " * len(match[0]), script)


class _ReaderHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.media_urls = []
        self._script = False
        self._audio = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self._script = attrs.get("type", "").lower() in (
                "", "module", "text/javascript", "application/javascript",
            )
        if tag == "audio":
            self._audio = True
        if tag == "audio" or (tag == "source" and self._audio):
            if attrs.get("src"):
                self.media_urls.append(attrs["src"])

    def handle_endtag(self, tag):
        if tag == "script":
            self._script = False
        if tag == "audio":
            self._audio = False

    def handle_data(self, data):
        if self._script:
            self.scripts.append(data)


def validate_mp3_url(value):
    """Accept direct HTTPS MP3s (including GitHub Releases) or local MP3 paths."""
    if not isinstance(value, str) or not value or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ReaderGuardrailError("Audio URLs must be nonempty direct MP3 paths without whitespace or backslashes")
    try:
        url = urlsplit(value)
        decoded_path = unquote(url.path)
        if url.scheme and url.scheme != "https":
            raise ValueError("scheme")
        if url.netloc and not url.scheme:
            raise ValueError("protocol-relative URL")
        if url.scheme and (not url.hostname or url.username or url.password):
            raise ValueError("host or credentials")
        if url.fragment or not decoded_path.lower().endswith(".mp3"):
            raise ValueError("extension or fragment")
        if any(part == ".." for part in decoded_path.split("/")) or "\\" in decoded_path:
            raise ValueError("path traversal")
        if url.hostname in {"github.com", "www.github.com"} and not re.fullmatch(
            r"/[^/]+/[^/]+/releases/download/[^/]+/.+\.mp3", decoded_path, re.IGNORECASE
        ):
            raise ValueError("GitHub page is not a release download")
    except ValueError as error:
        # Do not echo URLs: query strings can contain credentials.
        raise ReaderGuardrailError("Audio must use a relative MP3 file or a direct HTTPS MP3 download") from error
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReaderGuardrailError("Duplicate key in reader audio manifest")
        result[key] = value
    return result


def _json_constant(script, name, required=False):
    matches = list(re.finditer(rf"\bconst\s+{name}\s*=\s*", _code_mask(script)))
    if not matches and not required:
        return None
    if len(matches) != 1:
        raise ReaderGuardrailError(f"Exactly one executable const {name} JSON literal is required")
    remainder = script[matches[0].end():]
    try:
        value, end = json.JSONDecoder(object_pairs_hook=_unique_object).raw_decode(remainder)
    except (ValueError, json.JSONDecodeError) as error:
        raise ReaderGuardrailError(f"{name} must be a JSON literal, not computed or encoded audio") from error
    if not remainder[end:].lstrip().startswith(";"):
        raise ReaderGuardrailError(f"{name} must end after its JSON literal")
    return value


def validate_reader_html(html):
    size = len(html.encode("utf-8"))
    if size >= MAX_HTML_BYTES:
        raise ReaderGuardrailError(f"index.html is {size} bytes; it must be strictly below {MAX_HTML_BYTES}")
    parser = _ReaderHTML()
    parser.feed(html)
    script = _without_js_comments("\n".join(parser.scripts))
    code = _code_mask(script)
    # Decode escaped scheme characters before checking all HTML and script text.
    decoded = html_module.unescape(html)
    decoded = re.sub(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})",
                     lambda match: chr(int(match[1] or match[2], 16)), decoded)
    if re.search(r"data\s*:\s*(?:audio/|application/octet-stream)|blob\s*:", decoded, re.IGNORECASE):
        raise ReaderGuardrailError("Embedded data/blob audio is forbidden; use direct MP3 files")
    if re.search(r"\b(?:atob|btoa|mp3_to_b64|dataURItoBlob)\s*\(|\bnew\s+Blob\s*\(|\bcreateObjectURL\s*\(|\bconst\s+AB\s*=", code):
        raise ReaderGuardrailError("Base64/blob audio construction is forbidden in the reader")
    urls = _json_constant(script, "AUDIO_URLS", required=True)
    if not isinstance(urls, dict) or set(urls) != REQUIRED_LANGUAGES:
        raise ReaderGuardrailError("AUDIO_URLS must contain exactly fr, en and es")
    all_urls = [validate_mp3_url(value) for value in urls.values()]
    if not re.search(r"\.src\s*=\s*AUDIO_URLS\s*\[", code):
        raise ReaderGuardrailError("Reader audio elements must load from AUDIO_URLS")
    for name in ("PLAYLIST", "BROADCASTS", "PODCASTS"):
        manifest = _json_constant(script, name)
        if manifest is None:
            continue
        if not isinstance(manifest, list):
            raise ReaderGuardrailError(f"{name} must be a JSON array")
        for entry in manifest:
            if not isinstance(entry, dict):
                raise ReaderGuardrailError(f"{name} entries must be objects")
            for key, value in entry.items():
                if key.startswith("audio_"):
                    all_urls.append(validate_mp3_url(value))
    all_urls.extend(validate_mp3_url(value) for value in parser.media_urls)
    if not re.search(r"\b(?:function\s+setSpeed|setSpeed\s*=)", code):
        raise ReaderGuardrailError("Reader playback speed control is missing")
    if re.search(r"\bwindow\s*\.\s*_podAudio\b", code):
        raise ReaderGuardrailError("Podcast audio must remain script-scoped, not window._podAudio")
    return {"html_bytes": size, "audio_urls": sorted(set(all_urls))}


def write_reader_html(path, html):
    """Fail before opening the output file so invalid builds preserve the last HTML."""
    report = validate_reader_html(html)
    Path(path).write_text(html, encoding="utf-8")
    return report


def validate_local_audio(path, report):
    root = Path(path).resolve().parent
    for value in report["audio_urls"]:
        url = urlsplit(value)
        if url.scheme:  # Online availability belongs to deployment smoke checks.
            continue
        asset = (root / unquote(url.path).lstrip("/")).resolve()
        if not asset.is_relative_to(root) or not asset.is_file():
            raise ReaderGuardrailError("A local MP3 referenced by index.html is missing")
        with asset.open("rb") as handle:
            header = handle.read(3)
        if not (header == b"ID3" or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)):
            raise ReaderGuardrailError("A local MP3 has an invalid header")


def render_ci_fixture():
    # Importing the generator does not run its TTS/translation pipeline.
    from build_reader import build_html
    timing = [{"word": word, "start_ms": i * 400, "end_ms": (i + 1) * 400}
              for i, word in enumerate("Mole FM informe Haïti et sa diaspora.".split())]
    return build_html(timing, timing, timing, {"fr": [], "en": [], "es": []},
                      "2026-09-09 12:00", {"segments": []})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help="Actual generated index.html to validate")
    parser.add_argument("--render-fixture", metavar="OUTPUT", help="Render the actual template offline and validate it")
    parser.add_argument("--check-local-audio", action="store_true", help="Also require referenced local MP3 files and headers")
    args = parser.parse_args()
    if bool(args.path) == bool(args.render_fixture):
        parser.error("Provide an HTML path or --render-fixture OUTPUT")
    try:
        if args.render_fixture:
            path = Path(args.render_fixture)
            path.parent.mkdir(parents=True, exist_ok=True)
            report = write_reader_html(path, render_ci_fixture())
        else:
            path = Path(args.path)
            report = validate_reader_html(path.read_text(encoding="utf-8"))
        if args.check_local_audio:
            validate_local_audio(path, report)
    except (OSError, UnicodeError, ReaderGuardrailError) as error:
        parser.exit(1, f"Reader guardrail failed: {error}\n")
    print(f"Reader guardrails passed: {report['html_bytes']} bytes; {len(report['audio_urls'])} direct MP3 URLs")


if __name__ == "__main__":
    main()
