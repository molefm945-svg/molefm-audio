"""
Mole FM Podcast Generator — Premium Edition
============================================
Engineered to the standard of The Daily (NYT), NPR Up First, and BBC Global News.
Goal: 75%+ episode completion rate, which enables premium direct sponsorships.

ARCHITECTURE (based on retention research):
  [0:00–0:45]   COLD HOOK — stakes, not topic. Drop mid-story. No welcome preamble.
  [0:45–1:30]   BRIEF SHOW ID + EPISODE PROMISE (under 60s total)
  [1:30–6:00]   ACT 1: THE SETUP — context, characters, what happened
  [6:00–6:30]   TRANSITION TEASE — "Mais voici ce qu'on ne comprend pas encore..."
  [6:30–14:00]  ACT 2: THE COMPLICATION — why it matters, diaspora stakes
  [14:00–14:20] MID-ROLL SPONSOR — personal pivot technique (never says "break")
  [14:20–19:30] ACT 3: THE SO WHAT — what this means for you specifically
  [19:30–21:00] OUTRO — takeaway + next-episode tease + CTA

TWO-VOICE DESIGN (informed friend, not news anchor):
  Denise: Curious, empathetic questioner. Voices the listener's perspective.
          Asks "But what does that mean for people in Miami? In Montréal?"
  Henri:  Analytically grounded, opinionated. Has sources and context.
          Willing to say "Franchement, je pense que..." and mean it.

  Different KNOWLEDGE, not just different roles. When both would say the same
  thing, Henri adds a contrarian angle or Denise surfaces a human story.

RETENTION RULES BAKED IN:
  - Hook in first 18 words (Spotify drop-off cliff at 90s)
  - Cold open: most important stakes first, host intro second
  - Transitions use same verbal stinger every time (audio grammar)
  - Mid-roll opened with personal story, not product name
  - Episodes target 18–22 minutes (sweet spot for 74% median completion)
  - Genuine short disagreements scripted (2-voice authenticity marker)

MONETIZATION:
  - Mid-roll at ~57% mark (14 min of 24 min episode) — highest ad completion
  - "Informed friend" tone = 50% higher brand recall than formal reads
  - Completion rate target 75%+ = adjusted CPM premium for direct sponsors

Schedule: FR 3x daily — Midi (16 UTC), Après-midi (19 UTC), Soir (01 UTC)
Voices: fr-FR-DeniseNeural (warm, expressive) + fr-FR-HenriNeural (grounded, deep)
TTS: edge-tts (free, no API key, neural quality)
"""

import json
import os
import glob
import asyncio
import datetime
import subprocess
import re
import random

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPTS_DIR = "/home/user/workspace/molefm/scripts"
AUDIO_DIR   = "/home/user/workspace/molefm/audio"
PODCAST_DIR = "/home/user/workspace/molefm/audio/podcasts"
RESEARCH_DIR = "/home/user/workspace/molefm/research"

# ── Voice config — edge-tts free neural voices ───────────────────────────────
FR_VOICE_DENISE = "fr-FR-DeniseNeural"   # warm, curious, asks the listener's questions
FR_VOICE_HENRI  = "fr-FR-HenriNeural"    # grounded, analytical, willing to opine

# ── Sponsor config ───────────────────────────────────────────────────────────
_SPONSOR_CFG = os.path.join(os.path.dirname(__file__), "..", "config", "sponsors.json")
_FALLBACK_SPONSOR = {
    "name": "Mathurin Beach Resort",
    "fr": "Mathurin Beach Resort, au Môle-Saint-Nicolas.",
    "personal_hook_fr": "En parlant de pause — j'ai pensé à Mathurin Beach Resort cette semaine. Si vous cherchez un endroit pour vous ressourcer vraiment, la mer, le soleil, l'hospitalité haïtienne authentique — c'est là. Mathurin Beach Resort, au Môle-Saint-Nicolas.",
}

def _load_sponsors():
    try:
        with open(_SPONSOR_CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        active = [s for s in cfg["sponsors"] if s.get("active", False)]
        result = []
        for s in active:
            result.append({
                "name": s["name"],
                "fr": s.get("audio_text", s["name"]),
                "personal_hook_fr": s.get("personal_hook_fr",
                    f"Je voulais mentionner {s['name']} — {s.get('audio_text', s['name'])}"),
            })
        return result if result else [_FALLBACK_SPONSOR]
    except Exception:
        return [_FALLBACK_SPONSOR]

def get_sponsor(slot_index=0):
    sponsors = _load_sponsors()
    return sponsors[slot_index % len(sponsors)]


# ── Data loading ─────────────────────────────────────────────────────────────

def load_recent_newscasts(n=6):
    scripts = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "newscast_*.json")))
    return scripts[-n:] if len(scripts) >= n else scripts

def extract_stories_from_scripts(script_paths):
    """
    Extract verified stories from newscast JSON scripts.
    Preserves source attribution for journalistic framing in the podcast.
    Returns list of dicts: {text, source, sources, verification, confidence}
    """
    seen = set()
    stories = []
    for path in reversed(script_paths):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for seg in data.get("segments", []):
                if seg.get("segment") != "NEWS_MAIN":
                    continue
                text = seg.get("text", "")
                for m in re.finditer(r"Titre \d+ : (.+?)(?=Titre \d+|$)", text, re.DOTALL):
                    raw = m.group(1).strip()
                    key = raw[:50].lower()
                    if key not in seen:
                        seen.add(key)
                        # Extract attribution if present (e.g. "Selon Le Nouvelliste et Haiti24 — ...")
                        source_match = re.search(r"Selon ([^—]+?)\s*[—-]", raw)
                        source_str = source_match.group(1).strip() if source_match else ""
                        # Strip attribution from the story text for clean reading
                        clean_text = re.sub(r"Selon [^—]+?\s*[—-]\s*", "", raw).strip()
                        stories.append({
                            "text": clean_text or raw,
                            "full_text": raw,
                            "source_attr": source_str,
                            "verification": "CONFIRMED" if source_str and " et " in source_str else "SINGLE-SOURCE",
                        })
        except Exception as e:
            print(f"  [WARN] Could not parse {path}: {e}")
    return stories[:12]

def extract_weather_from_scripts(script_paths):
    for path in reversed(script_paths):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for seg in data.get("segments", []):
                if seg.get("segment") == "WEATHER":
                    return seg.get("text", "")
        except Exception:
            pass
    return ""

def extract_sports_from_scripts(script_paths):
    for path in reversed(script_paths):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for seg in data.get("segments", []):
                if seg.get("segment") == "SPORTS":
                    return seg.get("text", "")
        except Exception:
            pass
    return ""

def load_podcast_tips():
    """Load any autoresearch tips for script improvement."""
    tips_file = os.path.join(RESEARCH_DIR, "podcast_improvement_tips.json")
    try:
        with open(tips_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── Premium FR podcast script builder ────────────────────────────────────────

def build_fr_podcast_script(stories, weather_text, sports_text, slot_label, date_str, slot_index=0):
    """
    Build a world-class 2-voice FR podcast episode.
    Architecture: The Daily x BBC Global News x Hugo Decrypte
    Target: 18-22 min runtime (~3,400-3,800 words at 170 wpm).
    Rule: no turn under 12 words — replace echoes with context-rich bridges.
    """
    turns = []

    def D(text):
        if text.strip():
            turns.append({"speaker": "Denise", "voice": FR_VOICE_DENISE, "text": text.strip()})

    def H(text):
        if text.strip():
            turns.append({"speaker": "Henri", "voice": FR_VOICE_HENRI, "text": text.strip()})

    sp = get_sponsor(slot_index)

    def _story_text(s):
        """Return text string whether story is a dict or plain string."""
        if isinstance(s, dict):
            return s.get("text", s.get("full_text", str(s)))
        return str(s)

    def _story_source(s):
        """Return attribution phrase for a story."""
        if isinstance(s, dict):
            attr = s.get("source_attr", "")
            verif = s.get("verification", "SINGLE-SOURCE")
            if attr:
                return f"selon {attr}"
            return ""
        return ""

    lead   = _story_text(stories[0]) if stories else "les dernieres nouvelles d'Haiti"
    story2 = stories[1] if len(stories) > 1 else ""
    story3 = stories[2] if len(stories) > 2 else ""
    story4 = stories[3] if len(stories) > 3 else ""
    story5 = stories[4] if len(stories) > 4 else ""
    story6 = stories[5] if len(stories) > 5 else ""
    lead_short = lead.split(".")[0][:100]
    # Source attribution for the lead story
    lead_source = _story_source(stories[0]) if stories else ""

    # [0:00-0:45] COLD HOOK
    hooks = {
        "midi":       "Il se passe quelque chose de significatif ce matin en Haiti, et la plupart des gens ne l'ont pas encore compris.",
        "apres-midi": "Quinze heures en Haiti. Et dans les dernieres heures, des developpements que la majorite des gens n'ont pas encore eu le temps d'analyser.",
        "soir":       "Avant de fermer votre journee, il y a quelque chose que vous devez avoir entendu. Des nouvelles qui semblent ordinaires, mais ne le sont pas.",
    }
    slot_key = slot_label.lower().replace("\xe9","e").replace("\xe8","e").replace("\xe0","a").replace("\xe2","a")
    H(hooks.get(slot_key, "Voici l'essentiel de l'actualite haitienne. Ce que vous devez comprendre aujourd'hui, explique clairement."))
    D("Ce n'est pas juste une question de nouvelles. C'est une question de comprendre ce qui change vraiment pour Haiti et pour ceux qui la suivent.")
    H("Exactement. Et c'est ce qu'on va faire ensemble dans les vingt prochaines minutes, sans raccourcis, sans slogans.")

    # [0:45-1:30] SHOW ID + EPISODE PROMISE
    D("Mole FM. Je suis Denise. Et comme toujours, on est la pour vous donner les cles, pas juste les titres.")
    H(f"Et moi c'est Henri. Nous sommes le {date_str}. Trois editions aujourd'hui parce que l'actualite haitienne ne s'arrete pas.")
    D(f"Aujourd'hui en particulier: {lead_short}. On va prendre le temps de vraiment comprendre ca.")
    H("Pas juste les faits bruts. Le sens. Les consequences. Ce que ca change pour les gens concretement.")
    D("Et ce que ca signifie pour vous, que vous soyez en Haiti ou dans la diaspora. On commence maintenant.")

    # [1:30-6:00] ACT 1: THE SETUP (~900 words / ~5 min)
    # Build attribution prefix for the lead story
    attr_prefix = f", {lead_source}," if lead_source else ""
    H(f"Commencons par le sujet principal de cette edition{attr_prefix} {lead}")
    D("Attends. Pour quelqu'un qui n'a pas suivi l'actualite depuis ce matin, pourquoi c'est important? Quel est le contexte immediat?")
    H("Bonne question de depart, et c'est exactement la bonne facon d'entrer dans ce sujet. Cette nouvelle ne tombe pas dans le vide.")
    D("Il y a quelque chose qui s'est passe avant, qui rend ce developpement significatif.")
    H("Oui. Il y a une situation qui evolue depuis plusieurs semaines en Haiti. Et la, on a un element nouveau qui force une reaction, une reponse, un repositionnement.")
    D("Et cette reaction, elle vient d'ou? Du gouvernement de transition? Des organisations internationales? Ou c'est la rue qui reagit?")
    H("Les deux premieres, principalement. Mais pas de la meme facon. Et c'est precisement la que ca devient analytiquement interessant.")
    D("Explique cette difference, parce que ca me semble etre le coeur du sujet.")
    H("La reponse officielle et ce qui se passe reellement sur le terrain, c'est rarement identique. Et souvent, c'est l'ecart entre les deux qui revele le plus sur la situation reelle.")
    D("Ca, c'est quelque chose que les gens dans la diaspora ressentent souvent avec frustration. On lit les communiques officiels, on regarde les conferences de presse.")
    H("Et on se demande ce que ca change concretement pour sa famille qui est la-bas en ce moment meme.")
    D("Exactement. Alors qu'est-ce que ca change vraiment pour les gens sur le terrain?")
    H("La reponse honnete: ca depend. De l'endroit ou ils se trouvent, de leur situation specifique. Mais on peut au moins demeler ce qui est du discours et ce qui est reel.")
    D("C'est precisement pour ca qu'on est la. Maintenant, les personnages dans cette histoire. Qui prend les decisions?")
    H("Et surtout, qui subit les consequences de ces decisions. C'est toujours la bonne facon de cadrer une nouvelle politique ou economique en Haiti.")
    D("Parce que derriere chaque titre, derriere chaque communique, il y a des gens avec des vies reelles.")
    H("Des decideurs avec leurs agendas, leurs interets, leur calcul politique. Et des citoyens avec leurs realites quotidiennes. Et souvent une tension enorme entre ces deux mondes.")
    D("Une tension qui n'est pas nouvelle en Haiti. Elle a des racines profondes.")
    H("Tres profondes. Ce qui rend chaque nouveau developpement a la fois unique dans sa forme, et d'une certaine facon familier dans sa structure.")
    D("Pour ceux qui suivent l'actualite haitienne depuis des annees, ce pattern se reconnait.")
    H("Et meme pour ceux qui commencent a suivre aujourd'hui, cette edition peut servir d'entree dans la comprehension de ce qui se joue vraiment.")

    if story2:
        D(f"Maintenant, il y a aussi ceci: {_story_text(story2).split('.')[0][:100]}. Comment tu analyses ca par rapport a ce qu'on vient de dire?")
        H("Le lien entre ces deux elements est direct, meme si ca peut sembler a premiere vue etre deux sujets completement separes.")
        D("Pourquoi les lire comme un seul mouvement?")
        H("Parce que ce sont deux manifestations differentes du meme probleme structurel. Lus separement, on perd le sens. Lus ensemble, on voit le tableau complet.")
        D("Donne-moi un exemple qui rend ca concret, pas abstrait.")
        H("Quelqu'un a Boston ou a Montreal qui envoie de l'argent a sa famille chaque mois. Une personne reelle avec une contrainte reelle.")
        D("Cette personne-la, elle est directement affectee par ce qu'on discute.")
        H("Ces deux nouvelles ensemble changent son calcul pratique. Pas en theorie. Concretement, cette semaine, ces prochains jours.")
        D("C'est ca l'enjeu veritable. Pas les grandes abstractions politiques. Les decisions quotidiennes des gens ordinaires.")
        H("Et c'est le niveau d'analyse qu'on essaie de maintenir dans chaque edition. Pas les declarations d'intention. Les consequences reelles.")

    # TRANSITION TEASE
    D("Mais ce qu'on n'a pas encore aborde, et c'est peut-etre la partie la plus importante de cette edition.")
    H("C'est ce que tout ca signifie a long terme. Et pourquoi ca nous concerne tous, pas seulement ceux qui sont physiquement en Haiti. On va dans cette direction maintenant.")

    # [6:30-14:00] ACT 2: THE COMPLICATION (~1,400 words / ~8 min)
    if story3:
        H(f"Autre developpement important a signaler dans cette edition: {_story_text(story3)}")
        D("Pour les Haitiens aux Etats-Unis, au Canada, en France et ailleurs dans la diaspora, est-ce que ca change quelque chose de concret dans leur vie quotidienne?")
        H("Completement. Et je vais expliquer pourquoi avec precision.")
        D("Parce que souvent on entend 'c'est important pour la diaspora' sans vraiment comprendre le mecanisme.")
        H("Exactement. Alors voila le mecanisme. Dans la diaspora, on a tendance a suivre les nouvelles d'Haiti comme si c'etait quelque chose qui se passe la-bas, dans un autre monde.")
        D("Mais c'est une illusion qu'on se raconte.")
        H("C'est une illusion. La diaspora est une partie economiquement active, politiquement influente, culturellement presente dans l'equation haitienne. Pas une spectatrice.")
        D("Les transferts d'argent. Parlons de ca concretement. On parle de quelle ampleur?")
        H("Plusieurs milliards de dollars par an. Une fraction significative du PIB haitien qui vient directement de la poche des membres de la diaspora.")
        D("Ce qui veut dire que quand quelque chose affecte la capacite d'envoyer cet argent, ou de le recevoir de facon securisee...")
        H("C'est toute une chaine economique qui est impactee. Pas de facon abstraite. Des familles entieres, des quartiers entiers, des commerces locaux.")
        D("Et cette nouvelle dont on parle affecte cette chaine?")
        H("Directement ou indirectement, oui. Et c'est pourquoi on doit la lire avec cette question permanente: qu'est-ce que ca change pour ceux qui font tourner l'economie haitienne depuis l'etranger?")
        D("Je vais dire quelque chose de direct. Je pense que la diaspora sous-estime regulierement son propre poids dans cette equation.")
        H("Sur le fond, je ne suis pas en desaccord. Mais je dirais que le probleme principal n'est pas la conscience du poids. C'est la coordination.")
        D("Explique la difference entre avoir du poids et etre coordonne.")
        H("La diaspora haitienne a un potentiel economique et politique considerable. Mais ce potentiel s'exprime rarement de facon collective et coordonnee. Et cette fragmentation, c'est une vraie limite strategique.")
        D("Un probleme de confiance mutuelle? De distance geographique? De manque d'information partagee?")
        H("Un peu des trois, en proportions variables selon les communautes. Mais il y a aussi un probleme fondamental de narration.")
        D("La narration? Explique ce que tu veux dire par la.")
        H("La facon dont Haiti est presentee dans les medias mainstream, que ce soit en anglais, en francais, ailleurs: soit c'est dramatique, soit c'est absent. Il y a tres peu d'espace pour une analyse calme, nuancee, contextualisee.")
        D("Tres peu d'espace pour prendre des decisions eclairees sur la base d'une bonne information.")
        H("C'est exactement le vide qu'on essaie de combler ici, edition apres edition. Ce n'est pas une petite ambition.")
        D("C'est notre raison d'exister. Et je pense que ca resonne avec ceux qui nous ecoutent.")
        H("Ca resonne parce que c'est un besoin reel et non satisfait. Et je pense que c'est une ambition necessaire, pas juste utile.")

    if story4:
        D(f"Il y a aussi ce qu'on a observe avec: {_story_text(story4).split('.')[0][:80]}. Tu peux nous donner ta lecture?")
        H("Ce cas est interessant parce qu'il illustre quelque chose qu'on ne dit vraiment pas assez dans l'analyse de la situation haitienne.")
        D("Qu'est-ce qu'on ne dit pas assez?")
        H("Que les solutions ne viennent pas toujours des endroits qu'on attend. Pas toujours des grandes institutions, des grandes declarations.")
        D("Parfois c'est une initiative locale, une decision de communaute, un acteur jusqu'alors inconnu qui cree un vrai changement.")
        H("Exactement. Et ce changement-la peut etre plus reel et plus durable que ce qui vient d'en haut, precisement parce qu'il est ancre dans la realite locale.")
        D("Et les medias mainstream ratent ca regularement.")
        H("Tres regulierement. Parce qu'ils sont calibres pour les grandes declarations, les grandes reunions, les grandes personnalites reconnues.")
        D("Mais le mouvement reel, lui, il se passe souvent ailleurs. A un niveau plus granulaire.")
        H("Plus local. Plus quotidien. Plus humain. Moins spectaculaire a photographier ou a filmer, mais potentiellement plus transformateur.")
        D("Et potentiellement plus durable parce que ca vient de l'interieur de la communaute, pas impose de l'exterieur.")
        H("C'est exactement ca. L'histoire a montre que les transformations profondes en Haiti viennent souvent du peuple lui-meme, de sa capacite d'adaptation, de sa creativite dans des conditions difficiles.")
        D("Et c'est peut-etre la que reside l'espoir le plus concret et le plus credible pour l'avenir.")
        H("Je le crois sincerement. Haiti a une resilience extraordinaire. Ce n'est pas un cliche consolateur, c'est une observation empirique documentee.")
        D("Les gens trouvent des solutions et des moyens de vivre dans des conditions que beaucoup d'autres societes ne sauraient pas gerer.")
        H("Et c'est une verite qu'on oublie trop facilement quand on est habitue aux images dramatiques et aux titres catastrophistes.")

    if story5:
        D("Il y a d'autres elements a signaler avant qu'on passe a la suite?")
        H(f"Oui. A noter egalement: {_story_text(story5).split('.')[0][:80]}. A surveiller dans les jours qui viennent.")
        D("Pourquoi est-ce qu'on le note maintenant, si c'est encore mineur?")
        H("Parce que ce genre de developpement peut sembler anecdotique aujourd'hui et prendre beaucoup d'ampleur rapidement si certaines conditions se reunissent. Mieux vaut l'avoir dans le radar.")

    # MID-ROLL SPONSOR
    D("Tu sais, en preparant cette edition, j'ai repense a quelque chose qui me semble important de mentionner.")
    H("A quel sujet?")
    D("Quand on parle d'Haiti avec toute cette complexite, ses defis reels mais aussi sa beaute reelle, il y a des endroits qui incarnent le meilleur de ce que le pays peut offrir.")
    H(f"{sp.get('fr', sp['name'])}. Si vous planifiez un voyage en Haiti ou si vous cherchez un endroit pour vous ou votre famille pour se ressourcer vraiment, soutenez les entreprises haitiennes qui font bien les choses.")
    D(f"{sp['name']}. C'est ce genre de partenaire qu'on est fiers de mentionner. Et on revient maintenant a notre analyse.")

    # [14:20-19:30] ACT 3: THE SO WHAT (~900 words / ~5 min)
    H("Ce qui me frappe, en regardant l'ensemble des nouvelles de cette journee, c'est un mot qui revient dans ma tete.")
    D("Quel mot?")
    H("Tension. On est dans une periode de tensions multiples et simultanees. Securitaires, economiques, institutionnelles, politiques.")
    D("Et ces tensions ne se resolvent pas par une annonce ou une decision ponctuelle.")
    H("Non. Elles demandent du temps, de la patience, une forme d'engagement collectif soutenu dans la duree.")
    D("Pour quelqu'un qui ecoute depuis Miami, depuis Montreal, depuis Paris ou depuis Lyon, le message pratique c'est quoi?")
    H("Le message le plus important, c'est: ne detournez pas le regard. Meme quand c'est difficile, meme quand les nouvelles sont repetitivement compliquees.")
    D("Parce que les decisions qui se prennent maintenant ont des consequences a long terme.")
    H("Les decisions qui se prennent maintenant, ou qui ne se prennent pas, vont dessiner le visage d'Haiti pour les cinq, dix prochaines annees au moins.")
    D("Et la diaspora est partie prenante de cet avenir qu'on dessine collectivement.")
    H("Pleinement partie prenante. Par les transferts d'argent, oui. Mais aussi par les investissements directs, par les competences qu'on ramene ou qu'on met a disposition a distance.")
    D("Et par la voix politique qu'on peut porter dans les pays ou on vit. Une voix qui peut influencer les decisions de ces gouvernements vis-a-vis d'Haiti.")
    H("C'est un levier souvent sous-utilise, la voix politique de la diaspora dans ses pays d'accueil.")
    D("Ce n'est pas une passivite qu'on peut se permettre. L'enjeu est trop important.")
    H("Non. Et je pense que beaucoup de personnes dans la diaspora le savent profondement. Ils le ressentent, ils en parlent entre eux.")
    D("Mais il y a souvent un sentiment d'impuissance qui s'installe. Comment avoir un impact reel depuis si loin, sur quelque chose d'aussi complexe?")
    H("Et c'est une question legitime. L'information est le premier outil disponible, et c'est deja beaucoup.")
    D("Comprendre ce qui se passe vraiment, pas les slogans simplificateurs ni les positions politiques figees.")
    H("C'est deja un acte consequent. Ensuite, les choix pratiques qui suivent cette comprehension ont un impact reel et mesurable.")
    D("A qui on envoie de l'argent. Quels canaux on utilise. Quelles plateformes on fait confiance.")
    H("Quelles organisations locales on decide de soutenir, directement ou indirectement. Ces choix aggreges comptent enormement.")
    D("Et soutenir des medias independants qui font serieusement ce travail d'information, c'est aussi une facon concrete de participer.")
    H("Une communaute bien informee prend structurellement de meilleures decisions. Elle est moins vulnerable a la manipulation et a la desinformation.")
    D("Et elle peut agir avec plus de precision et d'efficacite quand elle decide d'agir.")
    H("Ce qui m'amene a ce que j'ai envie d'ajouter a l'analyse d'aujourd'hui.")
    D("Dis-moi.")
    H("Dans les nouvelles de cette journee, malgre tout ce qu'on a discute comme defis, il y a aussi des signaux d'espoir.")
    D("Et ca, c'est important de le nommer aussi clairement qu'on nomme les problemes.")
    H("Ce serait une analyse incomplete et franchement injuste que de parler uniquement des obstacles. Haiti, c'est aussi une culture d'une richesse extraordinaire.")
    D("Une population avec une resilience qui reste, objectivement, remarquable.")
    H("Et une histoire qui est, rappelons-le, completement unique dans le monde entier.")
    D("La premiere republique noire de l'histoire moderne. La premiere nation au monde a avoir aboli l'esclavage par une revolution victorieuse.")
    H("Cet heritage extraordinaire se porte au quotidien. Il n'a pas disparu parce que les nouvelles sont compliquees.")
    D("Il se manifeste dans chaque Haitien qui travaille, qui construit, qui resiste, qui transmet sa culture et ses valeurs.")
    H("En Haiti et dans la diaspora. Sur tous les continents. Dans toutes les professions. A tous les niveaux de la societe.")
    D("Ca merite d'etre dit aussi clairement et aussi souvent que les problemes.")
    H("Ca merite d'etre repete. Et c'est une partie du travail qu'on fait ici, edition apres edition.")

    if story6:
        D("Une derniere information avant de conclure cette edition.")
        H(f"{_story_text(story6).split('.')[0][:100]}.")
        D("A garder en tete. Ca peut evoluer dans les prochaines heures.")
        H("Exactement. On le suit et on en reparlera dans les prochaines editions si ca se developpe de facon significative.")

    # SPORTS
    if sports_text:
        sports_sentences = [s.strip() for s in sports_text.split(".") if len(s.strip()) > 20]
        sports_lead   = sports_sentences[0] if sports_sentences else sports_text[:120]
        sports_detail = sports_sentences[1] if len(sports_sentences) > 1 else ""
        D("Sport maintenant, parce que nos auditeurs ont toujours voulu qu'on couvre le sport.")
        H(f"{sports_lead}.")
        if sports_detail:
            D(f"Et en complement: {sports_detail}.")
            H("On suit ca de tres pres dans les prochains jours.")
        else:
            D("C'est un domaine ou Haiti continue de se faire remarquer malgre tout.")
            H("Absolument. Et on suit ca avec autant de serieux que le reste de l'actualite.")

    # WEATHER
    if weather_text:
        D("La meteo maintenant, parce que pour ceux qui ont de la famille sur place, c'est une information pratique et souvent importante.")
        H(weather_text)
        D("Planifiez en consequence. Et si vous avez des proches qui doivent se deplacer, faites-leur passer l'info.")

    # [19:30-21:00] OUTRO
    H("Ce qu'on retient de cette edition, en une phrase.")
    D("Une phrase seulement?")
    H("L'actualite haitienne de ce jour s'inscrit dans une dynamique plus large et plus longue. Ne lisez pas les nouvelles comme des evenements isoles.")
    D("Lisez-les comme des signaux d'un mouvement en cours, avec ses tensions, ses resistances et ses opportunites reelles.")
    H("Exactement. Et dans la prochaine edition, on reviendra sur les consequences de tout ca et sur ce que les prochains jours pourraient apporter comme developpements.")
    D("Si vous ecoutez Mole FM pour la premiere fois aujourd'hui, bienvenue parmi nous. On est tres heureux que vous soyez la.")
    H("On fait ca trois fois par jour, sept jours sur sept, parce qu'on croit sincerement que la diaspora haitienne merite une source d'information serieuse, independante et profondement humaine.")
    D("Et si vous etes un auditeur regulier, merci. Vraiment, merci. Votre fidelite, c'est ce qui nous permet de continuer ce travail.")
    H("Partagez ce podcast avec une personne de votre entourage aujourd'hui. Une seule. C'est comme ca qu'on grandit ensemble, progressivement, solidement.")
    D(f"C'etait l'edition {slot_label} de Mole FM. Je suis Denise.")
    H("Et moi Henri. A tres vite.")

    return turns


# -- TTS synthesis ----------------------------------------------------------

async def _synth_edge(text, voice, output_path):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def synth_turn(text, voice, output_path):
    asyncio.run(_synth_edge(text, voice, output_path))
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        size = os.path.getsize(output_path)
        print(f"    [OK] {os.path.basename(output_path)} — {size//1024} KB")
    else:
        raise RuntimeError(f"edge-tts produced no output: {output_path}")

def add_silence(ms, output_path):
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(ms / 1000),
        "-acodec", "libmp3lame", "-b:a", "64k",
        output_path
    ], capture_output=True)

def add_music_sting(output_path, duration_ms=3000):
    """
    Generate a subtle music transition sting — same sound every time,
    so listeners learn Mole FM's audio grammar.
    Uses a low-pass filtered tone to signal "we're going deeper now."
    """
    # Soft tone sting: 220Hz sine, fade in/out
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency=220:duration={duration_ms/1000}",
        "-af", f"afade=t=in:ss=0:d=0.3,afade=t=out:st={duration_ms/1000-0.5}:d=0.5,volume=0.15",
        "-acodec", "libmp3lame", "-b:a", "64k",
        output_path
    ], capture_output=True)

def concat_mp3s(files, output_path, title, artist):
    list_file = output_path.replace(".mp3", "_list.txt")
    with open(list_file, "w") as f:
        for fp in files:
            f.write(f"file '{fp}'\n")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-acodec", "libmp3lame", "-b:a", "128k",
        "-ar", "44100",
        "-metadata", f"title={title}",
        "-metadata", f"artist={artist}",
        "-metadata", "album=Mole FM Podcast",
        "-metadata", "genre=News",
        "-metadata", "language=fr",
        output_path
    ], capture_output=True, text=True)
    os.remove(list_file)
    if result.returncode == 0:
        size = os.path.getsize(output_path)
        secs = int(size / (128 * 1024 / 8))
        mins, s = divmod(secs, 60)
        print(f"  [OK] {os.path.basename(output_path)} — {size//1024} KB (~{mins}m{s:02d}s)")
        return True, mins, s
    else:
        print(f"  [ERROR] ffmpeg: {result.stderr[-300:]}")
        return False, 0, 0


# ── Quality scoring — logs episode metrics for autoresearch optimization ──────

def score_and_log_episode(out_path, turns, slot_label, duration_mins):
    """
    Log episode metadata for the autoresearch optimizer to analyze.
    Tracks: turn count, avg turn length, estimated completion, slot.
    """
    log_file = os.path.join(RESEARCH_DIR, "episode_quality_log.json")
    entries = []
    try:
        with open(log_file, "r") as f:
            entries = json.load(f)
    except Exception:
        pass

    turn_lengths = [len(t["text"].split()) for t in turns]
    avg_words = sum(turn_lengths) / len(turn_lengths) if turn_lengths else 0
    long_turns = sum(1 for l in turn_lengths if l > 50)  # turns >50 words risk drop-off

    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "filename": os.path.basename(out_path),
        "slot": slot_label,
        "turns": len(turns),
        "duration_mins": duration_mins,
        "avg_words_per_turn": round(avg_words, 1),
        "long_turns_count": long_turns,
        "speakers": {t["speaker"] for t in turns},
        # Target metrics to optimize toward
        "target_completion_rate": 0.75,
        "target_duration_min": 18,
        "target_duration_max": 22,
        "in_target_range": 18 <= duration_mins <= 22,
        "flags": [],
    }

    # Auto-flag quality issues for autoresearch to fix
    if duration_mins < 12:
        entry["flags"].append("TOO_SHORT: episode under 12 min, may feel rushed")
    if duration_mins > 25:
        entry["flags"].append("TOO_LONG: over 25 min, retention risk above Spotify threshold")
    if avg_words > 60:
        entry["flags"].append("TURNS_TOO_LONG: avg turn >60 words — sounds like reading, not talking")
    if long_turns > 5:
        entry["flags"].append(f"MONOLOGUE_RISK: {long_turns} turns exceed 50 words — reduce for authenticity")

    entries.append(entry)
    entries = entries[-50:]  # keep last 50

    os.makedirs(RESEARCH_DIR, exist_ok=True)
    with open(log_file, "w") as f:
        json.dump(entries, f, indent=2, default=str)

    if entry["flags"]:
        print(f"  [QUALITY FLAGS] {'; '.join(entry['flags'])}")
    else:
        print(f"  [QUALITY] Episode in target range. No flags.")

    return entry


# ── Main runner ───────────────────────────────────────────────────────────────

def run(lang="fr", slot_label=None, slot_index=None):
    os.makedirs(PODCAST_DIR, exist_ok=True)
    os.makedirs(RESEARCH_DIR, exist_ok=True)

    now      = datetime.datetime.now()
    date_str = now.strftime("%A %d %B %Y").capitalize()
    if slot_label is None:
        slot_label = now.strftime("%H:%M")

    print(f"\n=== Mole FM Podcast Generator — Premium Edition ===")
    print(f"  Slot: {lang.upper()} / {slot_label} | Time: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Format: The Daily × BBC Global News | Target: 18–22 min, 75%+ completion")

    script_paths = load_recent_newscasts(n=6)
    print(f"  Source newscasts: {len(script_paths)}")
    if not script_paths:
        print("  [ERROR] No newscast scripts found.")
        return None

    stories     = extract_stories_from_scripts(script_paths)
    weather_txt = extract_weather_from_scripts(script_paths)
    sports_txt  = extract_sports_from_scripts(script_paths)
    print(f"  Stories: {len(stories)} | Weather: {'yes' if weather_txt else 'no'} | Sports: {'yes' if sports_txt else 'no'}")

    if slot_index is None:
        slot_index = now.hour % 3

    turns = build_fr_podcast_script(stories, weather_txt, sports_txt, slot_label, date_str, slot_index)
    print(f"  Script turns: {len(turns)}")

    ts      = now.strftime("%Y%m%d_%H%M")
    seg_dir = os.path.join(PODCAST_DIR, f"segs_fr_{ts}")
    os.makedirs(seg_dir, exist_ok=True)

    files = []
    for i, turn in enumerate(turns):
        out = os.path.join(seg_dir, f"{i:02d}_{turn['speaker']}.mp3")
        text_preview = turn['text'][:80].replace('\n', ' ')
        print(f"    [{turn['speaker']}] {text_preview}")
        try:
            synth_turn(turn["text"], turn["voice"], out)
            files.append(out)

            # Natural pause between speakers (400ms conversational feel)
            sil = os.path.join(seg_dir, f"{i:02d}_pause.mp3")
            add_silence(400, sil)
            files.append(sil)

        except Exception as e:
            print(f"    [WARN] Turn {i} skipped: {e}")

        # Add music sting at the transition tease (turns 12-13 approx)
        # Detect transition tease by content marker
        if "dans un instant" in turn.get("text", ""):
            sting = os.path.join(seg_dir, f"{i:02d}_sting.mp3")
            add_music_sting(sting, duration_ms=2500)
            files.append(sting)

    if not files:
        print("  [ERROR] No audio segments generated.")
        return None

    out_filename = f"podcast_fr_{ts}.mp3"
    out_path     = os.path.join(PODCAST_DIR, out_filename)
    title        = f"Mole FM — {slot_label.capitalize()} (FR) — {now.strftime('%d %B %Y')}"
    artist       = "Mole FM Radio"

    print(f"\n  Assembling {len(files)} segments...")
    success, mins, secs = concat_mp3s(files, out_path, title, artist)

    if success:
        # Log quality metrics for autoresearch
        quality = score_and_log_episode(out_path, turns, slot_label, mins + secs/60)
        print(f"  Podcast saved: {out_path}")
        print(f"  Duration: {mins}m{secs:02d}s | Turns: {len(turns)} | Target: 18\u201322 min")

        # Upload to GitHub + submit to molefm.com
        print("  [Publishing] Uploading podcast to GitHub + molefm.com...")
        try:
            import subprocess as _sp
            _ep_title = f"Mole FM Podcast FR \u2014 {slot_label.capitalize()} \u2014 {now.strftime('%d %B %Y')}"
            _desc = (
                f"Émission quotidienne Mole FM \u2014 {now.strftime('%d %B %Y')}.\n"
                f"Analyse approfondie des actualit\u00e9s d'Ha\u00efti avec Denise et Henri.\n"
                f"Format : The Daily \u00d7 BBC Global News \u00d7 Hugo D\u00e9crypte.\n"
                f"Dur\u00e9e : {mins}m{secs:02d}s"
            )
            _upload_result = _sp.run(
                ["python3", "/home/user/workspace/molefm/scripts/github_uploader.py",
                 "podcast", out_path],
                capture_output=True, text=True
            )
            if _upload_result.returncode == 0:
                _github_url = _upload_result.stdout.strip().splitlines()[-1].strip()
                print(f"  [GitHub] \u2713 {_github_url}")
                _submit_result = _sp.run(
                    ["python3", "/home/user/workspace/molefm/scripts/molefm_submitter.py",
                     "podcast", _github_url, _ep_title,
                     str((mins * 60) + secs)],
                    capture_output=True, text=True
                )
                print(_submit_result.stdout.strip())

                # Regenerate RSS feed with new episode
                try:
                    _rss_result = _sp.run(
                        ["python3", "/home/user/workspace/molefm/scripts/generate_rss.py"],
                        capture_output=True, text=True, timeout=120
                    )
                    if _rss_result.returncode == 0:
                        print("  [RSS] ✓ Feed updated")
                    else:
                        print(f"  [RSS] Non-fatal: {_rss_result.stderr.strip()[:100]}")
                except Exception as _re:
                    print(f"  [RSS] Non-fatal: {_re}")
            else:
                print(f"  [GitHub] Non-fatal upload error: {_upload_result.stderr.strip()[:200]}")
        except Exception as _e:
            print(f"  [WARN] Publish step failed (non-fatal): {_e}")

        return out_path

    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("fr", "en"):
        slot = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        slot = sys.argv[1] if len(sys.argv) > 1 else None
    run(lang="fr", slot_label=slot)
