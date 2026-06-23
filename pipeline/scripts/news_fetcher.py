"""
Mole FM News Fetcher — Professional Edition
============================================
Industry-standard broadcast journalism practices:
  - Source quality tiers (Tier 1 = primary Haitian press, Tier 2 = regional/international)
  - Cross-source corroboration: a story is CONFIRMED if ≥2 sources report it
  - Source attribution: every story carries its origin outlet
  - Editorial filters: removes rumor language, unverified claims, clickbait
  - Deduplication: cross-hour title fingerprinting
  - Weather: Open-Meteo free API (no key needed)
  - Sports: dedicated sports sources

Goal: Mole FM becomes the #1 trusted Haitian news podcast by being
the most accurate and well-sourced, not just the most frequent.

Reference standards: NPR Ethics Handbook, BBC Editorial Guidelines,
RSF Press Freedom principles for Haitian media.
"""

import json
import datetime
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import re
import os
import email.utils
from pathlib import Path

# ── Source Registry (Tier 1 = primary Haitian press) ─────────────────────────
# Tier 1: Major, established Haitian outlets — highest weight in corroboration
# Tier 2: International outlets covering Haiti — strong credibility
# Tier 3: Community/regional — useful for local color, lower confidence alone

NEWS_SOURCES = [
    # ── TIER 1: Core Haitian Press ──────────────────────────────────────────
    {"name": "Le Nouvelliste",      "url": "https://lenouvelliste.com/feed",
     "lang": "fr", "tier": 1, "country": "HT",
     "note": "Haiti's oldest daily newspaper, est. 1898. Gold standard."},

    {"name": "Radio Métropole",     "url": "https://metropole.ht/feed/",
     "lang": "fr", "tier": 1, "country": "HT",
     "note": "Port-au-Prince's leading radio/news station. 100.1 FM."},

    {"name": "Juno7",               "url": "https://juno7.ht/feed",
     "lang": "fr", "tier": 1, "country": "HT",
     "note": "Major Haitian digital news outlet."},

    {"name": "Haiti24",             "url": "https://haiti24.net/feed",
     "lang": "fr", "tier": 1, "country": "HT",
     "note": "Haiti 24 news portal. Good breaking news coverage."},

    {"name": "Rezo Nodwes",         "url": "https://rezonodwes.com/feed/",
     "lang": "fr", "tier": 1, "country": "HT",
     "note": "Northern Haiti focus. Credible regional outlet."},

    {"name": "Haiti Liberté",       "url": "https://haitiliberte.com/feed/",
     "lang": "fr", "tier": 1, "country": "HT",
     "note": "Weekly newspaper covering Haiti politics and diaspora."},

    {"name": "Haiti Press Network", "url": "https://hpnhaiti.com/feed/",
     "lang": "en", "tier": 1, "country": "HT",
     "note": "HPN — press agency aggregating Haitian news."},

    # ── TIER 2: International / Diaspora ─────────────────────────────────────
    {"name": "Haitian Times",       "url": "https://haitiantimes.com/feed/",
     "lang": "en", "tier": 2, "country": "US",
     "note": "Largest Haitian diaspora newspaper. NYC-based. Pulitzer contacts."},

    {"name": "RFI Haïti",           "url": "https://www.rfi.fr/fr/tag/ha%C3%AFti/rss",
     "lang": "fr", "tier": 2, "country": "FR",
     "note": "Radio France Internationale — Haiti tag feed. High editorial standards."},

    {"name": "BBC Afrique",         "url": "https://feeds.bbci.co.uk/afrique/rss.xml",
     "lang": "fr", "tier": 2, "country": "UK",
     "note": "BBC French Africa/Caribbean service. High editorial standards."},

    {"name": "Caribbean National Weekly", "url": "https://caribbeannationalweekly.com/feed/",
     "lang": "en", "tier": 2, "country": "US",
     "note": "Caribbean diaspora US outlet."},

    # ── TIER 1 SPORTS: Haitian sports outlets ────────────────────────────────
    {"name": "Haiti Express Sports", "url": "https://www.haitiexpress.net/category/sports/feed/",
     "lang": "fr", "tier": 1, "country": "HT", "category": "sports",
     "note": "Haiti sports news."},

    {"name": "Bonpounou Sports",    "url": "https://www.bonpounou.com/news/rss/category/sports",
     "lang": "fr", "tier": 1, "country": "HT", "category": "sports",
     "note": "Haitian sports portal."},
]

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = os.environ.get(
    "MOLEFM_NEWS_SCRIPTS_DIR",
    str(PIPELINE_DIR / "runtime" / "scripts"),
)
SEEN_TITLES_FILE = os.environ.get(
    "MOLEFM_SEEN_TITLES_FILE",
    str(PIPELINE_DIR / "runtime" / "seen_titles.json"),
)
AUTOSEARCH_SOURCES_FILE = os.environ.get(
    "MOLEFM_AUTOSEARCH_SOURCES_FILE",
    str(PIPELINE_DIR / "runtime" / "autosearch_sources.json"),
)
VERIFICATION_LOG_FILE = os.environ.get(
    "MOLEFM_VERIFICATION_LOG_FILE",
    str(PIPELINE_DIR / "research" / "verification_log.json"),
)

TARGET_ARTICLES = 6

# ── Editorial quality filters ─────────────────────────────────────────────────
# Patterns that flag stories as unverified/rumor/clickbait — we exclude these
# unless they come from 2+ independent Tier 1 sources.
RUMOR_PATTERNS = [
    r"\bselon des sources\b",
    r"\bdes rumeurs\b",
    r"\bon dit que\b",
    r"\billégalement\b.{0,30}\bsans preuve\b",
    r"\bchoc !\b",
    r"\bincroyable !\b",
    r"\bvous ne croirez pas\b",
    r"\bexclusif !\b",
    r"\bBREAKING(?!\s+NEWS)\b",  # allow "BREAKING NEWS", block bare BREAKING spam
    r"\bWATCH:\b",
    r"\bVIDEO:\b",
    r"\bPHOTO:\b",
]

# Topics that require corroboration from 2+ sources before broadcast
HIGH_STAKES_KEYWORDS = [
    "assassinat", "assassin", "coup d'état", "putsch", "mort", "décès",
    "killed", "dead", "massacre", "attaque", "fusillade", "kidnapping",
    "tremblement de terre", "earthquake", "tsunami", "ouragan", "hurricane",
    "arrêté", "arrested", "condamné", "convicted",
]

BROADCAST_EXCLUSION_PATTERNS = [
    r"\bodds\b",
    r"\bpicks?\b",
    r"\bbest bets?\b",
    r"\bbetting\b",
    r"\bprediction\b",
    r"\bpronostic\b",
    r"\bparis sportifs\b",
    r"\bcommercials\b",
    r"\bpénis\b",
]

ENGLISH_HEADLINE_WORDS = {
    "the", "and", "with", "after", "before", "from", "what", "why", "how",
    "are", "is", "vs", "world", "cup", "roundup", "wins", "group", "match",
    "preview", "time", "commercials", "breaks", "takeaways", "last", "night",
    "baseball", "beat", "red", "sox", "rockies", "dodgers", "angels",
    "maybe", "never", "seen", "fashion", "team", "teams", "first", "action",
    "scotland", "miami", "mlb", "nba", "nfl", "nhl", "soccer", "live",
    "scores", "highlights", "season", "league", "players", "player",
}

JOURS_FR = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
MOIS_FR  = ["janvier","février","mars","avril","mai","juin",
             "juillet","août","septembre","octobre","novembre","décembre"]

WEATHER_CITIES = [
    {"name": "Môle-Saint-Nicolas", "lat": 19.80, "lon": -73.37},
    {"name": "Port-au-Prince",     "lat": 18.54, "lon": -72.34},
    {"name": "Cap-Haïtien",        "lat": 19.76, "lon": -72.20},
]

WMO_CODES = {
    0:"ciel dégagé", 1:"principalement dégagé", 2:"partiellement nuageux",
    3:"couvert", 45:"brouillard", 48:"brouillard givrant",
    51:"bruine légère", 53:"bruine modérée", 55:"bruine dense",
    61:"pluie légère", 63:"pluie modérée", 65:"forte pluie",
    71:"neige légère", 73:"neige modérée", 75:"forte neige",
    80:"averses légères", 81:"averses modérées", 82:"violentes averses",
    95:"orage", 96:"orage avec grêle", 99:"orage violent avec grêle",
}


# ── Utility functions ─────────────────────────────────────────────────────────

def date_en_francais(dt):
    jour  = JOURS_FR[dt.weekday()]
    mois  = MOIS_FR[dt.month - 1]
    heure = dt.strftime("%Hh%M")
    return f"{jour} {dt.day} {mois} {dt.year} à {heure}"

def clean_html(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&quot;', '"', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def title_fingerprint(title):
    """Normalize title for deduplication — removes punctuation, lowercases."""
    t = re.sub(r'[^\w\s]', '', title.lower())
    words = t.split()
    # Use first 6 significant words as fingerprint
    stopwords = {'le','la','les','un','une','des','de','du','en','et','ou',
                 'the','a','an','of','in','at','on','for','is','are','was'}
    sig = [w for w in words if w not in stopwords][:6]
    return " ".join(sig)

def is_rumor_or_clickbait(title, description):
    """Return True if the story should be flagged as unverified/clickbait."""
    text = (title + " " + description).lower()
    for pattern in RUMOR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def needs_corroboration(title, description):
    """Return True if this story touches high-stakes claims requiring 2+ sources."""
    text = (title + " " + description).lower()
    return any(kw in text for kw in HIGH_STAKES_KEYWORDS)

def is_unsuitable_for_broadcast(title, description):
    """Exclude betting-adjacent and sensitive adult health headlines from general radio news."""
    text = (title + " " + description).lower()
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in BROADCAST_EXCLUSION_PATTERNS)

def looks_like_english_headline(title):
    """Keep live news French-first when translation is unavailable or uncertain."""
    words = re.findall(r"[a-zA-Z]+", title.lower())
    if not words:
        return False
    english_hits = sum(1 for word in words if word in ENGLISH_HEADLINE_WORDS)
    return english_hits >= 2

def pub_date_timestamp(pub_date):
    """Parse RSS pubDate to a sortable timestamp. Undated items sort last."""
    if not pub_date:
        return 0
    try:
        parsed = email.utils.parsedate_to_datetime(pub_date)
        return parsed.timestamp() if parsed else 0
    except Exception:
        return 0

def translate_title_to_french(title):
    """Translate title to French using deep-translator (free, Google Translate)."""
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='auto', target='fr').translate(title)
        return translated if translated else title
    except Exception:
        return title


# ── RSS fetching with source metadata ────────────────────────────────────────

def fetch_rss(source, timeout=10):
    """
    Fetch and parse RSS feed. Returns items with source attribution attached.
    """
    url  = source["url"]
    name = source["name"]
    tier = source.get("tier", 2)
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "MoleFM-NewsBot/3.0 (professional broadcast)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        # Try UTF-8, fall back to latin-1
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = body.decode("latin-1")
        root = ET.fromstring(text)
        items = []
        for item in root.findall(".//item")[:6]:
            title       = clean_html(item.findtext("title", "") or "")
            description = clean_html(item.findtext("description", "") or "")[:300]
            link        = item.findtext("link", "") or ""
            pub_date    = item.findtext("pubDate", "") or ""
            if title and len(title) > 10:
                items.append({
                    "title":       title,
                    "description": description,
                    "link":        link,
                    "pub_date":    pub_date,
                    "source_name": name,
                    "source_tier": tier,
                    "source_lang": source.get("lang", "fr"),
                    "source_url":  url,
                    "category":    source.get("category", "news"),
                })
        return items
    except urllib.error.HTTPError as e:
        print(f"  [HTTP {e.code}] {name}: {url}")
        return []
    except ET.ParseError as e:
        # Try stripping bad entities and retry
        try:
            req2 = urllib.request.Request(url, headers={"User-Agent": "MoleFM-NewsBot/3.0"})
            with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                body2 = resp2.read()
            text2 = body2.decode("utf-8", errors="replace")
            # Strip undefined entities
            text2 = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;)[a-zA-Z][a-zA-Z0-9]*;', ' ', text2)
            root2 = ET.fromstring(text2)
            items2 = []
            for item in root2.findall(".//item")[:6]:
                title       = clean_html(item.findtext("title", "") or "")
                description = clean_html(item.findtext("description", "") or "")[:300]
                link        = item.findtext("link", "") or ""
                if title and len(title) > 10:
                    items2.append({
                        "title": title, "description": description, "link": link,
                        "pub_date": "", "source_name": name, "source_tier": tier,
                        "source_lang": source.get("lang", "fr"),
                        "source_url": url, "category": source.get("category","news"),
                    })
            print(f"  [OK-recovered] {name}: {len(items2)} items (entity-stripped)")
            return items2
        except Exception:
            print(f"  [ERR-XML] {name}: {str(e)[:60]}")
            return []
    except Exception as e:
        print(f"  [ERR] {name}: {str(e)[:60]}")
        return []


# ── Verification engine ───────────────────────────────────────────────────────

def cross_corroborate(all_items):
    """
    Industry-standard corroboration:
    - Group stories by title fingerprint
    - A story reported by 2+ independent sources gets CONFIRMED status
    - High-stakes stories REQUIRE 2+ sources to be included
    - Rumor/clickbait stories are flagged and excluded unless corroborated

    Returns list of verified story dicts with confidence scores.
    """
    # Group by fingerprint
    groups = {}
    for item in all_items:
        fp = title_fingerprint(item["title"])
        if not fp:
            continue
        if fp not in groups:
            groups[fp] = []
        groups[fp].append(item)

    verified = []
    for fp, items in groups.items():
        # Pick the best version (highest tier source first, most descriptive)
        items_sorted = sorted(items, key=lambda x: (x["source_tier"], -len(x["description"])))
        best = items_sorted[0]
        sources = list({i["source_name"] for i in items})
        source_count = len(sources)
        tier1_count  = sum(1 for i in items if i["source_tier"] == 1)

        # Confidence scoring (0-100)
        # Tier 1 single-source from established outlets = 65 base confidence
        base = 65 if tier1_count >= 1 else 40
        confidence = min(100, base + (source_count - 1) * 20 + tier1_count * 10)

        # Verification status
        is_rumor   = is_rumor_or_clickbait(best["title"], best["description"])
        needs_corr = needs_corroboration(best["title"], best["description"])

        if is_rumor and source_count < 2:
            print(f"  [EXCLUDED-RUMOR] {best['title'][:60]}")
            continue

        if needs_corr and source_count < 2:
            print(f"  [EXCLUDED-UNCONFIRMED] High-stakes, 1 source only: {best['title'][:60]}")
            continue

        verification = "CONFIRMED" if source_count >= 2 else "SINGLE-SOURCE"
        if needs_corr and source_count >= 2:
            verification = "CONFIRMED-HIGH-STAKES"

        if is_unsuitable_for_broadcast(best["title"], best["description"]):
            print(f"  [EXCLUDED-BROADCAST-SUITABILITY] {best['title'][:60]}")
            continue

        if best.get("source_lang", "fr") != "fr":
            print(f"  [EXCLUDED-NON-FRENCH-SOURCE] {best['title'][:60]}")
            continue

        if looks_like_english_headline(best["title"]):
            print(f"  [EXCLUDED-NON-FRENCH] {best['title'][:60]}")
            continue

        verified.append({
            **best,
            "all_sources":    sources,
            "source_count":   source_count,
            "confidence":     confidence,
            "verification":   verification,
            "fingerprint":    fp,
        })

    # Sort: corroborated first, then by confidence
    verified.sort(key=lambda x: (-x["source_count"], -x["confidence"]))
    return verified


def load_seen_titles(window_hours=6):
    try:
        with open(SEEN_TITLES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=window_hours)
        seen = set()
        for entry in data.get("entries", []):
            try:
                ts = datetime.datetime.fromisoformat(entry["ts"])
                if ts >= cutoff:
                    seen.add(entry["key"])
            except Exception:
                pass
        return seen
    except Exception:
        return set()


def save_seen_titles(new_keys):
    try:
        try:
            with open(SEEN_TITLES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"entries": []}
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
        entries = [
            e for e in data.get("entries", [])
            if datetime.datetime.fromisoformat(e["ts"]) >= cutoff
        ]
        now_iso = datetime.datetime.now().isoformat()
        for key in new_keys:
            entries.append({"key": key, "ts": now_iso})
        os.makedirs(SCRIPTS_DIR, exist_ok=True)
        with open(SEEN_TITLES_FILE, "w", encoding="utf-8") as f:
            json.dump({"entries": entries}, f, ensure_ascii=False)
    except Exception as e:
        print(f"  [WARN] Could not save seen titles: {e}")


def load_autosearch_sources():
    try:
        with open(AUTOSEARCH_SOURCES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("approved", [])
    except Exception:
        return []


def log_verification_run(stories, chosen, timestamp):
    """Log what was verified vs. excluded for editorial transparency."""
    try:
        os.makedirs(os.path.dirname(VERIFICATION_LOG_FILE), exist_ok=True)
        try:
            with open(VERIFICATION_LOG_FILE, "r", encoding="utf-8") as f:
                log = json.load(f)
        except Exception:
            log = []
        entry = {
            "timestamp":       timestamp.isoformat(),
            "total_fetched":   len(stories),
            "after_verify":    len(chosen),
            "confirmed":       sum(1 for s in chosen if "CONFIRMED" in s.get("verification","")),
            "single_source":   sum(1 for s in chosen if s.get("verification","") == "SINGLE-SOURCE"),
            "stories":         [
                {
                    "title":        s["title"][:80],
                    "source":       s["source_name"],
                    "source_lang":  s.get("source_lang", ""),
                    "all_sources":  s.get("all_sources", [s["source_name"]]),
                    "confidence":   s.get("confidence", 50),
                    "verification": s.get("verification", "SINGLE-SOURCE"),
                    "link":         s.get("link", ""),
                    "description":  s.get("description", "")[:200],
                    "pub_date":     s.get("pub_date", ""),
                    "source_url":   s.get("source_url", ""),
                }
                for s in chosen
            ]
        }
        log.append(entry)
        log = log[-72:]  # keep last 72 broadcasts (3 days)
        with open(VERIFICATION_LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [WARN] Verification log: {e}")


# ── Weather ───────────────────────────────────────────────────────────────────

def get_weather_haiti():
    results = []
    for city in WEATHER_CITIES:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={city['lat']}&longitude={city['lon']}"
            f"&current=temperature_2m,weathercode,windspeed_10m,precipitation,relative_humidity_2m"
            f"&timezone=America%2FPort-au-Prince&forecast_days=1"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MoleFM-WeatherBot/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            cur = data.get("current", {})
            wmo = cur.get("weathercode", 0)
            results.append({
                "name":      city["name"],
                "temp_c":    round(cur.get("temperature_2m", 0)),
                "condition": WMO_CODES.get(wmo, "conditions variables"),
                "wind_kmh":  round(cur.get("windspeed_10m", 0)),
                "humidity":  round(cur.get("relative_humidity_2m", 0)),
                "precip_mm": round(cur.get("precipitation", 0), 1),
            })
            print(f"  [Weather] {city['name']}: {results[-1]['temp_c']}°C, {results[-1]['condition']}")
        except Exception as e:
            print(f"  [WARN] Weather {city['name']}: {e}")
    return results


def build_weather_segment(weather_data):
    if not weather_data:
        return None
    lines = ["Et voici la météo pour Haïti."]
    for city in weather_data:
        line = (
            f"À {city['name']} : {city['temp_c']} degrés, {city['condition']}. "
            f"Vent : {city['wind_kmh']} km/h. Humidité : {city['humidity']} pourcent."
        )
        if city["precip_mm"] > 0:
            line += f" Précipitations : {city['precip_mm']} mm."
        lines.append(line)
    lines.append("Restez informés avec Mole FM.")
    return {
        "segment":    "WEATHER",
        "lang":       "fr",
        "text":       " ".join(lines),
        "voice_note": "Clear French female, weather forecast",
    }


# ── Script builder ────────────────────────────────────────────────────────────

def build_french_script(verified_stories, timestamp, weather_data=None):
    """
    Build a professional French broadcast script with full source attribution.
    Every claim is traceable to its source outlet, consistent with NPR/BBC standards.
    """
    date_str = date_en_francais(timestamp)
    segments = []

    # STATION ID
    segments.append({
        "segment": "STATION_ID",
        "lang":    "fr",
        "text":    f"Mole FM. Votre radio communautaire. Il est {date_str}.",
        "voice_note": "Warm French-Canadian male, station ID"
    })

    # SPONSOR
    _sponsor_cfg = os.path.join(os.path.dirname(__file__), "..", "config", "sponsors.json")
    try:
        with open(_sponsor_cfg, "r", encoding="utf-8") as _sf:
            _scfg = json.load(_sf)
        SPONSORS = [
            {"name": s["name"], "message": s["audio_text"]}
            for s in _scfg["sponsors"] if s.get("active", False)
        ]
    except Exception:
        SPONSORS = []
    if not SPONSORS:
        SPONSORS = [{"name": "Mathurin Beach Resort",
                     "message": "Mathurin Beach Resort, au Môle-Saint-Nicolas — la mer, le soleil, et l'hospitalité haïtienne à leur meilleur."}]
    sponsor = SPONSORS[timestamp.hour % len(SPONSORS)]
    segments.append({
        "segment": "SPONSOR", "lang": "fr",
        "text": sponsor["message"],
        "voice_note": "Clear French female, sponsor read"
    })

    # INTRO
    confirmed_count = sum(1 for s in verified_stories if "CONFIRMED" in s.get("verification",""))
    verification_line = ""
    if confirmed_count >= 3:
        verification_line = f"Ces nouvelles sont vérifiées et confirmées par nos sources."
    elif confirmed_count >= 1:
        verification_line = f"Ces informations proviennent de nos sources journalistiques vérifiées."

    segments.append({
        "segment": "INTRO", "lang": "fr",
        "text": (
            f"Bonjour et bienvenue sur Mole FM. "
            f"Voici votre bulletin d'informations du {date_str}. "
            f"Je vous présente les dernières nouvelles d'Haïti et de la Caraïbe. "
            f"{verification_line}"
        ),
        "voice_note": "Professional French female broadcaster"
    })

    # MAIN NEWS — with source attribution
    news_lines = []
    for i, story in enumerate(verified_stories[:6], 1):
        title_raw = story["title"].strip().rstrip(".")
        title_fr  = translate_title_to_french(title_raw)
        desc      = story["description"].strip()
        source    = story["source_name"]
        all_srcs  = story.get("all_sources", [source])
        verif     = story.get("verification", "SINGLE-SOURCE")
        confidence = story.get("confidence", 50)

        # Attribution phrasing — natural broadcast French
        if len(all_srcs) >= 3:
            attr = f"Selon plusieurs médias dont {all_srcs[0]} et {all_srcs[1]}"
        elif len(all_srcs) == 2:
            attr = f"Selon {all_srcs[0]} et {all_srcs[1]}"
        else:
            attr = f"Selon {source}"

        line = f"Titre {i} : {title_fr}."
        if desc and len(desc) > 30:
            desc_clean = desc[:220]
            last_p = desc_clean.rfind(".")
            if last_p > 80:
                desc_clean = desc_clean[:last_p + 1]
            line += f" {attr} — {desc_clean}"
        else:
            line += f" {attr}."

        news_lines.append(line)

    if news_lines:
        segments.append({
            "segment":    "NEWS_MAIN",
            "lang":       "fr",
            "text":       "Voici les titres de l'actualité. " + " ".join(news_lines),
            "voice_note": "Clear, professional French female broadcaster"
        })
    else:
        segments.append({
            "segment": "NEWS_MAIN", "lang": "fr",
            "text": "Nous n'avons pas de nouvelles récentes vérifiées disponibles pour le moment. Restez à l'écoute de Mole FM.",
            "voice_note": "French female broadcaster"
        })

    # SPORTS
    sport_stories = [s for s in verified_stories
                     if any(kw in (s["title"] + s["description"]).lower()
                            for kw in ["football","grenadiers","fifa","sport","soccer",
                                       "championnat","ligue","match","tournoi","coupe"])]
    if sport_stories:
        sport_lines = []
        for s in sport_stories[:3]:
            t    = translate_title_to_french(s["title"].strip().rstrip("."))
            src  = s["source_name"]
            sport_lines.append(f"{t}, selon {src}.")
        segments.append({
            "segment":    "SPORTS",
            "lang":       "fr",
            "text": (
                "Et maintenant, le sport. "
                + " ".join(sport_lines)
                + " Suivez tous les résultats sur Mole FM."
            ),
            "voice_note": "Energetic French male sports announcer"
        })

    # WEATHER
    if weather_data:
        w = build_weather_segment(weather_data)
        if w:
            segments.append(w)

    # SIGN-OFF
    segments.append({
        "segment": "SIGN_OFF", "lang": "fr",
        "text": (
            "C'était votre bulletin d'informations sur Mole FM. "
            "Mole FM — votre source d'information vérifiée, au service de la communauté haïtienne. "
            "Nous vous retrouvons dans une heure."
        ),
        "voice_note": "Warm French female, soft close"
    })

    return segments


def save_script(segments, timestamp, stories=None):
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    filename = timestamp.strftime("newscast_%Y%m%d_%H%M.json")
    filepath = os.path.join(SCRIPTS_DIR, filename)
    output = {
        "station":        "Mole FM",
        "language":       "fr",
        "generated_at":   timestamp.isoformat(),
        "broadcast_hour": timestamp.strftime("%Y-%m-%d %H:00"),
        "editorial_standard": "cross-source verification + attribution",
        "total_segments": len(segments),
        "source_backed": bool(stories),
        "source_story_count": len(stories or []),
        "source_backed_stories": [
            {
                "title": s.get("title", ""),
                "description": s.get("description", ""),
                "source": s.get("source_name", ""),
                "source_lang": s.get("source_lang", ""),
                "all_sources": s.get("all_sources", [s.get("source_name", "")]),
                "confidence": s.get("confidence", 0),
                "verification": s.get("verification", ""),
                "link": s.get("link", ""),
                "pub_date": s.get("pub_date", ""),
                "source_url": s.get("source_url", ""),
            }
            for s in (stories or [])
        ],
        "segments":       segments
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  [OK] Script saved: {filepath}")
    return filepath


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    timestamp = datetime.datetime.now()
    print(f"\n=== Mole FM Professional News Fetcher === {timestamp.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Standard: Cross-source verification + attribution (NPR/BBC principles)")

    # Fetch all sources
    all_sources = NEWS_SOURCES + [
        {**s, "tier": s.get("tier", 2)}
        for s in load_autosearch_sources()
    ]
    all_items = []
    live_count = 0
    for source in all_sources:
        print(f"  Fetching [T{source.get('tier',2)}] {source['name']}...")
        items = fetch_rss(source)
        if items:
            live_count += 1
        all_items.extend(items)
        print(f"    → {len(items)} stories")

    print(f"\n  Total fetched: {len(all_items)} from {live_count}/{len(all_sources)} live sources")

    # Cross-source verification
    print("  Running cross-source verification...")
    verified = cross_corroborate(all_items)
    verified.sort(key=lambda s: (
        -pub_date_timestamp(s.get("pub_date", "")),
        -s.get("source_count", 1),
        -s.get("confidence", 0),
    ))
    confirmed = sum(1 for v in verified if "CONFIRMED" in v.get("verification",""))
    print(f"  Verified pool: {len(verified)} stories ({confirmed} multi-source confirmed)")

    # Deduplication against recent broadcasts
    seen_titles = load_seen_titles(window_hours=6)
    print(f"  Seen titles in last 6h: {len(seen_titles)}")

    fresh, repeat = [], []
    for story in verified:
        fp = story.get("fingerprint", title_fingerprint(story["title"]))
        if fp in seen_titles:
            repeat.append(story)
        else:
            fresh.append(story)

    # Fill broadcast: fresh first, then repeated (corroborated preferred over single)
    chosen = fresh[:TARGET_ARTICLES]
    if len(chosen) < TARGET_ARTICLES:
        needed = TARGET_ARTICLES - len(chosen)
        chosen += repeat[:needed]
        print(f"  [INFO] {len(fresh)} fresh → filled {needed} from repeated.")

    if not chosen:
        print("  [WARN] No verified stories — using placeholder.")
        chosen = [{
            "title": "Mole FM est en ligne",
            "description": "Bienvenue sur Mole FM, votre radio communautaire haïtienne.",
            "link": "", "source_name": "Mole FM", "source_tier": 1,
            "all_sources": ["Mole FM"], "confidence": 100,
            "verification": "CONFIRMED", "fingerprint": "molefm en ligne",
        }]

    print(f"  Broadcasting: {len(chosen)} stories")
    for i, s in enumerate(chosen, 1):
        conf = s.get("confidence", 50)
        verif = s.get("verification","?")
        srcs  = ", ".join(s.get("all_sources", [s["source_name"]]))
        print(f"    {i}. [{verif} {conf}%] {s['title'][:60]}")
        print(f"       Sources: {srcs}")

    # Save seen fingerprints
    save_seen_titles([s.get("fingerprint", title_fingerprint(s["title"])) for s in chosen])

    # Log for editorial transparency
    log_verification_run(verified, chosen, timestamp)

    # Weather
    print("  Fetching weather...")
    weather_data = get_weather_haiti()

    # Build script
    print("  Building professional broadcast script...")
    segments = build_french_script(chosen, timestamp, weather_data=weather_data)

    path = save_script(segments, timestamp, chosen)
    print(f"  Done. Segments: {len(segments)} | Verified stories: {len(chosen)}")
    return path, segments


if __name__ == "__main__":
    run()
