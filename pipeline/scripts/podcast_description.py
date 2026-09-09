"""Offline podcast source notes and filename/audio-bound metadata. No fetching."""
import hashlib
import json
import os
import re
import tempfile
from urllib.parse import urlsplit, urlunsplit

SOURCE_HOMEPAGES = {
    "Le Nouvelliste": "https://lenouvelliste.com",
    "Radio Métropole": "https://metropole.ht",
    "Juno7": "https://juno7.ht",
    "Haiti24": "https://haiti24.net",
    "Rezo Nodwes": "https://rezonodwes.com",
    "Haiti Liberté": "https://haitiliberte.com",
    "Haiti Press Network": "https://hpnhaiti.com",
    "Haitian Times": "https://haitiantimes.com",
    "RFI Haïti": "https://www.rfi.fr/fr/tag/haïti",
    "BBC Afrique": "https://www.bbc.com/afrique",
}
SCHEMA = "molefm-podcast-metadata-v1"


def source_url(value):
    """Keep supplied HTTP(S) links; reject credentials, whitespace and active URLs."""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > 4096 or re.search(r'[\s\x00-\x1f\x7f<>"\\]', value):
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            return ""
        _ = parts.port
        return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, parts.fragment))
    except ValueError:
        return ""


def _label(value):
    return " ".join(str(value or "").split())[:500]


def source_references(stories):
    references, seen = [], set()

    def add(publisher, article="", supplied="", title=""):
        publisher = _label(publisher) or "Éditeur non précisé"
        article, supplied = source_url(article), source_url(supplied)
        url = article or supplied or SOURCE_HOMEPAGES.get(publisher, "")
        kind = "article" if article else "source_link" if supplied else "publisher_homepage" if url else "missing"
        key = (url or publisher.casefold())
        if key in seen:
            return
        seen.add(key)
        references.append({"publisher": publisher, "url": url, "kind": kind, "title": _label(title)})

    for story in stories:
        if not isinstance(story, dict):
            continue
        publisher = story.get("source") or story.get("source_name")
        names = story.get("all_sources", [])
        if not isinstance(names, list):
            names = []
        if not publisher:
            attr = re.sub(r"^plusieurs médias dont\s+", "", _label(story.get("source_attr")), flags=re.I)
            names = [name.strip() for name in re.split(r"\s+et\s+|,|;", attr) if name.strip()] + names
            publisher = names[0] if names else ""
        article = next((url for key in ("link", "article_url", "url") if (url := source_url(story.get(key)))), "")
        if publisher or article or story.get("source_url"):
            add(publisher, article, story.get("source_url"), story.get("title"))
        supplied_references = story.get("source_references", [])
        if not isinstance(supplied_references, list):
            supplied_references = []
        for reference in supplied_references:
            if isinstance(reference, dict):
                add(reference.get("publisher") or reference.get("source"), reference.get("link") or reference.get("url"), title=reference.get("title"))
        for name in names:
            if isinstance(name, str) and name and name != publisher:
                add(name)
    # Supplied article URLs supersede a fallback for that publisher, but different
    # supplied articles from the same publisher are all retained.
    linked = {ref["publisher"] for ref in references if ref["kind"] in ("article", "source_link")}
    return [ref for ref in references if ref["kind"] in ("article", "source_link") or ref["publisher"] not in linked]


def build_podcast_description(stories, date_display, duration_seconds):
    references = source_references(stories)
    lines = []
    for ref in references:
        label = ref["publisher"] + (f" — {ref['title']}" if ref["title"] else "")
        if ref["kind"] == "article":
            lines.append(f"  • {label} — article : {ref['url']}")
        elif ref["kind"] == "source_link":
            lines.append(f"  • {label} — lien source fourni (article non identifié) : {ref['url']}")
        elif ref["kind"] == "publisher_homepage":
            lines.append(f"  • {label} — site de l’éditeur (repli, article non fourni) : {ref['url']}")
        else:
            lines.append(f"  • {label} — URL d’article non fournie")
    if not lines:
        lines = ["  • Aucun lien source fourni pour cet épisode."]
    mins, secs = divmod(int(duration_seconds), 60)
    return (f"Émission quotidienne Mole FM — {date_display}.\n"
            "Analyse des actualités d’Haïti avec Denise et Henri.\n"
            f"Durée : {mins}m{secs:02d}s\n\nSources & Références :\n" + "\n".join(lines)
            + "\n\nLiens de provenance fournis ; leur présence ne constitue pas une vérification indépendante."
            "\nMole FM 94.5 — molefm.com")


def metadata_path(audio_path):
    return os.fspath(audio_path) + ".metadata.json"


def audio_sha256(audio_path):
    digest = hashlib.sha256()
    with open(audio_path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_metadata(value, filename):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("filename") != filename:
        raise ValueError("Podcast metadata identity mismatch")
    if not isinstance(value.get("description"), str) or not value["description"].strip() or len(value["description"]) > 100000:
        raise ValueError("Podcast description missing or oversized")
    if not re.fullmatch(r"[a-f0-9]{64}", value.get("audio_sha256", "")):
        raise ValueError("Podcast audio binding missing")
    return value


def read_metadata(file_path, filename, audio_path=None):
    with open(file_path, "r", encoding="utf-8") as source:
        value = validate_metadata(json.load(source), filename)
    if audio_path and value["audio_sha256"] != audio_sha256(audio_path):
        raise ValueError("Podcast audio metadata mismatch")
    return value


def save_metadata(audio_path, title, description, stories, duration_seconds, generated_at):
    value = {"schema": SCHEMA, "filename": os.path.basename(audio_path), "audio_sha256": audio_sha256(audio_path),
             "title": title, "description": description, "sources": source_references(stories),
             "duration_seconds": int(duration_seconds), "generated_at": generated_at}
    validate_metadata(value, value["filename"])
    target = metadata_path(audio_path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=os.path.dirname(target), delete=False) as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")
        temporary = out.name
    os.replace(temporary, target)
    return target
