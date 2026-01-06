import streamlit as st
import random
import time
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

import time

# 📥 Chargement initial (optionnellement caché)
@st.cache_data
def charger_questions_initial(dossier):
    fichiers = lister_fichiers_md(dossier)
    questions_par_fichier = {}
    for fichier in fichiers:
        questions_par_fichier[fichier] = extraire_questions_depuis_fichier(fichier)
    return questions_par_fichier, fichiers

def aplatir_questions(questions_par_fichier: dict) -> list:
    questions = []
    for qs in questions_par_fichier.values():
        questions.extend(qs)
    return questions

# --- Init session ---
if "t0" not in st.session_state:
    st.session_state.t0 = time.time()

if "questions_par_fichier" not in st.session_state:
    # premier run de la session : on charge tout
    qpf, fichiers = charger_questions_initial(DOSSIER)
    st.session_state.questions_par_fichier = qpf
    st.session_state.fichiers_md = fichiers

# --- Delta reload : uniquement fichiers modifiés / ajoutés / supprimés ---
fichiers_actuels = lister_fichiers_md(DOSSIER)
set_actuel = set(fichiers_actuels)
set_connu = set(st.session_state.fichiers_md)

# 1) Fichiers supprimés
fichiers_supprimes = sorted(set_connu - set_actuel)
for f in fichiers_supprimes:
    st.session_state.questions_par_fichier.pop(f, None)

# 2) Fichiers ajoutés
fichiers_ajoutes = sorted(set_actuel - set_connu)
for f in fichiers_ajoutes:
    st.session_state.questions_par_fichier[f] = extraire_questions_depuis_fichier(f)

# 3) Fichiers modifiés après t0
t0 = st.session_state.t0
fichiers_modifies = []
for f in fichiers_actuels:
    try:
        if os.path.getmtime(f) > t0:
            fichiers_modifies.append(f)
    except FileNotFoundError:
        # peut arriver si fichier supprimé entre listage et stat
        pass

for f in fichiers_modifies:
    st.session_state.questions_par_fichier[f] = extraire_questions_depuis_fichier(f)

# Mise à jour des références et du "dernier point de contrôle"
st.session_state.fichiers_md = fichiers_actuels
st.session_state.t0 = time.time()

# --- Variables utilisées par le reste de ton app ---
questions_globales = aplatir_questions(st.session_state.questions_par_fichier)
fichiers_md = st.session_state.fichiers_md

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

if st.button("🔄 Forcer le rechargement"):
    st.cache_data.clear()
    st.session_state.pop("questions_par_fichier", None)
    st.session_state.pop("fichiers_md", None)
    st.session_state.t0 = time.time()
    st.rerun()

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