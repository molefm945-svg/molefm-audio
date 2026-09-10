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

Runtime installation subsequently completed in Perplexity: exit 0, state installed, three changed scripts, and all eight destination hashes matched. The installer ran 42 offline tests and preserved a backup under the runtime root. GitHub CI passed at ac87ce0 (run 34503049862).

Remaining activation work: securely connect private worker settings and complete the durable review-to-publication adapter. The Perplexity credential vault save returned FETCHER_CLOUDFLARE_403_ERROR; the credential was not confirmed saved. The unsaved secret field was cleared. No secret was placed in Computer chat. Updated Perplexity credit consumption could not be verified because settings requests were affected by the same provider security check. The existing held site workflow was not enabled. No new broadcast was published by these tests.

## Credential vault follow-up — September 10

After the owner completed Perplexity verification, the credential `Mole FM Azure Speech S0` was successfully saved with header authentication restricted to `eastus.tts.speech.microsoft.com`. The vault displayed the saved credential, and Computer subsequently reported finding it without another approval. No raw key was placed in chat or Git.

A bounded runtime voice-catalog check did not complete: its proxy TLS certificate validation failed, an attempted proxy CA path was invalid, and Perplexity exhausted the account credits before returning an authenticated HTTP result. Do not disable certificate verification to work around this. Runtime authentication and automatic publication remain unverified.

Cost readback: before the connection check, 93 credits remained and automatic refill was false. The previous installer increased task cumulative usage from 244.33 to 327.35 (83.02 credits). The connection attempt increased it to 437.18 (109.83 additional credits), then the UI required more credits. These are consumed platform credits, not new cash purchases. No credits were purchased or automatic refill enabled. No further Computer execution should be used for recurring broadcasts under the near-zero-cost requirement; use a deterministic existing host/runner instead, preserving content review and publication gates.

## Repair follow-up — September 10

The Azure provider now honors explicitly configured trusted proxy CA bundles through `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, or `CURL_CA_BUNDLE`, retaining certificate and hostname verification. Supply a genuine existing runtime CA file; never guess a path or disable verification. Missing/invalid configured files stop before consuming the local allowance. This code change is tested locally; the correct Perplexity CA path and a successful remote handshake are still unverified because Computer has no usable credits (-17 on current readback).

Newscast assembly now stops on any failed narration/pause segment instead of assembling a partial bulletin. The legacy console no longer describes authenticated Azure generation as free Edge TTS. The installer is repinned to payload 9ed2b3a and includes the new completeness tests. No scheduler/publication gate is activated. Both Mac GitHub workers are currently online without Docker.
