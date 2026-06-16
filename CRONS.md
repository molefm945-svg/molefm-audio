# Mole FM — Scheduled Cron Reference

All crons run in Perplexity Computer. Times are UTC; Haiti = UTC-4.

| Cron ID | Name | UTC Schedule | Haiti Time | What It Does |
|---------|------|-------------|------------|--------------|
| `ff128060` | Hourly News Pipeline | `0 * * * *` | Top of every hour | Fetch news → TTS → reader → GitHub → molefm.com |
| `9f4a6b29` | FR Podcast 3x Daily | `0 1,16,19 * * *` | 21h, 12h, 15h | Generate 18-22 min podcast → GitHub → molefm.com |
| `3384244f` | AutoSearch Daily | `0 4 * * *` | Midnight | Karpathy RSS discovery engine |
| `05c8e13f` | Podcast Optimizer | `30 5 * * *` | 01:30 | Quality analysis + improvement patches |

## Podcast Slot Labels
- `0 1 * * *` UTC = **soir** (21h00 Haïti)
- `0 16 * * *` UTC = **midi** (12h00 Haïti)
- `0 19 * * *` UTC = **après-midi** (15h00 Haïti)

## To Restore Crons After a Reset
Crons are managed in Perplexity Computer. If they stop running:
1. Open a new session with Perplexity Computer
2. Load the `molefm-ops` skill
3. Re-create each cron using `schedule_cron` with the IDs and schedules above
4. Reference `AGENTS.md` for the full cron task descriptions
