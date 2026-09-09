import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from reader_guardrails import (
    MAX_HTML_BYTES, ReaderGuardrailError, render_ci_fixture, validate_local_audio,
    validate_mp3_url, validate_reader_html, write_reader_html,
)


def minimal_reader(urls=None, extra=""):
    urls = urls or {"fr": "audio_fr.mp3", "en": "audio_en.mp3", "es": "audio_es.mp3"}
    return ('<!doctype html><html><script>const AUDIO_URLS=' + json.dumps(urls) + ';'
            'function init(){audio.src=AUDIO_URLS[lang];}'
            'function setSpeed(value){audio.playbackRate=value;}' + extra + '</script></html>')


class ReaderGuardrailsTests(unittest.TestCase):
    def test_actual_template_renders_offline_with_direct_audio(self):
        report = validate_reader_html(render_ci_fixture())
        self.assertLess(report["html_bytes"], MAX_HTML_BYTES)
        self.assertEqual(report["audio_urls"], ["audio_en.mp3", "audio_es.mp3", "audio_fr.mp3"])

    def test_strict_decimal_megabyte_boundary(self):
        html = minimal_reader()
        html += " " * (MAX_HTML_BYTES - 1 - len(html.encode("utf-8")))
        self.assertEqual(validate_reader_html(html)["html_bytes"], 999_999)
        with self.assertRaisesRegex(ReaderGuardrailError, "strictly below"):
            validate_reader_html(html + " ")

    def test_size_counts_utf8_bytes_not_characters(self):
        html = minimal_reader() + "é" * 500_000
        self.assertLess(len(html), MAX_HTML_BYTES)
        with self.assertRaises(ReaderGuardrailError):
            validate_reader_html(html)

    def test_https_release_raw_and_relative_mp3_links(self):
        for url in ("https://github.com/molefm945-svg/molefm-audio/releases/download/day/episode.mp3",
                    "https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main/podcasts/episode.mp3",
                    "https://media.example.org/episode.mp3?version=2", "audio/episode.mp3", "/audio/episode.mp3"):
            with self.subTest(url=url):
                self.assertEqual(validate_mp3_url(url), url)

    def test_non_direct_or_unsafe_links_rejected(self):
        for url in ("data:audio/mpeg;base64,SUQz", "blob:https://example.org/id", "javascript:play()",
                    "http://example.org/a.mp3", "//example.org/a.mp3", "https://example.org/player?file=a.mp3",
                    "https://github.com/molefm945-svg/molefm-audio/blob/main/audio/a.mp3",
                    "https://user:secret@example.org/a.mp3", "../a.mp3", "%2e%2e/a.mp3", "a.mp3#fragment",
                    "a.mp3\n", "audio\\a.mp3", "", None):
            with self.subTest(url=url):
                with self.assertRaises(ReaderGuardrailError):
                    validate_mp3_url(url)

    def test_audio_urls_requires_each_language_and_direct_values(self):
        for urls in ({"fr": "a.mp3"}, {"fr": "a.mp3", "en": "b.mp3", "es": "player.html"},
                     {"fr": "a.mp3", "en": "b.mp3", "es": "c.mp3", "xx": "d.mp3"}):
            with self.subTest(urls=urls):
                with self.assertRaises(ReaderGuardrailError):
                    validate_reader_html(minimal_reader(urls))

    def test_missing_or_comment_only_manifest_does_not_pass(self):
        declaration = 'const AUDIO_URLS={"fr":"a.mp3","en":"b.mp3","es":"c.mp3"};'
        for fake in ("// " + declaration + "\n", "/* " + declaration + " */", "const example=" + json.dumps(declaration) + ";"):
            with self.subTest(fake=fake):
                html = '<script>' + fake + 'audio.src=AUDIO_URLS[lang];function setSpeed(){}</script>'
                with self.assertRaises(ReaderGuardrailError):
                    validate_reader_html(html)

    def test_computed_or_duplicate_manifest_rejected(self):
        for declaration in ('const AUDIO_URLS=readFromSomewhere();',
                            'const AUDIO_URLS={"fr":"a.mp3","en":"b.mp3","es":"c.mp3","fr":"d.mp3"};',
                            'const AUDIO_URLS={"fr":"a.mp3","en":"b.mp3","es":"c.mp3"} || fallback;'):
            with self.subTest(declaration=declaration):
                with self.assertRaises(ReaderGuardrailError):
                    validate_reader_html('<script>' + declaration + 'audio.src=AUDIO_URLS[lang];function setSpeed(){}</script>')

    def test_static_media_and_javascript_data_blob_audio_rejected(self):
        for extra in ('<audio src="data:audio/mpeg;base64,SUQz"></audio>',
                      '<audio><source src="data&#58;audio/mpeg;base64,SUQz"></audio>',
                      '<script>audio.src="\\u0064ata:audio/mpeg;base64,SUQz";</script>',
                      '<script>audio.src="blob:https://example.org/id";</script>',
                      '<script>audio.src="data:application/octet-stream;base64,SUQz";</script>'):
            with self.subTest(extra=extra):
                with self.assertRaises(ReaderGuardrailError):
                    validate_reader_html(minimal_reader() + extra)

    def test_base64_blob_builders_rejected(self):
        for code in ('atob("SUQz");', 'btoa(bytes);', 'new Blob(bytes);', 'URL.createObjectURL(bytes);',
                     'dataURItoBlob(encoded);', 'mp3_to_b64(path);', 'const AB="SUQz";'):
            with self.subTest(code=code):
                with self.assertRaises(ReaderGuardrailError):
                    validate_reader_html(minimal_reader(extra=code))

    def test_image_data_is_not_mistaken_for_audio(self):
        html = minimal_reader() + '<img src="data:image/png;base64,AA==" alt="Logo">'
        validate_reader_html(html)

    def test_playback_must_use_manifest(self):
        html = minimal_reader().replace("audio.src=AUDIO_URLS[lang];", "audio.src='other.mp3';")
        with self.assertRaisesRegex(ReaderGuardrailError, "must load from AUDIO_URLS"):
            validate_reader_html(html)

    def test_archive_and_podcast_manifests_are_also_checked(self):
        for name, key in (("PLAYLIST", "audio_fr"), ("BROADCASTS", "audio_url"), ("PODCASTS", "audio_url")):
            with self.subTest(name=name):
                validate_reader_html(minimal_reader(extra=f'const {name}=[{{"{key}":"archive/day.mp3"}}];'))
                with self.assertRaises(ReaderGuardrailError):
                    validate_reader_html(minimal_reader(extra=f'const {name}=[{{"{key}":"player.html"}}];'))

    def test_speed_and_script_scope_guards_retained(self):
        with self.assertRaisesRegex(ReaderGuardrailError, "speed control"):
            validate_reader_html(minimal_reader().replace("setSpeed", "removedSpeed"))
        with self.assertRaisesRegex(ReaderGuardrailError, "script-scoped"):
            validate_reader_html(minimal_reader(extra="window._podAudio=new Audio();"))

    def test_invalid_output_does_not_overwrite_last_valid_html(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            write_reader_html(path, minimal_reader())
            original = path.read_bytes()
            with self.assertRaises(ReaderGuardrailError):
                write_reader_html(path, "x" * MAX_HTML_BYTES)
            self.assertEqual(path.read_bytes(), original)

    def test_optional_local_mp3_presence_and_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            report = write_reader_html(path, minimal_reader())
            with self.assertRaisesRegex(ReaderGuardrailError, "missing"):
                validate_local_audio(path, report)
            for name in report["audio_urls"]:
                (path.parent / name).write_bytes(b"ID3" + bytes(20))
            validate_local_audio(path, report)
            (path.parent / "audio_fr.mp3").write_bytes(b"<html>Error</html>")
            with self.assertRaisesRegex(ReaderGuardrailError, "invalid header"):
                validate_local_audio(path, report)


if __name__ == "__main__":
    unittest.main()
