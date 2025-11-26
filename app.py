import streamlit as st
import random
import os
from moteur_jeu import (
    lister_fichiers_md,
    extraire_questions_depuis_fichier,
    jeu_qui_suis_je,
    jeu_with_year,
    jeu_depuis_liens,
    poser_questions,
    sauvegarder_modifications
)

# 🧠 Configuration
st.set_page_config(page_title="Coffre de culture générale", page_icon="🧠")

# Répertoire des fiches Markdown
DOSSIER = "/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance"

# 📥 Chargement des fichiers et questions
fichiers_md = lister_fichiers_md(DOSSIER)
questions_globales = []
for fichier in fichiers_md:
    questions_globales.extend(extraire_questions_depuis_fichier(fichier))

# 🎛️ Barre latérale - Menu
st.sidebar.title("🎮 Menu des jeux")
choix = st.sidebar.selectbox(
    "Choisissez un mode de jeu :",
    [
        "📌 Sélectionner un jeu",
        "🕵️ Qui suis-je ?",
        "📅 Deviner à partir des années",
        "🔗 Deviner à partir des liens internes",
        "✅ Révision classique"
    ]
)

# 🎯 Lancement du jeu sélectionné
if choix == "🕵️ Qui suis-je ?":
    jeu_qui_suis_je(questions_globales)

elif choix == "📅 Deviner à partir des années":
    jeu_with_year(questions_globales)

elif choix == "🔗 Deviner à partir des liens internes":
    jeu_depuis_liens(questions_globales, fichiers_md)

elif choix == "✅ Révision classique":
    poser_questions(questions_globales, nb_questions=1000)

else:
    st.title("🧠 Coffre de culture générale")
    st.markdown("Bienvenue dans ton coffre interactif basé sur tes fiches Obsidian.")
    st.markdown("Choisis un mode de jeu dans le menu à gauche pour commencer.")