# Install the reviewed Perplexity generator update

This standard-library Python installer transfers the six reviewed reader and podcast scripts from immutable audio commit `280d27653d9985d3f065ed9ee5c39244482174fb` into the existing runtime. It downloads only eight small files (six scripts and two offline test suites), verifies every SHA-256 checksum, checks Python syntax and runs all 34 reader/podcast tests before installation.

No paid API, package installation, AI generation or episode publication is involved. It preserves `run_pipeline.py`, schedules, configuration, credentials, audio, registries and existing HTML. It does not deploy the standalone reader or migrate the runtime to Vercel. The website remains on Vercel.

## Run in the existing runtime shell

Use a shell connected to the existing Perplexity runtime, not a new paid Computer task. These commands do not ask an external agent to edit code or run the pipeline.

Download the installer from this repository to a local file, then validate first:

```sh
curl --fail --silent --show-error --location \
  https://raw.githubusercontent.com/molefm945-svg/molefm-audio/main/pipeline/scripts/install_perplexity_generator.py \
  --output /tmp/install_perplexity_generator.py
python3 /tmp/install_perplexity_generator.py
```

The default result must be `validated_only`; it leaves the runtime untouched. The script requires Python 3.10 or later (the documented runtime uses 3.11).

Between generator jobs, with no job running or starting during the update:

```sh
python3 /tmp/install_perplexity_generator.py \
  --runtime /home/user/workspace/molefm --apply --runner-idle
```

`--runner-idle` is an operator acknowledgement, not scheduler detection. The installer does not stop jobs or change schedules. The lock prevents simultaneous installer runs, not generator runs. Do not install during an active generation job.

For an offline installation from a checked-out copy of the reviewed source, add `--source-tree /path/to/molefm-audio`. Its eight files must match the same pinned hashes; an altered local source fails before any runtime update.

## Result and recovery

Successful installation prints `installed`, six resulting hashes, and a backup directory under the runtime. An identical repeat returns `already_installed`. Original scripts and a receipt are saved in a private `.molefm-generator-backup-*` directory before replacements. Do not publish or commit backups: older scripts may contain obsolete credential literals.

Each replacement is atomic. Ordinary write/readback failures attempt to restore this installer's replacements while preserving concurrent edits. On any error, inspect the reported backup and runtime before resuming jobs. A process or machine crash can leave a partial update and an installer lock; do not delete that lock and retry blindly. The prepared receipt records the exact before/after hashes needed for reconciliation.

The six destination files are:

- `scripts/build_reader.py`
- `scripts/reader_guardrails.py`
- `scripts/podcast_generator.py`
- `scripts/podcast_description.py`
- `scripts/molefm_submitter.py`
- `scripts/generate_rss.py`

The existing protected runner environment must provide `MOLEFM_ADMIN_USERNAME` and `MOLEFM_ADMIN_PIN` for website submission. The installer neither reads nor configures them. Existing rights and editorial review requirements continue to apply to actual generation and publication.

After the next authorized episode, verify its source URLs on MoleFM.com and in the served RSS feed. An installer receipt proves script installation only; it does not prove a new episode was published.

## Maintaining the installer

Update `REVISION` and all eight pinned `HASHES` together only after reviewing and committing a new source release. Installer CI deliberately rejects a local payload that has drifted from the reviewed release. Do not remove the checksum checks to make a newer source pass.
