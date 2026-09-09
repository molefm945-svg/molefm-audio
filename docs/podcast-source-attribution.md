# Podcast source notes

The podcast generator preserves source notes from the saved newscast through the
website submission and RSS feed. This makes the supplied provenance available to
listeners without changing the spoken scripts, French voices, or the three daily
podcast slots.

## Metadata path

1. Numbered stories keep their corresponding `source_backed_stories` metadata
   from the same saved script. `link`, `article_url`, and `url` are preferred over
   `source_url`. The latter can be a feed and is labelled as a supplied source
   link with no identified article.
2. The generator writes `<episode>.mp3.metadata.json` before uploading. It holds
   the exact description, source references, filename, and SHA-256 of the audio.
3. The existing submitter receives `--metadata-file`. It preserves the same
   description in its submission log and requires exact form-field readback
   before clicking the existing save action.
4. RSS validates the sidecar against the audio and uses its description in both
   the RSS description and iTunes summary. The existing feed push also retains
   the sidecars under `podcasts/` in its archive checkout. A later feed rebuild
   can read those retained copies if the runtime sidecars are absent.

Different supplied articles from the same publisher remain listed. Repeated
links are deduplicated. A known publisher homepage is explicitly labelled as a
fallback when the article URL is missing. Unknown publishers receive a missing
URL notice; they are never attributed to Mole FM by default. Links are
provenance, not proof of independent verification.

Older scripts without structured story metadata can only preserve their existing
publisher attribution. Historical article links are not invented. Existing
registry descriptions remain a legacy RSS fallback; otherwise the feed states
that the archived episode has no supplied source links. A mismatched sidecar
stops feed generation instead of silently discarding its source notes.

## Website credentials and outcomes

The website submitter requires `MOLEFM_ADMIN_USERNAME` and `MOLEFM_ADMIN_PIN` in
its environment. It has no embedded credential fallback. Missing credentials
stop website submission before a browser process is started. The generator
reports the website episode as unconfirmed and may still update RSS through its
independent existing path. Configure credentials through the existing protected
runner mechanism; this change does not rotate any credential.

The browser automation still uses the existing website form and success signal.
Offline tests verify exact field preservation and reject truncated/unconfirmed
submissions. They do not prove that a real website database retained the notes.
An authorized live episode must still be read back on MoleFM.com and in the
served RSS feed before claiming publication or distribution.

## Offline verification

Run from the repository root:

```sh
python3 -m unittest discover -s pipeline/tests -p 'test_podcast_attribution.py' -v
```

The tests use synthetic local files and mocked external operations. They cover
source mapping, escaping, deduplication, honest fallbacks, missing credentials,
exact form readback, audio/metadata identity, and the generation-to-RSS path,
including a rebuild from retained archive metadata. They do not synthesize
voices, access services, publish content, or claim actual audio decoding.
