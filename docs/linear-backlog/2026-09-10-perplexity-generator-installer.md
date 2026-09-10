# Perplexity generator handoff

Owner request: add the recommended Perplexity generator script.

Purpose: make the previously reviewed reader reliability and podcast source-attribution changes installable in the existing runtime without new services, full repository downloads or manual edits to six files.

Scope: one pinned standard-library installer, offline installation tests, CI coverage and a runtime handoff guide. Preserve schedules, configuration, media and other scripts. Repository started clean on `codex/reader-podcast-improvements-20260909`; audio main was verified at `280d276`. This file is the local task record.

Hypothesis: a checksum-verified, backed-up six-file install will reduce operator work and deployment mistakes. Time saved and revenue effects have not been measured.

Validation: six installer tests cover successful installation, backup and configuration preservation, idempotence, idle acknowledgement, tamper rejection, symlink rejection, failure rollback and lock preservation. The staged payload also runs the 34 existing reader/podcast tests. No real generation or publication is part of these tests.

Result: all 40 checks passed locally. Both the local-source and real GitHub-download validation paths passed; syntax compilation and `git diff --check` passed. An initial manually transcribed test-file checksum was caught by validation and corrected before commit. The final installer pins hashes calculated from the reviewed source files.

Runtime follow-up, 2026-09-10: after the owner activated Pro and authorized continuation, access through the existing Perplexity Computer task was restored. Its `/home/user/workspace/molefm` directory was absent. A bounded restore copied only `pipeline/scripts` (19 files) and `pipeline/config` (two files) from verified commit `a530818a41e966dda9e8bd2b71eb34aae482a9b3` into the previously absent directory. Configuration is historical backup state, not current broadcast evidence; archived media and research were not restored.

The pinned installer ran in that sandbox with `--source-tree /tmp/molefm-restore --runtime /home/user/workspace/molefm --apply --runner-idle`. Its terminal output showed exit 0 and `already_installed`, revision `280d27653d9985d3f065ed9ee5c39244482174fb`, `changed: []`. The six files copied from the checkout already matched the intended update. Both offline suites passed (16 + 18 tests). All six destination SHA-256 values were separately read from terminal output and matched the local installer manifest. No backup was created because no pre-existing runtime files were replaced.

Remaining activation prerequisites: `MOLEFM_ADMIN_USERNAME` and `MOLEFM_ADMIN_PIN` were both absent (presence checked without reading values). No Mole FM scheduler was identified in the restored sandbox; this is not an audit of schedules on other hosts or the Perplexity platform. No dependencies, voice service, live episode generation, website submission, RSS publication, standalone-reader deployment or recurring execution were activated or verified in this restore. Existing external services and schedules were not changed. Restore approved narration and protected publication integration, verify an authorized episode end to end, and only then activate recurring execution.
