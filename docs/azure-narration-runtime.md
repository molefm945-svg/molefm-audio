# Azure narration runtime

The core newscast and podcast generators now require authenticated Azure Speech.
They do not fall back to Edge TTS. Existing voice assignments are preserved.

Configure these variables in the private worker environment, never in Git or the browser client:

- `AZURE_SPEECH_REGION`: `eastus` for the current Mole FM S0 resource.
- `AZURE_SPEECH_KEY_FILE`: path to a private key file; alternatively use the worker's `AZURE_SPEECH_KEY` secret.
- `MOLEFM_AZURE_USAGE_FILE`: durable local JSON ledger, shared by every process using this worker allowance. Do not reset or duplicate it between jobs.
- `MOLEFM_AZURE_ENABLED_UNTIL`: an explicit UTC timestamp before the funded authorization expires. Missing, naive or expired timestamps stop generation.
- `MOLEFM_AZURE_MONTHLY_CHARACTERS`: worker allowance, maximum 1,000,000 characters. At $15/million this is about $15 of narration before taxes; actual regional rates and other Azure usage are separate.

This ledger is a worker safeguard, **not an Azure-wide spending limit**. The portal trial currently shows $200 credits and requires an upgrade to continue after expiry; no upgrade was performed. Do not convert the trial to pay-as-you-go automatically. Refresh funding/protection evidence before enabling unattended runs.

Each request reserves characters atomically before contacting Azure. Failed or uncertain requests keep their reservation and are not retried. Existing audio files are not overwritten. Generated MP3 files receive an `.azure.json` provenance sidecar. Files still need the ordinary content, rights and publication review path; these sidecars do not invent review approval.

Installer: `pipeline/scripts/install_perplexity_generator.py` now stages eight runtime scripts and three offline test suites from its pinned revision. Run a dry run first, then apply only between jobs with `--apply --runner-idle`. The earlier six-script installation remains historical evidence, not proof this Azure update is installed remotely.

Verification on September 10: 48 offline tests passed. Installer staging independently passed 42 payload tests. A real call through the shared provider generated a decodable 49-character MP3, SHA-256 `739d73fd8b656deef6050c046e1d060ec5cedbc5c5983aa8bdad7e8b4f24452c`. Combined with the initial 245-character test, 294 characters were generated, estimated $0.00441 at $15/million, not an invoice reconciliation. The live provider test used a 1,000-character worker allowance and authorization ending September 11 at 00:00 UTC.

Remaining activation work: install this new payload and private worker settings in the selected persistent runtime; complete and verify the durable review-to-publication adapter. The existing held site workflow was not enabled. No new broadcast was published by these tests.
