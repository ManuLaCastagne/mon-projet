import os, sys
import pytest, yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import corriger_faits as cf
import audit_qualite as aq

FICHE = """---
tags:
  - Histoire
debut: 1423
fin: 1483
indice_1:
  - fils de Charles VIII
culture_g_score: 88
---
![Image](https://exemple.org/louis.jpg)

###### Questions

Quel roi, fils de Charles VIII, fut surnommé l'universelle aragne ? <!-- score: 3 -->

Quel roi affronta Charles le Téméraire ?

###### Description

Louis XI est roi de France de 1461 à 1483. Il est le fils de Charles VIII. Il meurt au Plessis-lès-Tours.
"""


def corps_jeu(t):
    """Ce que voit le jeu : la section Questions et la description, jusqu'au titre suivant."""
    return t.split("###### Archives")[0]


def test_question_corrigee_et_archivee():
    t = cf.corriger_question(FICHE, "Quel roi, fils de Charles VIII, fut surnommé l'universelle aragne ?",
                             "Quel roi, fils de Charles VII, fut surnommé l'universelle aragne ?")
    assert "fils de Charles VII, fut" in corps_jeu(t) and "Charles VIII, fut" not in corps_jeu(t)
    assert "###### Archives questions" in t and "Charles VIII, fut surnommé l'universelle aragne ? <!-- score: 3 --> <!-- cm034 corrigée" in t
    assert "Quel roi affronta Charles le Téméraire ?" in corps_jeu(t)


def test_phrase_corrigee_et_archivee():
    t = cf.corriger_phrase(FICHE, "Il est le fils de Charles VIII.", "Il est le fils de Charles VII.")
    desc = corps_jeu(t).split("###### Description")[1]
    assert "fils de Charles VII." in desc and "Charles VIII" not in desc
    assert "###### Archives description" in t and "Il est le fils de Charles VIII. <!-- cm034 corrigée" in t


def test_deux_corrections_successives_gardent_les_sections():
    t = cf.corriger_question(FICHE, "Quel roi, fils de Charles VIII, fut surnommé l'universelle aragne ?", "Quel roi fut surnommé l'universelle aragne ?")
    t = cf.corriger_phrase(t, "Il est le fils de Charles VIII.", "Il est le fils de Charles VII.")
    t = cf.corriger_question(t, "Quel roi affronta Charles le Téméraire ?", "Quel roi de France affronta Charles le Téméraire ?")
    assert t.count("###### Archives questions") == 1 and t.count("###### Archives description") == 1
    assert t.count("<!-- cm034 corrigée") == 3
    assert t.index("###### Description") < t.index("###### Archives")


def test_date_et_indice_archives_yaml_valide():
    t = cf.corriger_champ(FICHE, "debut", 1423)
    t = cf.corriger_champ(t, "fin", 1484)
    t = cf.corriger_indice(t, "indice_1", "fils de Charles VIII", "fils de Charles VII")
    d = yaml.safe_load(t.split("---")[1])
    assert d["fin"] == 1484 and d["fin_archive_cm034"] == "1483"
    assert d["indice_1"] == ["fils de Charles VII"] and d["indice_1_archive_cm034"] == ["fils de Charles VIII"]


def test_texte_introuvable_refuse():
    with pytest.raises(cf.Introuvable):
        cf.corriger_phrase(FICHE, "Phrase absente.", "x")
    with pytest.raises(cf.Introuvable):
        cf.corriger_question(FICHE, "Question absente ?", "x")


def test_questions_jouables_inchangees_en_nombre():
    t = cf.corriger_question(FICHE, "Quel roi affronta Charles le Téméraire ?", "Quel roi de France affronta Charles le Téméraire ?")
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(t)
    assert len(aq.lire_fiche(f.name)[1]) == 2


def test_indice_avec_espace_avant_deux_points():
    f = FICHE.replace("indice_1:\n  - fils de Charles VIII", "indice_1 : \n  - fils de Charles VIII")
    t = cf.corriger_indice(f, "indice_1", "fils de Charles VIII", "fils de Charles VII")
    d = yaml.safe_load(t.split("---")[1])
    assert d["indice_1"] == ["fils de Charles VII"] and d["indice_1_archive_cm034"] == ["fils de Charles VIII"]


def test_marquer_verifiee():
    t = cf.marquer_verifiee(FICHE, "2026-11-26")
    t = cf.marquer_verifiee(t, "2026-11-27")
    d = yaml.safe_load(t.split("---")[1])
    assert d["verifie_cm034"] == "2026-11-27" and t.count("verifie_cm034") == 1
