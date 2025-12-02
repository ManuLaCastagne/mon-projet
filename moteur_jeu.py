import os
import re
import random
import math
from collections import defaultdict
import streamlit as st
from scriptMarkdown import create_fiche

alpha = 1.5

def lister_fichiers_md(dossier):
    fichiers_md = []
    for racine, _, fichiers in os.walk(dossier):
        for f in fichiers:
            if f.endswith('.md'):
                fichiers_md.append(os.path.join(racine, f))
    return fichiers_md

def nettoyer_liens_wikilinks(texte):
    return re.sub(r'\[\[([^\]]+?)\]\]', r'\1', texte)

def separer_frontmatter_et_contenu(contenu):
    if contenu.startswith('---'):
        parts = contenu.split('---', 2)
        if len(parts) == 3:
            return '---' + parts[1] + '---', parts[2]
    return '', contenu

def extraire_questions_depuis_fichier(fichier):
    with open(fichier, 'r', encoding='utf-8') as f:
        contenu = f.read()

    frontmatter, corps = separer_frontmatter_et_contenu(contenu)
    lignes = corps.split('\n')
    questions = []

    in_questions = False
    for i, ligne in enumerate(lignes):
        if ligne.strip().lower().startswith("###### questions"):
            in_questions = True
            continue
        if in_questions:
            if ligne.strip().startswith('#') or ligne.strip().lower().startswith('###### description'):
                break
            if ligne.strip():
                score = extraire_score(ligne)
                questions.append({
                    'ligne': ligne,
                    'score': score,
                    'ligne_index': i,
                    'fichier': fichier,
                    'fiche_nom': os.path.splitext(os.path.basename(fichier))[0],
                    'lignes': lignes,
                    'frontmatter': frontmatter
                })

    return questions

def extraire_score(ligne):
    match = re.search(r'<!--\s*score\s*:\s*(\d+)\s*-->', ligne)
    return int(match.group(1)) if match else 5

def mettre_a_jour_score(ligne, score):
    ligne_sans_score = re.sub(r'\s*<!--\s*score\s*:\s*\d+\s*-->', '', ligne).strip()
    return ligne_sans_score + f' <!-- score: {score} -->'

def poser_questions(questions_globales, nb_questions=1000):
    if "quiz_index" not in st.session_state:
        st.session_state.quiz_index = 0
        st.session_state.quiz_questions = []
        st.session_state.quiz_modifications = defaultdict(list)

        poids = [math.exp(-alpha * q['score']) for q in questions_globales]
        total = sum(poids)
        if total == 0:
            poids = [1] * len(questions_globales)
            total = len(questions_globales)
        probabilites = [p / total for p in poids]

        st.session_state.quiz_questions = random.choices(
            questions_globales, weights=probabilites, k=nb_questions
        )

    questions = st.session_state.quiz_questions
    index = st.session_state.quiz_index

    if index >= len(questions):
        st.success("🎉 Révision terminée !")
        if st.button("🔁 Recommencer"):
            del st.session_state.quiz_index
            del st.session_state.quiz_questions
            del st.session_state.quiz_modifications
            st.rerun()
        return

    q = questions[index]
    question_clean = re.sub(r'\[\[([^\]]+?)\]\]', r'\1', q['ligne'])
    question_affichee = re.sub(r'\s*<!--.*?-->', '', question_clean).strip()

    st.markdown("### ❓ Question")
    st.markdown(question_affichee)

    if st.button("👀 Voir la réponse"):
        st.session_state.quiz_reveal = True
        st.rerun()

    if st.session_state.get("quiz_reveal"):
        st.info(f"📖 Réponse : {q['fiche_nom']}")
        score = st.slider("📝 Note cette question (0 = inconnu, 10 = acquis)", 0, 10, q['score'])
        afficher_description(q['fichier'])
        if st.button("✅ Valider et passer à la suivante"):
            nouvelle_ligne = mettre_a_jour_score(q['ligne'], score)
            q['ligne'] = nouvelle_ligne
            q['lignes'][q['ligne_index']] = nouvelle_ligne
            q['score'] = score

            st.session_state.quiz_modifications[q['fichier']] = (q['frontmatter'], q['lignes'])
            sauvegarder_modifications({q['fichier']: (q['frontmatter'], q['lignes'])})

            st.session_state.quiz_index += 1
            st.session_state.quiz_reveal = False
            st.rerun()

def sauvegarder_modifications(modifications):
    for fichier, (frontmatter, lignes) in modifications.items():
        nouveau_contenu = frontmatter + '\n' + '\n'.join(lignes)
        with open(fichier, 'w', encoding='utf-8') as f:
            f.write(nouveau_contenu)
        st.toast(f"💾 {os.path.basename(fichier)} sauvegardé.")

def mettre_a_jour_score(ligne, score):
    ligne_sans_score = re.sub(r'\s*<!--\s*score\s*:\s*\d+\s*-->', '', ligne).strip()
    return ligne_sans_score + f' <!-- score: {score} -->'

def jeu_with_year(questions_globales):
    if "with_year_fiches" not in st.session_state:
        questions_par_fiche = {}
        for q in questions_globales:
            questions_par_fiche[q['fiche_nom']] = q
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
                    match = re.search(r'debut:\s*(\d{4})', ligne)
                    if match:
                        debut = match.group(1)
                elif ligne.startswith("fin:"):
                    match = re.search(r'fin:\s*(\d{4})', ligne)
                    if match:
                        fin = match.group(1)
                if re.match(r'indice_\d+\s*:', ligne):
                    if i + 1 < len(lignes):
                        suite = lignes[i + 1].strip()
                        if suite.startswith('-'):
                            indices.append(suite[1:].strip())
            if debut or fin:
                q['debut'] = debut
                q['fin'] = fin
                q['indices'] = indices
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
    debut = q.get('debut')
    fin = q.get('fin')
    indices = q.get('indices', [])

    periode = f"{debut}-{fin}" if debut and fin else f"En {debut}" if debut else f"Jusqu’en {fin}"
    theme = os.path.basename(os.path.dirname(q['fichier']))
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

        afficher_description(q['fichier'])

        if st.button("🔜 Fiche suivante"):
            st.session_state.with_year_index += 1
            st.session_state.show_answer = False
            st.rerun()

def jeu_qui_suis_je(questions_globales):
    if "qui_index" not in st.session_state:
        questions_par_fiche = {}
        for q in questions_globales:
            questions_par_fiche[q['fiche_nom']] = q

        fiches_valides = []
        for q in questions_par_fiche.values():
            frontmatter = q.get('frontmatter', '')
            lignes = frontmatter.splitlines()
            indices = []
            for i, ligne in enumerate(lignes):
                if re.match(r'indice_\d+\s*:', ligne.strip()):
                    if i + 1 < len(lignes):
                        suivant = lignes[i + 1].strip()
                        if suivant.startswith('-'):
                            indices.append(suivant[1:].strip())
            if indices:
                q['indices'] = indices
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
    indices = q['indices']
    theme = os.path.basename(os.path.dirname(q['fichier']))

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
        afficher_description(q['fichier'])
        if st.button("🔜 Fiche suivante"):
            st.session_state.qui_index += 1
            st.session_state.qui_indice_revele = 0
            st.session_state.qui_reponse = False
            st.rerun()

def jeu_depuis_liens(questions_globales, fichiers_md):
    if "liens_index" not in st.session_state:
        fiches_existantes = set(os.path.splitext(os.path.basename(f))[0] for f in fichiers_md)
        fiches_par_nom = {q['fiche_nom']: q for q in questions_globales}

        valides = []
        for q in fiches_par_nom.values():
            nom_fiche = q['fiche_nom']
            with open(q['fichier'], 'r', encoding='utf-8') as f:
                contenu = f.read()
            liens = re.findall(r'\[\[([^\]]+?)\]\]', contenu)
            liens_valides = sorted(set(l for l in liens if l != nom_fiche and l in fiches_existantes))
            if liens_valides:
                q['liens_valides'] = liens_valides
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
    theme = os.path.basename(os.path.dirname(q['fichier']))
    liens_valides = q['liens_valides']

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
        afficher_description(q['fichier'])
        if st.button("🔜 Fiche suivante"):
            st.session_state.liens_index += 1
            st.session_state.liens_reponse = False
            st.rerun()

def afficher_description(fichier):
    try:
        with open(fichier, 'r', encoding='utf-8') as f:
            contenu = f.read()
        _, corps = separer_frontmatter_et_contenu(contenu)
        lignes = corps.split('\n')
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
    except Exception as e:
        st.error("Erreur lors du chargement de la description.")

def interface_generation_fiche():
    st.title("📝 Générer une fiche avec GPT")

    nom = st.text_input("Nom de la fiche")
    category = st.selectbox(
        "Catégorie",
        [
            "Anatomie", "Animaux", "Architecture", "Art", "Botanique", "Cinéma",
            "Gastronomie", "Géographie", "Histoire", "Littérature", "Musique",
            "Mythologie", "Religion", "Sciences", "Sport", "Télévision",
            "Vocabulaire"
        ]
    )

    if st.button("⚙️ Générer la fiche"):
        if not nom.strip():
            st.warning("Veuillez saisir un nom.")
            return

        try:
            st.write("⏳ Génération en cours…")

            # Appelle ton code existant
            create_fiche(nom, category)

            st.success(f"✨ Fiche **{nom}** créée dans la catégorie **{category}** !")
        except Exception as e:
            st.error(f"Erreur : {e}")

DOSSIER = "data"
fichiers_md = lister_fichiers_md(DOSSIER)

# Rassembler toutes les questions de tous les fichiers
questions_globales = []
for fichier in fichiers_md:
    questions_globales.extend(extraire_questions_depuis_fichier(fichier))
    