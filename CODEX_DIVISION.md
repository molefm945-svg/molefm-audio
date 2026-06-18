# Mole FM — Codex vs. Perplexity Computer Division of Labor

## Goal
Use your $200/month Codex subscription to handle all **code work, file edits, and
background automation** so Perplexity Computer credits are reserved for **real-time
decisions, live pipeline runs, and notifications** only.

---

## The Rule
> **If it touches code or files → Codex.**
> **If it requires live web access, real-time decisions, or user notifications → Computer.**

---

## What Codex Owns (zero Computer credits)

### 1. Code Improvements (bulk of the work)
- Edit `video_generator.py`, `youtube_optimizer.py`, `podcast_generator.py`, etc.
- Add new features to `molefm-site` frontend (React components, bug fixes)
- Refactor scripts, fix Python warnings, improve error handling
- Build new scripts (biography improvements, new cron tasks)
- All `molefm-site` frontend changes → `npm run build` → commit to GitHub

### 2. YouTube Pipeline Automation (via GitHub Actions)
- After every newscast commit to `molefm-audio` repo:
  - Run `video_generator.py` → generate MP4
  - Run `youtube_optimizer.py` → generate metadata JSON
  - Commit MP4 + metadata to `molefm-audio/videos/queue/`
- Trigger: `push` to `molefm-audio/audio/*.mp3`
- Codex Triggers (March 2026 feature) can watch the repo and auto-run

### 3. Source Attribution Completion (the in-progress task)
- Finish editing `news_fetcher.py` log_verification_run() — add link/description fields
- Finish editing `content_pack_generator.py` — pass link through to content pack
- Update `Home.tsx`, `Local.tsx`, `Podcasts.tsx` source link UI
- Build + deploy to Vercel (run `deploy_vercel.py`)
- All of this is pure code editing → perfect for Codex

### 4. Weekly Code Maintenance
- Review `pipeline.log` → identify recurring errors → patch scripts
- Optimize TTS generation speed
- Add new RSS sources discovered by AutoSearch
- Keep `AGENTS.md` updated with new decisions

### 5. A/B Title Testing Loop (YouTube growth)
- Read YouTube Studio export CSVs (when you paste them)
- Analyze CTR per title variant
- Auto-update `youtube_optimizer.py` keyword bank with winners
- Generate next week's title variants

---

## What Computer Owns (preserves credits)

### 1. Hourly Pipeline Cron (ff128060)
- Runs `run_pipeline.py` → sends you the notification
- Cannot be replaced by Codex — needs live web (RSS fetch) + notification

### 2. Podcast Cron (9f4a6b29) 
- Runs `podcast_generator.py` 3x/day → notification
- Same reason — live RSS + notification

### 3. AutoSearch Cron (3384244f)
- Probes live RSS candidate URLs → cannot pre-cache
- Keeps running here

### 4. Admin Decisions
- You ask a question → Computer answers from live context
- Deploy to Vercel when you ask (if not already automated via Codex)
- Approval queue notifications

### 5. New Feature Design
- Architecture decisions, push-back on bad ideas, strategy
- "Is this a good idea?" → Computer
- "Build it" → Codex

---

## How to Use Codex for Mole FM

### Setup (one-time, 10 minutes)
1. Open Codex at codex.openai.com or the desktop app
2. Connect your GitHub repo: `molefm945-svg/molefm-site`
3. Also connect: `molefm945-svg/molefm-audio`
4. The `AGENTS.md` file in `molefm-audio` already gives Codex full context

### Daily workflow
```
YOU:      "Codex, finish the source attribution task from AGENTS.md step 3"
CODEX:    Reads AGENTS.md → edits news_fetcher.py + content_pack_generator.py 
          + Home.tsx + Local.tsx → runs npm run build → commits to GitHub
COMPUTER: Deploys to Vercel on your next request (or Codex can run deploy_vercel.py too)
```

### Giving Codex tasks
Use the AGENTS.md file as the briefing document. Always say:
- "Read AGENTS.md first"
- "Commit when done"
- "Do not touch the TTS voices config"

---

## AGENTS.md for Codex (save this to both repos)

See /home/user/workspace/molefm/AGENTS.md — keep it updated.
Codex reads this file at the start of every task as its mission briefing.
