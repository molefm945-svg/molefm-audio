"""Test installation in disposable runtimes, without network or generation."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_perplexity_generator as installer

REPO = Path(__file__).resolve().parents[2]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.stage = self.root / "stage"
        installer.stage_files(self.stage, REPO)
        self.runtime = self.root / "runtime"
        self.scripts = self.runtime / "scripts"
        self.scripts.mkdir(parents=True)
        (self.scripts / "run_pipeline.py").write_text("# existing schedule entry point\n")
        (self.scripts / "build_reader.py").write_text("# owner version\n")
        (self.runtime / "config").mkdir()
        (self.runtime / "config" / "settings.json").write_text('{"keep":true}')

    def test_install_backup_preservation_and_idempotence(self):
        result = installer.install(self.stage, self.runtime, True)
        self.assertEqual(result["state"], "installed")
        self.assertEqual(len(result["changed"]), 8)
        self.assertEqual((Path(result["backup"]) / "build_reader.py").read_text(), "# owner version\n")
        self.assertEqual((self.runtime / "config/settings.json").read_text(), '{"keep":true}')
        self.assertEqual((self.scripts / "run_pipeline.py").read_text(), "# existing schedule entry point\n")
        self.assertEqual(installer.install(self.stage, self.runtime, True)["state"], "already_installed")
        self.assertFalse((self.scripts / "tests").exists())

    def test_requires_idle_acknowledgement(self):
        with self.assertRaises(ValueError):
            installer.install(self.stage, self.runtime)
        self.assertEqual((self.scripts / "build_reader.py").read_text(), "# owner version\n")

    def test_tampered_staged_script_leaves_runtime_untouched(self):
        (self.stage / "scripts/podcast_generator.py").write_text("# altered\n")
        with self.assertRaises(RuntimeError):
            installer.install(self.stage, self.runtime, True)
        self.assertEqual((self.scripts / "build_reader.py").read_text(), "# owner version\n")
        self.assertFalse((self.scripts / "podcast_generator.py").exists())

    def test_symlink_destination_is_not_overwritten(self):
        target = self.root / "outside.py"
        target.write_text("# preserve\n")
        (self.scripts / "podcast_generator.py").symlink_to(target)
        with self.assertRaises(RuntimeError):
            installer.install(self.stage, self.runtime, True)
        self.assertEqual(target.read_text(), "# preserve\n")

    def test_mid_install_failure_restores_original_and_removes_new_files(self):
        real_write = installer.atomic_write
        def fail_one(path, data, mode):
            if path == self.scripts / "podcast_generator.py":
                raise OSError("simulated write failure")
            return real_write(path, data, mode)
        with patch.object(installer, "atomic_write", side_effect=fail_one):
            with self.assertRaises(RuntimeError):
                installer.install(self.stage, self.runtime, True)
        self.assertEqual((self.scripts / "build_reader.py").read_text(), "# owner version\n")
        self.assertFalse((self.scripts / "reader_guardrails.py").exists())
        self.assertFalse((self.scripts / ".molefm-generator-update.lock").exists())

    def test_existing_update_lock_is_preserved(self):
        lock = self.scripts / ".molefm-generator-update.lock"
        lock.write_text("another updater")
        with self.assertRaises(FileExistsError):
            installer.install(self.stage, self.runtime, True)
        self.assertEqual(lock.read_text(), "another updater")


if __name__ == "__main__":
    unittest.main()
