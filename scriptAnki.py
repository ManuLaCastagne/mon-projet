import os
import re
import random
from collections import defaultdict
import math
alpha = 0.5

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

def poser_questions(questions_globales, nb_questions=10):
    poids = [math.exp(-alpha * q['score']) for q in questions_globales]
    total = sum(poids)
    if total == 0:
        poids = [1] * len(questions_globales)
        total = len(questions_globales)
    probabilites = [p / total for p in poids]

    modifications_par_fichier = defaultdict(list)

    for _ in range(nb_questions):
        q = random.choices(questions_globales, weights=probabilites, k=1)[0]

        question_clean = nettoyer_liens_wikilinks(q['ligne'])
        question_affichee = re.sub(r'\s*<!--.*?-->', '', question_clean).strip()

        print('\n' + '-' * 40)
        print(f"Question : {question_affichee}")
        input("Appuyez sur Entrée pour voir la réponse…")
        print(f"Réponse : {q['fiche_nom']}")
        # Interprétation de la commande
        cmd = input("👉 Que veux-tu faire ? ").strip().lower()

        if cmd == "o":
            new_score = min(q['score'] + 1, 10)
        elif cmd == "n":
            new_score = max(q['score'] - 1, 0)
        elif cmd.startswith("+") or cmd.startswith("-"):
            try:
                delta = int(cmd)
                new_score = max(0, min(10, q['score'] + delta))
            except ValueError:
                print("❌ Entrée invalide. Score inchangé.")
                new_score = q['score']
        else:
            try:
                new_score = max(0, min(10, int(cmd)))
            except ValueError:
                print("❌ Score invalide. Score inchangé.")
                new_score = q['score']

        nouvelle_ligne = mettre_a_jour_score(q['ligne'], new_score)
        q['ligne'] = nouvelle_ligne  # on met à jour le texte dans la question
        q['lignes'][q['ligne_index']] = nouvelle_ligne  # et dans le fichier

        modifications_par_fichier[q['fichier']] = (q['frontmatter'], q['lignes'])

        # Mise à jour du score local pour recalculer les pondérations
        q['score'] = new_score
        poids = [math.exp(-alpha * q['score']) for q in questions_globales]
        total = sum(poids)
        probabilites = [p / total for p in poids]

    return modifications_par_fichier

def sauvegarder_modifications(modifications):
    for fichier, (frontmatter, lignes) in modifications.items():
        # Retirer les lignes marquées pour suppression
        lignes_nettoyees = []
        for i, ligne in enumerate(lignes):
            # Est-ce que cette ligne a été marquée comme à supprimer ?
            supprimer = False
            for q in questions_globales:
                if (
                    q.get('supprimer') and
                    q['fichier'] == fichier and
                    q['ligne_index'] == i
                ):
                    supprimer = True
                    break
            if not supprimer:
                lignes_nettoyees.append(ligne)
        nouveau_contenu = frontmatter + '\n' + '\n'.join(lignes_nettoyees)
        with open(fichier, 'w', encoding='utf-8') as f:
            f.write(nouveau_contenu)
        print(f"💾 {os.path.basename(fichier)} mis à jour.")

# ---- Programme principal ----

dossier =  "/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance"
fichiers_md = lister_fichiers_md(dossier)

# Rassembler toutes les questions de tous les fichiers
questions_globales = []
for fichier in fichiers_md:
    questions_globales.extend(extraire_questions_depuis_fichier(fichier))

if not questions_globales:
    print("Aucune question trouvée.")
else:
    modifications = poser_questions(questions_globales, nb_questions=3)
    sauvegarder_modifications(modifications)
