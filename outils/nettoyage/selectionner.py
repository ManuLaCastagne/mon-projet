"""Sélectionne le prochain lot de questions à nettoyer.

Priorité : 1) questions qui citent leur réponse, 2) indices, 3) IA probable, 4) IA possible,
5) indéterminées ; au sein d'une priorité, thèmes dans l'ordre THEMES puis score culture G décroissant.
Exclut les questions déjà traitées (journal) et les fiches touchées par le lot précédent non vérifiées.

Usage : python3 -I selectionner.py <audit.csv> <journal.json> <taille> <sortie.json>
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_qualite as aq  # noqa: E402

THEMES = ["Cinéma", "Géographie", "Musique", "Littérature", "Télévision", "Art", "Histoire", "Sport",
          "Culture générale", "Animaux", "Architecture", "Mythologie", "Religion", "Vocabulaire",
          "Sciences", "Gastronomie", "Botanique", "Anatomie"]


def cle(l):
    return f"{l['fichier']}::{aq.normaliser(l['question'])}"


def priorite(l):
    if l["fuite"] == "titre cité":
        return 0
    if l["fuite"] == "indice":
        return 1
    return {"IA probable": 2, "IA possible": 3, "Indéterminée": 4}.get(l["provenance"], 9)


def main(argv):
    lignes = list(csv.DictReader(open(argv[1], encoding="utf-8-sig"), delimiter=";"))
    journal = json.load(open(argv[2], encoding="utf-8")) if os.path.exists(argv[2]) else {"traitees": [], "lots": []}
    faites = set(journal["traitees"])
    taille = int(argv[3])
    cand = [l for l in lignes if cle(l) not in faites and priorite(l) < 9]
    rang_theme = {t: i for i, t in enumerate(THEMES)}
    cand.sort(key=lambda l: (priorite(l), rang_theme.get(l["theme"], 99), -int(l["culture_g_score"] or 0),
                             l["fichier"], int(l["n"])))
    # Une fiche entière à la fois, pour diversifier ses questions d'un coup.
    par_fiche = {}
    for l in cand:
        par_fiche.setdefault(l["fichier"], []).append(l)
    lot, fiches = [], set()
    for l in cand:
        if l["fichier"] in fiches:
            continue
        if len(lot) >= taille:
            break
        fiches.add(l["fichier"])
        lot += par_fiche[l["fichier"]]
    json.dump(lot, open(argv[4], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(lot)} questions dans {len(fiches)} fiches ; reste {len(cand) - len(lot)} candidates")


if __name__ == "__main__":
    main(sys.argv)
