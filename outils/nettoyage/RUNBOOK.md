# Mode opératoire — nettoyage autonome du coffre Culture Max (CM-003)

Ce document guide une session Claude **sans personne pour répondre**. Il fait foi pour chaque lot.
Le Product Owner (Emmanuel) a délégué le nettoyage le 23/11/2026 : agir seul, ne remonter que les vrais doutes.

## Règles non négociables

1. Ne jamais pousser sur `main`, ne jamais fusionner, ne jamais supprimer de fichier ni de question.
   Une question écartée ou remplacée est **archivée** (section `###### Archives questions`) par `appliquer.py`.
2. Travailler uniquement sur la branche `cm003/nettoyage` du dépôt `ManuLaCastagne/mon-projet`.
   L'outillage et le journal vivent sur la branche `cm003/outillage`, dossier `outils/nettoyage/`.
3. Si quelque chose est inattendu (conflit, test qui échoue, branche absente, fiche modifiée par le PO,
   audit incohérent), **s'arrêter**, ne rien pousser, et laisser un commentaire sur la demande de fusion.
4. Ne jamais inventer un fait. En cas de doute non levé par une source web, la question n'est **pas**
   modifiée : elle part dans la liste « Doutes pour le PO » du commentaire de lot.

## Règles de rédaction d'une question

- Le jeu affiche **le nom de la fiche** comme réponse : la question doit avoir exactement cette réponse.
- La question ne contient ni ce nom, ni un alias, ni un indice évident (mot distinctif du titre).
- Garder les liens Obsidian `[[...]]` sur les personnes, œuvres, lieux (ils nourrissent le graphe).
  Ne jamais lier la réponse. Pas de lien vers un début de question.
- Une question = un fait précis et vérifiable, formulé comme en jeu télévisé, en français correct.
  Pas de tournures creuses (« emblématique », « connu pour », « souvent cité »…).
- Les questions d'une même fiche portent sur **des faits différents**.
- Pertinence (définition du PO) : bien posée et apporte une connaissance utile, entre le grand public
  et l'anecdote obscure.
- Verdicts : `garder` (exacte, claire, utile) · `reecrire` (juste mais mal posée, vague, cite la réponse)
  · `corriger` (fausse : la remplacer par une question juste ayant la même réponse) · `ecarter` (incohérente
  ou doublon sans fait récupérable ; elle sera archivée).

## Déroulé d'un lot

1. Préparer l'espace :
   - `add_repo` ManuLaCastagne/mon-projet en accès `push`, puis cloner (profondeur 1) dans `/home/claude/mon-projet`.
   - Récupérer les deux branches : `git fetch --depth=5 origin cm003/nettoyage cm003/outillage`.
   - `git worktree add /home/claude/outillage origin/cm003/outillage` ; se placer sur `cm003/nettoyage`.
   - Vérifier qu'aucune demande de fusion n'a été fusionnée entre-temps de façon à créer un conflit ;
     si `main` a avancé, `git merge origin/main` sur `cm003/nettoyage` (s'arrêter si conflit).
2. Auditer et sélectionner (O = /home/claude/outillage/outils/nettoyage) :
   - `python3 -I $O/audit_qualite.py data /tmp/audit`
   - `python3 -I $O/selectionner.py /tmp/audit/cm001_questions.csv $O/journal.json 100 /tmp/lot.json`
3. Pour chaque question de `/tmp/lot.json`, décider et rédiger dans `/tmp/propositions.json`
   (`{"1": [verdict, nouvelle_question, raison, source_url], ...}`, numéros = rang dans le lot à partir de 1).
   Faire une recherche web pour tout fait précis dont la certitude n'est pas totale (dates, récompenses,
   rôles, titres français). Lire les autres questions de la fiche avant de réécrire.
4. Contrôles automatiques : `python3 -I $O/preparer_lot.py /tmp/lot.json /tmp/propositions.json data /tmp/lot_final.json`
   → corriger jusqu'à « 0 problème ».
5. QA indépendante : lancer un agent séparé (outil Agent) sur au moins 15 questions dont toutes les
   `corriger` si ≤ 8, sinon 8 tirées au hasard + 7 réécritures. Consigne : vérifier par sources web,
   verdict OK / ERREUR / DOUTE par question. Corriger les ERREUR ; un DOUTE non levé → verdict `garder`
   pour cette question et ajout à la liste des doutes. Refaire l'étape 4.
6. Appliquer et vérifier :
   - `python3 -I $O/appliquer.py /tmp/lot_final.json data` (doit finir sans assertion)
   - `cd $O && python3 -m pytest -q -p no:cacheprovider` (tous les tests passent)
   - relancer l'audit et vérifier que le nombre de questions jouables a baissé exactement du nombre d'archivées.
7. Publier :
   - commit sur `cm003/nettoyage` (message : `CM-003 lot N : …`, résumé des verdicts et de la QA, lignes
     d'attribution Co-Authored-By et Claude-Session), puis `git -c push.negotiate=true push origin cm003/nettoyage`.
   - `python3 -I $O/journaliser.py $O/journal.json /tmp/lot_final.json N "<résumé QA>"`, commit et push sur
     `cm003/outillage` depuis le worktree.
   - Demande de fusion : s'il n'en existe pas d'ouverte pour `cm003/nettoyage`, la créer via
     `gh api repos/ManuLaCastagne/mon-projet/pulls` (base `main`) ; sinon ajouter un commentaire
     (`gh api repos/ManuLaCastagne/mon-projet/issues/<n>/comments`) avec : lot, fiches traitées, verdicts,
     QA, 3 exemples de corrections notables, et la liste « Doutes pour le PO » (vide si aucun).
8. Si le temps le permet, enchaîner un deuxième lot (étapes 2 à 7). Maximum 3 lots par exécution.
