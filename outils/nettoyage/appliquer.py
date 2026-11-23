"""CM-003 — Applique des propositions validées aux fiches du coffre.

Garanties :
- seule la ligne visée est modifiée ; elle est retrouvée par son rang dans la section
  `###### Questions` ET par son texte (sinon : ignorée et signalée, rien n'est écrit) ;
- rien n'est supprimé : la question d'origine (avec son score) est recopiée dans une
  section `###### Archives questions` placée en fin de fiche, hors de portée du jeu ;
- le reste du fichier est conservé octet pour octet.

Usage : python3 -I appliquer.py <propositions.json> <dossier_data> [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_qualite as aq  # noqa: E402

TITRE_ARCHIVES = "###### Archives questions"
DATE = "2026-11-23"


def indices_questions(lignes: list[str]) -> list[int]:
    """Indices des lignes de questions, même contrat que moteur_jeu.extraire_questions_depuis_fichier."""
    res, dedans = [], False
    debut_corps = 0
    if lignes and lignes[0].startswith("---"):
        for i in range(1, len(lignes)):
            if lignes[i].startswith("---"):
                debut_corps = i + 1
                break
    for i in range(debut_corps, len(lignes)):
        s = lignes[i].strip()
        if s.lower().startswith("###### questions"):
            dedans = True
            continue
        if dedans:
            if s.startswith("#"):
                break
            if s:
                res.append(i)
    return res


def appliquer_fiche(texte: str, items: list[dict]) -> tuple[str, list[dict]]:
    fin_ligne = "\r\n" if "\r\n" in texte else "\n"
    finale = texte.endswith(("\n", "\r\n"))
    lignes = texte.splitlines()
    idx = indices_questions(lignes)
    rapport, archives, a_retirer = [], [], set()
    for it in items:
        rang = it["rang_dans_fiche"]
        if rang > len(idx):
            rapport.append({**it, "statut": "ignorée : rang introuvable"}); continue
        i = idx[rang - 1]
        actuelle = aq.SCORE_RE.sub("", lignes[i]).strip()
        if aq.normaliser(actuelle) != aq.normaliser(it["question_actuelle"]):
            rapport.append({**it, "statut": "ignorée : texte différent (fiche modifiée depuis l'audit ?)"}); continue
        if it["verdict"] == "garder":
            rapport.append({**it, "statut": "inchangée"}); continue
        motif = "archivée" if it["verdict"] == "ecarter" else "remplacée"
        archives.append(f"{lignes[i].rstrip()} <!-- cm003 {motif} {DATE} -->")
        if it["verdict"] == "ecarter":
            a_retirer.add(i)
        else:
            lignes[i] = it["proposition"].strip()
        rapport.append({**it, "statut": motif})
    if not archives:
        return texte, rapport
    # Retrait des lignes archivées et de la ligne vide qui les suit (une ligne vide entre questions).
    nouvelles = []
    sauter_vide = False
    for i, l in enumerate(lignes):
        if i in a_retirer:
            sauter_vide = True
            continue
        if sauter_vide and l.strip() == "":
            sauter_vide = False
            continue
        sauter_vide = False
        nouvelles.append(l)
    lignes = nouvelles
    if any(l.strip() == TITRE_ARCHIVES for l in lignes):
        pos = max(i for i, l in enumerate(lignes) if l.strip() == TITRE_ARCHIVES)
        j = pos + 1
        while j < len(lignes) and not lignes[j].strip().startswith("#"):
            j += 1
        while j > pos + 1 and lignes[j - 1].strip() == "":
            j -= 1
        ajout = []
        for a in archives:
            ajout += ["", a]
        lignes = lignes[:j] + ajout + lignes[j:]
    else:
        while lignes and lignes[-1].strip() == "":
            lignes.pop()
        lignes += ["", TITRE_ARCHIVES, ""]
        for k, a in enumerate(archives):
            lignes.append(a)
            if k != len(archives) - 1:
                lignes.append("")
    sortie = fin_ligne.join(lignes)
    if finale:
        sortie += fin_ligne
    return sortie, rapport


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    props = json.load(open(argv[1], encoding="utf-8"))
    data = argv[2]
    dry = "--dry-run" in argv
    par_fichier = defaultdict(list)
    for p in props:
        par_fichier[p["fichier"]].append(p)
    rapport = []
    for rel, items in sorted(par_fichier.items()):
        chemin = os.path.join(data, rel)
        with open(chemin, encoding="utf-8", newline="") as f:
            texte = f.read()
        avant = len(aq.lire_fiche(chemin)[1])
        nouveau, r = appliquer_fiche(texte, items)
        rapport += [{**x, "fichier": rel} for x in r]
        if nouveau != texte and not dry:
            with open(chemin, "w", encoding="utf-8", newline="") as f:
                f.write(nouveau)
            apres = len(aq.lire_fiche(chemin)[1])
            attendu = avant - sum(1 for x in r if x["statut"] == "archivée")
            assert apres == attendu, f"{rel}: {apres} questions jouables au lieu de {attendu}"
    from collections import Counter
    print(json.dumps(Counter(x["statut"] for x in rapport), ensure_ascii=False))
    for x in rapport:
        if x["statut"].startswith("ignorée"):
            print("  !", x["fichier"], x["rang_dans_fiche"], x["statut"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
