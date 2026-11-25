"""CM-034 : dossiers de sources pour la vérification factuelle (Wikipédia FR + Wikidata, avec cache).

L'API de recherche de Wikidata est bridée (429) : on part de la page Wikipédia du même nom (redirections et pages
d'homonymie suivies selon le thème), puis on remonte à l'entité Wikidata par Special:ItemByTitle.
"""
import json, os, re, time, urllib.parse, urllib.request

UA = {"User-Agent": "CultureMax/1.0 (outil personnel)"}
CACHE = os.environ.get("CM_SOURCES", "/tmp/cm-sources")
MOTS = {"Cinéma": "film|acteur|actrice|réalisat", "Musique": "chanson|album|chanteu|groupe|musicien|compositeur|rappeur",
        "Littérature": "écrivain|roman|poète|auteur|pièce|œuvre|livre|dramaturge",
        "Histoire": "roi|homme|femme|président|bataille|guerre|militaire|politique|navire",
        "Géographie": "pays|ville|fleuve|mer|montagne|région|île|détroit|chaîne", "Mythologie": "mytholog|dieu|déesse|héros|créature",
        "Sport": "joueur|sportif|athlète|olympiques|échecs|football", "Art": "peintre|sculpteur|artiste|tableau",
        "Sciences": "scientifique|médecin|physicien|aviateur|ingénieur|inventeur",
        "Télévision": "série|émission|animateur|présentat|journaliste|film|manga", "Religion": "saint|sainte|biblique|ville|religieu|prophète",
        "Architecture": "château|palais|bâtiment|temple|monument|édifice|hôpital|musée",
        "Animaux": "espèce|animal|genre|insecte|oiseau|dinosaure", "Gastronomie": "cépage|vin|plat|fromage"}
LIEN = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")


def get(url, essai=0):
    time.sleep(1.2)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.geturl(), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 429 and essai < 2:
            time.sleep(10 * (essai + 1))
            return get(url, essai + 1)
        return "", ""
    except Exception:
        return "", ""


def brut_wp(titre):
    return get("https://fr.wikipedia.org/w/index.php?title=" + urllib.parse.quote(titre.replace(" ", "_")) + "&action=raw")[1]


def page_wp(theme, titre):
    """(page, wikitexte, homonymes) : suit les redirections ; sur une page d'homonymie, choisit selon le thème."""
    homonymes = []
    for depart in dict.fromkeys([titre, re.sub(r"\s*\(.*\)$", "", titre)]):
        t, b = depart, ""
        for _ in range(3):
            b = brut_wp(t)
            m = re.match(r"\s*#(?:REDIRECTION|REDIRECT)\s*\[\[([^\]|#]+)", b, re.I)
            if not m:
                break
            t = m.group(1).strip()
        if not b:
            continue
        if re.search(r"\{\{\s*(homonymie|patronymie)", b, re.I):
            mot = MOTS.get(theme, "")
            lignes = [l for l in b.split("\n") if l.startswith("*") and "[[" in l]
            homonymes = [LIEN.sub(r"\1", l)[:120] for l in lignes[:8]]
            bon = next((l for l in lignes if mot and re.search(mot, l, re.I)), None)
            if not bon:
                return t, "", homonymes
            t = re.search(r"\[\[([^\]|#]+)", bon).group(1).strip()
            b = brut_wp(t)
        return t, b, homonymes
    return None, "", homonymes


def intro(brut):
    x = brut.split("\n==", 1)[0]
    for _ in range(4):
        x = re.sub(r"\{\{[^{}]*\}\}", "", x)
    x = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", x, flags=re.S)
    x = re.sub(r"\[\[(?:Fichier|File|Image):[^\n]*", "", x)
    x = LIEN.sub(r"\1", x)
    x = re.sub(r"<[^>]+>", "", x).replace("'''", "").replace("''", "")
    return re.sub(r"\n{2,}", "\n", x).strip()[:3500]


def annee(c):
    try:
        v = c["mainsnak"]["datavalue"]["value"]["time"]
        return int(v[:v.index("-", 1)])
    except Exception:
        return None


def dossier(theme, titre):
    out = {"theme": theme, "titre": titre}
    page, brut, homonymes = page_wp(theme, titre)
    if homonymes:
        out["homonymes_wp"] = homonymes
    if not brut:
        return out
    out.update({"wikipedia": page, "intro_wp": intro(brut)})
    url, _ = get("https://www.wikidata.org/wiki/Special:ItemByTitle/frwiki/" + urllib.parse.quote(page.replace(" ", "_")))
    m = re.search(r"/(Q\d+)", url or "")
    if m:
        qid = m.group(1)
        ent = json.loads(get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")[1] or "{}").get("entities", {}).get(qid, {})
        claims, dates = ent.get("claims", {}), {}
        for pid, nom in (("P569", "naissance"), ("P570", "décès"), ("P571", "création"), ("P577", "publication"),
                         ("P580", "début"), ("P582", "fin"), ("P585", "date")):
            vals = sorted({a for a in (annee(c) for c in claims.get(pid, [])) if a is not None})
            if vals:
                dates[nom] = vals
        out.update({"wikidata": qid, "label": ent.get("labels", {}).get("fr", {}).get("value"),
                    "description_wd": ent.get("descriptions", {}).get("fr", {}).get("value", ""), "dates_wd": dates})
    return out


if __name__ == "__main__":
    # Usage : python3 -I sources.py <dossier mon-projet> <liste.txt (un chemin data/... par ligne)>
    import sys
    racine, liste = sys.argv[1], sys.argv[2]
    os.makedirs(CACHE, exist_ok=True)
    for p in [l.strip() for l in open(liste, encoding="utf-8") if l.strip()]:
        theme, titre = p.split("/")[1], os.path.basename(p)[:-3]
        f = os.path.join(CACHE, f"{theme}__{titre}.json")
        if os.path.exists(f):
            continue
        d = dossier(theme, titre)
        d["fiche"] = open(os.path.join(racine, p), encoding="utf-8").read()
        d["chemin"] = p
        json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(("OK " if d.get("intro_wp") else "-- ") + f"{theme}/{titre} → {d.get('wikipedia')} | {d.get('label')} ({d.get('description_wd', '')[:45]}) {d.get('dates_wd', {})}", flush=True)
