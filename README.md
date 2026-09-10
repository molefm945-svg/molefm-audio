# Mole FM 94.5 — Audio Archive

AI-powered Haitian radio serving the diaspora 24/7.

## Content
- **Hourly newscasts** — 6 verified stories in French, with English and Spanish translations
- **Daily podcasts** — 18-22 min deep-dive episodes (The Daily × BBC format)

## How It Works
Audio files are generated automatically by the Mole FM pipeline and published here as GitHub Releases.
Each release contains the MP3 and is permanently accessible via URL.

## Listen
- Reader: https://molefm-reader.pplx.app
- Website: https://www.molefm.com

## Audio URL Format
- Newscasts: `https://github.com/molefm945-svg/molefm-audio/releases/download/newscast-YYYYMMDD-HHMM/newscast_YYYYMMDD_HHMM.mp3`
- Podcasts: `https://github.com/molefm945-svg/molefm-audio/releases/download/podcast-fr-YYYYMMDD-HHMM/podcast_fr_YYYYMMDD_HHMM.mp3`

## Generator update

Use the [Perplexity generator installation guide](docs/perplexity-generator-install.md)
to install the reviewed reader and podcast source-attribution scripts in the existing
runtime. The installer verifies checksums, runs offline tests and backs up changed
files. Validation is the default; it does not generate or publish episodes.
