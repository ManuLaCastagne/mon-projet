#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import random
from collections import defaultdict

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from scriptMarkdown import create_fiche
from github_utils import update_file, read_file, normalize_path


# ============================================================
# PARAMÈTRES DE SÉLECTION ADAPTATIVE
# ============================================================

ALPHA_REVISION = 1.5
CULTURE_G_DEFAULT = 50
CULTURE_G_FLOOR = 5
REVISION_FLOOR = 0.5


def normaliser_bloc_questions(lignes):
    """Garantit exactement une ligne vide entre chaque question."""
    start = None
    end = len(lignes)

    for i, ligne in enumerate(lignes):
        if ligne.strip().lower().startswith("###### questions"):
            start = i + 1
            continue

        if start is not None:
            if (
                ligne.strip().startswith("######")
                and not ligne.strip().lower().startswith("###### questions")
            ):
                end = i
                break

    if start is None:
        return lignes

    questions_lines = [l for l in lignes[start:end] if l.strip() != ""]

    new_block = [""]
    for idx, l in enumerate(questions_lines):
        new_block.append(l)
        if idx != len(questions_lines) - 1:
            new_block.append("")

    return lignes[:start] + new_block + lignes[end:]


def lister_fichiers_md(dossier):
    fichiers_md = []
    for racine, _, fichiers in os.walk(dossier):
        for f in fichiers:
            if f.endswith(".md"):
                fichiers_md.append(os.path.join(racine, f))
    return fichiers_md


def nettoyer_liens_wikilinks(texte):
    return re.sub(r"\[\[([^\]]+?)\]\]", r"\1", texte)


def separer_frontmatter_et_contenu(contenu):
    if contenu.startswith("---"):
        parts = contenu.split("---", 2)
        if len(parts) == 3:
            return "---" + parts[1] + "---", parts[2]
    return "", contenu


def extraire_score(ligne):
    """Score personnel de maîtrise de la question, de 0 à 10."""
    match = re.search(r"<!--\s*score\s*:\s*(\d+)\s*-->", ligne)
    if not match:
        return 5

    try:
        return max(0, min(10, int(match.group(1))))
    except ValueError:
        return 5


def extraire_score_culture_g(frontmatter):
    """
    Extrait culture_g_score du frontmatter.
    Si le score est absent ou invalide, retourne 50.
    """
    match = re.search(
        r"(?m)^culture_g_score\s*:\s*(\d+(?:\.\d+)?)\s*$",
        frontmatter,
    )

    if not match:
        return CULTURE_G_DEFAULT

    try:
        return max(0, min(100, float(match.group(1))))
    except ValueError:
        return CULTURE_G_DEFAULT


def mettre_a_jour_score(ligne, score):
    score = int(max(0, min(10, score)))
    ligne_sans_score = re.sub(
        r"\s*<!--\s*score\s*:\s*\d+\s*-->",
        "",
        ligne,
    ).strip()

    return ligne_sans_score + f" <!-- score: {score} -->"


def calculer_poids_question(question):
    """
    Croise :
    - la non-maîtrise personnelle de la question ;
    - l'importance Culture G de la fiche.
    """
    score_question = question.get("score", 5)

    try:
        score_question = float(score_question)
    except (TypeError, ValueError):
        score_question = 5

    score_question = max(0, min(10, score_question))

    besoin_revision = max(
        REVISION_FLOOR,
        10 - score_question,
    )

    poids_revision = besoin_revision ** ALPHA_REVISION

    culture_g_score = question.get(
        "culture_g_score",
        CULTURE_G_DEFAULT,
    )

    if culture_g_score is None:
        culture_g_score = CULTURE_G_DEFAULT

    try:
        culture_g_score = float(culture_g_score)
    except (TypeError, ValueError):
        culture_g_score = CULTURE_G_DEFAULT

    culture_g_score = max(0, min(100, culture_g_score))

    poids_culture = max(
        CULTURE_G_FLOOR,
        culture_g_score,
    )

    return poids_revision * poids_culture


def choisir_question_ponderee(questions_globales, question_precedente=None):
    """
    Tire UNE question à la fois, avec recalcul des poids après chaque réponse.
    Évite si possible de tirer deux fois de suite exactement la même question.
    """
    if not questions_globales:
        return None

    candidates = questions_globales

    if question_precedente is not None and len(questions_globales) > 1:
        candidates_sans_precedente = [
            q
            for q in questions_globales
            if not (
                q.get("fichier") == question_precedente.get("fichier")
                and q.get("ligne_index") == question_precedente.get("ligne_index")
            )
        ]

        if candidates_sans_precedente:
            candidates = candidates_sans_precedente

    poids = [calculer_poids_question(q) for q in candidates]

    if not poids or sum(poids) <= 0:
        poids = [1] * len(candidates)

    return random.choices(
        candidates,
        weights=poids,
        k=1,
    )[0]


def extraire_questions_depuis_fichier(fichier):
    with open(fichier, "r", encoding="utf-8") as f:
        contenu = f.read()

    frontmatter, corps = separer_frontmatter_et_contenu(contenu)

    culture_g_score = extraire_score_culture_g(frontmatter)

    lignes = corps.split("\n")
    questions = []
    in_questions = False

    for i, ligne in enumerate(lignes):
        if ligne.strip().lower().startswith("###### questions"):
            in_questions = True
            continue

        if in_questions:
            if (
                ligne.strip().startswith("#")
                or ligne.strip().lower().startswith("###### description")
            ):
                break

            if ligne.strip():
                score = extraire_score(ligne)

                questions.append({
                    "ligne": ligne,
                    "score": score,
                    "culture_g_score": culture_g_score,
                    "ligne_index": i,
                    "fichier": fichier,
                    "fiche_nom": os.path.splitext(os.path.basename(fichier))[0],
                    "lignes": lignes,
                    "frontmatter": frontmatter,
                })

    return questions


def poser_questions(questions_globales, nb_questions=1000):
    """
    Quiz adaptatif : la prochaine question est choisie uniquement après
    validation de la question actuelle.
    """
    if "quiz_index" not in st.session_state:
        st.session_state.quiz_index = 0
        st.session_state.quiz_modifications = defaultdict(list)
        st.session_state.quiz_reveal = False
        st.session_state.quiz_current_question = choisir_question_ponderee(
            questions_globales
        )

    index = st.session_state.quiz_index

    if (
        index >= nb_questions
        or st.session_state.quiz_current_question is None
    ):
        st.success("🎉 Révision terminée !")

        if st.button("🔁 Recommencer"):
            for key in [
                "quiz_index",
                "quiz_modifications",
                "quiz_reveal",
                "quiz_current_question",
            ]:
                if key in st.session_state:
                    del st.session_state[key]

            st.rerun()

        return

    q = st.session_state.quiz_current_question

    question_clean = nettoyer_liens_wikilinks(q["ligne"])
    question_affichee = re.sub(
        r"\s*<!--.*?-->",
        "",
        question_clean,
    ).strip()

    st.caption(f"Question {index + 1} / {nb_questions}")
    st.markdown("### ❓ Question")
    st.markdown(question_affichee)

    if not st.session_state.get("quiz_reveal", False):
        if st.button("👀 Voir la réponse"):
            st.session_state.quiz_reveal = True
            st.rerun()
        return

    st.info(f"📖 Réponse : {q['fiche_nom']}")
    st.caption(
        "Importance Culture G : "
        f"{q.get('culture_g_score', CULTURE_G_DEFAULT):g}/100"
    )

    score = st.slider(
        "📝 Note cette question (0 = inconnu, 10 = acquis)",
        0,
        10,
        int(q["score"]),
        key=(
            f"quiz_score_{q['fichier']}_"
            f"{q['ligne_index']}_{index}"
        ),
    )

    if st.button("✅ Valider et passer à la suivante"):
        nouvelle_ligne = mettre_a_jour_score(q["ligne"], score)

        q["ligne"] = nouvelle_ligne
        q["score"] = score
        q["lignes"][q["ligne_index"]] = nouvelle_ligne

        st.session_state.quiz_modifications[q["fichier"]] = (
            q["frontmatter"],
            q["lignes"],
        )

        sauvegarder_modifications({
            q["fichier"]: (
                q["frontmatter"],
                q["lignes"],
            )
        })

        question_precedente = q

        st.session_state.quiz_index += 1
        st.session_state.quiz_reveal = False
        st.session_state.quiz_current_question = choisir_question_ponderee(
            questions_globales,
            question_precedente=question_precedente,
        )

        st.rerun()

    if st.button("✏️ Modifier les questions de cette fiche"):
        nouvelle_ligne = mettre_a_jour_score(q["ligne"], score)

        q["ligne"] = nouvelle_ligne
        q["score"] = score
        q["lignes"][q["ligne_index"]] = nouvelle_ligne

        sauvegarder_modifications({
            q["fichier"]: (
                q["frontmatter"],
                q["lignes"],
            )
        })

        st.session_state["page"] = "edition"
        st.session_state["edition_fichier"] = q["fichier"]
        st.stop()

    afficher_description(q["fichier"])


def sauvegarder_modifications(modifications):
    """Sauvegarde les fiches modifiées dans GitHub."""
    for fichier, (frontmatter, lignes) in modifications.items():
        nouveau_contenu = frontmatter + "\n" + "\n".join(lignes)

        success = update_file(
            path=fichier,
            content=nouveau_contenu,
            message=f"Update score in {os.path.basename(fichier)}",
        )

        if success:
            st.toast(
                f"💾 {os.path.basename(fichier)} mis à jour dans GitHub !"
            )
        else:
            st.error(
                f"❌ Impossible d'enregistrer {fichier} dans GitHub."
            )


def jeu_with_year(questions_globales):
    if "with_year_fiches" not in st.session_state:
        questions_par_fiche = {}

        for q in questions_globales:
            questions_par_fiche[q["fiche_nom"]] = q

        fiches = list(questions_par_fiche.values())
        random.shuffle(fiches)

        valides = []

        for q in fiches:
            debut = None
            fin = None
            lignes = q.get("frontmatter", "").splitlines()
            indices = []

            for i, ligne in enumerate(lignes):
                ligne = ligne.strip()

                if ligne.startswith("debut:"):
                    match = re.search(r"debut:\s*(\d{4})", ligne)
                    if match:
                        debut = match.group(1)

                elif ligne.startswith("fin:"):
                    match = re.search(r"fin:\s*(\d{4})", ligne)
                    if match:
                        fin = match.group(1)

                if re.match(r"indice_\d+\s*:", ligne):
                    if i + 1 < len(lignes):
                        suite = lignes[i + 1].strip()

                        if suite.startswith("-"):
                            indices.append(suite[1:].strip())

            if debut or fin:
                q["debut"] = debut
                q["fin"] = fin
                q["indices"] = indices
                valides.append(q)

        st.session_state.with_year_fiches = valides
        st.session_state.with_year_index = 0
        st.session_state.show_answer = False

    fiches = st.session_state.with_year_fiches
    index = st.session_state.with_year_index

    if index >= len(fiches):
        st.success("🎉 Tu as terminé toutes les fiches avec des années !")

        if st.button("🔁 Rejouer"):
            del st.session_state.with_year_fiches
            del st.session_state.with_year_index
            del st.session_state.show_answer
            st.rerun()

        return

    q = fiches[index]
    debut = q.get("debut")
    fin = q.get("fin")
    indices = q.get("indices", [])

    if debut and fin:
        periode = f"{debut}-{fin}"
    elif debut:
        periode = f"En {debut}"
    else:
        periode = f"Jusqu’en {fin}"

    theme = os.path.basename(os.path.dirname(q["fichier"]))
    indice = random.choice(indices) if indices else "Aucun indice"

    st.markdown("### 📅 Devine la fiche")
    st.markdown(f"📁 **Thème** : {theme}")
    st.markdown(f"📅 **Période** : {periode}")
    st.markdown(f"💡 **Indice** : {indice}")

    if not st.session_state.show_answer:
        if st.button("👀 Révéler la réponse"):
            st.session_state.show_answer = True
            st.rerun()

    else:
        st.success(f"✅ Réponse : {q['fiche_nom']}")
        afficher_description(q["fichier"])

        if st.button("🔜 Fiche suivante"):
            st.session_state.with_year_index += 1
            st.session_state.show_answer = False
            st.rerun()


def jeu_qui_suis_je(questions_globales):
    if "qui_index" not in st.session_state:
        questions_par_fiche = {}

        for q in questions_globales:
            questions_par_fiche[q["fiche_nom"]] = q

        fiches_valides = []

        for q in questions_par_fiche.values():
            frontmatter = q.get("frontmatter", "")
            lignes = frontmatter.splitlines()
            indices = []

            for i, ligne in enumerate(lignes):
                if re.match(r"indice_\d+\s*:", ligne.strip()):
                    if i + 1 < len(lignes):
                        suivant = lignes[i + 1].strip()

                        if suivant.startswith("-"):
                            indices.append(suivant[1:].strip())

            if indices:
                q["indices"] = indices
                fiches_valides.append(q)

        random.shuffle(fiches_valides)

        st.session_state.qui_fiches = fiches_valides
        st.session_state.qui_index = 0
        st.session_state.qui_indice_revele = 0
        st.session_state.qui_reponse = False

    fiches = st.session_state.qui_fiches
    index = st.session_state.qui_index

    if index >= len(fiches):
        st.success("🎉 Tu as terminé toutes les fiches !")

        if st.button("🔁 Rejouer"):
            del st.session_state.qui_fiches
            del st.session_state.qui_index
            del st.session_state.qui_indice_revele
            del st.session_state.qui_reponse
            st.rerun()

        return

    q = fiches[index]
    indices = q["indices"]
    theme = os.path.basename(os.path.dirname(q["fichier"]))

    st.markdown("### 🕵️ Qui suis-je ?")
    st.markdown(f"📁 **Thème** : {theme}")

    max_i = st.session_state.qui_indice_revele

    for i in range(max_i + 1):
        if i < len(indices):
            st.markdown(f"🔍 **Indice {i + 1}** : {indices[i]}")

    col1, col2 = st.columns(2)

    if col1.button("➕ Indice suivant") and max_i + 1 < len(indices):
        st.session_state.qui_indice_revele += 1
        st.rerun()

    if col2.button("👀 Révéler la réponse"):
        st.session_state.qui_reponse = True
        st.rerun()

    if st.session_state.qui_reponse:
        st.success(f"✅ Réponse : {q['fiche_nom']}")
        afficher_description(q["fichier"])

        if st.button("🔜 Fiche suivante"):
            st.session_state.qui_index += 1
            st.session_state.qui_indice_revele = 0
            st.session_state.qui_reponse = False
            st.rerun()


def jeu_depuis_liens(questions_globales, fichiers_md):
    if "liens_index" not in st.session_state:
        fiches_existantes = set(
            os.path.splitext(os.path.basename(f))[0]
            for f in fichiers_md
        )

        fiches_par_nom = {
            q["fiche_nom"]: q
            for q in questions_globales
        }

        valides = []

        for q in fiches_par_nom.values():
            nom_fiche = q["fiche_nom"]

            with open(q["fichier"], "r", encoding="utf-8") as f:
                contenu = f.read()

            liens = re.findall(r"\[\[([^\]]+?)\]\]", contenu)

            liens_valides = sorted(
                set(
                    l
                    for l in liens
                    if l != nom_fiche and l in fiches_existantes
                )
            )

            if liens_valides:
                q["liens_valides"] = liens_valides
                valides.append(q)

        random.shuffle(valides)

        st.session_state.liens_fiches = valides
        st.session_state.liens_index = 0
        st.session_state.liens_reponse = False

    fiches = st.session_state.liens_fiches
    index = st.session_state.liens_index

    if index >= len(fiches):
        st.success("🎉 Tu as terminé toutes les fiches avec des liens !")

        if st.button("🔁 Rejouer"):
            del st.session_state.liens_fiches
            del st.session_state.liens_index
            del st.session_state.liens_reponse
            st.rerun()

        return

    q = fiches[index]
    theme = os.path.basename(os.path.dirname(q["fichier"]))
    liens_valides = q["liens_valides"]

    st.markdown("### 🔗 Devine la fiche à partir de ses liens internes")
    st.markdown(f"📁 **Thème** : {theme}")
    st.markdown("#### Liens internes trouvés dans la fiche :")

    for lien in liens_valides:
        st.markdown(f"- {lien}")

    if not st.session_state.liens_reponse:
        if st.button("👀 Révéler la réponse"):
            st.session_state.liens_reponse = True
            st.rerun()

    else:
        st.success(f"✅ Réponse : {q['fiche_nom']}")
        afficher_description(q["fichier"])

        if st.button("🔜 Fiche suivante"):
            st.session_state.liens_index += 1
            st.session_state.liens_reponse = False
            st.rerun()


def afficher_description(fichier):
    try:
        contenu = read_file(fichier)

        if not contenu:
            return []

        _, corps = separer_frontmatter_et_contenu(contenu)
        lignes = corps.split("\n")
        description = []
        capture = False

        for ligne in lignes:
            if ligne.strip().lower().startswith("###### description"):
                capture = True
                continue

            if capture:
                if ligne.strip().startswith("######"):
                    break

                description.append(ligne)

        if description:
            st.markdown("---")
            st.markdown("### 📝 Description")

            for ligne in description:
                st.markdown(ligne)

    except Exception:
        st.error("Erreur lors du chargement de la description.")


def interface_generation_fiche():
    st.title("📝 Générer une fiche avec GPT")

    nom = st.text_input("Nom de la fiche")

    category = st.selectbox(
        "Catégorie",
        [
            "Anatomie",
            "Animaux",
            "Architecture",
            "Art",
            "Botanique",
            "Cinéma",
            "Gastronomie",
            "Géographie",
            "Histoire",
            "Littérature",
            "Musique",
            "Mythologie",
            "Religion",
            "Sciences",
            "Sport",
            "Télévision",
            "Vocabulaire",
        ],
    )

    if st.button("⚙️ Générer la fiche"):
        if not nom.strip():
            st.warning("Veuillez saisir un nom.")
            return

        try:
            st.write("⏳ Génération en cours…")

            create_fiche(nom, category)

            st.success(
                f"✨ Fiche **{nom}** créée dans la catégorie **{category}** !"
            )

            chemin_fiche = os.path.join(
                "data",
                category,
                f"{nom}.md",
            )

            contenu_fiche = read_file(chemin_fiche)

            if contenu_fiche:
                st.markdown("---")
                st.subheader("📄 Fiche générée")

                _, corps = separer_frontmatter_et_contenu(contenu_fiche)
                st.markdown(corps)

            else:
                st.error("Impossible de charger la fiche générée.")

        except Exception as e:
            st.error(f"Erreur : {e}")


def interface_edition_questions(fichier_force=None):
    st.title("✏️ Édition des questions d’une fiche")

    if fichier_force is None:
        noms_fichiers = {
            os.path.splitext(os.path.basename(f))[0]: f
            for f in fichiers_md
        }

        choix = st.selectbox(
            "Choisis une fiche à modifier :",
            sorted(noms_fichiers.keys()),
        )

        if not choix:
            return

        fichier = noms_fichiers[choix]

    else:
        fichier = fichier_force
        choix = os.path.splitext(os.path.basename(fichier_force))[0]

        st.markdown(
            f"### ✏️ Modification de la fiche : **{choix}**"
        )

    contenu_original = read_file(fichier)

    if not contenu_original:
        st.error("Impossible de charger la fiche.")
        return

    frontmatter, corps = separer_frontmatter_et_contenu(contenu_original)
    lignes_initiales = corps.split("\n")

    key_lignes = f"edition_lignes_{fichier}"

    if key_lignes not in st.session_state:
        st.session_state[key_lignes] = lignes_initiales

    lignes = st.session_state[key_lignes]

    def extraire_questions_depuis_lignes(lignes_locales):
        questions_locales = []
        in_questions = False

        for i, ligne in enumerate(lignes_locales):
            if ligne.strip().lower().startswith("###### questions"):
                in_questions = True
                continue

            if in_questions:
                if (
                    ligne.strip().startswith("#")
                    or ligne.strip().lower().startswith("###### description")
                ):
                    break

                if ligne.strip():
                    score = extraire_score(ligne)

                    questions_locales.append({
                        "ligne": ligne,
                        "score": score,
                        "ligne_index": i,
                        "fiche_nom": choix,
                    })

        return questions_locales

    questions = extraire_questions_depuis_lignes(lignes)

    st.subheader("📝 Questions existantes")

    for q in questions:
        idx = q["ligne_index"]
        old_line = q["ligne"]

        texte_sans_score = re.sub(
            r"<!--.*?-->",
            "",
            old_line,
        ).strip()

        new_text = st.text_area(
            f"Question ({q['fiche_nom']} - ligne {idx})",
            texte_sans_score,
            key=f"edit_{fichier}_{idx}",
            height=120,
        )

        if st.button(
            f"🗑️ Supprimer (ligne {idx})",
            key=f"delete_{fichier}_{idx}",
        ):
            st.session_state[key_lignes][idx] = ""
            st.rerun()

        score = q["score"]

        if new_text.strip() != texte_sans_score:
            lignes[idx] = mettre_a_jour_score(new_text, score)
            st.session_state[key_lignes] = lignes

    st.markdown("---")
    st.subheader("➕ Ajouter une nouvelle question")

    nouvelle_question = st.text_area(
        "Nouvelle question (sans score)",
        key=f"new_q_{fichier}",
        height=120,
    )

    if st.button(
        "Ajouter la question",
        key=f"add_q_{fichier}",
    ):
        if nouvelle_question.strip():
            lignes = st.session_state[key_lignes]
            insertion_index = None

            for i, ligne in enumerate(lignes):
                if ligne.strip().lower().startswith("###### questions"):
                    insertion_index = i + 1
                    break

            if insertion_index is None:
                insertion_index = 0

            lignes.insert(
                insertion_index,
                mettre_a_jour_score(
                    nouvelle_question.strip(),
                    5,
                ),
            )

            st.session_state[key_lignes] = lignes
            st.success("Nouvelle question ajoutée ✔️")
            st.rerun()

    st.markdown("---")

    if st.button(
        "💾 Enregistrer les modifications",
        key=f"save_{fichier}",
    ):
        lignes = st.session_state[key_lignes]
        lignes_normalisees = normaliser_bloc_questions(lignes)

        frontmatter_clean = frontmatter.rstrip() + "\n\n"
        corps_clean = "\n".join(lignes_normalisees).lstrip("\n")
        nouveau_contenu = frontmatter_clean + corps_clean

        success = update_file(
            path=fichier,
            content=nouveau_contenu,
            message=f"Edit questions in {choix}",
        )

        if success:
            st.success(f"🎉 Questions mises à jour dans {choix} !")

            del st.session_state[key_lignes]
            st.session_state["page"] = "quiz"

            for key in [
                "quiz_index",
                "quiz_modifications",
                "quiz_reveal",
                "quiz_current_question",
                "quiz_questions",
            ]:
                if key in st.session_state:
                    del st.session_state[key]

            st.stop()

        else:
            st.error("❌ Échec de l'enregistrement dans GitHub.")


def interface_afficher_fiche():
    st.title("📄 Afficher une fiche")

    noms_fichiers = {
        os.path.splitext(os.path.basename(f))[0]: f
        for f in fichiers_md
    }

    choix = st.selectbox(
        "Choisis une fiche à afficher :",
        sorted(noms_fichiers.keys()),
    )

    if not choix:
        return

    fichier = noms_fichiers[choix]

    contenu = read_file(fichier)

    if not contenu:
        st.error("Impossible de charger la fiche.")
        return

    _, corps = separer_frontmatter_et_contenu(contenu)

    st.subheader("📝 Contenu complet de la fiche")
    st.markdown(corps)


def interface_cartographie_savoir():
    """Affiche une cartographie locale centrée sur une fiche."""
    st.title("🧭 Cartographie locale du savoir")

    noms_fichiers = {
        os.path.splitext(os.path.basename(f))[0]: f
        for f in fichiers_md
    }

    choix = st.selectbox(
        "Choisis la fiche centrale :",
        sorted(noms_fichiers.keys()),
    )

    if not choix:
        return

    fichier_central = noms_fichiers[choix]
    contenu_central = read_file(fichier_central)

    if not contenu_central:
        st.error("Impossible de charger la fiche.")
        return

    _, corps = separer_frontmatter_et_contenu(contenu_central)

    liens_sortants = set(
        re.findall(r"\[\[([^\]]+?)\]\]", corps)
    )

    st.markdown("### 🧵 Liens sortants")

    if liens_sortants:
        st.markdown(
            ", ".join(
                f"**{l}**"
                for l in liens_sortants
            )
        )
    else:
        st.info("Aucun lien sortant trouvé.")

    net = Network(
        height="600px",
        width="100%",
        directed=False,
        notebook=False,
    )

    net.barnes_hut()

    net.add_node(
        choix,
        label=choix,
        color="#ffcc00",
        size=25,
    )

    for lien in liens_sortants:
        net.add_node(
            lien,
            label=lien,
            color="#66b3ff",
        )
        net.add_edge(choix, lien)

    if not liens_sortants:
        st.warning("Cette fiche n’a aucun lien interne ni backlink.")
        return

    html_path = "graph_locale.html"
    net.write_html(html_path)

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        components.html(
            html_content,
            height=600,
            scrolling=True,
        )

    except Exception as e:
        st.error(
            f"Erreur lors de l'affichage du graphe : {e}"
        )


DOSSIER = "data"
fichiers_md = lister_fichiers_md(DOSSIER)

questions_globales = []

for fichier in fichiers_md:
    questions_globales.extend(
        extraire_questions_depuis_fichier(fichier)
    )
