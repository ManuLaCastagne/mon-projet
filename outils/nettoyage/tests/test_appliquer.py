import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import appliquer as ap  # noqa: E402
import audit_qualite as aq  # noqa: E402

FICHE = """---
tags:
  - Cinéma
culture_g_score: 60
---
![Image](https://exemple.org/a.jpg)

###### Questions

Question A sur [[Truc]] ? <!-- score: 8 -->

Question B fausse ?

Question C doublon ?

###### Description

Texte avec [[liens]] et accents éàü.
"""


def item(rang, verdict, actuelle, prop=""):
    return {"rang_dans_fiche": rang, "verdict": verdict, "question_actuelle": actuelle, "proposition": prop}


def test_remplacement_archive_et_reste_intact():
    nouveau, r = ap.appliquer_fiche(FICHE, [
        item(1, "garder", "Question A sur [[Truc]] ?"),
        item(2, "corriger", "Question B fausse ?", "Question B juste sur [[Machin]] ?"),
        item(3, "ecarter", "Question C doublon ?"),
    ])
    assert [x["statut"] for x in r] == ["inchangée", "remplacée", "archivée"]
    assert "Question A sur [[Truc]] ? <!-- score: 8 -->" in nouveau
    assert "\nQuestion B juste sur [[Machin]] ?\n" in nouveau
    assert nouveau.rstrip().endswith("Question C doublon ? <!-- cm003 archivée 2026-11-23 -->")
    assert "Question B fausse ? <!-- cm003 remplacée 2026-11-23 -->" in nouveau
    # Tout ce qui précède la section et la description sont intacts.
    assert nouveau.startswith(FICHE.split("###### Questions")[0])
    assert "###### Description\n\nTexte avec [[liens]] et accents éàü.\n" in nouveau


def test_jeu_ne_voit_pas_les_archives(tmp_path):
    nouveau, _ = ap.appliquer_fiche(FICHE, [item(3, "ecarter", "Question C doublon ?")])
    p = tmp_path / "f.md"
    p.write_text(nouveau, encoding="utf-8")
    assert aq.lire_fiche(str(p))[1] == ["Question A sur [[Truc]] ? <!-- score: 8 -->", "Question B fausse ?"]
    assert "Question B fausse ?\n\n###### Description" in nouveau  # une seule ligne vide conservée


def test_texte_different_rien_ecrit():
    nouveau, r = ap.appliquer_fiche(FICHE, [item(2, "corriger", "Autre texte ?", "X ?")])
    assert nouveau == FICHE and r[0]["statut"].startswith("ignorée")


def test_archives_existantes_completees():
    once, _ = ap.appliquer_fiche(FICHE, [item(3, "ecarter", "Question C doublon ?")])
    twice, _ = ap.appliquer_fiche(once, [item(2, "corriger", "Question B fausse ?", "B2 ?")])
    assert twice.count(ap.TITRE_ARCHIVES) == 1
    assert "Question B fausse ? <!-- cm003 remplacée" in twice


def test_fins_de_ligne_windows():
    crlf = FICHE.replace("\n", "\r\n")
    nouveau, _ = ap.appliquer_fiche(crlf, [item(2, "corriger", "Question B fausse ?", "B2 ?")])
    assert "\n" not in nouveau.replace("\r\n", "")
