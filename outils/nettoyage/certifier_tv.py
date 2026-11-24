"""CM-024 — Certification des questions d'origine des jeux TV et remplacement d'image.

Règles du PO (24/11/2026) :
- la réponse est toujours le concept, c'est-à-dire le nom de la fiche ;
- une question coupée au buzz reste telle quelle, sauf si elle est fausse ;
- une question retravaillée est inscrite dans `###### Questions` avec la marque `<!-- source: tv -->` ;
- l'original n'est jamais effacé : il passe de `questions:` à `questions_tv_archivees:` dans l'en-tête.

Fonctions pures (texte → texte) ; le reste du fichier est conservé octet pour octet.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_qualite as aq  # noqa: E402

MARQUE_TV = "<!-- source: tv -->"
CLE_ARCHIVE = "questions_tv_archivees"


class Introuvable(Exception):
    pass


def _decouper(texte: str) -> tuple[str, str, str]:
    if not texte.startswith("---"):
        raise Introuvable("fiche sans en-tête")
    debut = texte.index("\n") + 1
    fin = texte.index("\n---", debut)
    return texte[:debut], texte[debut:fin + 1], texte[fin + 1:]


def _valeur(ligne_item: str) -> str:
    v = re.sub(r"^\s*-\s+", "", ligne_item).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def archiver_question_tv(entete: str, question: str) -> str:
    """Déplace l'élément `question` de la liste `questions:` (toutes occurrences) vers `questions_tv_archivees:`."""
    lignes = entete.split("\n")
    cible = aq.normaliser(question)
    retirees, garder, i, dans = [], [], 0, False
    while i < len(lignes):
        l = lignes[i]
        if re.match(r"^questions:\s*$", l):
            dans = True
            garder.append(l)
            i += 1
            continue
        if dans and re.match(r"^\s*-\s+", l):
            bloc = [l]
            while i + 1 < len(lignes) and lignes[i + 1].startswith((" ", "\t")) and not re.match(r"^\s*-\s+", lignes[i + 1]):
                i += 1
                bloc.append(lignes[i])
            if aq.normaliser(_valeur(" ".join(x.strip() for x in bloc))) == cible:
                retirees.append(bloc)
            else:
                garder.extend(bloc)
            i += 1
            continue
        if dans and l.strip() and not l.startswith((" ", "\t")):
            dans = False
        garder.append(l)
        i += 1
    if not retirees:
        raise Introuvable(f"question TV absente de l'en-tête : {question[:60]}")
    # Une clé `questions:` vidée et répétée ailleurs ne porte plus rien : on la retire pour que le YAML
    # (où la dernière clé l'emporte) garde les questions restantes.
    cles = [k for k, l in enumerate(garder) if re.match(r"^questions:\s*$", l)]
    vides = [k for k in cles if not (k + 1 < len(garder) and re.match(r"^\s*-\s+", garder[k + 1]))]
    if len(cles) > 1:
        for k in sorted(vides, reverse=True)[: len(cles) - 1]:
            del garder[k]
    item = "  - " + retirees[0][0].strip()[2:].strip() + "".join(" " + x.strip() for x in retirees[0][1:])
    if any(re.match(rf"^{CLE_ARCHIVE}:\s*$", l) for l in garder):
        pos = max(k for k, l in enumerate(garder) if re.match(rf"^{CLE_ARCHIVE}:\s*$", l))
        j = pos + 1
        while j < len(garder) and garder[j].startswith((" ", "\t")):
            j += 1
        garder.insert(j, item)
    else:
        while garder and garder[-1] == "":
            garder.pop()
        garder += [f"{CLE_ARCHIVE}:", item, ""]
    return "\n".join(garder)


def ajouter_question(corps: str, question: str) -> str:
    """Ajoute une question à la fin de la section `###### Questions` (créée avant la Description si absente)."""
    ligne = f"{question.strip()} {MARQUE_TV}"
    m = re.search(r"^###### Questions[^\n]*\n", corps, re.M)
    if not m:
        d = re.search(r"^###### Description", corps, re.M)
        pos = d.start() if d else len(corps)
        return corps[:pos] + f"###### Questions\n\n{ligne}\n\n" + corps[pos:]
    suite = corps[m.end():]
    n = re.search(r"^#", suite, re.M)
    fin_section = m.end() + (n.start() if n else len(suite))
    section = corps[m.end():fin_section].rstrip("\n")
    nouvelle = section + ("\n\n" if section.strip() else "\n") + ligne + "\n\n"
    return corps[:m.end()] + nouvelle + corps[fin_section:]


def questions_section(corps: str) -> list[str]:
    res, dedans = [], False
    for l in corps.split("\n"):
        s = l.strip()
        if s.lower().startswith("###### questions"):
            dedans = True
            continue
        if dedans:
            if s.startswith("#"):
                break
            if s:
                res.append(s)
    return res


class DejaCouverte(Exception):
    """La fiche contient déjà une question équivalente : archiver l'original TV sans rien ajouter."""


def question_proche(corps: str, nouvelle: str) -> str | None:
    """Renvoie la question existante trop proche de `nouvelle` (même seuil que preparer_lot), sinon None."""
    import preparer_lot as pl
    for q in questions_section(corps):
        propre = re.sub(r"<!--.*?-->", "", q).strip()
        if aq.normaliser(propre) == aq.normaliser(nouvelle) or pl.proximite(nouvelle, propre) > pl.SEUIL_DOUBLON:
            return propre
    return None


def archiver_seule(texte: str, question_tv: str) -> str:
    """La question TV est déjà couverte par la fiche : on l'archive sans ajout."""
    debut, entete, corps = _decouper(texte)
    return debut + archiver_question_tv(entete, question_tv) + corps


def certifier(texte: str, question_tv: str, nouvelle: str) -> str:
    debut, entete, corps = _decouper(texte)
    proche = question_proche(corps, nouvelle)
    if proche:
        raise DejaCouverte(proche)
    return debut + archiver_question_tv(entete, question_tv) + ajouter_question(corps, nouvelle)


def remplacer_image(texte: str, nouvelle_url: str) -> str:
    """Remplace la première image distante placée avant les questions ; l'ancien lien est gardé en commentaire."""
    avant, sep, apres = texte.partition("###### Questions")
    m = re.search(r"^(!\[[^\]]*\]\()(https://[^)\s]+)(\)).*$", avant, re.M)
    if not m:
        raise Introuvable("aucune image distante en tête de fiche")
    ligne = m.group(1) + nouvelle_url + m.group(3) + f"\n<!-- image remplacée (cm020) : {m.group(2)} -->"
    return avant[:m.start()] + ligne + avant[m.end():] + sep + apres
