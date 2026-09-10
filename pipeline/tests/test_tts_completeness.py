import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import tts_generator


class CompletenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / 'script.json'
        self.script.write_text(json.dumps({'generated_at': '2026-09-10T20:00:00Z',
            'segments': [{'segment': 'INTRO', 'text': 'Bienvenue sur Mole FM.'},
                         {'segment': 'NEWS_MAIN', 'text': 'Voici notre bulletin.'}]}))
        self.directory = patch.object(tts_generator, 'AUDIO_DIR', str(self.root))
        self.directory.start()
        self.addCleanup(self.directory.stop)

    @patch.object(tts_generator, 'concat_mp3s', return_value=True)
    @patch.object(tts_generator, 'add_silence', return_value=True)
    @patch.object(tts_generator, 'synth', side_effect=[True, False])
    def test_partial_narration_is_not_assembled(self, synth, silence, concat):
        self.assertIsNone(tts_generator.process_script(str(self.script)))
        concat.assert_not_called()
        self.assertEqual(synth.call_count, 2)

    @patch.object(tts_generator, 'concat_mp3s', return_value=True)
    @patch.object(tts_generator, 'add_silence', return_value=False)
    @patch.object(tts_generator, 'synth', return_value=True)
    def test_assembly_failure_stops_next_provider_call(self, synth, silence, concat):
        self.assertIsNone(tts_generator.process_script(str(self.script)))
        concat.assert_not_called()
        self.assertEqual(synth.call_count, 1)

    @patch.object(tts_generator, 'concat_mp3s', return_value=True)
    @patch.object(tts_generator, 'add_silence', return_value=True)
    @patch.object(tts_generator, 'synth', return_value=True)
    def test_complete_narration_is_assembled(self, synth, silence, concat):
        self.assertIsNotNone(tts_generator.process_script(str(self.script)))
        concat.assert_called_once()
        self.assertEqual(len(concat.call_args.args[0]), 4)
