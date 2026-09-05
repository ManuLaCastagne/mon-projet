#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Moteur de jeu Streamlit pour les fiches Obsidian.

Optimisations principales :
- chargement des fichiers/questions mis en cache par Streamlit ;
- lecture locale prioritaire, GitHub seulement en secours ;
- quiz adaptatif : une seule question est tirée à la fois ;
- score de maîtrise + score Culture G croisés pour le tirage ;
- culture_g_score absent = 50 ;
- sauvegarde locale immédiate après chaque réponse ;
- synchronisation GitHub groupée toutes les N réponses ;
- plusieurs modifications d'une même fiche = un seul commit au prochain sync ;
- bouton de synchronisation manuelle ;
- aucun appel GitHub pour simplement afficher une description locale.
"""

import os
import re
import random
from collections import defaultdict

import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network

from scriptMarkdown import create_fiche
from github_utils import update_file, read_file


# ============================================================
# CONFIGURATION
# ============================================================

DOSSIER = "data"

# Sélection adaptative
ALPHA_REVISION = 1.5
CULTURE_G_DEFAULT = 50
CULTURE_G_FLOOR = 5
REVISION_FLOOR = 0.5

# Synchronisation GitHub :
# les réponses sont écrites localement immédiatement,
# puis regroupées avant envoi à GitHub.
SYNC_EVERY_N_QUESTIONS = 10

# Le cache global des questions est reconstruit périodiquement.
# Dans la session en cours, les scores modifiés sont conservés
# via quiz_score_overrides, donc ils sont pris en compte immédiatement.
CACHE_TTL_SECONDS = 300


# ============================================================
# UTILITAIRES MARKDOWN
# ============================================================

def normaliser_bloc_questions(lignes):
    """
    Garantit exactement une ligne vide entre chaque question
    dans la section '###### Questions'.
    """
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

    questions_lines = [
        ligne
        for ligne in lignes[start:end]
        if ligne.strip() != ""
    ]

    new_block = [""]

    for idx, ligne in enumerate(questions_lines):
        new_block.append(ligne)

        if idx != len(questions_lines) - 1:
            new_block.append("")

    return lignes[:start] + new_block + lignes[end:]


def lister_fichiers_md(dossier):
    fichiers_md = []

    for racine, _, fichiers in os.walk(dossier):
        for fichier in fichiers:
            if fichier.endswith(".md"):
                fichiers_md.append(
                    os.path.join(racine, fichier)
                )

    return sorted(fichiers_md)


def nettoyer_liens_wikilinks(texte):
    return re.sub(
        r"\[\[([^\]]+?)\]\]",
        r"\1",
        texte
    )


def separer_frontmatter_et_contenu(contenu):
    if contenu.startswith("---"):
        parts = contenu.split("---", 2)

        if len(parts) == 3:
            return (
                "---" + parts[1] + "---",
                parts[2]
            )

    return "", contenu


def reconstruire_contenu(frontmatter, lignes):
    """
    Reconstruit une fiche à partir de son frontmatter et de son corps.
    """
    corps = "\n".join(lignes)

    if frontmatter:
        return frontmatter.rstrip() + "\n" + corps

    return corps


def lire_contenu(fichier):
    """
    Lecture rapide :
    1. fichier local si disponible ;
    2. GitHub uniquement en secours.

    Cela évite un appel réseau lors de chaque rerun Streamlit.
    """
    try:
        if os.path.exists(fichier):
            with open(
                fichier,
                "r",
                encoding="utf-8"
            ) as f:
                return f.read()
    except Exception:
        pass

    try:
        return read_file(fichier)
    except Exception:
        return None


def ecrire_localement(fichier, contenu):
    """
    Écrit immédiatement la fiche sur le disque local.

    Retourne True en cas de succès.
    """
    try:
        dossier_parent = os.path.dirname(fichier)

        if dossier_parent:
            os.makedirs(
                dossier_parent,
                exist_ok=True
            )

        with open(
            fichier,
            "w",
            encoding="utf-8"
        ) as f:
            f.write(contenu)

        return True

    except Exception as exc:
        st.warning(
            f"⚠️ Sauvegarde locale impossible pour "
            f"{os.path.basename(fichier)} : {exc}"
        )
        return False


# ============================================================
# IMAGE PRINCIPALE
# ============================================================

def extraire_image_principale(contenu):
    """
    Extrait la première image Markdown de la fiche.

    Exemple :
        ![Image de Norman Foster](https://...)

    Retourne un dictionnaire {"alt": ..., "url": ...}
    ou None si aucune image n'est trouvée.
    """
    if not contenu:
        return None

    _, corps = separer_frontmatter_et_contenu(contenu)

    # On privilégie l'image placée avant le bloc Questions.
    avant_questions = re.split(
        r"(?im)^\s*######\s+questions\s*$",
        corps,
        maxsplit=1
    )[0]

    match = re.search(
        r'!\[([^\]]*)\]\((https?://[^)]+)\)',
        avant_questions
    )

    if not match:
        match = re.search(
            r'!\[([^\]]*)\]\((https?://[^)]+)\)',
            corps
        )

    if not match:
        return None

    return {
        "alt": match.group(1).strip(),
        "url": match.group(2).strip(),
    }


def supprimer_image_principale_du_corps(corps):
    """Retire uniquement la première image Markdown du corps."""
    return re.sub(
        r'!\[[^\]]*\]\((https?://[^)]+)\)\s*',
        '',
        corps,
        count=1
    )


def afficher_image_principale(fichier):
    """Affiche l'image principale de la fiche si elle existe."""
    contenu = lire_contenu(fichier)

    if not contenu:
        return False

    image = extraire_image_principale(contenu)

    if not image:
        return False

    try:
        st.image(
            image["url"],
            caption=image["alt"] or None,
            use_container_width=True
        )
        return True
    except Exception:
        return False


# ============================================================
# SCORES
# ============================================================

def extraire_score(ligne):
    """
    Score personnel de maîtrise, de 0 à 10.
    Valeur par défaut : 5.
    """
    match = re.search(
        r"<!--\s*score\s*:\s*(\d+)\s*-->",
        ligne
    )

    if not match:
        return 5

    try:
        return max(
            0,
            min(10, int(match.group(1)))
        )
    except ValueError:
        return 5


def extraire_score_culture_g(frontmatter):
    """
    Extrait culture_g_score depuis le frontmatter.

    Exemple :
        culture_g_score: 84

    Champ absent ou invalide -> 50.
    """
    match = re.search(
        r"(?m)^culture_g_score\s*:\s*(\d+(?:\.\d+)?)\s*$",
        frontmatter
    )

    if not match:
        return CULTURE_G_DEFAULT

    try:
        return max(
            0,
            min(100, float(match.group(1)))
        )
    except ValueError:
        return CULTURE_G_DEFAULT


def mettre_a_jour_score(ligne, score):
    """
    Remplace ou ajoute le commentaire HTML du score personnel.
    """
    score = int(
        max(0, min(10, score))
    )

    ligne_sans_score = re.sub(
        r"\s*<!--\s*score\s*:\s*\d+\s*-->",
        "",
        ligne
    ).strip()

    return (
        ligne_sans_score
        + f" <!-- score: {score} -->"
    )


def id_question(question):
    """
    Identifiant stable d'une question dans la session.
    """
    return (
        f"{question.get('fichier', '')}"
        f"::{question.get('ligne_index', '')}"
    )


def obtenir_score_question(question):
    """
    Retourne le score courant.

    Les modifications de la session ont priorité sur le score
    présent dans le cache initial.
    """
    overrides = st.session_state.get(
        "quiz_score_overrides",
        {}
    )

    qid = id_question(question)

    if qid in overrides:
        return overrides[qid]

    return question.get(
        "score",
        5
    )


def calculer_poids_question(question):
    """
    Poids de tirage :

        (besoin de révision ** ALPHA_REVISION)
        × importance Culture G

    Plus le poids est élevé, plus la question est susceptible
    d'être choisie.
    """
    score_question = obtenir_score_question(
        question
    )

    try:
        score_question = float(
            score_question
        )
    except (TypeError, ValueError):
        score_question = 5

    score_question = max(
        0,
        min(10, score_question)
    )

    besoin_revision = max(
        REVISION_FLOOR,
        10 - score_question
    )

    poids_revision = (
        besoin_revision
        ** ALPHA_REVISION
    )

    culture_g_score = question.get(
        "culture_g_score",
        CULTURE_G_DEFAULT
    )

    if culture_g_score is None:
        culture_g_score = CULTURE_G_DEFAULT

    try:
        culture_g_score = float(
            culture_g_score
        )
    except (TypeError, ValueError):
        culture_g_score = (
            CULTURE_G_DEFAULT
        )

    culture_g_score = max(
        0,
        min(100, culture_g_score)
    )

    poids_culture = max(
        CULTURE_G_FLOOR,
        culture_g_score
    )

    return (
        poids_revision
        * poids_culture
    )


# ============================================================
# EXTRACTION DES QUESTIONS
# ============================================================

def extraire_questions_depuis_fichier(fichier):
    contenu = lire_contenu(fichier)

    if not contenu:
        return []

    frontmatter, corps = (
        separer_frontmatter_et_contenu(
            contenu
        )
    )

    culture_g_score = (
        extraire_score_culture_g(
            frontmatter
        )
    )

    lignes = corps.split("\n")
    questions = []

    in_questions = False

    for i, ligne in enumerate(lignes):
        if (
            ligne.strip()
            .lower()
            .startswith(
                "###### questions"
            )
        ):
            in_questions = True
            continue

        if in_questions:
            if (
                ligne.strip().startswith("#")
                or ligne.strip()
                .lower()
                .startswith(
                    "###### description"
                )
            ):
                break

            if ligne.strip():
                questions.append({
                    "ligne": ligne,
                    "score": extraire_score(ligne),
                    "culture_g_score": culture_g_score,
                    "ligne_index": i,
                    "fichier": fichier,
                    "fiche_nom": os.path.splitext(
                        os.path.basename(fichier)
                    )[0],
                })

    return questions


@st.cache_data(
    show_spinner="📚 Chargement des questions…",
    ttl=CACHE_TTL_SECONDS
)
def charger_donnees(dossier):
    """
    Parcours complet du coffre.

    Cette opération coûteuse n'est plus refaite à chaque clic :
    Streamlit conserve le résultat en cache.
    """
    fichiers = lister_fichiers_md(
        dossier
    )

    questions = []

    for fichier in fichiers:
        questions.extend(
            extraire_questions_depuis_fichier(
                fichier
            )
        )

    return (
        fichiers,
        questions
    )


# ============================================================
# TIRAGE ADAPTATIF
# ============================================================

def choisir_question_ponderee(
    questions_globales,
    question_precedente=None
):
    """
    Tire UNE question seulement au moment où elle est nécessaire.

    Le poids utilise les scores les plus récents de la session.
    On évite si possible la répétition immédiate de la même question.
    """
    if not questions_globales:
        return None

    candidates = questions_globales

    if (
        question_precedente is not None
        and len(questions_globales) > 1
    ):
        precedente_id = id_question(
            question_precedente
        )

        sans_precedente = [
            q
            for q in questions_globales
            if id_question(q)
            != precedente_id
        ]

        if sans_precedente:
            candidates = sans_precedente

    poids = [
        calculer_poids_question(q)
        for q in candidates
    ]

    if (
        not poids
        or sum(poids) <= 0
    ):
        poids = [1] * len(candidates)

    return random.choices(
        candidates,
        weights=poids,
        k=1
    )[0]


# ============================================================
# SAUVEGARDE LOCALE + SYNCHRONISATION GITHUB
# ============================================================

def initialiser_etat_synchronisation():
    if (
        "quiz_pending_github"
        not in st.session_state
    ):
        st.session_state.quiz_pending_github = {}

    if (
        "quiz_answers_since_sync"
        not in st.session_state
    ):
        st.session_state.quiz_answers_since_sync = 0

    if (
        "quiz_score_overrides"
        not in st.session_state
    ):
        st.session_state.quiz_score_overrides = {}


def enregistrer_score_local(question, score):
    """
    Met à jour la question dans la VERSION LOCALE ACTUELLE de la fiche.

    On relit la fiche sur disque avant modification afin d'éviter
    qu'une ancienne copie du corps n'écrase une autre réponse modifiée
    précédemment dans la même fiche.

    Retourne la nouvelle ligne, ou None en cas d'erreur.
    """
    fichier = question["fichier"]

    contenu = lire_contenu(
        fichier
    )

    if not contenu:
        st.error(
            f"❌ Impossible de lire "
            f"{os.path.basename(fichier)}."
        )
        return None

    frontmatter, corps = (
        separer_frontmatter_et_contenu(
            contenu
        )
    )

    lignes = corps.split("\n")

    index = question.get(
        "ligne_index"
    )

    if (
        index is None
        or index < 0
        or index >= len(lignes)
    ):
        st.error(
            "❌ La question ne correspond plus "
            "à la structure actuelle de la fiche."
        )
        return None

    nouvelle_ligne = (
        mettre_a_jour_score(
            lignes[index],
            score
        )
    )

    lignes[index] = nouvelle_ligne

    nouveau_contenu = (
        reconstruire_contenu(
            frontmatter,
            lignes
        )
    )

    # Écriture locale immédiate.
    ecrire_localement(
        fichier,
        nouveau_contenu
    )

    # Dernière version de cette fiche à envoyer à GitHub.
    st.session_state.quiz_pending_github[
        fichier
    ] = nouveau_contenu

    # Score courant utilisé immédiatement par le tirage adaptatif.
    st.session_state.quiz_score_overrides[
        id_question(question)
    ] = int(score)

    question["ligne"] = nouvelle_ligne
    question["score"] = int(score)

    return nouvelle_ligne


def synchroniser_github(
    force=False,
    silencieux=False
):
    """
    Envoie à GitHub uniquement la dernière version des fichiers modifiés.

    Si 5 questions ont été modifiées dans la même fiche,
    un seul update_file est effectué pour cette fiche.
    """
    initialiser_etat_synchronisation()

    pending = (
        st.session_state
        .quiz_pending_github
    )

    if not pending:
        if (
            force
            and not silencieux
        ):
            st.toast(
                "☁️ Rien à synchroniser."
            )

        st.session_state.quiz_answers_since_sync = 0
        return True

    fichiers_a_envoyer = list(
        pending.items()
    )

    echecs = []

    for fichier, contenu in fichiers_a_envoyer:
        try:
            success = update_file(
                path=fichier,
                content=contenu,
                message=(
                    "Update quiz scores in "
                    f"{os.path.basename(fichier)}"
                )
            )
        except Exception:
            success = False

        if success:
            pending.pop(
                fichier,
                None
            )
        else:
            echecs.append(
                fichier
            )

    if not echecs:
        st.session_state.quiz_answers_since_sync = 0

        if not silencieux:
            st.toast(
                "☁️ Synchronisation GitHub terminée."
            )

        return True

    if not silencieux:
        st.warning(
            f"⚠️ {len(echecs)} fichier(s) "
            "restent à synchroniser avec GitHub."
        )

    return False


def synchroniser_si_necessaire():
    """
    Synchronisation automatique toutes les N réponses.
    """
    initialiser_etat_synchronisation()

    if (
        st.session_state
        .quiz_answers_since_sync
        >= SYNC_EVERY_N_QUESTIONS
    ):
        synchroniser_github(
            silencieux=False
        )


def afficher_etat_synchronisation():
    """
    Petit indicateur dans le quiz.
    """
    initialiser_etat_synchronisation()

    nb_fichiers = len(
        st.session_state
        .quiz_pending_github
    )

    if nb_fichiers:
        col1, col2 = st.columns(
            [3, 1]
        )

        col1.caption(
            f"💾 {nb_fichiers} fiche(s) "
            "modifiée(s) en attente de GitHub"
        )

        if col2.button(
            "☁️ Sync",
            key="quiz_sync_manual"
        ):
            synchroniser_github(
                force=True
            )
            st.rerun()


# Compatibilité avec d'éventuels appels existants.
def sauvegarder_modifications(modifications):
    """
    Sauvegarde groupée compatible avec l'ancienne API interne.

    Les modifications sont écrites localement puis placées
    dans la file de synchronisation GitHub.
    """
    initialiser_etat_synchronisation()

    for fichier, (
        frontmatter,
        lignes
    ) in modifications.items():
        nouveau_contenu = (
            reconstruire_contenu(
                frontmatter,
                lignes
            )
        )

        ecrire_localement(
            fichier,
            nouveau_contenu
        )

        st.session_state.quiz_pending_github[
            fichier
        ] = nouveau_contenu


# ============================================================
# QUIZ PRINCIPAL
# ============================================================

def poser_questions(
    questions_globales,
    nb_questions=1000
):
    """
    Quiz adaptatif et performant.

    La question suivante n'est tirée qu'après validation.
    Le score validé influence immédiatement le prochain tirage.
    """
    initialiser_etat_synchronisation()

    if (
        "quiz_index"
        not in st.session_state
    ):
        st.session_state.quiz_index = 0
        st.session_state.quiz_reveal = False
        st.session_state.quiz_current_question = (
            choisir_question_ponderee(
                questions_globales
            )
        )

    index = (
        st.session_state.quiz_index
    )

    if (
        index >= nb_questions
        or st.session_state
        .quiz_current_question
        is None
    ):
        st.success(
            "🎉 Révision terminée !"
        )

        # On essaie de pousser les dernières modifications.
        if (
            st.session_state
            .quiz_pending_github
        ):
            st.info(
                "Des modifications locales "
                "restent à synchroniser."
            )

            if st.button(
                "☁️ Synchroniser maintenant"
            ):
                synchroniser_github(
                    force=True
                )
                st.rerun()

        if st.button(
            "🔁 Recommencer"
        ):
            for key in [
                "quiz_index",
                "quiz_reveal",
                "quiz_current_question",
            ]:
                if key in st.session_state:
                    del st.session_state[
                        key
                    ]

            st.rerun()

        return

    q = (
        st.session_state
        .quiz_current_question
    )

    afficher_etat_synchronisation()

    question_clean = (
        nettoyer_liens_wikilinks(
            q["ligne"]
        )
    )

    question_affichee = re.sub(
        r"\s*<!--.*?-->",
        "",
        question_clean
    ).strip()

    st.caption(
        f"Question {index + 1} / "
        f"{nb_questions}"
    )

    st.markdown(
        "### ❓ Question"
    )

    st.markdown(
        question_affichee
    )

    if not st.session_state.get(
        "quiz_reveal",
        False
    ):
        if st.button(
            "👀 Voir la réponse"
        ):
            st.session_state.quiz_reveal = True
            st.rerun()

        return

    st.info(
        f"📖 Réponse : "
        f"{q['fiche_nom']}"
    )

    # Image affichée immédiatement au moment où la réponse est révélée.
    afficher_image_principale(
        q["fichier"]
    )

    st.caption(
        "Importance Culture G : "
        f"{q.get('culture_g_score', CULTURE_G_DEFAULT):g}/100"
    )

    score_courant = int(
        obtenir_score_question(q)
    )

    score = st.slider(
        "📝 Note cette question "
        "(0 = inconnu, 10 = acquis)",
        0,
        10,
        score_courant,
        key=(
            f"quiz_score_"
            f"{id_question(q)}_"
            f"{index}"
        )
    )

    if st.button(
        "✅ Valider et passer à la suivante"
    ):
        nouvelle_ligne = (
            enregistrer_score_local(
                q,
                score
            )
        )

        if nouvelle_ligne is None:
            return

        question_precedente = q

        st.session_state.quiz_index += 1
        st.session_state.quiz_reveal = False
        st.session_state.quiz_answers_since_sync += 1

        # La prochaine question est choisie AVANT tout rechargement
        # massif des fichiers.
        st.session_state.quiz_current_question = (
            choisir_question_ponderee(
                questions_globales,
                question_precedente=question_precedente
            )
        )

        # Un accès réseau n'a lieu qu'une fois toutes les N réponses.
        synchroniser_si_necessaire()

        st.rerun()

    if st.button(
        "✏️ Modifier les questions de cette fiche"
    ):
        nouvelle_ligne = (
            enregistrer_score_local(
                q,
                score
            )
        )

        if nouvelle_ligne is None:
            return

        st.session_state[
            "page"
        ] = "edition"

        st.session_state[
            "edition_fichier"
        ] = q["fichier"]

        st.stop()

    afficher_description(
        q["fichier"],
        afficher_image=False
    )


# ============================================================
# AUTRES JEUX
# ============================================================

def jeu_with_year(questions_globales):
    if "with_year_fiches" not in st.session_state:
        questions_par_fiche = {}

        for q in questions_globales:
            questions_par_fiche[
                q["fiche_nom"]
            ] = q

        fiches = list(
            questions_par_fiche.values()
        )

        random.shuffle(fiches)

        valides = []

        for q in fiches:
            contenu = lire_contenu(
                q["fichier"]
            )

            if not contenu:
                continue

            frontmatter, _ = (
                separer_frontmatter_et_contenu(
                    contenu
                )
            )

            debut = None
            fin = None
            lignes = frontmatter.splitlines()
            indices = []

            for i, ligne in enumerate(lignes):
                ligne = ligne.strip()

                if ligne.startswith("debut:"):
                    match = re.search(
                        r"debut:\s*(\d{4})",
                        ligne
                    )

                    if match:
                        debut = match.group(1)

                elif ligne.startswith("fin:"):
                    match = re.search(
                        r"fin:\s*(\d{4})",
                        ligne
                    )

                    if match:
                        fin = match.group(1)

                if re.match(
                    r"indice_\d+\s*:",
                    ligne
                ):
                    if i + 1 < len(lignes):
                        suite = (
                            lignes[i + 1]
                            .strip()
                        )

                        if suite.startswith("-"):
                            indices.append(
                                suite[1:].strip()
                            )

            if debut or fin:
                q = dict(q)
                q["debut"] = debut
                q["fin"] = fin
                q["indices"] = indices
                valides.append(q)

        st.session_state.with_year_fiches = valides
        st.session_state.with_year_index = 0
        st.session_state.show_answer = False

    fiches = (
        st.session_state
        .with_year_fiches
    )

    index = (
        st.session_state
        .with_year_index
    )

    if index >= len(fiches):
        st.success(
            "🎉 Tu as terminé toutes "
            "les fiches avec des années !"
        )

        if st.button(
            "🔁 Rejouer"
        ):
            del st.session_state.with_year_fiches
            del st.session_state.with_year_index
            del st.session_state.show_answer
            st.rerun()

        return

    q = fiches[index]

    debut = q.get("debut")
    fin = q.get("fin")
    indices = q.get(
        "indices",
        []
    )

    if debut and fin:
        periode = f"{debut}-{fin}"
    elif debut:
        periode = f"En {debut}"
    else:
        periode = f"Jusqu’en {fin}"

    theme = os.path.basename(
        os.path.dirname(
            q["fichier"]
        )
    )

    indice = (
        random.choice(indices)
        if indices
        else "Aucun indice"
    )

    st.markdown(
        "### 📅 Devine la fiche"
    )

    st.markdown(
        f"📁 **Thème** : {theme}"
    )

    st.markdown(
        f"📅 **Période** : {periode}"
    )

    st.markdown(
        f"💡 **Indice** : {indice}"
    )

    if not st.session_state.show_answer:
        if st.button(
            "👀 Révéler la réponse"
        ):
            st.session_state.show_answer = True
            st.rerun()

    else:
        st.success(
            f"✅ Réponse : "
            f"{q['fiche_nom']}"
        )

        afficher_description(
            q["fichier"]
        )

        if st.button(
            "🔜 Fiche suivante"
        ):
            st.session_state.with_year_index += 1
            st.session_state.show_answer = False
            st.rerun()


def jeu_qui_suis_je(questions_globales):
    if "qui_index" not in st.session_state:
        questions_par_fiche = {}

        for q in questions_globales:
            questions_par_fiche[
                q["fiche_nom"]
            ] = q

        fiches_valides = []

        for q in questions_par_fiche.values():
            contenu = lire_contenu(
                q["fichier"]
            )

            if not contenu:
                continue

            frontmatter, _ = (
                separer_frontmatter_et_contenu(
                    contenu
                )
            )

            lignes = (
                frontmatter.splitlines()
            )

            indices = []

            for i, ligne in enumerate(lignes):
                if re.match(
                    r"indice_\d+\s*:",
                    ligne.strip()
                ):
                    if i + 1 < len(lignes):
                        suivant = (
                            lignes[i + 1]
                            .strip()
                        )

                        if suivant.startswith("-"):
                            indices.append(
                                suivant[1:].strip()
                            )

            if indices:
                q = dict(q)
                q["indices"] = indices
                fiches_valides.append(q)

        random.shuffle(
            fiches_valides
        )

        st.session_state.qui_fiches = fiches_valides
        st.session_state.qui_index = 0
        st.session_state.qui_indice_revele = 0
        st.session_state.qui_reponse = False

    fiches = (
        st.session_state
        .qui_fiches
    )

    index = (
        st.session_state
        .qui_index
    )

    if index >= len(fiches):
        st.success(
            "🎉 Tu as terminé toutes les fiches !"
        )

        if st.button(
            "🔁 Rejouer"
        ):
            del st.session_state.qui_fiches
            del st.session_state.qui_index
            del st.session_state.qui_indice_revele
            del st.session_state.qui_reponse
            st.rerun()

        return

    q = fiches[index]
    indices = q["indices"]

    theme = os.path.basename(
        os.path.dirname(
            q["fichier"]
        )
    )

    st.markdown(
        "### 🕵️ Qui suis-je ?"
    )

    st.markdown(
        f"📁 **Thème** : {theme}"
    )

    max_i = (
        st.session_state
        .qui_indice_revele
    )

    for i in range(max_i + 1):
        if i < len(indices):
            st.markdown(
                f"🔍 **Indice {i + 1}** : "
                f"{indices[i]}"
            )

    col1, col2 = st.columns(2)

    if (
        col1.button("➕ Indice suivant")
        and max_i + 1 < len(indices)
    ):
        st.session_state.qui_indice_revele += 1
        st.rerun()

    if col2.button(
        "👀 Révéler la réponse"
    ):
        st.session_state.qui_reponse = True
        st.rerun()

    if st.session_state.qui_reponse:
        st.success(
            f"✅ Réponse : "
            f"{q['fiche_nom']}"
        )

        afficher_description(
            q["fichier"]
        )

        if st.button(
            "🔜 Fiche suivante"
        ):
            st.session_state.qui_index += 1
            st.session_state.qui_indice_revele = 0
            st.session_state.qui_reponse = False
            st.rerun()


def jeu_depuis_liens(
    questions_globales,
    fichiers_md
):
    if "liens_index" not in st.session_state:
        fiches_existantes = set(
            os.path.splitext(
                os.path.basename(f)
            )[0]
            for f in fichiers_md
        )

        fiches_par_nom = {
            q["fiche_nom"]: q
            for q in questions_globales
        }

        valides = []

        for q in fiches_par_nom.values():
            nom_fiche = (
                q["fiche_nom"]
            )

            contenu = lire_contenu(
                q["fichier"]
            )

            if not contenu:
                continue

            liens = re.findall(
                r"\[\[([^\]]+?)\]\]",
                contenu
            )

            liens_valides = sorted(
                set(
                    lien
                    for lien in liens
                    if (
                        lien != nom_fiche
                        and lien
                        in fiches_existantes
                    )
                )
            )

            if liens_valides:
                q = dict(q)
                q["liens_valides"] = (
                    liens_valides
                )
                valides.append(q)

        random.shuffle(valides)

        st.session_state.liens_fiches = valides
        st.session_state.liens_index = 0
        st.session_state.liens_reponse = False

    fiches = (
        st.session_state
        .liens_fiches
    )

    index = (
        st.session_state
        .liens_index
    )

    if index >= len(fiches):
        st.success(
            "🎉 Tu as terminé toutes les "
            "fiches avec des liens !"
        )

        if st.button(
            "🔁 Rejouer"
        ):
            del st.session_state.liens_fiches
            del st.session_state.liens_index
            del st.session_state.liens_reponse
            st.rerun()

        return

    q = fiches[index]

    theme = os.path.basename(
        os.path.dirname(
            q["fichier"]
        )
    )

    liens_valides = (
        q["liens_valides"]
    )

    st.markdown(
        "### 🔗 Devine la fiche "
        "à partir de ses liens internes"
    )

    st.markdown(
        f"📁 **Thème** : {theme}"
    )

    st.markdown(
        "#### Liens internes trouvés "
        "dans la fiche :"
    )

    for lien in liens_valides:
        st.markdown(
            f"- {lien}"
        )

    if not st.session_state.liens_reponse:
        if st.button(
            "👀 Révéler la réponse"
        ):
            st.session_state.liens_reponse = True
            st.rerun()

    else:
        st.success(
            f"✅ Réponse : "
            f"{q['fiche_nom']}"
        )

        afficher_description(
            q["fichier"]
        )

        if st.button(
            "🔜 Fiche suivante"
        ):
            st.session_state.liens_index += 1
            st.session_state.liens_reponse = False
            st.rerun()


# ============================================================
# DESCRIPTION
# ============================================================

def afficher_description(fichier, afficher_image=True):
    """
    Affiche la description depuis le fichier LOCAL.

    Par défaut, l'image principale est affichée avant la description.
    Dans la révision classique, elle est déjà affichée immédiatement
    sous la réponse, donc on peut appeler cette fonction avec
    afficher_image=False pour éviter un doublon.
    """
    try:
        contenu = lire_contenu(
            fichier
        )

        if not contenu:
            return []

        image = None

        if afficher_image:
            image = extraire_image_principale(contenu)

            if image:
                st.markdown("---")
                st.image(
                    image["url"],
                    caption=image["alt"] or None,
                    use_container_width=True
                )

        _, corps = (
            separer_frontmatter_et_contenu(
                contenu
            )
        )

        lignes = corps.split("\n")
        description = []
        capture = False

        for ligne in lignes:
            if (
                ligne.strip()
                .lower()
                .startswith(
                    "###### description"
                )
            ):
                capture = True
                continue

            if capture:
                if (
                    ligne.strip()
                    .startswith("######")
                ):
                    break

                description.append(
                    ligne
                )

        if description:
            if not image:
                st.markdown("---")

            st.markdown(
                "### 📝 Description"
            )

            for ligne in description:
                st.markdown(ligne)

    except Exception as exc:
        st.error(
            "Erreur lors du chargement "
            f"de la description : {exc}"
        )


# ============================================================
# GÉNÉRATION DE FICHE
# ============================================================

def interface_generation_fiche():
    st.title(
        "📝 Générer une fiche avec GPT"
    )

    nom = st.text_input(
        "Nom de la fiche"
    )

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
        ]
    )

    if st.button(
        "⚙️ Générer la fiche"
    ):
        if not nom.strip():
            st.warning(
                "Veuillez saisir un nom."
            )
            return

        try:
            st.write(
                "⏳ Génération en cours…"
            )

            create_fiche(
                nom,
                category
            )

            # Une nouvelle fiche vient d'être créée :
            # on invalide le cache global.
            charger_donnees.clear()

            st.success(
                f"✨ Fiche **{nom}** créée "
                f"dans la catégorie "
                f"**{category}** !"
            )

            chemin_fiche = os.path.join(
                "data",
                category,
                f"{nom}.md"
            )

            contenu_fiche = (
                lire_contenu(
                    chemin_fiche
                )
            )

            if contenu_fiche:
                st.markdown("---")
                st.subheader(
                    "📄 Fiche générée"
                )

                _, corps = (
                    separer_frontmatter_et_contenu(
                        contenu_fiche
                    )
                )

                st.markdown(corps)

            else:
                st.error(
                    "Impossible de charger "
                    "la fiche générée."
                )

        except Exception as exc:
            st.error(
                f"Erreur : {exc}"
            )


# ============================================================
# ÉDITION DES QUESTIONS
# ============================================================

def interface_edition_questions(
    fichier_force=None
):
    st.title(
        "✏️ Édition des questions d’une fiche"
    )

    if fichier_force is None:
        noms_fichiers = {
            os.path.splitext(
                os.path.basename(f)
            )[0]: f
            for f in fichiers_md
        }

        choix = st.selectbox(
            "Choisis une fiche à modifier :",
            sorted(
                noms_fichiers.keys()
            )
        )

        if not choix:
            return

        fichier = (
            noms_fichiers[choix]
        )

    else:
        fichier = fichier_force

        choix = os.path.splitext(
            os.path.basename(
                fichier_force
            )
        )[0]

        st.markdown(
            "### ✏️ Modification de la fiche : "
            f"**{choix}**"
        )

    contenu_original = (
        lire_contenu(fichier)
    )

    if not contenu_original:
        st.error(
            "Impossible de charger la fiche."
        )
        return

    frontmatter, corps = (
        separer_frontmatter_et_contenu(
            contenu_original
        )
    )

    lignes_initiales = (
        corps.split("\n")
    )

    key_lignes = (
        f"edition_lignes_{fichier}"
    )

    if (
        key_lignes
        not in st.session_state
    ):
        st.session_state[
            key_lignes
        ] = lignes_initiales

    lignes = st.session_state[
        key_lignes
    ]

    def extraire_questions_depuis_lignes(
        lignes_locales
    ):
        questions_locales = []
        in_questions = False

        for i, ligne in enumerate(
            lignes_locales
        ):
            if (
                ligne.strip()
                .lower()
                .startswith(
                    "###### questions"
                )
            ):
                in_questions = True
                continue

            if in_questions:
                if (
                    ligne.strip().startswith("#")
                    or ligne.strip()
                    .lower()
                    .startswith(
                        "###### description"
                    )
                ):
                    break

                if ligne.strip():
                    questions_locales.append({
                        "ligne": ligne,
                        "score": extraire_score(
                            ligne
                        ),
                        "ligne_index": i,
                        "fiche_nom": choix,
                    })

        return questions_locales

    questions = (
        extraire_questions_depuis_lignes(
            lignes
        )
    )

    st.subheader(
        "📝 Questions existantes"
    )

    for q in questions:
        idx = q[
            "ligne_index"
        ]

        old_line = q[
            "ligne"
        ]

        texte_sans_score = re.sub(
            r"<!--.*?-->",
            "",
            old_line
        ).strip()

        new_text = st.text_area(
            f"Question "
            f"({q['fiche_nom']} - ligne {idx})",
            texte_sans_score,
            key=(
                f"edit_{fichier}_{idx}"
            ),
            height=120
        )

        if st.button(
            f"🗑️ Supprimer (ligne {idx})",
            key=(
                f"delete_{fichier}_{idx}"
            )
        ):
            st.session_state[
                key_lignes
            ][idx] = ""

            st.rerun()

        score = q["score"]

        if (
            new_text.strip()
            != texte_sans_score
        ):
            lignes[idx] = (
                mettre_a_jour_score(
                    new_text,
                    score
                )
            )

            st.session_state[
                key_lignes
            ] = lignes

    st.markdown("---")
    st.subheader(
        "➕ Ajouter une nouvelle question"
    )

    nouvelle_question = st.text_area(
        "Nouvelle question (sans score)",
        key=f"new_q_{fichier}",
        height=120
    )

    if st.button(
        "Ajouter la question",
        key=f"add_q_{fichier}"
    ):
        if nouvelle_question.strip():
            lignes = st.session_state[
                key_lignes
            ]

            insertion_index = None

            for i, ligne in enumerate(
                lignes
            ):
                if (
                    ligne.strip()
                    .lower()
                    .startswith(
                        "###### questions"
                    )
                ):
                    insertion_index = i + 1
                    break

            if insertion_index is None:
                insertion_index = 0

            lignes.insert(
                insertion_index,
                mettre_a_jour_score(
                    nouvelle_question.strip(),
                    5
                )
            )

            st.session_state[
                key_lignes
            ] = lignes

            st.success(
                "Nouvelle question ajoutée ✔️"
            )

            st.rerun()

    st.markdown("---")

    if st.button(
        "💾 Enregistrer les modifications",
        key=f"save_{fichier}"
    ):
        lignes = st.session_state[
            key_lignes
        ]

        lignes_normalisees = (
            normaliser_bloc_questions(
                lignes
            )
        )

        nouveau_contenu = (
            reconstruire_contenu(
                frontmatter,
                lignes_normalisees
            )
        )

        # Mise à jour locale immédiate.
        ecrire_localement(
            fichier,
            nouveau_contenu
        )

        # Ici on synchronise volontairement tout de suite :
        # c'est une édition explicite de fiche, pas une simple réponse de quiz.
        success = update_file(
            path=fichier,
            content=nouveau_contenu,
            message=(
                "Edit questions in "
                f"{choix}"
            )
        )

        if success:
            # Évite qu'une ancienne version en attente ne soit
            # envoyée plus tard par-dessus cette édition.
            if (
                "quiz_pending_github"
                in st.session_state
            ):
                st.session_state.quiz_pending_github.pop(
                    fichier,
                    None
                )

            # Le nombre / l'ordre des questions peut avoir changé.
            charger_donnees.clear()

            st.success(
                f"🎉 Questions mises à jour "
                f"dans {choix} !"
            )

            del st.session_state[
                key_lignes
            ]

            st.session_state[
                "page"
            ] = "quiz"

            for key in [
                "quiz_index",
                "quiz_reveal",
                "quiz_current_question",
            ]:
                if key in st.session_state:
                    del st.session_state[
                        key
                    ]

            st.stop()

        else:
            st.error(
                "❌ Échec de l'enregistrement "
                "dans GitHub."
            )


# ============================================================
# AFFICHER UNE FICHE
# ============================================================

def interface_afficher_fiche():
    st.title(
        "📄 Afficher une fiche"
    )

    noms_fichiers = {
        os.path.splitext(
            os.path.basename(f)
        )[0]: f
        for f in fichiers_md
    }

    choix = st.selectbox(
        "Choisis une fiche à afficher :",
        sorted(
            noms_fichiers.keys()
        )
    )

    if not choix:
        return

    fichier = (
        noms_fichiers[choix]
    )

    contenu = (
        lire_contenu(fichier)
    )

    if not contenu:
        st.error(
            "Impossible de charger la fiche."
        )
        return

    _, corps = (
        separer_frontmatter_et_contenu(
            contenu
        )
    )

    # Affichage explicite de l'image principale en haut de la fiche.
    image = extraire_image_principale(contenu)

    if image:
        st.image(
            image["url"],
            caption=image["alt"] or None,
            use_container_width=True
        )

        # Évite d'afficher l'image une seconde fois via st.markdown.
        corps = supprimer_image_principale_du_corps(corps)

    st.subheader(
        "📝 Contenu complet de la fiche"
    )

    st.markdown(corps)


# ============================================================
# CARTOGRAPHIE
# ============================================================

def interface_cartographie_savoir():
    """
    Affiche une cartographie locale centrée sur une fiche.
    """
    st.title(
        "🧭 Cartographie locale du savoir"
    )

    noms_fichiers = {
        os.path.splitext(
            os.path.basename(f)
        )[0]: f
        for f in fichiers_md
    }

    choix = st.selectbox(
        "Choisis la fiche centrale :",
        sorted(
            noms_fichiers.keys()
        )
    )

    if not choix:
        return

    fichier_central = (
        noms_fichiers[choix]
    )

    contenu_central = (
        lire_contenu(
            fichier_central
        )
    )

    if not contenu_central:
        st.error(
            "Impossible de charger la fiche."
        )
        return

    _, corps = (
        separer_frontmatter_et_contenu(
            contenu_central
        )
    )

    liens_sortants = set(
        re.findall(
            r"\[\[([^\]]+?)\]\]",
            corps
        )
    )

    st.markdown(
        "### 🧵 Liens sortants"
    )

    if liens_sortants:
        st.markdown(
            ", ".join(
                f"**{lien}**"
                for lien
                in liens_sortants
            )
        )
    else:
        st.info(
            "Aucun lien sortant trouvé."
        )

    net = Network(
        height="600px",
        width="100%",
        directed=False,
        notebook=False
    )

    net.barnes_hut()

    net.add_node(
        choix,
        label=choix,
        color="#ffcc00",
        size=25
    )

    for lien in liens_sortants:
        net.add_node(
            lien,
            label=lien,
            color="#66b3ff"
        )

        net.add_edge(
            choix,
            lien
        )

    if not liens_sortants:
        st.warning(
            "Cette fiche n’a aucun "
            "lien interne ni backlink."
        )
        return

    html_path = (
        "graph_locale.html"
    )

    net.write_html(
        html_path
    )

    try:
        with open(
            html_path,
            "r",
            encoding="utf-8"
        ) as f:
            html_content = (
                f.read()
            )

        components.html(
            html_content,
            height=600,
            scrolling=True
        )

    except Exception as exc:
        st.error(
            "Erreur lors de l'affichage "
            f"du graphe : {exc}"
        )


# ============================================================
# CHARGEMENT GLOBAL
# ============================================================

fichiers_md, questions_globales = (
    charger_donnees(
        DOSSIER
    )
)
