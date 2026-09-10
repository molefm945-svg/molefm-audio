import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import azure_speech


class AzureSpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "sample.mp3"
        self.ledger = self.root / "usage.json"
        self.env = patch.dict(os.environ, {
            "AZURE_SPEECH_KEY": "test-key",
            "AZURE_SPEECH_REGION": "eastus",
            "MOLEFM_AZURE_ENABLED_UNTIL": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat(),
            "MOLEFM_AZURE_USAGE_FILE": str(self.ledger),
            "MOLEFM_AZURE_MONTHLY_CHARACTERS": "100",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_synthesis(self, text="Bonjour & bienvenue"):
        return azure_speech.synthesize(text, "fr-FR-DeniseNeural", self.output)

    @patch("azure_speech.urlopen")
    def test_mp3_provenance_and_xml_escaping(self, request):
        request.return_value = io.BytesIO(b"ID3" + b"a" * 1200)
        receipt = self.run_synthesis()
        self.assertEqual(receipt["audio_bytes"], self.output.stat().st_size)
        self.assertIn(b"&amp;", request.call_args.args[0].data)
        self.assertNotIn("test-key", Path(str(self.output) + ".azure.json").read_text())
        self.assertEqual(sum(json.loads(self.ledger.read_text()).values()), 19)

    @patch("azure_speech.urlopen")
    def test_expired_authorization_makes_no_request(self, request):
        os.environ["MOLEFM_AZURE_ENABLED_UNTIL"] = "2020-01-01T00:00:00Z"
        with self.assertRaises(RuntimeError): self.run_synthesis()
        request.assert_not_called()

    @patch("azure_speech.urlopen")
    def test_exhausted_allowance_makes_no_request(self, request):
        os.environ["MOLEFM_AZURE_MONTHLY_CHARACTERS"] = "1"
        with self.assertRaises(RuntimeError): self.run_synthesis()
        request.assert_not_called()

    @patch("azure_speech.urlopen", side_effect=TimeoutError("private diagnostic"))
    def test_uncertain_failure_is_reserved_and_not_retried(self, request):
        with self.assertRaisesRegex(RuntimeError, "no automatic retry") as error:
            self.run_synthesis()
        self.assertNotIn("private diagnostic", str(error.exception))
        self.assertEqual(request.call_count, 1)
        self.assertEqual(sum(json.loads(self.ledger.read_text()).values()), 19)
        self.assertFalse(self.output.exists())

    @patch("azure_speech.urlopen")
    def test_rejects_non_audio(self, request):
        request.return_value = io.BytesIO(b"<html>" + b"a" * 1200)
        with self.assertRaises(RuntimeError): self.run_synthesis()
        self.assertFalse(self.output.exists())

    @patch("azure_speech.urlopen")
    def test_never_overwrites_existing_audio(self, request):
        self.output.write_bytes(b"original")
        with self.assertRaises(FileExistsError): self.run_synthesis()
        self.assertEqual(self.output.read_bytes(), b"original")
        request.assert_not_called()

    @patch("azure_speech.urlopen")
    def test_corrupt_ledger_fails_closed(self, request):
        self.ledger.write_text("broken")
        with self.assertRaises(ValueError): self.run_synthesis()
        request.assert_not_called()

    @patch("azure_speech.urlopen")
    def test_missing_credentials_fails_closed(self, request):
        os.environ["AZURE_SPEECH_KEY"] = ""
        os.environ.pop("AZURE_SPEECH_KEY_FILE", None)
        with self.assertRaises(KeyError): self.run_synthesis()
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
