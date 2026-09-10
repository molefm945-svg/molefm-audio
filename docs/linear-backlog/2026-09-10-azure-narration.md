# Azure narration connection

Owner authorized automatic broadcasting and Azure trial setup. Hypothesis: authenticated, commercially licensed French narration with a bounded usage allowance will reduce release delays while preserving trust and controlling cost.

Scope: replace the two core Python narration entry points with Azure Speech; preserve the existing voices, cadence, source attribution and publication gates. No Edge fallback. Keep credentials outside Git. Runtime installation and automatic publication remain separate acceptance steps.

Live setup: Azure Speech resource `molefm-denise-fr`, East US, Standard S0 deployed successfully on September 10. Portal showed $200 trial credits, 30 days remaining and $0 amount due; no pay-as-you-go upgrade was performed. Authenticated voice inventory returned `fr-FR-DeniseNeural` with GA status. One private 245-character recording produced a valid 16.584-second MP3, SHA-256 `c09685e6c3890947b8b697f366c6a5c29aef44d42521d2bfeb7760863e9d2feb`. Estimated generation cost at $15/million characters: $0.003675, not a reconciled invoice.

Implementation plan: shared standard-library provider, atomic monthly reservation ledger, expiration check, no provider retries, MP3 response validation and provenance sidecar. Run offline failure-path tests and one bounded provider integration check. Then commit the reviewed change. Do not enable the existing held workflow until its review-to-publication adapter is complete.

Microsoft's paid-tier prebuilt TTS output grant supports commercial use: https://www.microsoft.com/licensing/terms/en-US/productoffering/MicrosoftAzure/allprograms . Applying that grant to S0 funded by valid trial credits follows the documented paid resource tier; credits are temporary funding, not perpetual free service.
