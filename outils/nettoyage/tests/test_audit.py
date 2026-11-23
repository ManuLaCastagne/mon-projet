import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_qualite as aq  # noqa: E402

FICHE_LOLA = """---
tags:
  - Cinéma
aliases:
  - Lola Montès
questions:
  - En 1955, dans quel film de Max Ophuls, Martine Carol interprète-t-elle une danseuse et courtisane ?
culture_g_score: 47
---
###### Questions

En 1955, dans quel film de [[Max Ophüls]], [[Martine Carol]] interprète-t-elle une danseuse et courtisane ?

Dans quel film de [[Max Ophüls]] sorti en 1955 [[Martine Carol]] incarne-t-elle une célèbre danseuse du XIXe siècle ? <!-- score: 3 -->

Quelle œuvre de 1955, souvent citée pour ses décors, raconte la vie tumultueuse de [[Lola Montes]] ?

En quelle année est sorti [[Lola Montès]] de [[Max Ophüls]] ?

###### Description

Texte libre.
"""

FICHE_ROSA = """---
questions:
  - En 1955, quelle couturière noire refuse de céder sa place dans un bus ?
---
###### Questions

Quelle figure emblématique des droits civiques a été arrêtée à [[Montgomery]] en [[1955]] ?
"""

FICHE_IO = """---
tags: [Astronomie]
---
###### Questions

Quel satellite de Jupiter, le plus volcanique du système solaire, porte le nom d'une prêtresse d'Héra ?
"""

FICHE_SANS_SECTION = """---
questions:
  - Une question TV seule ?
---
Pas de section ici.
"""


def creer_coffre(tmp_path):
    (tmp_path / "Cinéma").mkdir()
    (tmp_path / "Histoire").mkdir()
    (tmp_path / "Sciences").mkdir()
    (tmp_path / "Cinéma" / "Lola Montes.md").write_text(FICHE_LOLA, encoding="utf-8")
    (tmp_path / "Histoire" / "Rosa Parks.md").write_text(FICHE_ROSA, encoding="utf-8")
    (tmp_path / "Sciences" / "Io.md").write_text(FICHE_IO, encoding="utf-8")
    (tmp_path / "Histoire" / "Vide.md").write_text(FICHE_SANS_SECTION, encoding="utf-8")
    return tmp_path


def empreinte(dossier):
    h = hashlib.sha256()
    for racine, _, fichiers in sorted(os.walk(dossier)):
        for f in sorted(fichiers):
            p = os.path.join(racine, f)
            h.update(p.encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


def lignes_de(tmp_path, fiche):
    return [l for l in aq.auditer(str(creer_coffre(tmp_path))) if l["fiche"] == fiche]


def test_lecture_alignee_sur_le_moteur(tmp_path):
    lignes = lignes_de(tmp_path, "Lola Montes")
    assert len(lignes) == 4  # s'arrête à ###### Description, ignore les lignes vides


def test_reprise_tv_identique(tmp_path):
    q = lignes_de(tmp_path, "Lola Montes")[0]
    assert q["provenance"] == "Reprise jeu TV" and q["confiance"] == "haute"


def test_reformulation_tv(tmp_path):
    q = lignes_de(tmp_path, "Lola Montes")[1]
    assert q["provenance"] == "Reformulation jeu TV"


def test_score_lu_et_retire_du_texte(tmp_path):
    q = lignes_de(tmp_path, "Lola Montes")[1]
    assert q["score_maitrise"] == 3 and "score" not in q["question"]


def test_titre_cite_avec_wikilink_et_sans_accent(tmp_path):
    q = lignes_de(tmp_path, "Lola Montes")[2]
    assert q["fuite"] == "titre cité"


def test_titre_cite_meme_si_question_sur_autre_chose(tmp_path):
    # Le jeu affiche "Lola Montes" comme réponse alors que la question demande une année : défaut aussi.
    q = lignes_de(tmp_path, "Lola Montes")[3]
    assert q["fuite"] == "titre cité"


def test_marqueurs_ia(tmp_path):
    q = lignes_de(tmp_path, "Rosa Parks")[0]
    assert q["provenance"] in {"IA probable", "IA possible"} and q["marqueurs_ia"] >= 1


def test_titre_court_pas_de_faux_positif(tmp_path):
    q = lignes_de(tmp_path, "Io")[0]
    assert q["fuite"] == ""  # "Io" (2 lettres) n'est pas cherché dans "prêtresse", "volcanique"...


def test_fiche_sans_section_ignoree(tmp_path):
    assert lignes_de(tmp_path, "Vide") == []


def test_aucune_modification_du_coffre(tmp_path):
    (tmp_path / "c").mkdir()
    coffre = creer_coffre(tmp_path / "c")
    avant = empreinte(coffre)
    aq.main(["x", str(coffre), str(tmp_path / "sortie")])
    assert empreinte(coffre) == avant
    assert (tmp_path / "sortie" / "cm001_questions.csv").exists()


def test_yaml_invalide_ne_bloque_pas(tmp_path):
    (tmp_path / "Casse.md").write_text("---\ntags: [non ferme\n---\n###### Questions\n\nQuestion ?\n", encoding="utf-8")
    lignes = aq.auditer(str(tmp_path))
    assert len(lignes) == 1 and lignes[0]["provenance"] == "Indéterminée"


def test_indice_par_mot_distinctif(tmp_path):
    (tmp_path / "La Fée électricité.md").write_text("###### Questions\n\nQuelle œuvre de [[Raoul Dufy]] retrace l'histoire de l'électricité ?\n", encoding="utf-8")
    assert aq.auditer(str(tmp_path))[0]["fuite"] == "indice"
