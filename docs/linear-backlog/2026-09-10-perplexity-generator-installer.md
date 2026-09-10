# Perplexity generator handoff

Owner request: add the recommended Perplexity generator script.

Purpose: make the previously reviewed reader reliability and podcast source-attribution changes installable in the existing runtime without new services, full repository downloads or manual edits to six files.

Scope: one pinned standard-library installer, offline installation tests, CI coverage and a runtime handoff guide. Preserve schedules, configuration, media and other scripts. Repository started clean on `codex/reader-podcast-improvements-20260909`; audio main was verified at `280d276`. This file is the local task record.

Hypothesis: a checksum-verified, backed-up six-file install will reduce operator work and deployment mistakes. Time saved and revenue effects have not been measured.

Validation: six installer tests cover successful installation, backup and configuration preservation, idempotence, idle acknowledgement, tamper rejection, symlink rejection, failure rollback and lock preservation. The staged payload also runs the 34 existing reader/podcast tests. No real generation or publication is part of these tests.

Result: all 40 checks passed locally. Both the local-source and real GitHub-download validation paths passed; syntax compilation and `git diff --check` passed. An initial manually transcribed test-file checksum was caught by validation and corrected before commit. The final installer pins hashes calculated from the reviewed source files.

Runtime limitation: no connected shell/tool for the existing Perplexity runtime is available in this session. Repository delivery and local simulated installation are distinct from production installation. Follow `docs/perplexity-generator-install.md` in that existing runtime, then read back the next authorized episode's public description and RSS.
