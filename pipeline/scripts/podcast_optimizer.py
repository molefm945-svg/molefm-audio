"""
Mole FM Podcast Revenue Optimizer — Karpathy-style Self-Improvement
====================================================================
Inspired by Andrej Karpathy's iterative self-improvement philosophy:
evaluate everything, keep what works, discard what doesn't — driven
by a clear quantitative goal.

REVENUE GOAL: $1,000/day ($30,000/month)
REALISTIC TIMELINE (based on research):
  Month  1–6:   $200–$2,500/month   (first sponsors, affiliate, Patreon launch)
  Month  7–12:  $2,000–$8,000/month (2–3 direct sponsors + membership)
  Year   2:     $8,000–$20,000/month (full blended stack)
  Year   2–3:   $30,000+/month → $1,000/day (blended model)

PATH TO $1K/DAY (not ads alone — blended model):
  1. Direct diaspora sponsorships ($500–$3,000/month flat per sponsor)
     — Wire services (MoneyGram, Western Union, Unitransfer Haiti)
     — Telecoms (Digicel, Natcom)
     — Caribbean consumer brands, real estate, travel
  2. Patreon/membership ($5–$15/month — target 500 members = $2,500–$7,500/mo)
  3. WhatsApp premium digest ($3–$10/month — target 1,000 subscribers)
  4. Programmatic ads (Podcorn, Spotify Partner at 1K+ listeners)
  5. Events + licensing (Year 2+)

WHAT THIS SCRIPT DOES (runs daily):
  1. ANALYZE    — Read episode quality logs, identify format regressions
  2. BENCHMARK  — Compare Mole FM format against research standards
  3. GENERATE   — Write specific improvement patches for podcast_generator.py
  4. REVENUE    — Track progress toward blended $1K/day goal, flag next action
  5. LOG        — Write daily optimization report to research/optimizer_log.json

Run daily at 05:00 UTC (01:00 Haiti) via scheduled cron.
"""

import json
import os
import datetime
import glob

SCRIPTS_DIR  = "/home/user/workspace/molefm/scripts"
RESEARCH_DIR = "/home/user/workspace/molefm/research"
PODCAST_DIR  = "/home/user/workspace/molefm/audio/podcasts"

# ── Revenue goal tracking ─────────────────────────────────────────────────────
DAILY_GOAL_USD      = 1000    # target: $1,000/day
MONTHLY_GOAL_USD    = 30000   # target: $30,000/month

# Current revenue estimates (updated manually or by future integrations)
REVENUE_STATE_FILE  = os.path.join(RESEARCH_DIR, "revenue_state.json")

def load_revenue_state():
    try:
        with open(REVENUE_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "phase": "pre-launch",
            "month_num": 1,
            "sponsors_direct": [],      # {name, monthly_usd, start_date}
            "patreon_members": 0,
            "patreon_avg_usd": 5.0,
            "whatsapp_subscribers": 0,
            "whatsapp_avg_usd": 5.0,
            "programmatic_monthly_est": 0,
            "other_monthly_usd": 0,
            "total_monthly_est": 0,
            "listener_estimate": 0,     # estimated monthly unique listeners
            "downloads_per_episode": 0, # estimated
            "last_updated": datetime.date.today().isoformat(),
            "notes": "Pre-launch. First episode generated. No revenue yet.",
        }

def save_revenue_state(state):
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    with open(REVENUE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def calculate_revenue_estimate(state):
    sponsor_total = sum(s.get("monthly_usd", 0) for s in state.get("sponsors_direct", []))
    patreon_total = state.get("patreon_members", 0) * state.get("patreon_avg_usd", 5.0)
    wa_total      = state.get("whatsapp_subscribers", 0) * state.get("whatsapp_avg_usd", 5.0)
    prog_total    = state.get("programmatic_monthly_est", 0)
    other_total   = state.get("other_monthly_usd", 0)
    total         = sponsor_total + patreon_total + wa_total + prog_total + other_total
    return {
        "direct_sponsors": sponsor_total,
        "patreon": patreon_total,
        "whatsapp": wa_total,
        "programmatic": prog_total,
        "other": other_total,
        "total_monthly": total,
        "daily_est": total / 30,
        "pct_of_goal": (total / MONTHLY_GOAL_USD) * 100,
        "gap_monthly": max(0, MONTHLY_GOAL_USD - total),
    }


# ── Episode quality analysis ──────────────────────────────────────────────────

def load_quality_logs():
    log_file = os.path.join(RESEARCH_DIR, "episode_quality_log.json")
    try:
        with open(log_file, "r") as f:
            return json.load(f)
    except Exception:
        return []

def analyze_quality_trends(logs):
    """Identify systematic quality issues across recent episodes."""
    if not logs:
        return {"status": "no_data", "findings": []}

    recent = logs[-10:]  # last 10 episodes

    findings = []
    flags_counter = {}
    duration_sum = 0
    turns_sum = 0
    in_range_count = 0

    for ep in recent:
        for flag in ep.get("flags", []):
            key = flag.split(":")[0]
            flags_counter[key] = flags_counter.get(key, 0) + 1
        duration_sum += ep.get("duration_mins", 0)
        turns_sum += ep.get("turns", 0)
        if ep.get("in_target_range", False):
            in_range_count += 1

    avg_duration = duration_sum / len(recent)
    avg_turns    = turns_sum / len(recent)
    in_range_pct = (in_range_count / len(recent)) * 100

    # Generate specific findings
    for flag_type, count in flags_counter.items():
        if count >= 3:  # pattern (not one-off)
            findings.append({
                "type": "SYSTEMATIC",
                "flag": flag_type,
                "frequency": f"{count}/{len(recent)} episodes",
                "severity": "HIGH" if count >= 7 else "MEDIUM",
            })

    if avg_duration < 12:
        findings.append({
            "type": "DURATION",
            "issue": f"Average episode {avg_duration:.1f} min — below 18-min target",
            "action": "Expand Act 2 complication section with more diaspora context",
            "severity": "HIGH",
        })
    elif avg_duration > 25:
        findings.append({
            "type": "DURATION",
            "issue": f"Average episode {avg_duration:.1f} min — above 22-min ceiling",
            "action": "Cut brief stories section; tighten Act 1 setup",
            "severity": "MEDIUM",
        })

    return {
        "status": "analyzed",
        "episodes_analyzed": len(recent),
        "avg_duration_mins": round(avg_duration, 1),
        "avg_turns": round(avg_turns, 1),
        "in_target_range_pct": round(in_range_pct, 1),
        "systematic_flags": flags_counter,
        "findings": findings,
    }


# ── Format benchmark comparison ───────────────────────────────────────────────

BENCHMARK_STANDARDS = {
    "target_duration_range": (18, 22),      # minutes
    "target_turns_range": (25, 45),         # dialogue turns
    "max_avg_words_per_turn": 50,           # words — above = monologue risk
    "completion_rate_target": 0.75,         # 75%+
    "hook_within_words": 18,               # listener decides in first 18 words
    "mid_roll_position_pct": (0.40, 0.60), # 40–60% of runtime
    "ideal_format": "The Daily × BBC Global × Hugo Décrypte",
    "tone": "informed friend, not news anchor",
}

def generate_improvement_patches(quality_analysis, revenue_state):
    """
    Generate specific, actionable patches for the podcast generator.
    These are written to podcast_improvement_tips.json for the generator to read.
    """
    patches = []

    # Duration fixes
    avg_dur = quality_analysis.get("avg_duration_mins", 0)
    if avg_dur < 12:
        patches.append({
            "id": "EXPAND_ACT2",
            "priority": 1,
            "area": "duration",
            "description": "Episode too short — expand Act 2 complication",
            "specific_fix": "Add 3–4 more Henri/Denise exchanges in Act 2. Henri should give historical context (2–3 sentences). Denise should ask about diaspora implications. Add one specific 'what does this mean for someone in Miami/Montréal?' exchange.",
            "expected_impact": "+4–6 minutes to episode duration",
        })
    elif avg_dur > 25:
        patches.append({
            "id": "TRIM_BRIEF",
            "priority": 1,
            "area": "duration",
            "description": "Episode too long — trim brief stories section",
            "specific_fix": "Limit brief_stories to 1 item max. Remove sports if weather already covered. Tighten outro to 3 turns max.",
            "expected_impact": "-3–5 minutes",
        })

    # Turn length fixes
    flags = quality_analysis.get("systematic_flags", {})
    if flags.get("TURNS_TOO_LONG", 0) >= 3:
        patches.append({
            "id": "SHORTEN_TURNS",
            "priority": 1,
            "area": "authenticity",
            "description": "Turns too long — sounds like reading, not talking",
            "specific_fix": "Break any turn over 40 words into two turns. Henri makes a statement. Denise reacts or asks. No turn should be a paragraph — aim for 15–35 words per turn.",
            "expected_impact": "+10–15% authenticity score, estimated +5% completion",
        })

    # Revenue-driven improvements
    rev = calculate_revenue_estimate(revenue_state)
    if rev["total_monthly"] < 1000:
        patches.append({
            "id": "PATREON_CTA",
            "priority": 2,
            "area": "monetization",
            "description": "No Patreon revenue — add organic CTA to outro",
            "specific_fix": "In outro, add: 'Si vous voulez soutenir Mole FM directement — et avoir accès à des contenus exclusifs — on a un espace Patreon. C'est vous qui rendez ça possible.' Natural, not pushy. One mention per episode.",
            "expected_impact": "First $200–$500/month when 40–100 members join",
        })
        patches.append({
            "id": "SPONSOR_PITCH",
            "priority": 1,
            "area": "monetization",
            "description": "No direct sponsors beyond Mathurin — need outreach list",
            "specific_fix": "Target outreach: 1) MoneyGram/Unitransfer (Haiti remittances — high CPM niche), 2) Digicel Haiti (telecom), 3) Caribbean Airlines / travel, 4) Haitian cultural orgs in diaspora cities. Offer: $300–$1,000/month flat for mid-roll read.",
            "expected_impact": "2 sponsors = $600–$2,000/month",
        })

    if revenue_state.get("listener_estimate", 0) < 1000:
        patches.append({
            "id": "DISTRIBUTION_FIRST",
            "priority": 1,
            "area": "growth",
            "description": "Listener count too low for any monetization — distribution is the bottleneck",
            "specific_fix": "Before optimizing format further: (1) Submit to Apple Podcasts + Spotify via RSS, (2) Post clips on WhatsApp diaspora groups, (3) Cross-promote on Haitian Facebook groups (Boston, Miami, Montreal), (4) Engage Haitian journalists on Twitter/X.",
            "expected_impact": "500–2,000 monthly listeners in 30–60 days with active distribution",
        })

    return patches


# ── Revenue milestone tracker ─────────────────────────────────────────────────

MILESTONES = [
    {"monthly": 500,   "daily": 17,   "label": "First Coffee Money",      "unlock": "Submit to Apple Podcasts"},
    {"monthly": 2000,  "daily": 67,   "label": "First Real Sponsor",      "unlock": "Approach Unitransfer/MoneyGram"},
    {"monthly": 5000,  "daily": 167,  "label": "Viable Side Income",      "unlock": "Hire part-time content researcher"},
    {"monthly": 10000, "daily": 333,  "label": "Professional Operation",  "unlock": "Full Spotify Partner, premium CPM"},
    {"monthly": 20000, "daily": 667,  "label": "Serious Media Property",  "unlock": "Haiti correspondent, events"},
    {"monthly": 30000, "daily": 1000, "label": "Goal: $1K/Day",           "unlock": "Network syndication, licensing"},
]

def get_current_milestone(monthly_est):
    achieved = [m for m in MILESTONES if monthly_est >= m["monthly"]]
    next_up  = next((m for m in MILESTONES if monthly_est < m["monthly"]), None)
    return {
        "current": achieved[-1] if achieved else None,
        "next": next_up,
        "pct_to_next": ((monthly_est / next_up["monthly"]) * 100) if next_up else 100,
    }


# ── Daily report generator ────────────────────────────────────────────────────

def generate_daily_report(quality_analysis, revenue_state, patches):
    rev = calculate_revenue_estimate(revenue_state)
    milestone = get_current_milestone(rev["total_monthly"])
    now = datetime.datetime.now()

    # Count episodes generated
    podcasts = glob.glob(os.path.join(PODCAST_DIR, "podcast_fr_*.mp3"))
    episode_count = len(podcasts)

    report = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),

        "revenue_summary": {
            "monthly_estimate_usd": round(rev["total_monthly"], 2),
            "daily_estimate_usd": round(rev["daily_est"], 2),
            "goal_monthly_usd": MONTHLY_GOAL_USD,
            "goal_daily_usd": DAILY_GOAL_USD,
            "pct_of_goal": round(rev["pct_of_goal"], 1),
            "gap_to_goal_monthly": round(rev["gap_monthly"], 2),
            "breakdown": {
                "direct_sponsors": rev["direct_sponsors"],
                "patreon_members": rev["patreon"],
                "whatsapp_digest": rev["whatsapp"],
                "programmatic": rev["programmatic"],
            },
        },

        "milestone": {
            "current": milestone["current"]["label"] if milestone["current"] else "Pre-launch",
            "next": milestone["next"]["label"] if milestone["next"] else "Goal achieved",
            "next_unlock": milestone["next"]["unlock"] if milestone["next"] else "Scale",
            "pct_to_next": round(milestone["pct_to_next"], 1),
        },

        "format_quality": {
            "episodes_generated": episode_count,
            "avg_duration_mins": quality_analysis.get("avg_duration_mins", 0),
            "in_target_range_pct": quality_analysis.get("in_target_range_pct", 0),
            "systematic_issues": quality_analysis.get("systematic_flags", {}),
            "findings": quality_analysis.get("findings", []),
        },

        "improvement_patches": patches,

        "top_priority_action": patches[0]["specific_fix"] if patches else "No immediate fixes needed — maintain format.",

        "honest_assessment": {
            "7_day_revenue": "~$0 without distribution. Focus: get podcast on Spotify/Apple + WhatsApp diaspora groups.",
            "30_day_revenue": f"$300–$1,500 realistic with 1 sponsor + active distribution.",
            "90_day_revenue": f"$1,000–$4,000 realistic with 2–3 sponsors + 50–200 Patreon members.",
            "1_year_revenue": f"$5,000–$15,000/month if daily publishing + 2,000+ monthly listeners.",
            "1k_per_day_timeline": "Year 2–3 via blended model. Ads alone require 300K+ monthly downloads — unrealistic in Year 1.",
            "key_bottleneck": "DISTRIBUTION first. Format quality is necessary but useless without listeners.",
        },

        "next_run": (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d 05:00 UTC"),
    }

    return report


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print(f"\n=== Mole FM Podcast Revenue Optimizer ===")
    print(f"  Goal: ${DAILY_GOAL_USD}/day | Run: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Load data
    quality_logs    = load_quality_logs()
    revenue_state   = load_revenue_state()

    # 2. Analyze
    quality_analysis = analyze_quality_trends(quality_logs)
    print(f"  Episodes analyzed: {quality_analysis.get('episodes_analyzed', 0)}")
    print(f"  Avg duration: {quality_analysis.get('avg_duration_mins', 0):.1f} min")
    print(f"  In target range: {quality_analysis.get('in_target_range_pct', 0):.0f}%")

    # 3. Revenue estimate
    rev = calculate_revenue_estimate(revenue_state)
    print(f"  Revenue est: ${rev['total_monthly']:.0f}/month (${rev['daily_est']:.0f}/day)")
    print(f"  Goal progress: {rev['pct_of_goal']:.1f}% of ${MONTHLY_GOAL_USD:,}/month")

    # 4. Generate patches
    patches = generate_improvement_patches(quality_analysis, revenue_state)
    print(f"  Improvement patches: {len(patches)}")
    for p in patches[:3]:
        print(f"    [{p['priority']}] {p['id']}: {p['description']}")

    # 5. Save patches for podcast_generator to pick up
    tips_file = os.path.join(RESEARCH_DIR, "podcast_improvement_tips.json")
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    with open(tips_file, "w") as f:
        json.dump({
            "generated": datetime.datetime.now().isoformat(),
            "patches": patches,
            "top_priority": patches[0] if patches else None,
        }, f, indent=2)

    # 6. Generate daily report
    report = generate_daily_report(quality_analysis, revenue_state, patches)

    # 7. Save report log
    log_file = os.path.join(RESEARCH_DIR, "optimizer_log.json")
    logs = []
    try:
        with open(log_file, "r") as f:
            logs = json.load(f)
    except Exception:
        pass
    logs.append(report)
    logs = logs[-30:]  # keep 30 days
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)

    print(f"\n  Report saved: {log_file}")
    print(f"  Top action: {report['top_priority_action'][:100]}...")
    print(f"  Next milestone: {report['milestone']['next']} ({report['milestone']['pct_to_next']:.0f}% there)")

    return report


if __name__ == "__main__":
    run()
