# Broadcast repair — September 10, 2026

Owner request: fix Perplexity and activate broadcasting without unnecessary charges.

Hypothesis: stopping incomplete narration and honoring an explicitly configured trusted proxy CA prevents silent partial bulletins and avoids insecure TLS workarounds.

Implemented: Azure HTTPS requests use a validating TLS context, loading operator-provided SSL_CERT_FILE, REQUESTS_CA_BUNDLE and CURL_CA_BUNDLE roots. Invalid bundles stop before usage reservation. The newscast generator stops immediately on failed narration or pause assembly, preserving private partial files for diagnosis. Removed obsolete Edge/free billing claims.

Verification: 54 offline tests passed, including complete/failed segment assembly and TLS verification/bundle failure. No paid synthesis or remote Computer execution was performed during this repair. Runtime installation and real proxy handshake remain unverified.

Live account/worker readback: Perplexity Pro available credits -17, refill off, no payment method displayed. Three credit-grant pages contain historical grants; no unused 4,000-credit promotional grant was shown. Eligibility for the advertised limited-time Pro offer is not established. Both existing Mac GitHub runners are online and idle; they run natively, so Docker is unnecessary.

Publication remains blocked: site hourly workflow deliberately outputs publication_allowed=false and still uses its older voice-generation path. Its full-edition durable review/publication adapter is not complete. The separate short-bulletin path requires current exact-media reviews. Existing September 9 bulletin has expired; no review or freshness evidence was extended. Repairing Python does not enable this site workflow or renew expired media.

Next: install this tested revision on the chosen runtime, supply its actual trusted proxy CA only if using Perplexity, and qualify a current reviewed full edition through the protected site adapter. No credits bought, no auto-refill enabled, no Azure billing upgrade, no public audio published.
