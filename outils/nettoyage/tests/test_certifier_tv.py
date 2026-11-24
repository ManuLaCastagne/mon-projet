import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audit_qualite as aq  # noqa: E402
import certifier_tv as ct  # noqa: E402

FICHE = """---
tags:
  - Histoire
questions:
 - Quel roi de France, fils de Charles VIII, était appelé l'universelle Aragne ?
 - En 1461, quel roi est sacré à Reims ?
questions:
 - Quel roi de France, fils de Charles VIII, était appelé l'universelle Aragne ?
culture_g_score: 70
---
![Image de Louis XI](https://upload.wikimedia.org/ancienne.jpg)

###### Questions

Question existante ? <!-- score: 4 -->

###### Description

Texte [[Charles VII]].
"""

TV = "Quel roi de France, fils de Charles VIII, était appelé l'universelle Aragne ?"
NEUVE = "Quel roi de France, fils de [[Charles VII]], était surnommé « l'universelle aragne » ?"


def test_certification_complete(tmp_path):
    t = ct.certifier(FICHE, TV, NEUVE)
    debut, entete, corps = ct._decouper(t)
    assert "fils de Charles VIII" not in entete.split("questions_tv_archivees:")[0]  # retirée de toutes les listes
    assert entete.count("fils de Charles VIII") == 1  # archivée une seule fois
    assert "  - En 1461, quel roi est sacré à Reims ?" not in entete and " - En 1461, quel roi est sacré à Reims ?" in entete
    assert ct.questions_section(corps) == ["Question existante ? <!-- score: 4 -->", NEUVE + " " + ct.MARQUE_TV]
    assert "###### Description\n\nTexte [[Charles VII]].\n" in t
    p = tmp_path / "f.md"
    p.write_text(t, encoding="utf-8")
    props, qs = aq.lire_fiche(str(p))  # l'en-tête reste du YAML valide
    assert not props.get("_yaml_invalide") and len(props["questions_tv_archivees"]) == 1 and len(qs) == 2
    assert props["questions"] == ["En 1461, quel roi est sacré à Reims ?"]  # la clé répétée vidée est retirée


def test_rien_n_est_perdu():
    t = ct.certifier(FICHE, TV, NEUVE)
    for ligne in FICHE.split("\n"):
        if ligne.strip() and not ligne.startswith((" -", "questions:")):
            assert ligne in t, ligne


def test_question_absente():
    with pytest.raises(ct.Introuvable):
        ct.certifier(FICHE, "Question inconnue ?", NEUVE)


def test_doublon_refuse():
    with pytest.raises(ct.Introuvable):
        ct.certifier(FICHE, TV, "Question existante ?")


def test_section_creee_si_absente():
    sans = FICHE.replace("###### Questions\n\nQuestion existante ? <!-- score: 4 -->\n\n", "")
    t = ct.certifier(sans, TV, NEUVE)
    assert "###### Questions\n\n" + NEUVE + " " + ct.MARQUE_TV + "\n\n###### Description" in t


def test_remplacer_image():
    t = ct.remplacer_image(FICHE, "https://commons.wikimedia.org/wiki/Special:FilePath/Nouvelle.jpg")
    assert "![Image de Louis XI](https://commons.wikimedia.org/wiki/Special:FilePath/Nouvelle.jpg)\n<!-- image remplacée (cm020) : https://upload.wikimedia.org/ancienne.jpg -->" in t
    assert t.replace("![Image de Louis XI](https://commons.wikimedia.org/wiki/Special:FilePath/Nouvelle.jpg)\n<!-- image remplacée (cm020) : https://upload.wikimedia.org/ancienne.jpg -->", "![Image de Louis XI](https://upload.wikimedia.org/ancienne.jpg)") == FICHE
