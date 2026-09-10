#!/usr/bin/env python3
"""Install the reviewed reader/podcast update; no generation or publication.

Default: download, verify and test in a temporary directory only.
Apply only between runs, with --apply --runner-idle.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

REVISION = "2b8c6decf9f90c6929086fcb79ad8f1190a8e577"
BASE_URL = f"https://raw.githubusercontent.com/molefm945-svg/molefm-audio/{REVISION}/pipeline/"
HASHES = {
    "scripts/build_reader.py": "9fd17225b07097d7abe1f1b1f607ac4b7a069f64a27a683b82aa9ab7e301ea14",
    "scripts/reader_guardrails.py": "0a0041e60ecceb4a8a737a361f83e17e81042f80f741979b4788e2646a3b49b2",
    "scripts/podcast_generator.py": "2bb02d8c2c3394d266d0cdf047236b91684b6dc69ade5779fe3dfbf7a262a3ba",
    "scripts/podcast_description.py": "5e73f6e6875ff045de4673496d07dddf826df23867eb459bc9293c7a3a7576a8",
    "scripts/molefm_submitter.py": "754c76ecf67699281b3b062cc3aa118cb000eafbfab3a93edb72ff4b79135c18",
    "scripts/generate_rss.py": "8d1f547eadf2c8071b4ca5756ad073c9ea6ef25c4e66019112945d3fb99d2634",
    "tests/test_reader_guardrails.py": "d47dddc7992f67ffe908a5b73915911f33b62124467a61865b11959feaee1bfe",
    "tests/test_podcast_attribution.py": "091ca7cd20438b139c61cc3221ad2376946292997e580c13097eba72098b27d4",
    "scripts/azure_speech.py": "7d0d3ad6232d0f5a6c31ff96934652a33c3dd2c31eabc3f2661e0107eadffe7f",
    "scripts/tts_generator.py": "53381cfa300f82e838f1bc441ae3459ad8bf895976e9fdf4d22adb84d4e1ea38",
    "tests/test_azure_speech.py": "13a14da1fa3da8ce35d42cbbd905d89474d03e93641f9c00b06b0c47e9fddc12"
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stage_files(stage, source_tree=None):
    for relative, expected in HASHES.items():
        if source_tree is None:
            with urllib.request.urlopen(BASE_URL + relative, timeout=30) as response:
                data = response.read(1_000_001)
        else:
            data = (source_tree / "pipeline" / relative).read_bytes()
        if len(data) > 1_000_000 or digest(data) != expected:
            raise ValueError(f"Checksum mismatch: {relative}; runtime untouched")
        compile(data, relative, "exec")
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)


def validate_stage(stage):
    # These pinned suites mock generation, network, browser and publishing calls.
    environment = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}
    for suite in ("test_reader_guardrails.py", "test_podcast_attribution.py", "test_azure_speech.py"):
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", suite],
                       cwd=stage, env=environment, check=True, timeout=120)


def runtime_directory(root):
    root = Path(os.path.abspath(root))
    scripts = root / "scripts"
    if not root.is_dir() or not scripts.is_dir():
        raise ValueError("Existing runtime and scripts directory required")
    if any(path.is_symlink() for path in (scripts, *scripts.parents)):
        raise ValueError("Runtime path must not contain symlinks")
    if not (scripts / "run_pipeline.py").is_file():
        raise ValueError("Existing run_pipeline.py required; refusing unrelated directory")
    return scripts


def snapshot(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Refusing non-regular destination: {path.name}")
    return path.read_bytes() if path.exists() else None


def atomic_write(path, data, mode):
    descriptor, temporary = tempfile.mkstemp(prefix=".molefm-update-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def install(stage, root, runner_idle=False):
    if not runner_idle:
        raise ValueError("Run between generator jobs and acknowledge --runner-idle")
    scripts = runtime_directory(root)
    lock = scripts / ".molefm-generator-update.lock"
    with lock.open("x") as handle:
        handle.write(str(os.getpid()))
    backup = None
    changed = []
    try:
        names = [Path(relative).name for relative in HASHES if relative.startswith("scripts/")]
        before = {name: snapshot(scripts / name) for name in names}
        modes = {name: (scripts / name).stat().st_mode & 0o777 if before[name] is not None else 0o644 for name in names}
        after = {name: (stage / "scripts" / name).read_bytes() for name in names}
        for name in names:
            if digest(after[name]) != HASHES[f"scripts/{name}"]:
                raise ValueError(f"Staged checksum changed: {name}")
        pending = [name for name in names if before[name] != after[name]]
        if not pending:
            return {"state": "already_installed", "revision": REVISION, "changed": []}
        backup = Path(tempfile.mkdtemp(prefix=".molefm-generator-backup-", dir=scripts.parent))
        receipt = {"revision": REVISION, "state": "prepared", "changed": pending,
                   "before": {name: digest(data) if data is not None else None for name, data in before.items()},
                   "after": {name: digest(data) for name, data in after.items()}}
        for name in pending:
            if before[name] is not None:
                atomic_write(backup / name, before[name], 0o600)
        atomic_write(backup / "receipt.json", json.dumps(receipt, indent=2).encode(), 0o600)
        try:
            for name in pending:
                if snapshot(scripts / name) != before[name]:
                    raise ValueError(f"Runtime changed during update: {name}")
                atomic_write(scripts / name, after[name], modes[name])
                changed.append(name)
            if any(snapshot(scripts / name) != after[name] for name in names):
                raise ValueError("Installed file readback mismatch")
            receipt["state"] = "installed"
            atomic_write(backup / "receipt.json", json.dumps(receipt, indent=2).encode(), 0o600)
        except Exception:
            # Restore only our unchanged replacements; never overwrite concurrent work.
            for name in reversed(changed):
                if snapshot(scripts / name) != after[name]:
                    continue
                if before[name] is None:
                    (scripts / name).unlink()
                else:
                    atomic_write(scripts / name, before[name], modes[name])
            raise
        return {**receipt, "backup": str(backup), "publication_performed": False}
    except Exception as error:
        raise RuntimeError(f"Update stopped; inspect runtime before resuming jobs. Backup: {backup}") from error
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("/home/user/workspace/molefm"))
    parser.add_argument("--source-tree", type=Path, help="Use a local molefm-audio checkout instead of downloading")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--runner-idle", action="store_true", help="Confirm no generator jobs are running or starting during this update")
    args = parser.parse_args()
    if args.apply:
        if not args.runner_idle:
            parser.error("--apply requires --runner-idle; install between scheduled runs")
        runtime_directory(args.runtime)
    with tempfile.TemporaryDirectory(prefix="molefm-generator-check-") as directory:
        stage = Path(directory)
        stage_files(stage, args.source_tree)
        validate_stage(stage)
        result = install(stage, args.runtime, args.runner_idle) if args.apply else {
            "state": "validated_only", "revision": REVISION, "runtime_changed": False,
            "publication_performed": False, "next": "Run with --apply --runner-idle in the existing runtime between jobs"}
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
