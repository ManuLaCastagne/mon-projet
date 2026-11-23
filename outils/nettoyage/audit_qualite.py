"""CM-001 — Audit de provenance et de fuites des questions du coffre Culture Max.

Lecture seule : aucun fichier du coffre n'est modifié. Produit un CSV par question
et un résumé JSON.

Contrat de lecture aligné sur `moteur_jeu.extraire_questions_depuis_fichier` :
une question = une ligne non vide de la section `###### Questions`, jusqu'à la
première ligne commençant par `#`.

Usage : python3 -I audit_qualite.py <dossier_data> <dossier_sortie>
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

import yaml

VERSION = "cm001-v1"

SEUIL_REPRISE = 0.85
SEUIL_REFORMULATION = 0.55

# Formulations typiques des questions générées par IA (GPT, ~2023) observées dans le coffre.
MARQUEURS_IA = [
    r"\bquel(?:le)? individu\b",
    r"\bquelle? (?:figure|personnalite|icone) (?:emblematique|marquante|du|de la|des)\b",
    r"\bemblematique\b",
    r"\b(?:est |etait )?(?:souvent )?(?:connue?s? |celebres? |reputee?s? )(?:pour|comme)\b",
    r"\bsouvent (?:citee?s?|consideree?s?|decrite?s?|associee?s?)\b",
    r"\bconsideree?s? comme (?:l'une?|un|une|le|la)\b",
    r"\bl'une? des? .{0,40}\bles plus\b",
    r"\b(?:a|ont) (?:marque|revolutionne|faconne|transforme|influence)\b",
    r"\bdevenue? (?:un|une) (?:phenomene|symbole|icone|reference)\b",
    r"\bun montant exceptionnel\b",
    r"\bainsi\b",
    r"\bnotamment\b",
    r"\bquel acteur et actrice\b",
]
_MARQUEURS = [re.compile(m) for m in MARQUEURS_IA]

SCORE_RE = re.compile(r"<!--\s*score\s*:\s*(\d+)\s*-->")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def normaliser(texte: str) -> str:
    texte = WIKILINK_RE.sub(lambda m: m.group(2) or m.group(1), texte)
    texte = SCORE_RE.sub(" ", texte)
    texte = texte.replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae")
    texte = unicodedata.normalize("NFKD", texte.lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.replace("’", "'")
    texte = re.sub(r"[^a-z0-9']+", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def lire_fiche(chemin: str) -> tuple[dict, list[str]]:
    """Retourne (propriétés YAML, lignes de questions de section)."""
    with open(chemin, encoding="utf-8") as f:
        contenu = f.read()
    props: dict = {}
    corps = contenu
    if contenu.startswith("---"):
        parties = contenu.split("---", 2)
        if len(parties) == 3:
            try:
                props = yaml.safe_load(parties[1]) or {}
                if not isinstance(props, dict):
                    props = {}
            except yaml.YAMLError:
                props = {"_yaml_invalide": True}
            corps = parties[2]
    questions: list[str] = []
    dans_section = False
    for ligne in corps.split("\n"):
        s = ligne.strip()
        if s.lower().startswith("###### questions"):
            dans_section = True
            continue
        if dans_section:
            if s.startswith("#"):
                break
            if s:
                questions.append(ligne)
    return props, questions


def _liste(valeur) -> list[str]:
    if valeur is None:
        return []
    if isinstance(valeur, (list, tuple)):
        return [str(v) for v in valeur if v is not None and str(v).strip()]
    return [str(valeur)] if str(valeur).strip() else []


def similarite(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def marqueurs_ia(q_norm: str) -> list[str]:
    return [MARQUEURS_IA[i] for i, r in enumerate(_MARQUEURS) if r.search(q_norm)]


def detecter_fuite(q_norm: str, noms: list[str]) -> str:
    """'titre cité', 'indice' (mot distinctif du titre) ou ''.

    Le jeu affiche le nom de la fiche comme réponse : une question qui cite ce nom
    soit donne la réponse, soit attend autre chose que la réponse affichée.
    """
    for nom in noms:
        n = normaliser(nom)
        if len(n) >= 4 and re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", q_norm):
            return "titre cité"
    # Fuite partielle : un mot distinctif du titre (>= 6 lettres), hors mots courants.
    courants = {"france", "francais", "francaise", "grand", "grande", "saint", "sainte", "guerre", "bataille",
                "musique", "theatre", "histoire", "republique", "royaume", "empire", "riviere", "montagne"}
    titre = normaliser(noms[0]) if noms else ""
    mots = [m for m in titre.split() if len(m) >= 6 and m not in courants]
    if len(titre.split()) >= 2 and mots:
        for m in mots:
            if re.search(r"(?<![a-z0-9])" + re.escape(m) + r"(?![a-z0-9])", q_norm):
                return "indice"
    return ""


def classer(sim_tv: float, n_marqueurs: int, n_liens: int, a_questions_tv: bool) -> tuple[str, str]:
    """Retourne (provenance, confiance)."""
    if sim_tv >= SEUIL_REPRISE:
        return "Reprise jeu TV", "haute"
    if sim_tv >= SEUIL_REFORMULATION:
        return "Reformulation jeu TV", "moyenne"
    indice = n_marqueurs + (1 if n_liens >= 3 else 0)
    if indice >= 2:
        return "IA probable", "moyenne"
    if indice == 1:
        return "IA possible", "faible"
    return "Indéterminée", "faible"


def auditer(dossier: str) -> list[dict]:
    lignes: list[dict] = []
    for racine, dirs, fichiers in os.walk(dossier):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for nom in sorted(fichiers):
            if not nom.endswith(".md"):
                continue
            chemin = os.path.join(racine, nom)
            props, questions = lire_fiche(chemin)
            if not questions:
                continue
            rel = os.path.relpath(chemin, dossier)
            titre = nom[:-3]
            noms = [titre] + _liste(props.get("aliases"))
            q_tv = [normaliser(q) for q in _liste(props.get("questions"))]
            for i, brut in enumerate(questions, start=1):
                q_norm = normaliser(brut)
                sim = max((similarite(q_norm, t) for t in q_tv), default=0.0)
                marq = marqueurs_ia(q_norm)
                n_liens = len(WIKILINK_RE.findall(brut))
                provenance, confiance = classer(sim, len(marq), n_liens, bool(q_tv))
                m = SCORE_RE.search(brut)
                lignes.append({
                    "fichier": rel,
                    "theme": rel.split(os.sep)[0] if os.sep in rel else "",
                    "fiche": titre,
                    "n": i,
                    "question": SCORE_RE.sub("", brut).strip(),
                    "provenance": provenance,
                    "confiance": confiance,
                    "similarite_tv": round(sim, 2),
                    "nb_questions_tv_fiche": len(q_tv),
                    "marqueurs_ia": len(marq),
                    "liens": n_liens,
                    "fuite": detecter_fuite(q_norm, noms),
                    "score_maitrise": int(m.group(1)) if m else "",
                    "culture_g_score": props.get("culture_g_score", ""),
                })
    return lignes


def resumer(lignes: list[dict]) -> dict:
    fiches = {l["fichier"] for l in lignes}
    return {
        "version": VERSION,
        "fiches": len(fiches),
        "questions": len(lignes),
        "provenance": dict(Counter(l["provenance"] for l in lignes).most_common()),
        "fuite": dict(Counter(l["fuite"] or "aucune" for l in lignes).most_common()),
        "titre_cite_par_theme": dict(Counter(l["theme"] for l in lignes if l["fuite"] == "titre cité").most_common()),
        "questions_deja_travaillees": sum(1 for l in lignes if l["score_maitrise"] != ""),
        "fiches_avec_questions_tv": len({l["fichier"] for l in lignes if l["nb_questions_tv_fiche"]}),
        "questions_tv_jamais_jouees": sum({l["fichier"]: l["nb_questions_tv_fiche"] for l in lignes}.values()),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    dossier, sortie = argv[1], argv[2]
    os.makedirs(sortie, exist_ok=True)
    lignes = auditer(dossier)
    with open(os.path.join(sortie, "cm001_questions.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0].keys()) if lignes else ["fichier"], delimiter=";")
        w.writeheader()
        w.writerows(lignes)
    resume = resumer(lignes)
    with open(os.path.join(sortie, "cm001_resume.json"), "w", encoding="utf-8") as f:
        json.dump(resume, f, ensure_ascii=False, indent=2)
    print(json.dumps(resume, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
