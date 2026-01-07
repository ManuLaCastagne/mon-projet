from github_utils import read_file, update_file, write_content_to_github
from scriptCarte import ajoute_latitude_et_longitude_as_an_attribute, fiche_to_carte
from scriptSpotify import add_uri_to_playlist
from scriptSpotify import get_artist_and_album_image_urls
from scriptSpotify import return_uri_from_titre
import os
from openai import OpenAI
import random
import re
import requests
from collections import defaultdict
import unicodedata
import os
import random
import pyperclip
import argparse
import streamlit as st
from html2image import Html2Image

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
output_dir = "data"

### Prompts bouclés et améliorés avec GPT
prompt_description = """
    Je veux un paragraphe descriptif sur “NOM_FICHE” (catégorie : NOM_CATEGORY) composé de quatre phrases distinctes.

Toutes les phrases doivent être séparées par exactement deux sauts de ligne.

Tous les noms propres, lieux, institutions, concepts historiques, œuvres ou événements mentionnés doivent être entourés de [[ ]] afin de favoriser les connexions dans [[Obsidian]].

Le texte doit inclure obligatoirement :
– une ville de naissance clairement identifiée,
– au moins un fait étonnant, peu connu, record ou statistique marquante concernant “NOM_FICHE”, exploitable comme base de question de quiz de culture générale.

Les informations utilisées doivent être exactes à la date actuelle.
Si un élément est susceptible d’avoir changé avec l’actualité (fonction, statut, titre, record récent, situation en cours), utilise la version la plus récente connue.

Si une information est devenue incorrecte, obsolète ou incertaine, ne l’utilise pas et remplace-la par un fait vérifié, stable ou clairement daté.

Donne des années exactes, des chiffres précis et des éléments factuels susceptibles d’être posés dans des jeux télévisés français.

Le ton doit être informatif, neutre et encyclopédique, sans adjectifs inutiles ni formules promotionnelles.

Évite toute formulation tautologique ou évidente (ne pas reformuler le titre ou la catégorie comme information).

Avant de produire le texte, vérifie mentalement que chacune des phrases serait encore considérée comme correcte par un jury de jeu télévisé aujourd’hui."""

prompt_description_animaux = """
Je veux une description encyclopédique de "NOM_FICHE" (catégorie : NOM_CATEGORY) composée de exactement quatre phrases distinctes.

Chaque phrase doit être séparée par exactement deux sauts de ligne.

Tous les noms propres, termes scientifiques, lieux, concepts culturels ou symboliques doivent être entourés de [[ ]] afin de favoriser les connexions dans [[Obsidian]].

La description doit obligatoirement inclure, répartis sur les quatre phrases :
– le type d’animal,
– le nom scientifique binominal,
– au moins un nom vernaculaire,
– l’ordre zoologique,
– la famille zoologique,
– la région géographique naturelle principale,
– un rôle culturel, symbolique ou mythologique attesté.

Si pertinent, inclue un fait étonnant, rare, peu connu ou record concernant "NOM_FICHE", exploitable comme base de question de quiz de culture générale.

Donne des informations factuelles, stables et vérifiables, avec des éléments susceptibles d’être posés dans des jeux télévisés français.

N’utilise aucune liste, aucune puce, aucune explication hors texte descriptif.
"""
prompt_description_botanique = """
Je veux une description encyclopédique de "NOM_FICHE" (catégorie : NOM_CATEGORY) composée de exactement quatre phrases distinctes.

Chaque phrase doit être séparée par exactement deux sauts de ligne.

Tous les noms propres, termes botaniques, lieux géographiques, appellations alternatives et usages culturels doivent être entourés de [[ ]] afin de favoriser les connexions dans [[Obsidian]].

La description doit obligatoirement inclure, répartis sur les quatre phrases :
– la famille botanique scientifique,
– la région géographique d’origine,
– une caractéristique morphologique distinctive,
– la période ou saison principale de floraison ou de fructification,
– au moins une autre appellation vernaculaire,
– un exemple d’utilisation humaine documentée.

Inclue au moins un fait étonnant, peu connu, historique ou scientifique concernant "NOM_FICHE", exploitable comme base de question de quiz de culture générale.

Donne des informations factuelles, stables et vérifiables, compatibles avec des jeux télévisés français.

N’utilise aucune liste, aucune puce, aucune phrase de remplissage.
"""
prompt_description_vocabulaire = """
Je veux une description lexicale et culturelle du mot "NOM_FICHE" composée de exactement quatre phrases distinctes.

Chaque phrase doit être séparée par exactement un saut de ligne.

Tous les noms propres, concepts, œuvres, événements historiques ou références culturelles doivent être entourés de [[ ]] afin de favoriser les connexions dans [[Obsidian]].

La description doit inclure :
– une définition claire et précise du mot,
– son domaine d’usage principal,
– un contexte historique, culturel ou linguistique pertinent,
– une anecdote, un usage notable ou une information surprenante exploitable en quiz de culture générale.

Le ton doit être neutre, informatif et encyclopédique, sans effet stylistique inutile.

N’utilise aucune liste, aucune puce, aucune explication hors texte descriptif.
"""

prompt_questions = """
Je veux trois questions de culture générale portant sur trois faits surprenants distincts dont la réponse est “NOM_FICHE” (catégorie : NOM_CATEGORY).

Interdiction absolue d’inclure le nom NOM_FICHE, toute variante de ce nom, son prénom, son nom de famille, un surnom, un titre officiel, une fonction directement identifiable ou toute formulation permettant de déduire immédiatement la réponse.

Les questions doivent être formulées de manière indirecte, sur le modèle des jeux télévisés français (description factuelle, événement précis, record, action datée, contexte historique clairement identifiable), et rester compréhensibles sans révéler l’identité recherchée.

Les trois questions doivent être différentes,
Les trois questions ne doivent pas être numérotées,
Fais un saut de ligne entre chaque question,
Je ne veux aucun autre mot, phrase explicative, ponctuation hors question ou emoji en dehors des questions elles-mêmes.

Tous les noms propres, lieux, concepts historiques, événements, œuvres ou institutions mentionnés doivent être entourés de [[ ]] afin de favoriser les connexions dans [[Obsidian]].

Les informations utilisées doivent être exactes à la date actuelle.
Si un fait est susceptible d’avoir changé avec l’actualité (fonction en cours, statut, classement, record récent, situation politique ou scientifique), utilise la version la plus récente connue.

Si une information est devenue incorrecte, obsolète ou incertaine, ne génère pas la question et remplace-la par un autre fait vérifié.

Donne des années exactes, des chiffres précis et des éléments factuels susceptibles d’être posés dans des quiz de jeux télévisés français.

Privilégie les faits historiques, scientifiques, juridiques ou culturels solidement établis, ou les événements récents clairement datés.

Avant de produire les questions, vérifie mentalement que chacune d’elles serait encore considérée comme correcte par un jury de jeu télévisé aujourd’hui.
Toute question risquant d’être invalidée par un changement récent doit être reformulée ou remplacée.
"""

prompt_questions_vocabulaire = """
Je veux que tu me poses exactement trois questions de culture générale dont la réponse est le mot "NOM_FICHE".

Interdiction absolue d’utiliser le mot "NOM_FICHE", ses dérivés morphologiques, ses synonymes évidents ou toute formulation permettant de deviner directement la réponse.

Les questions doivent être formulées de manière indirecte, comme dans un jeu télévisé français, en s’appuyant sur :
– la définition du mot,
– son domaine d’usage,
– un contexte historique, culturel ou linguistique,
– une anecdote ou un usage notable.

Les trois questions doivent être différentes.
Les trois questions ne doivent pas être numérotées.
Fais exactement un saut de ligne entre chaque question.
Je ne veux aucun autre mot, commentaire ou emoji en dehors des questions elles-mêmes.

Tous les noms propres, concepts, œuvres, événements ou références culturelles mentionnés doivent être entourés de [[ ]] afin de favoriser les connexions dans [[Obsidian]].

Donne des informations factuelles, stables et exploitables dans des quiz de jeux télévisés français.
"""

prompt_indices_debut = """
    Thème : NOM_FICHE (NOM_CATEGORY)

    Donne-moi exactement six éléments (composés de noms propres ou d'un ou plusieurs mots) séparés uniquement par une barre verticale (|).
    Ces éléments doivent à eux seuls me permettre de deviner le thème dont il est question.
    Le format doit être strictement : 
    """
prompt_indices_fin = """
Chaque indice doit être utile à l’identification.
Aucun indice ne doit être redondant avec un autre.
Aucun indice ne doit être purement générique ou applicable à de nombreux thèmes.
Ne mets absolument rien avant ou après la liste.
Aucune explication.
Aucun exemple.
Aucun commentaire.
Uniquement la liste finale au format demandé.
"""

indices_generic = """Lieu géographique précis associé à NOM_FICHE | Période d’activité principale de NOM_FICHE au format Années_YYYY ou Années_-YYYY | Siècle correspondant au format Ve ou Ve_avant_JC | Domaine ou type d’activité caractéristique de NOM_FICHE | Élément factuel distinctif lié à NOM_FICHE | Notion ou concept fortement associé à NOM_FICHE """
prompt_indices = prompt_indices_debut + indices_generic + prompt_indices_fin

indices_animaux = """Type zoologique général de NOM_FICHE | Nom scientifique binominal de NOM_FICHE | Ordre zoologique scientifique de NOM_FICHE | Zone géographique naturelle principale de NOM_FICHE | Caractéristique biologique remarquable de NOM_FICHE | Usage symbolique ou culturel attesté de NOM_FICHE"""
prompt_indices_animaux = prompt_indices_debut + indices_animaux + prompt_indices_fin

indices_botanique = """Famille botanique scientifique de NOM_FICHE | Région géographique d’origine de NOM_FICHE | Caractéristique morphologique distinctive de NOM_FICHE | Période de floraison ou de fructification principale de NOM_FICHE | Nom vernaculaire ou appellation alternative de NOM_FICHE | Utilisation humaine documentée de NOM_FICHE"""
prompt_indices_botanique = prompt_indices_debut + indices_botanique + prompt_indices_fin

prompt_tags_debut = """
Je veux que tu me retournes exactement les éléments demandés concernant "NOM_FICHE" (catégorie : NOM_CATEGORY).

Les éléments doivent être fournis dans l’ordre strict indiqué ci-dessous
et être séparés uniquement par une barre verticale (|),
sans retour à la ligne, sans espace superflu, sans ponctuation supplémentaire.

Format strict attendu :
"""
prompt_tags_fin = """
Si un élément n’est pas applicable, indique exactement : None

Ne mets absolument rien avant ou après la liste.
Aucune phrase explicative.
Aucun commentaire.
Aucun exemple.
Uniquement la liste finale au format demandé.
"""
tags_generic = """Lieu géographique principal associé à NOM_FICHE | Décennie d’activité principale de NOM_FICHE au format Années_YYYY ou Années_-YYYY | Siècle correspondant au format Ve ou Ve_avant_JC"""
prompt_tags = prompt_tags_debut + tags_generic + prompt_tags_fin

tags_geography = """Région de NOM_FICHE | Pays de NOM_FICHE | Département de NOM_FICHE"""
prompt_tags_geography = prompt_tags_debut + tags_geography + prompt_tags_fin
prompt_tag_vocabulaire = """
Je veux que tu attribues une unique catégorie au mot "NOM_FICHE" en fonction de sa définition principale.

Choisis obligatoirement UNE SEULE catégorie parmi la liste suivante :
Anatomie
Animaux
Architecture
Art
Botanique
Cinéma
Gastronomie
Géographie
Histoire
Littérature
Musique
Mythologie
Religion
Sciences
Sport
Télévision

Ne retourne strictement que le nom exact de la catégorie choisie,
sans guillemets, sans ponctuation, sans commentaire, sans autre mot.
"""

prompt_annee_debut = """
Je veux que tu me retournes une seule valeur correspondant à "NOM_FICHE" (catégorie : NOM_CATEGORY).

Si "NOM_FICHE" est une personne ou un personnage :
– retourne l’année exacte de naissance.

Sinon :
– retourne l’année exacte de début, de fondation, de première apparition ou de mise en activité documentée.

L’année doit être fournie sous forme d’un nombre entier.
Elle peut être négative si l’événement a eu lieu avant J.-C.

Si aucune année fiable et documentée n’existe, retourne exactement : None

Ne retourne strictement aucun autre mot, symbole ou ponctuation.
"""
prompt_annee_fin = """
Je veux que tu me retournes une seule valeur correspondant à "NOM_FICHE" (catégorie : NOM_CATEGORY).

Si "NOM_FICHE" est une personne ou un personnage :
– retourne l’année exacte de décès.

Sinon :
– retourne l’année exacte de fin, de dissolution, d’abandon ou de disparition documentée.

L’année doit être fournie sous forme d’un nombre entier.
Elle peut être négative si l’événement a eu lieu avant J.-C.

Si la personne est toujours en vie, si l’entité est toujours en activité
ou si aucune date fiable n’existe, retourne exactement : None

Ne retourne strictement aucun autre mot, symbole ou ponctuation.
"""
prompt_superficie = """
Je veux que tu me retournes la superficie totale de "NOM_FICHE" exprimée en kilomètres carrés.

Retourne uniquement la valeur numérique,
sans unité, sans texte, sans symbole.

Utilise un nombre entier si possible.
Sinon, utilise un nombre décimal avec un point comme séparateur.

Si la superficie n’est pas applicable ou inconnue, retourne exactement : None
"""

def print_prompt(prompt, nom, category):
    prompt = prompt.replace("NOM_FICHE", nom)
    prompt = prompt.replace("NOM_CATEGORY", category)
    pyperclip.copy(prompt)
    print(prompt)

### Fonctions GPT

def ajoute_superficie_et_tags_sur_toutes_les_fiches(directory_path):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_name = os.path.splitext(file)[0]
                #ajoute_tags(fiche_name)
                ajoute_fin(fiche_name)
                #ajoute_latitude_et_longitude_as_an_attribute(fiche_name)
                #ajoute_superficie(fiche_name)
                print(fiche_name)

def ajoute_superficie(fiche_name):
    # Chemin du fichier de la fiche
    fiche_path = os.path.join(output_dir+"/Géographie", fiche_name + ".md")

    # Vérifier si le fichier existe
    if not os.path.exists(fiche_path):
        print(f"❌ La fiche {fiche_name} n'existe pas.")
        return

    # Ajouter la superficie à la fiche
    content = read_file(fiche_path)
    if "superficie:" not in content and "indice_1" in content:
        superficie = ask_gpt(prompt_superficie.replace("NOM_FICHE", fiche_name))
        new_content = content.replace(
            "indice_1",
            f"superficie: {superficie}\nindice_1"
        )
    else:
        print(f"⚠️ La fiche {fiche_name} a déjà une superficie. Passage à la suivante.")
        return
    write_content_to_github(fiche_path, new_content)

def ajoute_fin(fiche_name):
    # Chemin du fichier de la fiche
    fiche_path = os.path.join(output_dir+"/Histoire", fiche_name + ".md")

    # Vérifier si le fichier existe
    if not os.path.exists(fiche_path):
        print(f"❌ La fiche {fiche_name} n'existe pas.")
        return

    # Ajouter les tags à la fiche
    content = read_file(fiche_path)
    if "debut:" in content and "indice_1" in content:
        annee_fin = ask_gpt(prompt_annee_fin.replace("NOM_FICHE", fiche_name))
        new_content = content.replace(
            "indice_1",
            f"fin: {annee_fin}\nindice_1"
        )
    else:
            print(f"⚠️ La fiche {fiche_name} a déjà des tags. Passage à la suivante.")
            return
    write_content_to_github(fiche_path, new_content)

def ajoute_tags(fiche_name):
    # Chemin du fichier de la fiche
    fiche_path = os.path.join(output_dir+"/Architecture", fiche_name + ".md")

    # Vérifier si le fichier existe
    if not os.path.exists(fiche_path):
        print(f"❌ La fiche {fiche_name} n'existe pas.")
        return

    # Ajouter les tags à la fiche
    content = read_file(fiche_path)
    if "tags:" not in content and "indice_1" in content:
        tags = ask_gpt(prompt_tags_geography.replace("NOM_FICHE", fiche_name))
        new_tags = "tags: \n"
        split_char = "|"
        for tag in tags.split(split_char):
            new_tags += f"  - {tag.strip().replace(' ', '_')}\n"
        new_content = content.replace("indice_1",
            new_tags + "\nindice_1"
        )
    else:
        print(f"⚠️ La fiche {fiche_name} a déjà des tags. Passage à la suivante.")
        return
    write_content_to_github(fiche_path, new_content)

def ask_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Tu es un assistant expert en culture générale, en jeux télévisés français et en rédaction de fiches informatives."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

def ask_gpt5(prompt):
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": "Tu es un assistant expert en culture générale, en jeux télévisés français et en rédaction de fiches informatives."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

def generate_gpt_from_name(nom, category):
    if category == "Géographie":
        return generate_gpt_from_name_geography(nom, category)
    elif category == "Botanique":
        return generate_gpt_from_name_botanique(nom, category)
    elif category == "Architecture":
        return generate_gpt_from_name_architecture(nom, category)
    elif category == "Animaux":
        return generate_gpt_from_name_animaux(nom, category)
    elif category == "Vocabulaire":
        return generate_gpt_from_name_vocabulaire(nom)
    else:
        return generate_gpt_from_name_generic(nom, category)

def generate_gpt_from_name_botanique(nom, category):

    indices = ask_gpt(prompt_indices_botanique.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    description = ask_gpt(prompt_description_botanique.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))

    return indices, description

def generate_gpt_from_name_vocabulaire(nom):

    indices = ask_gpt(prompt_indices.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", "définition"))
    tag = ask_gpt(prompt_tag_vocabulaire.replace("NOM_FICHE", nom))
    questions = ask_gpt5(prompt_questions_vocabulaire.replace("NOM_FICHE", nom))
    description = ask_gpt(prompt_description_vocabulaire.replace("NOM_FICHE", nom))

    return tag, questions, description, indices

def generate_gpt_from_name_animaux(nom, category):

    indices = ask_gpt(prompt_indices_animaux.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    description = ask_gpt(prompt_description_animaux.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    questions = ask_gpt5(prompt_questions.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))

    return indices, description, questions

def generate_gpt_from_name_geography(nom, category):
    tags = ask_gpt(prompt_tags_geography.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    superficie = ask_gpt(prompt_superficie.replace("NOM_FICHE", nom))
    if superficie == "None":
        superficie = ""

    indices = ask_gpt(prompt_indices.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    questions = ask_gpt5(prompt_questions.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    description = ask_gpt(prompt_description.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    
    return tags, indices, description, questions, superficie

def generate_gpt_from_name_architecture(nom, category):
    tags = ask_gpt(prompt_tags_geography.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    indices = ask_gpt(prompt_indices.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    questions = ask_gpt5(prompt_questions.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    description = ask_gpt(prompt_description.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    annee_debut = ask_gpt(prompt_annee_debut.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    annee_fin = ask_gpt(prompt_annee_fin.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    return tags, indices, description, questions, annee_debut, annee_fin

def generate_gpt_from_name_generic(nom, category):
    tags = ask_gpt(prompt_tags.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    annee_debut = ask_gpt(prompt_annee_debut.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    annee_fin = ask_gpt(prompt_annee_fin.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    indices = ask_gpt5(prompt_indices.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    description = ask_gpt(prompt_description.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))
    question = ask_gpt5(prompt_questions.replace("NOM_FICHE", nom).replace("NOM_CATEGORY", category))

    return tags, annee_debut, indices, description, question, annee_fin
  
def generate_fiche(nom, category):
    if category == "Géographie":
        return generate_fiche_geography(nom, category)
    elif category == "Botanique":
        return generate_fiche_botanique(nom, category)
    elif category == "Architecture":
        return generate_fiche_architecture(nom, category)
    elif category == "Animaux":
        return generate_fiche_animaux(nom, category)
    elif category == "Vocabulaire":
        return generate_fiche_vocabulaire(nom)
    else:
        return generate_fiche_generic(nom, category)

def generate_fiche_botanique(nom, category):
    indices, description = generate_gpt_from_name_botanique(nom, category)

    indices = indices.replace('"', '').replace(':', '').replace("[",'').replace("]","")
    indices_split_char = " | "

    url_wiki = ""
    #url_wiki = query_to_image_url(f"{nom}")

    new_content = f"""---
tags: 
  - Botanique
indice_1 : 
  - {indices.split(indices_split_char)[0]}
indice_2 : 
  - {indices.split(indices_split_char)[1]}
indice_3 : 
  - {indices.split(indices_split_char)[2]}
indice_4 : 
  - {indices.split(indices_split_char)[3]}
indice_5 : 
  - {indices.split(indices_split_char)[4]}
indice_6 : 
  - {indices.split(indices_split_char)[5]}
---

![Image de {nom}]({url_wiki})

###### Questions



###### Description

{description}
"""
    return new_content

def generate_fiche_animaux(nom, category):
    indices, description, questions = generate_gpt_from_name_animaux(nom, category)

    indices = indices.replace('"', '').replace(':', '').replace("[",'').replace("]","")
    indices_split_char = " | "

    url_wiki = ""
    #url_wiki = query_to_image_url(f"{nom}")

    new_content = f"""---
tags: 
  - Animaux
indice_1 : 
  - {indices.split(indices_split_char)[0]}
indice_2 : 
  - {indices.split(indices_split_char)[1]}
indice_3 : 
  - {indices.split(indices_split_char)[2]}
indice_4 : 
  - {indices.split(indices_split_char)[3]}
indice_5 : 
  - {indices.split(indices_split_char)[4]}
indice_6 : 
  - {indices.split(indices_split_char)[5]}
---

![Image de {nom}]({url_wiki})

###### Questions

{questions}

###### Description

{description}
"""
    return new_content

def generate_fiche_vocabulaire(nom):
    tag, questions, description, indices = generate_gpt_from_name_vocabulaire(nom)
    url_wiki = ""
    #url_wiki = query_to_image_url(f"{nom}")
    indices = indices.replace('"', '').replace(':', '').replace("[",'').replace("]","")
    indices_split_char = " | "

    new_content = f"""---
tags: 
  - DCDL
  - {tag}
indice_1 : 
  - {indices.split(indices_split_char)[0]}
indice_2 : 
  - {indices.split(indices_split_char)[1]}
indice_3 : 
  - {indices.split(indices_split_char)[2]}
indice_4 : 
  - {indices.split(indices_split_char)[3]}
indice_5 : 
  - {indices.split(indices_split_char)[4]}
indice_6 : 
  - {indices.split(indices_split_char)[5]}
---

![Image de {nom}]({url_wiki})

###### Questions

{questions}

###### Description

{description}
"""
    return new_content

def generate_fiche_geography(nom, category):
    tags, indices, description, question, superficie = generate_gpt_from_name(nom, category)

    indices = indices.replace('"', '').replace(':', '').replace("[",'').replace("]","")
    
    from geopy.geocoders import Nominatim
    #fiche_to_carte(nom)
    geolocator = Nominatim(user_agent="geo_attribute", timeout=10)
    location = geolocator.geocode(nom)
    if not location :
        latitude = ""
        longitude = ""
        location = ""
    else:
        latitude = location.latitude
        longitude = location.longitude
        location = str(latitude).replace(',','.') + "," + str(longitude).replace(',','.')
                                         
    print(tags)
    print(indices)
    split_char = "|"

    new_content = f"""---
description: {indices}
latitude: {latitude}
longitude: {longitude}
superficie: {superficie}
location: {location}
tags: 
  - {tags.split(split_char)[0].strip().replace(" ", "_").replace(",","")}
  - {tags.split(split_char)[1].strip().replace(" ", "_").replace(",","")}
  - {tags.split(split_char)[2].strip().replace(" ", "_").replace(",","")}
  - GPS_mano
indice_1 : 
  - {indices.split(split_char)[0].strip()}
indice_2 : 
  - {indices.split(split_char)[1].strip()}
indice_3 : 
  - {indices.split(split_char)[2].strip()}
indice_4 : 
  - {indices.split(split_char)[3].strip()}
indice_5 : 
  - {indices.split(split_char)[4].strip()}
indice_6 : 
  - {indices.split(split_char)[5].strip()}
---

![[Carte_{nom}.png]]

###### Questions

{question}

###### Description

{description}
"""
    return new_content

def generate_fiche_architecture(nom, category):
    tags, indices, description, questions, annee_debut, annee_fin = generate_gpt_from_name(nom, category)

    indices = indices.replace('"', '').replace(':', '').replace("[",'').replace("]","")
    url_wiki = ""
    #url_wiki = query_to_image_url(f"{nom}")

    from geopy.geocoders import Nominatim
    geolocator = Nominatim(user_agent="geo_attribute", timeout=10)
    location = geolocator.geocode(nom)
    if "None" in annee_fin:
        annee_fin = ""
    if "None" in annee_debut:
        annee_debut = ""
    if not location :
        latitude = ""
        longitude = ""
        location = ""
    else:
        latitude = location.latitude
        longitude = location.longitude
        location = str(latitude).replace(',','.') + "," + str(longitude).replace(',','.')
                                         
    split_char = "|"

    new_content = f"""---
description: {indices}
latitude: {latitude}
longitude: {longitude}
location: {location}
tags: 
  - {tags.split(split_char)[0].strip().replace(" ", "_").replace(",","")}
  - {tags.split(split_char)[1].strip().replace(" ", "_").replace(",","")}
  - {tags.split(split_char)[2].strip().replace(" ", "_").replace(",","")}
  - GPS_mano
debut: {annee_debut}
fin: {annee_fin}
indice_1 : 
  - {indices.split(split_char)[0].strip()}
indice_2 : 
  - {indices.split(split_char)[1].strip()}
indice_3 : 
  - {indices.split(split_char)[2].strip()}
indice_4 : 
  - {indices.split(split_char)[3].strip()}
indice_5 : 
  - {indices.split(split_char)[4].strip()}
indice_6 : 
  - {indices.split(split_char)[5].strip()}
---

![Image de {nom}]({url_wiki})

###### Questions

{questions}

###### Description

{description}
"""
    return new_content

def generate_fiche_generic(nom, category):
    tags, annee_debut, indices, description, question, annee_fin = generate_gpt_from_name(nom, category)
    print("Tags : "+tags)
    print("Année début : "+annee_debut)
    print("Année fin : "+annee_fin)
    print("Indices : "+indices)
    print("Description : "+description)
    print("Question : "+question)

    annee_debut_info = annee_debut.strip()
    annee_fin_info = annee_fin.strip()
    if "None" in annee_fin_info:
        annee_fin_info = ""
    if "None" in annee_debut_info:
        annee_debut_info = ""

    indices = indices.replace('"', '').replace(':', '').replace("[",'').replace("]","")
    description = description.strip()
    question = question.strip()
    url_wiki = ""
    #url_wiki = query_to_image_url(f"{nom}")

    split_char = "|"
    new_content = f"""---
tags: 
  - {category}
  - {tags.split(split_char)[0].strip().replace(" ", "_").replace(",","")}
  - {tags.split(split_char)[1].strip().replace(" ", "_").replace(",","")}
  - {tags.split(split_char)[2].strip().replace(" ", "_").replace(",","")}
debut: {annee_debut_info}
fin: {annee_fin_info}
indice_1 : 
  - {indices.split(split_char)[0].strip()}
indice_2 : 
  - {indices.split(split_char)[1].strip()}
indice_3 : 
  - {indices.split(split_char)[2].strip()}
indice_4 : 
  - {indices.split(split_char)[3].strip()}
indice_5 : 
  - {indices.split(split_char)[4].strip()}
indice_6 : 
  - {indices.split(split_char)[5].strip()}
---

![Image de {nom}]({url_wiki})

###### Questions

{question}

###### Description

{description}
"""
    return new_content

def update_fiche_with_gpt(nom, category):
    fiche_name = unicodedata.normalize('NFC', f"{nom}.md")
    file_path = f"{output_dir}/{category}/{fiche_name}"

    content = read_file(file_path)
    if content and "![" in content:
        print(f"❌ La fiche {fiche_name} a déjà été mise à jour.")
        return False

    new_content = generate_fiche(nom, category)

    if content:
        updated = include_questions(content, new_content)
    else:
        updated = new_content

    return write_content_to_github(file_path, updated)

### Fonctions création fiches

def initialize_fiche(fiche_path):
    content = read_file(fiche_path)
    if content is None:
        content = ""
    if '---' not in content:
        content = '---\ntags:\n---\n' + content
    write_content_to_github(fiche_path, content)

def include_questions(content_with_question, new_content):
    new_markdown = new_content
    questions = return_questions(content_with_question)
    if questions:
        questions_str = "\n".join([f" - {question}" for question in questions])
        new_markdown = replace_second_occurrence(new_markdown, '---\n', f'questions:\n{questions_str}\n---\n')
    return new_markdown

def add_questions(fiche_path):
    content = path_to_content(fiche_path)
    new_content = include_questions(content, content)
    write_content_to_github(fiche_path, new_content)
    
def create_fiches_in_directory(directory_path, number_max):
    incr = 0
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md") and incr < number_max:
                fiche_path = os.path.join(root, file)
                fiche_name = fiche_path.split("/")[-1].replace(".md", "")
                category_from_path = fiche_path.split("/")[-2]
                initialize_fiche(fiche_path)
                add_questions(fiche_path)
                add_category(fiche_path, fiche_path.split("/")[-2])
                if update_fiche_with_gpt(fiche_name, category_from_path):
                    incr += 1
                    print("Fiche mise à jour avec GPT dans", fiche_path)
  
def create_fiche(nom, category):
    flag = True
    for root, dirs, files in os.walk(output_dir):
        file_name = unicodedata.normalize('NFC', f"{nom}.md")
        for file in files:
            file_name_0 = unicodedata.normalize('NFC', file)
            if file_name == file_name_0:
                flag = False
                fiche_path = os.path.join(root, file)
                result = update_fiche_with_gpt(nom, category)
                if result :
                    print(f"Fiche '{nom}.md' mise à jour avec GPT dans '{root}'.")
                else:
                    print(f"Fiche '{nom}.md inchangée car déjà modifiée avec GPT")
                return
    if flag:
        content = generate_fiche(nom, category)
        file_path = os.path.join(output_dir, category, f"{nom}.md")
        print(file_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        write_content_to_github(file_path, content)

def create_fiches_from_array(names_array, indication=""):
    for name in names_array:
        create_fiche(name, indication)

### Modification des fiches      

def reorder_indices_in_directory(directory_path):
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                reorder_indices_in_yaml(file_path)

def reorder_indices_in_yaml(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Détection du frontmatter YAML
    if not content.startswith('---'):
        print(f"Pas de frontmatter YAML trouvé dans {filepath}")
        return

    yaml_start = 0
    yaml_end = content.find('---', 3)
    if yaml_end == -1:
        print(f"Frontmatter mal fermé dans {filepath}")
        return

    yaml_end += 3  # inclure les '---'
    yaml_block = content[yaml_start:yaml_end]
    rest_of_file = content[yaml_end:].lstrip()

    # Extraction des lignes d'indice
    indice_lines = re.findall(r'(indice_\d+:\s*\n(?:\s*-\s*.*\n?)*)', yaml_block)
    yaml_without_indices = re.sub(r'(indice_\d+:\s*\n(?:\s*-\s*.*\n?)*)', '', yaml_block).strip()

    # Nettoyage et recomposition du frontmatter
    if indice_lines:
        new_yaml = '---\n' + '\n'.join(line.strip() for line in indice_lines) + '\n' + yaml_without_indices + '\n---\n'
    else:
        new_yaml = yaml_block  # rien à modifier

    # Réassembler le fichier
    new_content = new_yaml + '\n' + rest_of_file

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"✔️ Modifié : {filepath}")

def change_all_fiches(directory_path, this, into):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                updated_content = content.replace(this, into)
                # if "Jeux olympiques" in content or "Jeux Olympiques" in content:
                #     add_category(fiche_path, "JO")
                write_content_to_github(fiche_path, updated_content)

def remove_brackets_around_years(directory_path):
    year_pattern = re.compile(r'\[\[(\d{4})\]\]')  # Matches [[YYYY]]

    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                # Replace [[YYYY]] with YYYY
                updated_content = year_pattern.sub(r'\1', content)
                # Write back the updated content
                write_content_to_github(fiche_path, updated_content)

def remove_brackets_around_word(directory_path, word):
    word_pattern = re.compile(rf'\[\[({word})\]\]')

    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                updated_content = re.sub(r'\[\[(' + re.escape(word) + r')\]\]', r'\1', content)
                # Write back the updated content
                write_content_to_github(fiche_path, updated_content)

def add_brackets_around_word(directory_path, word):
    word_pattern = re.compile(rf'\b({word})\b(?!\]\])')

    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                updated_content = word_pattern.sub(r'[[\1]]', content)
                # Write back the updated content
                if updated_content != content:
                    write_content_to_github(fiche_path, updated_content)

def remove_brackets_from_nonexistent_fiches(directory_path):
    # Collect all existing fiches (sans extension .md) dans tout le répertoire
    existing_fiches = set()
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file.endswith(".md"):
                fiche_name = os.path.splitext(file)[0]
                existing_fiches.add(fiche_name)

    # Parcours à nouveau pour modifier les fichiers
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                # Remplace [[NonExistentFiche]] par NonExistentFiche si elle n'existe pas
                updated_content = re.sub(
                    r'\[\[(.*?)\]\]',
                    lambda match: match.group(1) if match.group(1) not in existing_fiches else match.group(0),
                    content
                )

                # Réécriture seulement si modifié
                if updated_content != content:
                    write_content_to_github(fiche_path, updated_content)

#def put_brackets_when_existent_files(directory_path):
    # Collecte de tous les noms de fichiers .md existants dans tout le répertoire
    existing_fiches = set()
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file.endswith(".md"):
                fiche_name = os.path.splitext(file)[0]
                existing_fiches.add(fiche_name)

    # Re-traitement des fichiers pour ajouter les [[brackets]] autour des noms existants
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                # Construction d'une regex intelligente : mots qui ne sont pas déjà entre crochets
                updated_content = re.sub(
                    r'\b(' + '|'.join(re.escape(name) for name in existing_fiches) + r')\b(?!\]\])',
                    lambda match: f"[[{match.group(1)}]]" 
                    if f"[[{match.group(1)}]]" not in content else match.group(1),
                    content
                )

                # Réécriture si du contenu a été modifié
                if updated_content != content:
                    write_content_to_github(fiche_path, updated_content)

def add_category(fiche_path, category_from_path):
    content = path_to_content(fiche_path)
    first_three_lines = "\n".join(content.split("\n")[:3])
    if category_from_path in first_three_lines:
        return
    spaces_before_dash = re.search(r'tags: \n(\s*)-', content)
    if spaces_before_dash:
        spaces_before_dash = len(spaces_before_dash.group(1))
        if spaces_before_dash == 0:
            spaces_before_dash = 1
    else:
        spaces_before_dash = 1
    spaces = ""
    for i in range(spaces_before_dash):
        spaces += " "
    #Warning for spaces after tags
    new_content = content.replace('tags: \n', f'tags:\n{spaces}- {category_from_path}\n')
    write_content_to_github(fiche_path, new_content)
    
def add_category_to_fiche_in_directory(directory_path, category):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                # Check if the category is already present
                if f"- {category}" in content:
                    continue

                # Add category to the beginning of the file
                new_content = f"---\ntags:\n - {category}\n---\n{content}"
                write_content_to_github(fiche_path, new_content)
                
def add_description_attribute_in_first(directory_path):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                # Extract indices
                indices = []
                for i in range(1, 7):
                    match = re.search(rf'indice_{i}\s*:\s*\n\s*-\s*(.*)', content)
                    if match:
                        indices.append(match.group(1).strip()+" | ")

                # Aggregate indices into a description
                if indices:
                    description = " ".join(indices)
                    if "description:" not in content:
                        # Add description attribute
                        content = content.replace(
                            "---\n", f"---\ndescription: {description}\n", 1
                        )
                # Extract and remove latitude, longitude, superficie, and location
                attributes = {}
                for attr in ["latitude", "longitude", "superficie", "location"]:
                    match = re.search(rf'{attr}:\s*(.*)', content)
                    if match:
                        attributes[attr] = match.group(1).strip()
                        content = re.sub(rf'{attr}:\s*.*\n', '', content)

                # Add the attributes after the description
                description_match = re.search(r'description:\s*(.*)', content)
                if description_match:
                    description = description_match.group(1).strip()
                    new_description = description + "\n"
                    for attr, value in attributes.items():
                        new_description += f"{attr}: {value}\n"
                    content = re.sub(r'description:\s*.*', f"description: {new_description.strip()}", content)
                # Write back the updated content
                write_content_to_github(fiche_path, content)

def supprime_attribut_from_fiche(nom_attribut, category):
    for root, dirs, files in os.walk(output_dir+"/"+category):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
            content = read_file(fiche_path)
            # Regex pour supprimer les attributs YAML avec une liste indentée
            updated_content = re.sub(
                rf'{nom_attribut}\s*:\s*\n((\s*-\s*.*\n)+)', '', content, flags=re.MULTILINE
            )
            # Et pour les scalaires simples comme : nom: valeur
            updated_content = re.sub(
                rf'{nom_attribut}\s*:\s*.*\n', '', updated_content, flags=re.MULTILINE
            )
            if updated_content != content:
                write_content_to_github(fiche_path, updated_content)

def change_question(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".md"):
                fiche_path = os.path.join(root, file)
                content = read_file(fiche_path)
                # Replace "Question : " with "###### Questions \n"
                updated_content = content.replace("Question : ", "###### Questions \n\n")

                # Write the updated content back to the file
                write_content_to_github(fiche_path, updated_content)

### Fonctions utilitaires

def extract_year_from_date(date_str):
    try:
        year = date_str.split('/')[0]
        if year.isdigit():
            return year
        return ""
    except:
        return ""

def search_commons_images(query, limit=10):
    url = 'https://commons.wikimedia.org/w/api.php'
    params = {
        'action': 'query',
        'format': 'json',
        'list': 'search',
        'srsearch': query,
        'srlimit': limit,
        'srnamespace': 6  # Namespace 6 corresponds to files
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data['query']['search']

def get_image_info(title):
    url = 'https://commons.wikimedia.org/w/api.php'
    params = {
        'action': 'query',
        'format': 'json',
        'titles': title,
        'prop': 'imageinfo',
        'iiprop': 'url|size|mime'
    }
    response = requests.get(url, params=params)
    data = response.json()
    page = next(iter(data['query']['pages'].values()))
    return page['imageinfo'][0] if 'imageinfo' in page else None

def query_to_image_url(query):
    print(f'Searching for images related to "{query}" on Wikimedia Commons...\n')
    search_results = search_commons_images(query)
    print(search_results)
    if not search_results:
        print('No images found.')
        return ""
    
    for result in search_results:
        title = result['title']
        image_info = get_image_info(title)
        if image_info:
            print(f"URL: {image_info['url']}")
        else:
            print('No image information available.')
        return image_info['url']

def alea_fiches(nombre_fiches, repertoire="./knowledge"):
    try:
        # Vérifier si le répertoire existe
        if not os.path.isdir(repertoire):
            raise FileNotFoundError(f"Le répertoire '{repertoire}' n'existe pas.")
        
        # Récupérer tous les fichiers du répertoire et de ses sous-répertoires
        fichiers = []
        for root, _, files in os.walk(repertoire):
            for file in files:
                fichiers.append(file.split('.')[0])  # Stocker le chemin complet du fichier
        
        # Vérifier qu'on a assez de fichiers
        if nombre_fiches > len(fichiers):
            raise ValueError(f"Nombre de fiches demandé ({nombre_fiches}) supérieur au nombre de fichiers disponibles ({len(fichiers)}).")
        
        # Sélectionner aléatoirement les fichiers
        fiches_selectionnees = random.sample(fichiers, nombre_fiches)
        
        return fiches_selectionnees
    
    except Exception as e:
        return str(e)

def return_questions(content):
    questions = []

    # Format 1 : "Question : ..."
    q1_pattern = re.compile(r'Question\s*:\s*(.*?)(?=\nQuestion|$)', re.DOTALL)
    questions += q1_pattern.findall(content)

    # Format 2 : YAML "question:\n - ... "
    q2_pattern = re.compile(r'question\s*:\s*\n((?:\s*-\s+.*\n?)*)', re.DOTALL)
    q2_match = q2_pattern.search(content)
    if q2_match:
        lines = q2_match.group(1).strip().splitlines()
        questions += [line.strip()[2:].strip() for line in lines if line.strip().startswith("-")]

    # Format 3 : Bloc markdown "###### Questions"
    q3_blocks = re.findall(r'###### Questions\s*\n+(.+?)(?=\n#{1,6} |\Z)', content, re.DOTALL)
    for block in q3_blocks:
        # Séparation par double saut de ligne = plusieurs questions
        for q in re.split(r'\n{2,}', block.strip()):
            cleaned = q.strip()
            if cleaned:
                questions.append(cleaned)

    # Nettoyage : retirer [[...]] et remplacer ":" par espace
    cleaned_questions = [re.sub(r'\[\[|\]\]', '', q.strip()).replace(':', ' ') for q in questions]

    return cleaned_questions

def replace_second_occurrence(text, target, replacement):
    parts = text.split(target, 2)  # Split into at most 3 parts
    if len(parts) > 2:
        return target.join([parts[0], parts[1]]) + replacement + parts[2]
    return text  # Return unchanged if there aren't at least two occurrences

def path_to_content(path):
    content = read_file(path)
    if content is None:
        print(f"❌ Impossible de lire {path} depuis GitHub")
        return ""
    return content

### Fonctions informations depuis fiches (quiz)

def return_category(content):
    tags_pattern = re.compile(r'tags:\s*\n\s*- (.*?)\n', re.DOTALL)
    tags_match = tags_pattern.search(content)
    if tags_match:
        return tags_match.group(1).strip()
    return "Non trouvé."
         
def retourne_indices(fiche):
    content = path_to_content(fiche)
    indices_pattern = re.compile(r'indice_\d+\s*:\s*\n\s*-\s*(.*)')
    indices_matches = indices_pattern.findall(content)
    if indices_matches:
        return [indice.strip() for indice in indices_matches]
    return []

def create_decks(number_of_decks):
    directory_path = "./knowledge/Cinéma"
    decks = []
    all_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                all_files.append(os.path.join(root, file))
    
    selected_files = random.sample(all_files, min(len(all_files), number_of_decks))
    for file in selected_files[:number_of_decks]:
        if file.endswith(".md"):
            fiche_path = os.path.join(file)
            name = os.path.splitext(file)[0]
            indices = retourne_indices(fiche_path)
            
            if len(indices) >= 3:
                selected_indices = random.sample(indices, 3)
                question_side = ", ".join(selected_indices)
                answer_side = name.split("/")[-1]
                decks.append((question_side, answer_side))

    for question, answer in decks:
        print(f"Q: {question}\nA: {answer}\n")

def get_files_between_years(directory_path, start_year, end_year):
    matching_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    content = f.read()
                # Extract the year from the "annee" field
                year_match = re.search(r'annee:\s*(\d{4})', content)
                if year_match:
                    year = int(year_match.group(1))
                    if start_year <= year <= end_year:
                        matching_files.append(file)
    return matching_files

def pick_connected_fiches_triplet(directory_path, reveal_mediator=False):
    # Dictionnaire : fiche -> set(fiches qu'elle mentionne via [[...]])
    fiche_links = defaultdict(set)

    # Récupère tous les fichiers .md
    fiches = []
    fiche_names_set = set()
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md"):
                fiche_name = os.path.splitext(file)[0]
                fiche_path = os.path.join(root, file)
                fiches.append((fiche_name, fiche_path))
                fiche_names_set.add(fiche_name)

    # Extraction des liens dans chaque fiche
    for fiche_name, fiche_path in fiches:
        content = read_file(fiche_path)
        links = re.findall(r'\[\[(.*?)\]\]', content)
        fiche_links[fiche_name].update(links)

    # Liste des triplets potentiels : (fiche_A, fiche_B, fiche_médiatrice)
    triplets = []
    for mediator, links in fiche_links.items():
        valid_links = [link for link in links if link in fiche_names_set and link != mediator]
        if len(valid_links) >= 2 and mediator in fiche_names_set:
            for i in range(len(valid_links)):
                for j in range(i + 1, len(valid_links)):
                    fiche_A = valid_links[i]
                    fiche_B = valid_links[j]
                    if fiche_A != fiche_B:
                        triplets.append((fiche_A, fiche_B, mediator))

    # Choix aléatoire d’un triplet
    if triplets:
        selected = random.choice(triplets)
        if reveal_mediator:
            return selected  # (fiche_A, fiche_B, fiche_médiatrice)
        else:
            return selected[0], selected[1]  # seulement A et B
    else:
        return None  # Aucun chemin trouvé
    
def return_question_from_fiche(fiche_path):
    content = path_to_content(fiche_path)
    question_pattern = re.compile(r'###### Questions\s*(.*?)\s*###### Description', re.DOTALL)
    question_match = question_pattern.search(content)
    if question_match:
        questions = question_match.group(1).strip().split("\n")
        questions = [re.sub(r'\[\[|\]\]', '', q.strip()) for q in questions if q.strip()]
        if questions:
            return random.choice(questions)
    return None

def create_deck(directory_path):
    deck = []
    count = 0

    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".md") and count < 100:
                fiche_path = os.path.join(root, file)
                question = return_question_from_fiche(fiche_path)
                if question:
                    answer = os.path.splitext(file)[0]
                    deck.append((question, answer))
                    count += 1

    return deck

def pyperclip_copy_deck(deck):
    """
    Copies the deck to the clipboard in the format:
    question,answer\n
    """
    formatted_deck = "\n".join([f"{question}|{answer}" for question, answer in deck])
    pyperclip.copy(formatted_deck)
    print("Deck copied to clipboard!")

#change_all_fiches("data/Anatomie", "Question : ", "###### Questions \n\n")
generate_fiche("L'Amour Ouf", "Cinéma")