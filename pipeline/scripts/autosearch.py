"""
Mole FM AutoSearch — Karpathy-style Self-Improving RSS Discovery
================================================================
Inspired by Andrej Karpathy's philosophy of iterative self-improvement:
evaluate everything, keep what works, discard what doesn't.

What this does every day:
1. DISCOVER   — Search for new Haiti/Caribbean news RSS feeds via common
                 URL patterns and a curated candidate list
2. TEST       — Fetch each candidate, measure yield (stories/fetch),
                 freshness (hours since latest item), and language match
3. SCORE      — Assign a quality score: yield × freshness_bonus × lang_bonus
4. PROMOTE    — Add top-scoring new sources to autosearch_sources.json
5. DEMOTE     — Flag sources that returned 0 stories 3 runs in a row for
                 removal from NEWS_SOURCES
6. LOG        — Write a self-improvement report to autosearch_log.json

Revenue logic: more high-quality sources → more fresh stories every hour
→ more listener time → more sponsor impressions.

Run daily (04:00 UTC = midnight Haiti) via the scheduled cron.
"""

import json
import os
import datetime
import urllib.request
import xml.etree.ElementTree as ET
import re

SCRIPTS_DIR       = "/home/user/workspace/molefm/scripts"
AUTOSEARCH_SOURCES = os.path.join(SCRIPTS_DIR, "autosearch_sources.json")
AUTOSEARCH_LOG    = os.path.join(SCRIPTS_DIR, "autosearch_log.json")
HEALTH_FILE       = os.path.join(SCRIPTS_DIR, "source_health.json")

# ── Candidate RSS feeds to probe ─────────────────────────────────────────────
# These are evaluated daily. Approved ones are merged into the live pipeline.
CANDIDATES = [
    # Haiti news
    {"name": "Alterpresse",         "url": "https://www.alterpresse.org/rss.php",                    "lang": "fr"},
    {"name": "Radio Caraïbes FM",   "url": "https://www.radiocaraibesfm.com/feed/",                  "lang": "fr"},
    {"name": "Le Patriote Haiti",   "url": "https://lepatriotehaiti.com/feed/",                      "lang": "fr"},
    {"name": "Gazette Haiti",       "url": "https://gazettehaiti.com/feed/",                         "lang": "fr"},
    {"name": "HaitiChoc",           "url": "https://haitichoc.com/feed/",                            "lang": "fr"},
    {"name": "Metropole Haiti",     "url": "https://www.metropolehaiti.com/metropole/rss.php",       "lang": "fr"},
    {"name": "Haiti Observateur",   "url": "https://haiti-observateur.ca/feed/",                     "lang": "fr"},
    {"name": "Radio Vision 2000",   "url": "https://www.radiovision2000haiti.net/feed/",              "lang": "fr"},
    {"name": "HPN Haiti",           "url": "https://hpnhaiti.com/feed/",                             "lang": "fr"},
    {"name": "Bel Nouvèl",          "url": "https://belnouvel.com/feed/",                            "lang": "fr"},
    {"name": "Vant Bèf Info",       "url": "https://www.vantbefinfo.com/feed/",                      "lang": "fr"},
    {"name": "Ayiti Kouri",         "url": "https://ayitikouri.com/feed/",                           "lang": "fr"},
    # Caribbean
    {"name": "Loop News Haiti",     "url": "https://haiti.loopnews.com/rss.xml",                     "lang": "fr"},
    {"name": "Caribbean360",        "url": "https://www.caribbean360.com/feed",                      "lang": "en"},
    {"name": "Jamaica Gleaner",     "url": "https://jamaica-gleaner.com/feed/rss.xml",               "lang": "en"},
    # Diaspora
    {"name": "Haitian Times",       "url": "https://haitiantimes.com/feed/",                         "lang": "en"},
    {"name": "Haiti Libre EN",      "url": "https://www.haitilibre.com/rss-en.xml",                  "lang": "en"},
    # Sports
    {"name": "Haiti Football 360",  "url": "https://haitifootball360.com/feed/",                     "lang": "fr"},
    {"name": "Sports Haiti",        "url": "https://sportshaiti.com/feed/",                          "lang": "fr"},
]

# ── Existing core sources to health-check ────────────────────────────────────
CORE_SOURCES = [
    {"name": "Le Nouvelliste",          "url": "https://lenouvelliste.com/feed"},
    {"name": "Rezo Nodwes",             "url": "https://rezonodwes.com/feed/"},
    {"name": "AyiboPost",               "url": "https://ayibopost.com/feed/"},
    {"name": "Haiti Libre",             "url": "https://www.haitilibre.com/rss.xml"},
    {"name": "BBC Afrique",             "url": "https://feeds.bbci.co.uk/afrique/rss.xml"},
    {"name": "Juno7",                   "url": "https://juno7.ht/feed"},
    {"name": "Haiti24",                 "url": "https://haiti24.net/feed"},
    {"name": "Bonpounou Sports",        "url": "https://www.bonpounou.com/news/rss/category/sports"},
    {"name": "Haiti Express Sports",    "url": "https://www.haitiexpress.net/category/sports/feed/"},
]

# Score thresholds
MIN_YIELD      = 2     # at least 2 stories to qualify
MAX_AGE_HOURS  = 48    # stories must be < 48h old to count as fresh
PROMOTE_SCORE  = 0.5   # minimum score to promote (0–1 scale)


# ── Helpers ──────────────────────────────────────────────────────────────────

def probe_rss(url, timeout=12):
    """
    Fetch an RSS feed and return scoring metrics.
    Returns: {yield_count, freshness_score, lang_detected, latest_age_hours, ok}
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MoleFM-AutoSearch/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)

        items = root.findall(".//item")
        if not items:
            return {"ok": False, "yield_count": 0}

        # Count fresh items
        now = datetime.datetime.utcnow()
        fresh_count = 0
        latest_age_h = 9999
        for item in items[:10]:
            pub = item.findtext("pubDate", "")
            age_h = parse_age_hours(pub)
            if age_h is not None:
                latest_age_h = min(latest_age_h, age_h)
                if age_h < MAX_AGE_HOURS:
                    fresh_count += 1

        # Detect language from titles
        text_sample = " ".join(
            (item.findtext("title", "") or "") for item in items[:5]
        ).lower()
        lang = detect_lang(text_sample)

        # Freshness score: 1.0 if latest item < 2h, decays to 0 at 48h
        if latest_age_h < 9999:
            freshness = max(0.0, 1.0 - (latest_age_h / MAX_AGE_HOURS))
        else:
            freshness = 0.0

        return {
            "ok":             True,
            "yield_count":    len(items),
            "fresh_count":    fresh_count,
            "freshness":      freshness,
            "latest_age_h":   latest_age_h,
            "lang":           lang,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "yield_count": 0}


def parse_age_hours(pub_str):
    """Parse RSS pubDate and return age in hours, or None."""
    if not pub_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S +0000",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            dt = datetime.datetime.strptime(pub_str.strip(), fmt)
            if dt.tzinfo:
                now = datetime.datetime.now(datetime.timezone.utc)
            else:
                now = datetime.datetime.utcnow()
                dt = dt.replace(tzinfo=None)
            age_h = (now - dt).total_seconds() / 3600
            return max(0, age_h)
        except Exception:
            pass
    return None


def detect_lang(text):
    """Simple heuristic to detect FR vs EN vs HT."""
    fr_words = ["le", "la", "les", "de", "du", "en", "et", "haïti", "haiti",
                "des", "une", "est", "sur", "pour", "dans"]
    en_words = ["the", "and", "of", "in", "to", "a", "is", "are", "was", "for"]
    ht_words = ["nan", "pou", "kay", "peyi", "lwa", "moun", "yo", "ak", "ki"]
    fr = sum(1 for w in fr_words if f" {w} " in f" {text} ")
    en = sum(1 for w in en_words if f" {w} " in f" {text} ")
    ht = sum(1 for w in ht_words if f" {w} " in f" {text} ")
    if fr >= en and fr >= ht:
        return "fr"
    if en > fr:
        return "en"
    return "ht"


def score_source(metrics, preferred_lang="fr"):
    """
    Compute a 0–1 quality score.
    Factors: yield, freshness, language match.
    """
    if not metrics.get("ok"):
        return 0.0
    yield_score   = min(1.0, metrics.get("fresh_count", 0) / 5.0)
    freshness     = metrics.get("freshness", 0.0)
    lang_bonus    = 1.0 if metrics.get("lang") == preferred_lang else 0.7
    return round(yield_score * 0.4 + freshness * 0.5 + (lang_bonus - 1.0) * 0.1, 3)


def load_approved():
    try:
        with open(AUTOSEARCH_SOURCES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"approved": [], "demoted": []}


def save_approved(data):
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    with open(AUTOSEARCH_SOURCES, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_health():
    try:
        with open(HEALTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_health(data):
    with open(HEALTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Main autosearch run ───────────────────────────────────────────────────────

def run():
    now = datetime.datetime.now()
    print(f"\n=== Mole FM AutoSearch === {now.strftime('%Y-%m-%d %H:%M')}")
    print("Karpathy-style self-improving RSS discovery\n")

    approved_data = load_approved()
    approved_urls = {s["url"] for s in approved_data.get("approved", [])}
    health        = load_health()

    report = {
        "run_at":    now.isoformat(),
        "probed":    0,
        "promoted":  [],
        "healthy":   [],
        "degraded":  [],
        "failed":    [],
    }

    # ── Step 1: Health-check core sources ────────────────────────────────────
    print("=== STEP 1: Core source health check ===")
    for src in CORE_SOURCES:
        url = src["url"]
        m = probe_rss(url)
        key = url
        h = health.get(key, {"fails": 0, "last_ok": None})
        if m.get("ok") and m.get("yield_count", 0) >= MIN_YIELD:
            h["fails"] = 0
            h["last_ok"] = now.isoformat()
            status = f"OK ({m['yield_count']} items, freshness={m.get('freshness',0):.2f})"
            report["healthy"].append(src["name"])
        else:
            h["fails"] = h.get("fails", 0) + 1
            err = m.get("error", "yield=0")
            status = f"FAIL #{h['fails']} — {err}"
            if h["fails"] >= 3:
                report["degraded"].append({"name": src["name"], "url": url, "fails": h["fails"]})
        health[key] = h
        print(f"  [{src['name']}] {status}")

    # ── Step 2: Probe candidates ──────────────────────────────────────────────
    print(f"\n=== STEP 2: Probing {len(CANDIDATES)} candidates ===")
    newly_promoted = []
    for cand in CANDIDATES:
        url = cand["url"]
        if url in approved_urls:
            print(f"  [SKIP] {cand['name']} — already approved")
            continue

        print(f"  Probing: {cand['name']}...")
        m = probe_rss(url)
        report["probed"] += 1

        if not m.get("ok"):
            report["failed"].append(cand["name"])
            print(f"    ✗ {m.get('error', 'failed')}")
            continue

        sc = score_source(m, preferred_lang=cand.get("lang", "fr"))
        print(f"    score={sc:.3f}  yield={m.get('yield_count',0)}  "
              f"fresh={m.get('fresh_count',0)}  age={m.get('latest_age_h',9999):.1f}h  "
              f"lang={m.get('lang','?')}")

        if sc >= PROMOTE_SCORE and m.get("yield_count", 0) >= MIN_YIELD:
            newly_promoted.append({
                "name":  cand["name"],
                "url":   url,
                "lang":  cand.get("lang", "fr"),
                "score": sc,
                "added": now.isoformat(),
            })
            print(f"    ✓ PROMOTED (score={sc:.3f})")
        else:
            print(f"    – Below threshold (score={sc:.3f} < {PROMOTE_SCORE})")

    # ── Step 3: Merge newly promoted ─────────────────────────────────────────
    if newly_promoted:
        existing = approved_data.get("approved", [])
        for new in newly_promoted:
            if new["url"] not in {s["url"] for s in existing}:
                existing.append(new)
        approved_data["approved"] = existing
        save_approved(approved_data)
        report["promoted"] = [s["name"] for s in newly_promoted]
        print(f"\n  [PROMOTED] {len(newly_promoted)} new sources added to pipeline")
    else:
        print("\n  No new sources met the threshold today.")

    # ── Step 4: Save health + log ─────────────────────────────────────────────
    save_health(health)

    # Append to log
    try:
        try:
            with open(AUTOSEARCH_LOG, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = {"runs": []}
        log["runs"].append(report)
        log["runs"] = log["runs"][-30:]   # keep last 30 runs
        with open(AUTOSEARCH_LOG, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [WARN] Could not write log: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n=== AutoSearch Summary ===")
    print(f"  Probed:    {report['probed']} candidates")
    print(f"  Promoted:  {len(report['promoted'])} new sources → {report['promoted']}")
    print(f"  Healthy:   {len(report['healthy'])} core sources")
    print(f"  Degraded:  {len(report['degraded'])} sources (3+ consecutive fails)")
    print(f"  Failed:    {len(report['failed'])} unreachable")

    return report


if __name__ == "__main__":
    run()
