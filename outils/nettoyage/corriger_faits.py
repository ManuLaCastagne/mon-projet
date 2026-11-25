"""CM-034 — Corrige des erreurs factuelles dans une fiche, sans rien supprimer.

- question : la ligne de `###### Questions` est remplacée ; l'original (avec son score) part dans
  `###### Archives questions` (même convention que CM-003, marqueur cm034) ;
- phrase de description : la phrase est remplacée dans `###### Description` ; l'original part dans
  `###### Archives description`, en fin de fiche, hors de portée du jeu ;
- date (`debut`, `fin`) : la valeur est remplacée ; l'ancienne est gardée dans `<champ>_archive_cm034` ;
- indice (`indice_n`) : la valeur est remplacée ; l'ancienne est gardée dans `indice_n_archive_cm034`.

Chaque correction exige de retrouver EXACTEMENT le texte visé (une seule occurrence), sinon `Introuvable`.
Le frontmatter doit rester un YAML valide.
"""
from __future__ import annotations

import json
import re

import yaml

import audit_qualite as aq

MARQUE = "cm034"
DATE = "2026-11-25"
ARCH_Q = "###### Archives questions"
ARCH_D = "###### Archives description"


class Introuvable(Exception):
    pass


def _q(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)


def _decouper(texte: str) -> tuple[str, str]:
    if not texte.startswith("---"):
        return "", texte
    i = texte.index("\n---", 3) + 4
    return texte[:i], texte[i:]


def _section(corps: str, titre: str) -> tuple[int, int]:
    """(début, fin) du contenu d'une section `###### Titre` dans le corps ; (-1, -1) si absente."""
    m = re.search(r"^" + re.escape(titre) + r"[ \t]*$", corps, re.M | re.I)
    if not m:
        return -1, -1
    suite = re.search(r"^#", corps[m.end():], re.M)
    return m.end(), m.end() + (suite.start() if suite else len(corps) - m.end())


def _archiver(corps: str, titre: str, ligne: str) -> str:
    ligne = f"{ligne.rstrip()} <!-- {MARQUE} corrigée {DATE} -->"
    d, f = _section(corps, titre)
    if d >= 0:
        bloc = corps[d:f].rstrip("\n")
        return corps[:d] + bloc + "\n\n" + ligne + "\n" + ("\n" if f < len(corps) else "") + corps[f:].lstrip("\n")
    return corps.rstrip("\n") + f"\n\n{titre}\n\n{ligne}\n"


def corriger_question(texte: str, actuelle: str, nouvelle: str) -> str:
    entete, corps = _decouper(texte)
    d, f = _section(corps, "###### Questions")
    if d < 0:
        raise Introuvable("section Questions absente")
    lignes = corps[d:f].split("\n")
    cible = [i for i, l in enumerate(lignes) if l.strip() and aq.normaliser(aq.SCORE_RE.sub("", l).strip()) == aq.normaliser(actuelle)]
    if len(cible) != 1:
        raise Introuvable(f"question trouvée {len(cible)} fois : {actuelle[:60]}")
    i = cible[0]
    original = lignes[i]
    lignes[i] = nouvelle.strip()
    corps = corps[:d] + "\n".join(lignes) + corps[f:]
    return entete + _archiver(corps, ARCH_Q, original)


def corriger_phrase(texte: str, phrase: str, nouvelle: str) -> str:
    entete, corps = _decouper(texte)
    d, f = _section(corps, "###### Description")
    if d < 0:
        raise Introuvable("section Description absente")
    bloc = corps[d:f]
    if bloc.count(phrase) != 1:
        raise Introuvable(f"phrase trouvée {bloc.count(phrase)} fois : {phrase[:60]}")
    corps = corps[:d] + bloc.replace(phrase, nouvelle.strip()) + corps[f:]
    return entete + _archiver(corps, ARCH_D, phrase)


def corriger_champ(texte: str, champ: str, nouvelle) -> str:
    """Champ scalaire du frontmatter (`debut`, `fin`)."""
    entete, corps = _decouper(texte)
    m = list(re.finditer(r"^" + re.escape(champ) + r":[ \t]*(.*)$", entete, re.M))
    if len(m) != 1:
        raise Introuvable(f"champ {champ} trouvé {len(m)} fois")
    ancienne = m[0].group(1).strip()
    rempl = f"{champ}: {nouvelle}\n{champ}_archive_{MARQUE}: {_q(ancienne)}"
    entete = entete[:m[0].start()] + rempl + entete[m[0].end():]
    yaml.safe_load(entete[3:entete.rindex("\n---")])
    return entete + corps


def corriger_indice(texte: str, champ: str, ancienne: str, nouvelle: str) -> str:
    """Valeur d'une liste du frontmatter (`indice_n:` suivi de `  - valeur`)."""
    entete, corps = _decouper(texte)
    m = re.search(r"^" + re.escape(champ) + r":[ \t]*\n((?:[ \t]+-.*\n?)+)", entete, re.M)
    if not m:
        raise Introuvable(f"champ {champ} absent")
    items = m.group(1).split("\n")
    cible = [i for i, l in enumerate(items) if l.strip().startswith("-") and
             aq.normaliser(l.strip()[1:].strip().strip("'\"")) == aq.normaliser(ancienne)]
    if len(cible) != 1:
        raise Introuvable(f"indice trouvé {len(cible)} fois dans {champ} : {ancienne[:40]}")
    indent = items[cible[0]][: len(items[cible[0]]) - len(items[cible[0]].lstrip())]
    original = items[cible[0]].strip()[1:].strip()
    items[cible[0]] = f"{indent}- {_q(nouvelle)}"
    bloc = "\n".join(items)
    if not bloc.endswith("\n"):
        bloc += "\n"
    bloc += f"{champ}_archive_{MARQUE}:\n{indent}- {_q(original.strip(chr(39)).strip(chr(34)))}\n"
    entete = entete[:m.start(1)] + bloc + entete[m.end(1):]
    yaml.safe_load(entete[3:entete.rindex("\n---")])
    return entete + corps
