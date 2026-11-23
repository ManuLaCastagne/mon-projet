"""Construit le JSON d'un lot et applique les contrôles automatiques de qualité.

Contrôles sur chaque réécriture : pas de nom de fiche ni d'alias ni d'indice fort,
pas de tournure IA connue, question terminée par « ? », wikilinks équilibrés,
pas de doublon (similarité > 0,5) avec les autres questions de la fiche, y compris
les autres réécritures du même lot.

Usage : python3 -I preparer_lot.py <selection.json> <propositions.json | module_python> <dossier_data> <sortie.json>

propositions.json : {"1": ["garder|reecrire|corriger|ecarter", "nouvelle question", "raison", "url source ou vide"], ...}
"""
import importlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_qualite as aq  # noqa: E402

SEUIL_DOUBLON = 0.35
VIDES = set("""quel quelle quels quelles dans pour avec sans leur leurs sont elle elles ils dont dans cette celui celle
lors entre apres avant depuis aussi comme tres plus moins film films acteur actrice realisateur realise realisee
joue jouee incarne incarnee interprete role sorti sortie annee titre oeuvre personnage remporte recoit obtient
oscar meilleur meilleure premier premiere grand grande celebre fait faire etre avoir""".split())


def mots(q):
    return {m for m in aq.normaliser(q).split() if len(m) >= 4 and m not in VIDES and not m.isdigit()}


def entites(q):
    return {aq.normaliser(m.group(1)) for m in aq.WIKILINK_RE.finditer(q) if not m.group(1).strip().isdigit()}


def proximite(a, b):
    """Jaccard des mots porteurs de sens ; 1.0 si au moins deux entités liées sont communes."""
    if len(entites(a) & entites(b)) >= 2:
        return 1.0
    ma, mb = mots(a), mots(b)
    return len(ma & mb) / len(ma | mb) if ma and mb else 0.0


def controler(lot, data):
    problemes = []
    finales = {}
    for o in lot:
        props, qs = aq.lire_fiche(os.path.join(data, o["fichier"]))
        o["_noms"] = [o["fiche"]] + aq._liste(props.get("aliases"))
        f = finales.setdefault(o["fichier"], {k: q for k, q in enumerate(qs, 1)})
        if o["verdict"] in ("reecrire", "corriger"):
            f[o["rang_dans_fiche"]] = o["proposition"]
        elif o["verdict"] == "ecarter":
            f.pop(o["rang_dans_fiche"], None)
    for o in lot:
        if o["verdict"] not in ("reecrire", "corriger"):
            continue
        q = o["proposition"]
        n = aq.normaliser(q)
        if aq.detecter_fuite(n, o["_noms"]):
            problemes.append((o["n"], "fuite", aq.detecter_fuite(n, o["_noms"])))
        if aq.marqueurs_ia(n):
            problemes.append((o["n"], "tournure IA", aq.marqueurs_ia(n)))
        if not q.rstrip().endswith("?") or q.count("[[") != q.count("]]"):
            problemes.append((o["n"], "forme", q[-20:]))
        for k, autre in finales[o["fichier"]].items():
            if k != o["rang_dans_fiche"]:
                s = proximite(q, autre)
                if s > SEUIL_DOUBLON:
                    problemes.append((o["n"], f"doublon {s:.2f}", autre[:80]))
    for o in lot:
        o.pop("_noms", None)
    return problemes


def main(argv):
    sel = json.load(open(argv[1], encoding="utf-8"))
    if argv[2].endswith(".json"):
        P = {int(k): v for k, v in json.load(open(argv[2], encoding="utf-8")).items()}
    else:
        P = importlib.import_module(argv[2]).P
    data = argv[3]
    lot = []
    for i, l in enumerate(sel, 1):
        v, prop, raison = P[i][:3]
        source = P[i][3] if len(P[i]) > 3 else ""
        lot.append({"n": i, "fichier": l["fichier"], "fiche": l["fiche"], "rang_dans_fiche": int(l["n"]),
                    "question_actuelle": l["question"], "verdict": v, "proposition": prop,
                    "raison": raison, "source": source})
    pb = controler(lot, data)
    for p in pb:
        print("  !", *p)
    print(f"{len(lot)} questions, {len(pb)} problème(s)")
    json.dump(lot, open(argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if pb else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
