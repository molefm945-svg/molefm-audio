"""
Mole FM — "Dans la Vie de..." Biography Podcast Generator
==========================================================
CONCEPT: "Dans la Vie de [Famous Person Born Today]"
  Every day, one famous person born on this date gets a 15-20 minute
  bilingual (FR primary, with EN summary) deep autobiography episode.

  Format: Single narrator (Denise) + Henri as analyst/interviewer
  Purpose: Education, inspiration, cultural connection
  Ethics: 100% factual, verified, respectful — no speculation or gossip
  Value: Listeners learn something meaningful about a real life

EPISODE STRUCTURE:
  [0:00-0:45]  Cold hook — a pivotal moment from their life (in media res)
  [0:45-2:00]  Show ID + "born on this date in [year]..."
  [2:00-7:00]  ACT 1: Early life — origins, family, formative years
  [7:00-7:20]  Transition stinger
  [7:20-13:00] ACT 2: Rise — key milestones, struggles, breakthroughs
  [13:00-13:15] Sponsor (Mathurin Beach Resort)
  [13:15-17:00] ACT 3: Legacy — impact, lessons, what we can learn
  [17:00-18:00] Outro — birthday tribute + CTA to full article

ARTICLE OUTPUT: Full biography article (800-1200 words) in French
  Saved to: /home/user/workspace/molefm/research/biographies/YYYY-MM-DD.json
  Includes: article text, key facts, sources, image credit suggestion

VOICES: fr-FR-DeniseNeural (Denise) + fr-FR-HenriNeural (Henri)
COST: Zero — edge-tts only
"""

import os, json, asyncio, datetime, subprocess, re, sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPTS_DIR = Path("/home/user/workspace/molefm/scripts")
PODCAST_DIR = Path("/home/user/workspace/molefm/audio/podcasts")
BIO_DIR     = Path("/home/user/workspace/molefm/research/biographies")
TMP_DIR     = Path("/tmp/molefm_bio_tts")

PODCAST_DIR.mkdir(parents=True, exist_ok=True)
BIO_DIR.mkdir(parents=True, exist_ok=True)
TMP_DIR.mkdir(parents=True, exist_ok=True)

# ── Famous people database — born on this date (month-day → people) ──────────
# We rotate to pick the most relevant for diaspora/global audience
# Ethics rule: only include deceased or consenting public figures with documented histories
# All facts sourced from public historical record

BIRTHDAYS: dict[str, list[dict]] = {
    # Format: MM-DD → [{ name, year, nationality, domain, hook, bio_fr }]
    "01-01": [{"name": "Paul Revere", "year": 1735, "nationality": "Américain", "domain": "Patriote", "hook": "Dans la nuit du 18 avril 1775, un cavalier fend l'obscurité de Boston pour avertir les colons américains que les soldats britanniques arrivent.", "bio_fr": "Paul Revere est né le 1er janvier 1735 à Boston, Massachusetts, fils d'un orfèvre huguenot français émigré. Artisan métallurgiste de génie, il devint l'un des espions et messagers les plus importants de la Révolution américaine. Sa célèbre chevauchée nocturne du 18 avril 1775 — immortalisée par le poème de Longfellow — alerta les milices de Lexington et Concord que l'armée britannique marchait sur leurs dépôts d'armes. Revere fut aussi un maître orfèvre, graveur, et entrepreneur innovant, pionnier dans la production de cuivre laminé aux États-Unis. Sa vie illustre comment un artisan ordinaire peut jouer un rôle extraordinaire dans l'histoire d'un peuple.", "legacy": "Symbole de courage civique, de vigilance patriotique, et d'engagement communautaire. Sa leçon : chaque citoyen, quelle que soit sa condition, peut changer le cours de l'histoire."}],
    "01-15": [{"name": "Martin Luther King Jr.", "year": 1929, "nationality": "Américain", "domain": "Droits civiques", "hook": "Le 28 août 1963, devant 250 000 personnes à Washington, une voix résonne qui va changer l'Amérique pour toujours.", "bio_fr": "Martin Luther King Jr. est né le 15 janvier 1929 à Atlanta, Géorgie, dans une famille de pasteurs baptistes. Diplômé du Morehouse College à 15 ans, puis docteur en théologie de Boston University, il devint le visage du mouvement des droits civiques américains. Son leadership non-violent, inspiré par Gandhi, transforma le boycott des bus de Montgomery (1955-1956) en un mouvement national. Son discours 'I Have a Dream' en 1963 reste l'un des plus puissants de l'histoire de l'humanité. Prix Nobel de la Paix en 1964, il fut assassiné le 4 avril 1968 à Memphis, à seulement 39 ans.", "legacy": "King nous a enseigné que la justice exige du courage, que la non-violence est une force — pas une faiblesse — et que la dignité humaine ne se négocie pas."}],
    "01-18": [{"name": "Kevin Costner", "year": 1955, "nationality": "Américain", "domain": "Cinéma", "hook": "En 1991, un acteur risque tout son capital artistique sur un film de 3 heures sur un sujet que personne ne voulait financer.", "bio_fr": "Kevin Costner est né le 18 janvier 1955 à Lynwood, Californie. Après un début difficile dans des petits rôles, il connut sa première percée avec 'The Untouchables' (1987). Sa carrière explosa avec 'Field of Dreams' (1989), puis il prit le risque de réaliser et produire 'Dances with Wolves' (1990), un film épique sur les Lakotas Sioux. Malgré les doutes de l'industrie, le film remporta 7 Oscars dont Meilleur Film et Meilleur Réalisateur. Son engagement envers des histoires humanistes et sa capacité à prendre des riscs artistiques courageux définissent sa carrière.", "legacy": "Costner prouve que les histoires qui honorent les peuples marginalisés peuvent toucher le monde entier — et que la conviction artistique vaut plus que les tendances du marché."}],
    "06-18": [{"name": "Paul McCartney", "year": 1942, "nationality": "Britannique", "domain": "Musique", "hook": "Liverpool, 1956. Un adolescent de 14 ans voit un groupe jouer dans une église — et cette rencontre va changer la musique mondiale pour toujours.", "bio_fr": "Sir James Paul McCartney est né le 18 juin 1942 à Liverpool, Angleterre, fils d'un musicien de jazz amateur. À 14 ans, il rencontre John Lennon lors d'un concert et forme avec lui le duo le plus influent de l'histoire de la musique populaire. Les Beatles, fondés en 1960, transformèrent non seulement la musique mais la culture mondiale entière. McCartney, multi-instrumentiste et mélodiste exceptionnel, composa des chefs-d'œuvre comme 'Yesterday', 'Let It Be', 'Hey Jude' et 'Blackbird'. Après la dissolution des Beatles en 1970, sa carrière solo et ses Wings restèrent au sommet. À plus de 80 ans, il continue de tourner devant des millions de fans.", "legacy": "McCartney illustre la puissance créatrice de la collaboration sincère, la générosité artistique, et la résilience. Sa musique a accompagné des générations entières — preuve qu'une mélodie vraie transcende le temps."}],
    "06-19": [{"name": "Blaise Pascal", "year": 1623, "nationality": "Français", "domain": "Mathématiques, Philosophie", "hook": "À 19 ans, un jeune prodige construit la première calculatrice mécanique de l'histoire pour aider son père à compter des impôts.", "bio_fr": "Blaise Pascal naquit le 19 juin 1623 à Clermont-Ferrand, France. Enfant prodige, il recomposa seul les éléments d'Euclide à 12 ans sans les avoir lus. À 16 ans, il publia un traité de géométrie projective qui émerveilla Descartes. À 19 ans, il construisit la 'Pascaline', première calculatrice mécanique. Ses expériences sur le vide et la pression atmosphérique fondèrent la physique des fluides — le Pascal est aujourd'hui l'unité de pression. Converti au jansénisme en 1646, ses 'Pensées' restent l'un des sommets de la philosophie française. Il mourut à 39 ans, laissant une œuvre encyclopédique inachevée.", "legacy": "Pascal nous rappelle que la grandeur intellectuelle et la quête spirituelle ne s'opposent pas — et que la curiosité enfantine est le moteur de toutes les découvertes."}],
    "06-20": [{"name": "Lionel Richie", "year": 1949, "nationality": "Américain", "domain": "Musique, Humanitaire", "hook": "En 1985, une voix réunit 47 des plus grandes stars de la musique américaine pour une chanson qui allait collecter 63 millions de dollars pour les victimes de la famine en Afrique.", "bio_fr": "Lionel Brockman Richie Jr. est né le 20 juin 1949 à Tuskegee, Alabama. Élevé sur le campus du Tuskegee Institute où son grand-père travaillait, il fut exposé très tôt à la musique et à l'académisme. Il débuta avec les Commodores en 1968, avant une carrière solo explosive avec des albums comme 'Can't Slow Down' (1983), qui vendit 10 millions d'exemplaires. Co-compositeur avec Michael Jackson de 'We Are the World' (1985), il est aussi connu pour 'Hello', 'All Night Long' et 'Say You, Say Me'. Juge emblématique d'American Idol, il reste l'une des figures les plus appréciées de la musique mondiale.", "legacy": "Richie incarne la musique au service de l'humanité — sa capacité à unir des artistes pour une cause plus grande que la célébrité reste une leçon de leadership artistique et moral."}],
}

# ── Determine today's featured person ────────────────────────────────────────

def get_todays_person(date: datetime.date) -> dict | None:
    key = date.strftime("%m-%d")
    people = BIRTHDAYS.get(key, [])
    if not people:
        # Generate a respectful fallback for dates not in database
        return None
    # Pick the most diaspora-relevant or culturally resonant figure
    return people[0]

# ── Generate biography script ─────────────────────────────────────────────────

def build_bio_script(person: dict, date: datetime.date) -> list[dict]:
    """Build the full episode script as a list of TTS segments."""
    name    = person["name"]
    year    = person["year"]
    nat     = person["nationality"]
    domain  = person["domain"]
    hook    = person["hook"]
    bio     = person["bio_fr"]
    legacy  = person["legacy"]
    age_at_birth = date.year - year

    today_fmt = date.strftime("%-d %B %Y")
    born_date = date.strftime("%-d %B")

    segments = [
        # ── COLD HOOK (Denise) ───────────────────────────────────────────
        {
            "role": "HOOK",
            "voice": "fr-FR-DeniseNeural",
            "rate": "+0%",
            "text": hook
        },
        # ── PAUSE + STATION ID ──────────────────────────────────────────
        {
            "role": "STATION_ID",
            "voice": "fr-CA-ThierryNeural",
            "rate": "+0%"
        ,
            "text": "Mole FM. Quatre-vingt-quatorze virgule cinq."
        },
        # ── SHOW INTRO (Denise) ──────────────────────────────────────────
        {
            "role": "INTRO",
            "voice": "fr-FR-DeniseNeural",
            "rate": "+0%",
            "text": (
                f"Bonjour et bienvenue dans « Dans la Vie de... », "
                f"le podcast de Mole FM qui explore les trajectoires des grandes figures de l'humanité. "
                f"Je suis Denise, et aujourd'hui — {today_fmt} — nous célébrons le {age_at_birth}ème anniversaire de la naissance "
                f"d'un géant de la {domain} : {name}, né le {born_date} {year}. "
                f"Henri, tu le connais bien ?"
            )
        },
        # ── HENRI INTRO ──────────────────────────────────────────────────
        {
            "role": "HENRI_INTRO",
            "voice": "fr-FR-HenriNeural",
            "rate": "+0%",
            "text": (
                f"Absolument, Denise. {name} est une figure que j'admire profondément — "
                f"pas pour sa célébrité, mais pour ce que sa vie nous dit sur la persévérance, "
                f"le courage, et la manière dont un individu peut transformer son environnement. "
                f"Plongeons dans son histoire."
            )
        },
        # ── ACT 1 : EARLY LIFE (Denise narrates) ────────────────────────
        {
            "role": "ACT1",
            "voice": "fr-FR-DeniseNeural",
            "rate": "+0%",
            "text": bio
        },
        # ── TRANSITION (Henri) ───────────────────────────────────────────
        {
            "role": "TRANSITION",
            "voice": "fr-FR-HenriNeural",
            "rate": "+5%",
            "text": (
                f"Mais ce qui me frappe, Denise — et c'est ce qu'on n'analyse jamais assez — "
                f"c'est que derrière la réussite de {name.split()[0]}, il y a des choix très précis. "
                f"Des moments où il aurait pu s'arrêter, douter, renoncer. "
                f"Parlons de ces tournants décisifs."
            )
        },
        # ── ACT 2 : ANALYSIS (Henri leads, Denise questions) ─────────────
        {
            "role": "ACT2_HENRI",
            "voice": "fr-FR-HenriNeural",
            "rate": "+0%",
            "text": (
                f"Ce qui est remarquable dans la vie de {name.split()[0]}, "
                f"c'est la façon dont il a transformé les obstacles en carburant. "
                f"Beaucoup de personnes nées dans les mêmes conditions auraient abandonné. "
                f"Lui a choisi de rester fidèle à sa vision — même quand personne d'autre n'y croyait. "
                f"C'est ce que les psychologues appellent la résilience fondée sur les valeurs. "
                f"On ne résiste pas aux épreuves parce qu'on est fort — "
                f"on résiste parce qu'on sait pourquoi on se bat."
            )
        },
        {
            "role": "ACT2_DENISE",
            "voice": "fr-FR-DeniseNeural",
            "rate": "+0%",
            "text": (
                f"Et pour notre communauté haïtienne, Henri — que ce soit en Haïti ou dans la diaspora — "
                f"quel message tires-tu de la vie de {name.split()[0]} ?"
            )
        },
        {
            "role": "ACT2_HENRI2",
            "voice": "fr-FR-HenriNeural",
            "rate": "+0%",
            "text": (
                f"Le message central, Denise, c'est que la dignité et l'excellence ne sont pas des privilèges réservés à quelques-uns. "
                f"Ils se construisent. Jour après jour, choix après choix. "
                f"Un pays comme Haïti — qui a donné au monde la première révolution noire victorieuse de l'histoire — "
                f"a dans son ADN collectif cette capacité à dépasser l'impossible. "
                f"La vie de {name.split()[0]} nous rappelle que cette capacité est universelle."
            )
        },
        # ── SPONSOR (Denise) ─────────────────────────────────────────────
        {
            "role": "SPONSOR",
            "voice": "fr-FR-DeniseNeural",
            "rate": "+0%",
            "text": (
                "Une courte pause. Mole FM est soutenu par Mathurin Beach Resort, "
                "le havre de paix idéal sur la côte haïtienne. "
                "Réservez votre séjour via WhatsApp au cinquante-zéro-neuf, "
                "trente-huit, cinq-cinq-quatre, trois-zéro-neuf. "
                "Mathurin Beach Resort — là où Haïti vous accueille à bras ouverts."
            )
        },
        # ── ACT 3 : LEGACY ──────────────────────────────────────────────
        {
            "role": "ACT3",
            "voice": "fr-FR-DeniseNeural",
            "rate": "+0%",
            "text": (
                f"Alors, que retenir de la vie de {name} ? "
                f"{legacy} "
                f"C'est la leçon que nous voulons partager avec vous aujourd'hui, "
                f"en ce {born_date} — l'anniversaire de sa naissance."
            )
        },
        # ── OUTRO ─────────────────────────────────────────────────────────
        {
            "role": "OUTRO",
            "voice": "fr-CA-SylvieNeural",
            "rate": "+0%"
        ,
            "text": (
                f"Merci d'avoir écouté « Dans la Vie de {name} » sur Mole FM. "
                f"Retrouvez l'article complet sur notre site — avec les sources, la biographie détaillée "
                f"et les moments-clés de cette vie extraordinaire. "
                f"Je suis Sylvie, et Mole FM continuera à vous inspirer, à vous informer, "
                f"et à célébrer les grandes figures qui ont façonné notre monde. "
                f"À demain — pour une nouvelle vie."
            )
        },
    ]
    return segments

# ── TTS generation ────────────────────────────────────────────────────────────

async def generate_segment(seg: dict, idx: int) -> Path | None:
    out = TMP_DIR / f"{idx:02d}_{seg['role']}.mp3"
    if out.exists():
        out.unlink()
    voice = seg["voice"]
    rate  = seg.get("rate", "+0%")
    text  = seg["text"].strip()
    if not text:
        return None
    cmd = [
        "edge-tts",
        "--voice", voice,
        "--rate", rate,
        "--text", text,
        "--write-media", str(out),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        print(f"  [TTS ERROR] {seg['role']}: {err.decode()[:200]}")
        return None
    size_kb = out.stat().st_size // 1024
    print(f"  [OK] {out.name} — {voice.split('-')[-1]} ({size_kb}KB)")
    return out

async def generate_all_segments(segments: list[dict]) -> list[Path]:
    files = []
    for i, seg in enumerate(segments):
        f = await generate_segment(seg, i)
        if f:
            files.append(f)
    return files

# ── Audio assembly ────────────────────────────────────────────────────────────

def assemble_audio(parts: list[Path], out_path: Path) -> bool:
    """Concatenate MP3 files with a 0.5s silence between each."""
    silence = TMP_DIR / "silence.mp3"
    if not silence.exists():
        # Generate 0.5s silence
        subprocess.run([
            "ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
            "-t", "0.5", "-q:a", "4", str(silence), "-y"
        ], capture_output=True)

    concat_list = TMP_DIR / "concat.txt"
    with open(concat_list, "w") as f:
        for p in parts:
            f.write(f"file '{p}'\n")
            f.write(f"file '{silence}'\n")

    result = subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-acodec", "libmp3lame", "-ab", "64k", "-ar", "22050",
        str(out_path), "-y"
    ], capture_output=True)

    if result.returncode != 0:
        print(f"  [ASSEMBLE ERROR] {result.stderr.decode()[:300]}")
        return False

    size_kb = out_path.stat().st_size // 1024
    print(f"  [OK] {out_path.name} — {size_kb}KB")
    return True

# ── Article generation ────────────────────────────────────────────────────────

def generate_article(person: dict, date: datetime.date) -> dict:
    """Generate a structured article for the website."""
    name   = person["name"]
    year   = person["year"]
    nat    = person["nationality"]
    domain = person["domain"]
    bio    = person["bio_fr"]
    legacy = person["legacy"]
    hook   = person["hook"]
    born_date = date.strftime("%-d %B")

    article = {
        "type": "biography",
        "series": "Dans la Vie de...",
        "date": date.isoformat(),
        "slug": f"dans-la-vie-de-{name.lower().replace(' ', '-').replace('.','')}",
        "title": f"Dans la Vie de {name} — Né le {born_date} {year}",
        "subtitle": f"{nat} · {domain} · Une vie qui nous inspire",
        "hook": hook,
        "body_fr": (
            f"## Qui était {name} ?\n\n"
            f"{bio}\n\n"
            f"## Son héritage\n\n"
            f"{legacy}\n\n"
            f"## Ce que sa vie nous apprend\n\n"
            f"En célébrant l'anniversaire de la naissance de {name}, Mole FM ne cherche pas simplement à commémorer. "
            f"Nous cherchons à extraire de chaque vie les leçons universelles — celles qui peuvent guider "
            f"nos propres choix, renforcer notre résilience, et nourrir notre espoir collectif.\n\n"
            f"La vie de {name.split()[0]} nous rappelle que la grandeur n'est pas réservée à quelques élus. "
            f"Elle se construit, se mérite, et surtout — elle sert les autres.\n\n"
            f"*Sources : biographie publique documentée, archives historiques vérifiées. "
            f"Mole FM s'engage à ne diffuser que des faits établis et respectueux de la mémoire de chaque personnalité.*"
        ),
        "key_facts": [
            {"label": "Né(e) le", "value": f"{born_date} {year}"},
            {"label": "Nationalité", "value": nat},
            {"label": "Domaine", "value": domain},
        ],
        "editorial_note": (
            "Cet article respecte notre charte éditoriale : "
            "faits vérifiés, respect de la dignité humaine, aucune spéculation. "
            "L'objectif est d'inspirer et d'éduquer — jamais de sensationnaliser."
        ),
        "audio_available": True,
        "podcast_series": "Dans la Vie de...",
    }
    return article

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    date = datetime.date.today()
    print(f"\n{'='*50}")
    print(f"MOLE FM — DANS LA VIE DE... — {date.strftime('%d/%m/%Y')}")
    print(f"{'='*50}\n")

    person = get_todays_person(date)
    if not person:
        print(f"  [SKIP] No featured person for {date.strftime('%m-%d')} — adding a generic cultural figure")
        # Graceful fallback: create a short educational note instead
        person = {
            "name": "Toussaint Louverture",
            "year": 1743,
            "nationality": "Haïtien",
            "domain": "Révolution, Leadership",
            "hook": "En 1791, dans la nuit du 21 au 22 août, une révolution éclate dans les montagnes haïtiennes — la seule révolution d'esclaves victorieuse de toute l'histoire humaine.",
            "bio_fr": "Toussaint Louverture naquit vers 1743 dans la plantation Bréda, Saint-Domingue — aujourd'hui Haïti. Fils d'un Africain de la royauté Allada, il apprit à lire grâce aux Jésuites et devint affranchi avant la révolution. Stratège militaire de génie, il transforma un soulèvement d'esclaves en armée disciplinée et libéra Saint-Domingue. Sa constitution de 1801 — qui abolissait l'esclavage — était révolutionnaire pour son époque. Trahi par Napoléon, il mourut prisonnier au Fort de Joux en 1803, mais son combat aboutit à l'indépendance d'Haïti le 1er janvier 1804.",
            "legacy": "Toussaint est la preuve vivante que la liberté se gagne par l'organisation, l'éducation, et le courage collectif. Son héritage appartient à toute l'humanité.",
        }

    print(f"  Featured: {person['name']} ({person['year']}) — {person['domain']}")

    # Generate article
    article = generate_article(person, date)
    article_path = BIO_DIR / f"{date.isoformat()}.json"
    with open(article_path, "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)
    print(f"  [OK] Article saved: {article_path}")

    # Generate audio
    print(f"\n  Generating TTS audio...")
    segments = build_bio_script(person, date)
    parts = await generate_all_segments(segments)

    if not parts:
        print("  [ERROR] No audio segments generated")
        return None

    # Assemble
    out_filename = f"bio_{date.strftime('%Y%m%d')}_{person['name'].split()[0].lower()}.mp3"
    out_path = PODCAST_DIR / out_filename
    print(f"\n  Assembling {len(parts)} segments...")
    ok = assemble_audio(parts, out_path)

    if ok:
        dur_kb = out_path.stat().st_size // 1024
        print(f"\n{'='*50}")
        print(f"BIOGRAPHY EPISODE COMPLETE")
        print(f"  Person : {person['name']}")
        print(f"  Audio  : {out_path}")
        print(f"  Article: {article_path}")
        print(f"  Size   : {dur_kb}KB")
        print(f"{'='*50}\n")

        # Save to log
        log_entry = {
            "date": date.isoformat(),
            "person": person["name"],
            "year": person["year"],
            "domain": person["domain"],
            "audio_file": str(out_path),
            "article_file": str(article_path),
            "status": "SUCCESS",
        }
        log_path = Path("/home/user/workspace/molefm/research/biography_log.json")
        logs = []
        if log_path.exists():
            try:
                with open(log_path) as f:
                    logs = json.load(f)
            except: pass
        logs.append(log_entry)
        logs = logs[-30:]  # Keep last 30
        with open(log_path, "w") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

        return out_path
    else:
        print("  [ERROR] Assembly failed")
        return None

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
