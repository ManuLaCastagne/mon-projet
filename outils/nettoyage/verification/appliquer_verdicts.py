"""CM-034 : applique les verdicts « faux » et « imprécis » qui ont une correction, via corriger_faits (archivage).

Usage : python3 -I appliquer_verdicts.py <dossier mon-projet> <verdicts.json>... [--ecrire]
Sans --ecrire : simulation (rien n'est écrit), rapport de ce qui serait appliqué ou refusé.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import corriger_faits as cf  # noqa: E402

racine, fichiers, ecrire = sys.argv[1], [a for a in sys.argv[2:] if not a.startswith("--")], "--ecrire" in sys.argv
bilan = {"appliqué": 0, "refusé": 0, "ignoré": 0}
refus = []
for vf in fichiers:
    for fiche in json.load(open(vf, encoding="utf-8")):
        chemin = os.path.join(racine, fiche["chemin"])
        texte = open(chemin, encoding="utf-8", newline="").read()
        for e in fiche.get("elements", []):
            if e.get("verdict") not in ("faux", "imprécis") or not e.get("correction"):
                bilan["ignoré"] += 1
                continue
            try:
                t, c = e["texte"], str(e["correction"]).strip()
                if e["type"] == "question":
                    texte = cf.corriger_question(texte, t, c)
                elif e["type"] == "description":
                    texte = cf.corriger_phrase(texte, t, c)
                elif e["type"] == "date":
                    champ = "fin" if re.match(r"\s*fin\b", t) else "debut"
                    valeur = re.search(r"-?\d{1,5}", c).group(0)
                    texte = cf.corriger_champ(texte, champ, valeur)
                elif e["type"] == "indice":
                    m = re.match(r"\s*(indice_\d)\s*[:=]\s*(.*)", t)
                    champ, ancienne = (m.group(1), m.group(2).strip().strip("'\"")) if m else (None, t)
                    if not champ:
                        champ = next(k for k in re.findall(r"^(indice_\d)[ \t]*:", texte, re.M)
                                     if re.search(r"^" + k + r"[ \t]*:[ \t]*\n[ \t]+-[ \t]*['\"]?" + re.escape(t.strip()) + r"['\"]?[ \t]*$", texte, re.M))
                    texte = cf.corriger_indice(texte, champ, ancienne, re.sub(r"^\s*indice_\d\s*[:=]\s*", "", c).strip("'\""))
                else:
                    raise cf.Introuvable("type inconnu " + e["type"])
                bilan["appliqué"] += 1
            except (cf.Introuvable, StopIteration, AttributeError, ValueError) as err:
                bilan["refusé"] += 1
                refus.append(f"{fiche['chemin']} [{e['type']}] {str(err)[:90]} | {e['texte'][:70]}")
        if ecrire:
            texte = cf.marquer_verifiee(texte)  # fiche vérifiée en entier : ne sera plus resélectionnée
            open(chemin, "w", encoding="utf-8", newline="").write(texte)
print(bilan)
print("\n".join(refus))
