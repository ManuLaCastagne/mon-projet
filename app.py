import streamlit as st
import random
import os
from github_utils import read_file, update_file, get_file_sha
from moteur_jeu import (
    lister_fichiers_md,
    extraire_questions_depuis_fichier,
    jeu_qui_suis_je,
    jeu_with_year,
    jeu_depuis_liens,
    poser_questions,
    interface_generation_fiche,
    sauvegarder_modifications,
    interface_edition_questions,
    interface_afficher_fiche,
    interface_cartographie_savoir
)

# 🧠 Configuration
st.set_page_config(page_title="Coffre de culture générale", page_icon="🧠")
# Répertoire des fiches Markdown
DOSSIER = "data"

# 📥 Chargement des fichiers et questions
@st.cache_data
def charger_questions(DOSSIER):
    fichiers = lister_fichiers_md(DOSSIER)
    questions = []
    for fichier in fichiers:
        questions.extend(extraire_questions_depuis_fichier(fichier))
    return questions, fichiers

questions_globales, fichiers_md = charger_questions(DOSSIER)

# 🎛️ Barre latérale - Menu
st.sidebar.title("🎮 Menu des jeux")
choix = st.sidebar.selectbox(
    "Choisissez un mode de jeu :",
    [
        "📌 Sélectionner un jeu",
        "✅ Révision classique",
        "🤖 Générer une fiche",
        "📝 Afficher une fiche",
        "❓ Éditer les questions d’une fiche",
        "🗺️ Cartographie du savoir",
        "🕵️ Qui suis-je ?",
        "📅 Deviner à partir des années",
        "🔗 Deviner à partir des liens internes"
    ]
)

# 🔀 Gestion des pages internes (redirigées depuis poser_questions)
if st.session_state.get("page") == "edition" and (choix == "✅ Révision classique" or choix == "❓ Éditer les questions d’une fiche"):
    interface_edition_questions(st.session_state.get("edition_fichier"))
    st.stop()

# 🔀 Gestion des pages internes (redirigées depuis poser_questions)
if st.session_state.get("page") == "quiz" and (choix == "✅ Révision classique" or choix == "❓ Éditer les questions d’une fiche"):
    poser_questions(questions_globales, nb_questions=1000)
    st.stop()

# 🎯 Lancement du jeu sélectionné
if choix == "🕵️ Qui suis-je ?":
    jeu_qui_suis_je(questions_globales)

elif choix == "✅ Révision classique":
    poser_questions(questions_globales, nb_questions=1000)

elif choix == "📝 Afficher une fiche":
    interface_afficher_fiche()

elif choix == "❓ Éditer les questions d’une fiche":
    interface_edition_questions()

elif choix == "🤖 Générer une fiche":
    interface_generation_fiche()

elif choix == "🗺️ Cartographie du savoir":
    interface_cartographie_savoir()

elif choix == "📅 Deviner à partir des années":
    jeu_with_year(questions_globales)

elif choix == "🔗 Deviner à partir des liens internes":
    jeu_depuis_liens(questions_globales, fichiers_md)

else:
    st.title("🧠 Coffre de culture générale")
    st.markdown("Bienvenue dans ton coffre interactif basé sur tes fiches Obsidian.")
    st.markdown("Choisis un mode de jeu dans le menu à gauche pour commencer.")