"""Offline publication-contract tests. No TTS, browser, network, or Git process."""
import ast
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import podcast_description as notes
import podcast_generator as generator
import molefm_submitter as submitter
import generate_rss as rss

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


class OfflinePage:
    def __init__(self, truncate_description=False):
        self.url = ""
        self.values = {}
        self.save_clicks = 0
        self.truncate_description = truncate_description

    async def goto(self, url, **kwargs):
        self.url = url

    async def wait_for_timeout(self, value):
        pass

    async def inner_text(self, selector):
        return "Episode saved"

    def locator(self, selector):
        page = self

        class Locator:
            @property
            def first(self):
                return self

            def nth(self, index):
                return self

            async def is_visible(self, **kwargs):
                return True

            async def count(self):
                return 1

            async def fill(self, value):
                page.values[selector] = value[:-1] if page.truncate_description and "description" in selector.lower() else value

            async def input_value(self):
                return page.values.get(selector, "")

            async def select_option(self, **kwargs):
                pass

            async def click(self):
                if 'has-text("Save")' in selector:
                    page.save_clicks += 1

        return Locator()


def run_fake_browser(script, page):
    class Context:
        async def new_page(self):
            return page

    class Browser:
        async def new_context(self, **kwargs):
            return Context()

        async def close(self):
            pass

    class Chromium:
        async def launch(self, **kwargs):
            return Browser()

    class Playwright:
        chromium = Chromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    module = types.ModuleType("playwright.async_api")
    module.async_playwright = Playwright
    output = io.StringIO()
    with patch.dict(sys.modules, {"playwright": types.ModuleType("playwright"), "playwright.async_api": module}), contextlib.redirect_stdout(output):
        exec(compile(script, "offline-generated-submitter", "exec"), {})
    return output.getvalue()


class PodcastAttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio_dir = self.root / "audio"
        self.audio_dir.mkdir()
        self.audio = self.audio_dir / "podcast_fr_20260909_1600.mp3"
        self.audio.write_bytes(b"offline exact audio fixture, never decoded or uploaded")
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.url = "https://media.example.org/" + self.audio.name + "?download=1&lang=fr"
        self.stories = [{"source": "Le Nouvelliste", "title": "Une école & ses élèves", "link": "https://lenouvelliste.com/article/123?lang=fr&part=2", "all_sources": ["Le Nouvelliste", "Juno7"]}]

    def metadata(self, description=None):
        description = description or notes.build_podcast_description(self.stories, "9 septembre 2026", 123)
        return notes.save_metadata(str(self.audio), "Titre", description, self.stories, 123, "2026-09-09T16:00:00Z")

    def test_article_urls_survive_numbered_newscast_extraction_without_invented_verification(self):
        script = self.root / "newscast.json"
        script.write_text(json.dumps({"segments": [{"segment": "NEWS_MAIN", "text": "Titre 1 : Une école. Selon Le Nouvelliste et Juno7 — Les détails de cette actualité."}], "source_backed_stories": self.stories}), encoding="utf-8")
        extracted = generator.extract_stories_from_scripts([str(script)])
        self.assertEqual(extracted[0]["link"], self.stories[0]["link"])
        self.assertEqual(extracted[0]["verification"], "UNSPECIFIED")
        self.assertIn(self.stories[0]["link"], notes.build_podcast_description(extracted, "date", 60))

    def test_null_nested_references_and_supplied_article_aliases_survive_extraction(self):
        for key in ("link", "article_url", "url"):
            with self.subTest(key=key):
                supplied = {"source": "Éditeur", key: "https://publisher.example.org/article", "source_references": None}
                script = self.root / (key + ".json")
                script.write_text(json.dumps({"segments": [{"segment": "NEWS_MAIN", "text": "Titre 1 : Une nouvelle et ses détails."}], "source_backed_stories": [supplied]}), encoding="utf-8")
                extracted = generator.extract_stories_from_scripts([str(script)])
                self.assertEqual(notes.source_references(extracted)[0]["url"], supplied[key])
        for malformed in (None, "bad", {"url": "https://example.org"}):
            self.assertEqual(len(notes.source_references([{"source": "Juno7", "source_references": malformed}])), 1)

    def test_legacy_attribution_is_honest_publisher_fallback(self):
        description = notes.build_podcast_description([{"source_attr": "Le Nouvelliste et Inconnu"}], "date", 60)
        self.assertIn("site de l’éditeur (repli, article non fourni)", description)
        self.assertIn("Inconnu — URL d’article non fournie", description)
        self.assertNotIn("https://www.molefm.com", description)
        self.assertNotIn("Sources vérifiées", description)

    def test_supplied_source_feed_is_not_mislabelled_as_article_or_homepage(self):
        references = notes.source_references([{"source": "Éditeur", "source_url": "https://publisher.example.org/feed"}])
        self.assertEqual(references[0]["kind"], "source_link")
        self.assertIn("article non identifié", notes.build_podcast_description([{"source": "Éditeur", "source_url": references[0]["url"]}], "date", 1))

    def test_dedup_retains_distinct_articles_and_removes_obsolete_homepage_fallback(self):
        stories = [{"source": "Juno7"}, {"source": "Juno7", "link": "https://juno7.ht/a"}, {"source": "Juno7", "link": "https://juno7.ht/a"}, {"source": "Juno7", "link": "https://juno7.ht/b"}]
        self.assertEqual([ref["url"] for ref in notes.source_references(stories)], ["https://juno7.ht/a", "https://juno7.ht/b"])

    def test_invalid_urls_do_not_become_links(self):
        for url in ["javascript:alert(1)", "data:text/html,evil", "https://user:password@example.org/a", "/relative", "https://example.org/a\nInjected", 'https://example.org/"bad', "https://example.org:invalid/a"]:
            with self.subTest(url=url):
                self.assertEqual(notes.source_url(url), "")
        description = notes.build_podcast_description([{"source": "Unknown", "link": "javascript:alert(1)"}], "date", 60)
        self.assertIn("URL d’article non fournie", description)
        self.assertNotIn("alert", description)

    def test_supplied_article_beats_publisher_homepage(self):
        refs = notes.source_references([{**self.stories[0], "source_url": "https://lenouvelliste.com"}])
        self.assertEqual(refs[0]["url"], self.stories[0]["link"])
        self.assertEqual(refs[0]["kind"], "article")

    def test_metadata_binds_description_to_exact_audio_and_filename(self):
        metadata = self.metadata()
        self.assertIn("Sources & Références", notes.read_metadata(metadata, self.audio.name, self.audio)["description"])
        with self.assertRaises(ValueError):
            notes.read_metadata(metadata, "other.mp3")
        self.audio.write_bytes(b"different audio")
        with self.assertRaises(ValueError):
            notes.read_metadata(metadata, self.audio.name, self.audio)

    def test_rss_escapes_xml_url_and_cdata_without_changing_description(self):
        description = 'Sources & Références :\nÉditeur <nom> ]]> https://example.org/a?x=1&y=2'
        item = rss.build_episode_item(self.audio.name, self.url + '&quote="oui"', 12, 61, "Wed, 09 Sep 2026 16:00:00 +0000", description)
        parsed = ET.fromstring('<rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">' + item + "</rss>")
        self.assertEqual(parsed.findtext("item/description"), description)
        self.assertEqual(parsed.findtext("item/" + ITUNES + "summary"), description)
        self.assertEqual(parsed.find("item/enclosure").get("url"), self.url + '&quote="oui"')

    def test_legacy_rss_uses_saved_registry_description_or_honest_missing_notice(self):
        self.assertEqual(rss.episode_description(str(self.audio), {"description": "Sources : https://example.org/original"}), "Sources : https://example.org/original")
        fallback = rss.build_episode_item(self.audio.name, self.url, 12, 61, "date")
        self.assertIn("aucun lien source fourni", fallback)
        self.assertNotIn("Nouvelles vérifiées", fallback)

    def test_missing_credentials_fail_before_tempfile_browser_or_subprocess(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(submitter.subprocess, "run") as command, patch.object(submitter.tempfile, "NamedTemporaryFile") as temporary, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(submitter.submit_via_playwright("podcast", self.url, "Titre", 123))
            command.assert_not_called()
            temporary.assert_not_called()
            self.assertIn("MOLEFM_ADMIN_PIN", output.getvalue())

    def test_generated_browser_script_uses_environment_only_and_quotes_inputs(self):
        with patch.dict(os.environ, {"MOLEFM_ADMIN_USERNAME": "fixture-owner-not-real", "MOLEFM_ADMIN_PIN": "fixture-private-pin-not-real"}):
            script = submitter._build_playwright_script("podcast", self.url + '"\nnot_code()', 'Titre " cité', 123, "Sources\n" + self.stories[0]["link"])
        ast.parse(script)
        self.assertNotIn("fixture-owner-not-real", script)
        self.assertNotIn("fixture-private-pin-not-real", script)
        values = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(script).body if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)}
        self.assertEqual(values["DESCRIPTION"], "Sources\n" + self.stories[0]["link"])
        self.assertEqual(values["AUDIO_URL"], self.url + '"\nnot_code()')

    def test_browser_form_retains_exact_multiline_description_before_save(self):
        description = notes.build_podcast_description(self.stories, "date", 123)
        page = OfflinePage()
        with patch.dict(os.environ, {"MOLEFM_ADMIN_USERNAME": "fixture-owner", "MOLEFM_ADMIN_PIN": "fixture-pin"}):
            output = run_fake_browser(submitter._build_playwright_script("podcast", self.url, "Titre", 123, description), page)
        self.assertEqual(page.values['textarea[placeholder*="description" i]'], description)
        self.assertEqual(page.save_clicks, 1)
        self.assertEqual(json.loads(output.splitlines()[-1])["status"], "success")

    def test_description_truncation_blocks_publish_click(self):
        page = OfflinePage(truncate_description=True)
        with patch.dict(os.environ, {"MOLEFM_ADMIN_USERNAME": "fixture-owner", "MOLEFM_ADMIN_PIN": "fixture-pin"}):
            output = run_fake_browser(submitter._build_playwright_script("podcast", self.url, "Titre", 123, "Sources exactes"), page)
        self.assertEqual(page.save_clicks, 0)
        self.assertEqual(json.loads(output.splitlines()[-1])["code"], "required_episode_fields_unconfirmed")

    def test_uncertain_browser_result_is_not_reported_as_success(self):
        with patch.dict(os.environ, {"MOLEFM_ADMIN_USERNAME": "fixture-owner", "MOLEFM_ADMIN_PIN": "fixture-pin"}), patch.object(submitter, "SUBMISSION_LOG", str(self.root / "submissions.jsonl")), patch.object(submitter.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, '{"status":"completed"}\n', "")), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(submitter.submit_via_playwright("podcast", self.url, "Titre", 123, "Source fournie"))
        log = json.loads((self.root / "submissions.jsonl").read_text())
        self.assertFalse(log["success"])
        self.assertEqual(log["description"], "Source fournie")

    def test_cli_rejects_metadata_for_different_episode_before_submission(self):
        metadata = self.metadata()
        with patch.object(submitter, "submit_episode") as submit, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(submitter.main(["podcast", "https://media.example.org/other.mp3", "Titre", "123", "--metadata-file", metadata]), 1)
            submit.assert_not_called()

    def test_generator_submitter_persisted_archive_and_rss_preserve_same_sources(self):
        calls, page = [], OfflinePage()
        registry = self.root / "registry.json"
        registry.write_text(json.dumps({"podcasts": [{"filename": self.audio.name, "url": self.url}]}))

        def command(args, **kwargs):
            calls.append(args)
            if args[0] == "git":
                return subprocess.CompletedProcess(args, 0, "", "")
            name = os.path.basename(args[1])
            if name == "github_uploader.py":
                return subprocess.CompletedProcess(args, 0, self.url + "\n", "")
            if name == "molefm_submitter.py":
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = submitter.main(args[2:])
                return subprocess.CompletedProcess(args, code, output.getvalue(), "")
            if name == "generate_rss.py":
                feed, count = rss.generate_feed()
                self.assertEqual(count, 1)
                rss.save_and_push_feed(feed)
                return subprocess.CompletedProcess(args, 0, "", "")
            if name.endswith(".py") and Path(args[1]).parent == Path(tempfile.gettempdir()):
                return subprocess.CompletedProcess(args, 0, run_fake_browser(Path(args[1]).read_text(), page), "")
            self.fail("Unexpected offline command: " + args[0])

        with patch.dict(os.environ, {"MOLEFM_ADMIN_USERNAME": "fixture-owner", "MOLEFM_ADMIN_PIN": "fixture-pin"}), patch.object(submitter, "SUBMISSION_LOG", str(self.root / "submissions.jsonl")), patch.object(rss, "PODCAST_DIR", str(self.audio_dir)), patch.object(rss, "ARCHIVE_DIR", str(self.archive)), patch.object(rss, "OUTPUT_PATH", str(self.archive / "feed.xml")), patch.object(rss, "REGISTRY_PATH", str(registry)), patch.object(rss, "get_mp3_duration_seconds", return_value=123), patch.object(subprocess, "run", side_effect=command), contextlib.redirect_stdout(io.StringIO()):
            url, title = generator.publish_podcast_episode(str(self.audio), self.stories, "midi", datetime.datetime(2026, 9, 9, 16), 2, 3)
            self.assertEqual(url, self.url)
            saved = notes.read_metadata(notes.metadata_path(self.audio), self.audio.name, self.audio)
            self.assertEqual(page.values['textarea[placeholder*="description" i]'], saved["description"])
            log = json.loads((self.root / "submissions.jsonl").read_text())
            self.assertEqual(log["description"], saved["description"])
            self.assertTrue(log["success"])
            self.assertTrue((self.archive / "podcasts" / (self.audio.name + ".metadata.json")).is_file())
            self.assertIn(["git", "add", "feed.xml", "podcasts/" + self.audio.name + ".metadata.json"], calls)
            Path(notes.metadata_path(self.audio)).unlink()
            rebuilt, _ = rss.generate_feed()
        parsed = ET.fromstring(rebuilt)
        self.assertEqual(parsed.findtext("channel/item/description"), saved["description"])
        self.assertEqual(parsed.findtext("channel/item/" + ITUNES + "summary"), saved["description"])
        self.assertIn(self.stories[0]["link"], parsed.findtext("channel/item/description"))

    def test_fixed_french_voices_and_existing_slot_labels_are_preserved(self):
        self.assertEqual(generator.FR_VOICE_DENISE, "fr-FR-DeniseNeural")
        self.assertEqual(generator.FR_VOICE_HENRI, "fr-FR-HenriNeural")
        self.assertEqual([rss.slot_label_from_filename(f"podcast_fr_20260909_{hour}.mp3") for hour in ("1600", "1900", "0100")], ["Midi", "Après-midi", "Soir"])


if __name__ == "__main__":
    unittest.main()
