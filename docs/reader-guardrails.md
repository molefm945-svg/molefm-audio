# Reader audio release checks

The reader stays small for mobile and low-bandwidth listeners. The generator now validates every HTML result before opening `index.html`: it must be **strictly below 1,000,000 UTF-8 bytes**, contain an executable `AUDIO_URLS` JSON object for French, English and Spanish, and load the player from those direct MP3 URLs. Relative MP3 assets and HTTPS downloads, including GitHub Release URLs, are accepted. GitHub file-view pages, other schemes, inline data audio and base64/blob reconstruction are rejected. Embedded playlist, broadcast and podcast audio URLs are checked too.

An invalid result raises an error and leaves the previous `index.html` intact. Existing language voices, hourly newscasts, daily podcast slots and synthesis are unchanged. The check makes no network requests and purchases no services.

Run the offline tests and render the real template with deterministic sample text:

```sh
python3 -m unittest discover -s pipeline/tests -p 'test_reader_guardrails.py' -v
python3 pipeline/scripts/reader_guardrails.py --render-fixture /tmp/molefm-reader-check/index.html
```

Validate a real generated folder before deploying it:

```sh
python3 pipeline/scripts/reader_guardrails.py /path/to/reader/webapp/index.html --check-local-audio
```

The optional local-file check also verifies referenced local MP3 files exist and have MP3 headers. It does not decode audio, fetch external links, prove commercial rights, or substitute for real Safari playback QA.

CI runs when the reader generator, validator, tests, sponsor configuration, workflow or generated reader changes. The same lightweight job also tests the podcast description, submission and RSS paths when their sources or tests change. It always renders and checks the actual reader template without TTS. If `reader/webapp/index.html` is committed, CI also checks that exact artifact and its local MP3 files. The externally generated reader output is not currently in this repository; a green template check is not proof that an external reader deployment updated. The existing audio/podcast runtime must pull the updated scripts; the runtime generator check then covers each real reader output.

## Review item: reader audio safety — 2026-09-09

- Problem: the former workflow watched an absent generated folder and did not check generator changes; it only searched for a few legacy marker strings.
- Hypothesis: checking every generated HTML output and testing regression cases prevents oversized/embedded audio releases that can leave mobile Safari silent, preserving listening completion and trust.
- Changes: shared validator, validation before writing, source-triggered offline CI, negative tests.
- Measurement: generated UTF-8 byte count and pass/fail outcomes; audience or revenue impact has not been measured.
- Local validation: all 16 offline tests passed; the real template rendered to 67,179 UTF-8 bytes and its saved HTML passed the CLI check. Python compilation, workflow YAML/shell parsing and `git diff --check` passed. Hosted CI and deployment evidence belong to the root release report.
- Remaining check: deploy the updated generator to its existing runtime and verify actual Safari playback against the resulting MP3 URLs.
