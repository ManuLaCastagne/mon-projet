#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Score automatiquement les fiches Markdown d'un coffre Obsidian
selon leur intérêt pour un entraînement généraliste de haut niveau
en culture générale.

Le script :
- parcourt les fichiers Markdown du coffre ;
- utilise le titre + un court extrait uniquement pour désambiguïser ;
- demande à l'IA cinq sous-notes de 0 à 5 ;
- calcule localement un score absolu sur 100 ;
- conserve un cache permettant de reprendre après interruption ;
- exporte un CSV trié par score ;
- peut éventuellement écrire le score dans le frontmatter YAML.

IMPORTANT :
Le score évalue le SUJET, pas la qualité ni la richesse de la fiche.
"""

import csv
import json
import os
import random
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

# Dossier contenant les fiches Markdown.
VAULT_PATH = Path(__file__).parent / "data"

# Modèle :
# - gpt-5.6-luna  : économique, adapté aux gros volumes
# - gpt-5.6-terra : compromis qualité / coût
# - gpt-5.6-sol   : qualité maximale
MODEL = "gpt-5.6-luna"

# Numéro de version de la grille.
#
# IMPORTANT :
# Si tu modifies fortement le prompt, les critères ou les pondérations,
# change cette valeur (ex. "v3").
#
# Cela évite de mélanger dans le cache des scores provenant
# d'anciennes méthodes de notation.
SCORING_VERSION = "v2"

# Nombre de fiches envoyées par appel API.
BATCH_SIZE = 50

# Nombre maximal de caractères de contexte pris dans chaque fiche.
# Le contexte sert UNIQUEMENT à identifier précisément le sujet.
CONTEXT_CHARS = 700

# ============================================================
# MODE TEST / ÉCHANTILLONNAGE
# ============================================================

# Pour tester :
#   MAX_FILES = 200
#
# Pour traiter tout le coffre :
#   MAX_FILES = None
MAX_FILES: Optional[int] = 200

# Si True et MAX_FILES n'est pas None :
# prend un échantillon aléatoire dans tout le coffre,
# plutôt que les N premiers fichiers par ordre alphabétique.
#
# C'est fortement recommandé pour calibrer la grille.
RANDOM_SAMPLE = True

# Graine fixe afin que le même test de 200 fiches
# retourne toujours les mêmes fichiers.
RANDOM_SEED = 42


# ============================================================
# FICHIERS DE SORTIE
# ============================================================

OUTPUT_DIR = Path("culture_g_scoring")

# On inclut la version dans les fichiers :
# l'ancien cache ne sera donc PAS réutilisé avec la nouvelle grille.
CACHE_FILE = OUTPUT_DIR / f"scores_cache_{SCORING_VERSION}.jsonl"
CSV_FILE = OUTPUT_DIR / f"scores_culture_g_{SCORING_VERSION}.csv"
ERROR_FILE = OUTPUT_DIR / f"erreurs_{SCORING_VERSION}.jsonl"

# Par défaut : aucune fiche Markdown n'est modifiée.
WRITE_SCORE_TO_YAML = False

# Nom du champ ajouté au frontmatter YAML si activé.
YAML_SCORE_FIELD = "culture_g_score"

# Sauvegarde des Markdown avant modification.
BACKUP_DIR = OUTPUT_DIR / f"backup_markdown_{SCORING_VERSION}"

# Nombre maximal de tentatives en cas d'erreur API.
MAX_RETRIES = 6
RETRY_BASE_SECONDS = 2


# ============================================================
# GRILLE DE NOTATION
# ============================================================

SYSTEM_PROMPT = """
Tu es un expert des questions de culture générale et des jeux télévisés
francophones.

Tu dois évaluer l'intérêt d'apprendre chaque sujet dans le cadre d'un
entraînement généraliste de haut niveau.

Tu notes le SUJET lui-même, et NON la qualité de la fiche Markdown fournie.


OBJECTIF GENERAL

Le but final est de déterminer une PRIORITE D'APPRENTISSAGE.

Imagine une personne disposant d'un temps limité pour progresser en culture
générale et devant choisir, parmi des dizaines de milliers de sujets, ceux
qu'elle doit apprendre en premier.

La question fondamentale est :

"À quel point connaître CE SUJET PRECIS est-il rentable pour répondre
correctement à des questions variées de culture générale généraliste ?"


REGLES IMPERATIVES

- N'évalue pas la qualité de la fiche.
- N'évalue pas la longueur de la fiche.
- N'évalue pas le nombre d'informations présentes.
- N'évalue pas le nombre de liens Obsidian.
- Le contexte fourni sert UNIQUEMENT à identifier précisément le sujet et à
  lever une éventuelle ambiguïté.

- N'évalue pas uniquement la célébrité.
- Un mot connu de tout le monde n'est pas nécessairement une connaissance
  importante de culture générale.
- Un spécialiste extrêmement important dans un domaine très étroit peut
  obtenir une note relativement basse.
- Une personnalité, une œuvre, un lieu, un événement ou une notion pouvant
  apparaître dans de nombreuses questions indépendantes doit être mieux noté.

- Le fait qu'un sujet appartienne à un domaine fréquent dans les quiz ne
  signifie PAS que ce sujet précis soit lui-même fréquent.

Exemple :
le corps humain est un grand thème de culture générale.
Cela ne signifie pas que chaque muscle, chaque artère ou chaque terme médical
soit une connaissance prioritaire.

- Une connaissance très spécifique pouvant donner une jolie question de quiz
  doit rester basse si cette question est très rare.
- Une anecdote amusante ou surprenante ne rend pas automatiquement le sujet
  important.
- Ne surévalue pas les sujets scientifiques ou médicaux parce qu'ils sont
  "fondamentaux" dans leur discipline.
- Ne surévalue pas les professions courantes.
- Ne surévalue pas les parties du corps simplement parce que tout le monde
  connaît leur nom.
- Ne surévalue pas un sujet grâce à un autre sens du même mot si ce deuxième
  sens n'est pas réellement celui de la fiche.

- Raisonne pour des quiz et jeux télévisés FRANCOPHONES de culture générale.
- Raisonne du point de vue d'un joueur généraliste de haut niveau, pas d'un
  spécialiste.

- Utilise réellement toute l'échelle de 0 à 5.
- Les notes 4 doivent déjà correspondre à des sujets importants.
- La note 5 doit être EXCEPTIONNELLE.
- Les notes 0 et 1 doivent réellement être utilisées pour les sujets très
  obscurs, anecdotiques ou spécialisés.


============================================================
CRITERE 1 — NOTORIETE
============================================================

Mesure la notoriété du sujet EN TANT QUE REFERENCE DE CULTURE GENERALE.

Il ne suffit pas que le mot soit compris ou que l'objet soit familier dans
la vie quotidienne.

0 = pratiquement inconnu hors d'un cercle extrêmement spécialisé

1 = surtout connu des spécialistes ou des amateurs avertis

2 = reconnaissable par une personne cultivée, mais peu connu du grand public

3 = référence bien établie de culture générale

4 = très grande référence, connue d'une large majorité du public

5 = référence universellement célèbre et culturellement incontournable


ATTENTION :

Un doigt, un genou, une dent, une maladie courante ou un médicament courant
peuvent être connus de presque tout le monde sans mériter 5.

Une personnalité historique centrale, une œuvre mondialement célèbre ou un
monument emblématique peuvent mériter 5.

Ne confonds jamais familiarité quotidienne et importance culturelle.


============================================================
CRITERE 2 — FREQUENCE_QUIZ
============================================================

C'EST LE CRITERE LE PLUS IMPORTANT.

Évalue la probabilité que CE SUJET PRECIS soit :

- lui-même la réponse à une question ;
- un indice décisif permettant de trouver la réponse ;
- ou une connaissance nécessaire pour résoudre une question de culture
  générale généraliste.

Ne récompense PAS simplement la fréquence du domaine auquel appartient
le sujet.

Exemple :

Le corps humain est un thème fréquent.

Cela ne signifie pas que "artère fémorale", "péricarde", "pisiforme",
"muscle soléaire" ou "creux poplité" soient des sujets fréquents.

0 = pratiquement jamais rencontré dans un quiz généraliste

1 = question très spécialisée ou exceptionnelle

2 = peut apparaître occasionnellement

3 = sujet assez classique des quiz de culture générale

4 = revient régulièrement sous plusieurs formulations

5 = marronnier majeur de culture générale, extrêmement fréquent


La note 5 doit être réservée à une petite minorité de sujets réellement
incontournables.


============================================================
CRITERE 3 — TRANSVERSALITE
============================================================

Évalue le nombre d'ANGLES INDEPENDANTS sous lesquels le sujet peut être
interrogé.

Il faut compter des familles de questions réellement différentes,
et non plusieurs variantes d'une même question.

Exemples de portes d'entrée possibles :

- histoire
- géographie
- littérature
- cinéma
- télévision
- musique
- sciences
- politique
- arts
- sport
- langue
- étymologie
- religion
- mythologie
- économie
- société
- inventions
- biographies
- œuvres
- événements historiques
- récompenses
- culture populaire


0 = pratiquement un seul fait ou une seule question possible

1 = sujet extrêmement étroit

2 = quelques questions ou angles proches

3 = plusieurs angles réellement distincts

4 = nombreuses portes d'entrée indépendantes

5 = sujet exceptionnellement transversal permettant un très grand nombre
    de questions différentes


ATTENTION :

Plusieurs détails appartenant tous au même petit domaine ne constituent pas
une forte transversalité.

Par exemple, connaître l'emplacement, la fonction, la vascularisation et
les pathologies d'un organe reste essentiellement un seul domaine :
l'anatomie / médecine.


============================================================
CRITERE 4 — IMPORTANCE
============================================================

Évalue l'importance historique, scientifique, artistique, intellectuelle,
géographique, politique, sportive ou culturelle intrinsèque du sujet.

La question est :

"Quelle place ce sujet occupe-t-il dans un socle solide de culture générale ?"


0 = aucune importance générale identifiable

1 = importance très locale, secondaire, anecdotique ou spécialisée

2 = intérêt réel mais périphérique

3 = sujet significatif dans son domaine et utile en culture générale

4 = sujet majeur ayant laissé une trace importante

5 = sujet fondamental dans l'histoire ou la culture générale mondiale
    ou francophone


ATTENTION :

Être extrêmement important dans une spécialité étroite ne suffit PAS
à obtenir 5.

Une structure anatomique essentielle à la survie humaine n'est pas
automatiquement une connaissance fondamentale de culture générale.

La note doit refléter la place du sujet dans une culture générale large.


============================================================
CRITERE 5 — RENDEMENT_APPRENTISSAGE
============================================================

Évalue à quel point apprendre QUELQUES INFORMATIONS SIMPLES sur ce sujet
permet ensuite de répondre à plusieurs questions différentes.

Ce critère mesure le rendement du temps consacré à son apprentissage.


0 = connaissance presque isolée, très peu réutilisable

1 = rendement très faible ; essentiellement un fait précis

2 = quelques utilisations possibles

3 = apprentissage rentable

4 = très rentable ; quelques repères permettent de résoudre de nombreuses
    questions

5 = rendement exceptionnel ; sujet extrêmement structurant ouvrant l'accès
    à de très nombreuses connaissances


Exemples :

Un petit os, une artère précise ou un terme médical technique peut être
scientifiquement parfaitement valide mais avoir un rendement de 0 ou 1.

À l'inverse, connaître une grande personnalité historique, une grande œuvre,
un pays, un mouvement artistique ou un événement majeur peut donner accès
à de très nombreux repères et obtenir 4 ou 5.


============================================================
CALIBRATION GLOBALE
============================================================

TU DOIS ETRE SEVERE.

Les scores ne doivent surtout pas se concentrer artificiellement entre
60 et 90.

Repères intuitifs pour le score final qui sera calculé ensuite :

90-100
= connaissances absolument incontournables
= catégorie exceptionnelle
= très petite minorité de l'ensemble des sujets

75-89
= sujets de très grande importance en culture générale

60-74
= bonnes connaissances classiques et rentables

40-59
= connaissances secondaires ou spécialisées mais utiles

20-39
= sujets de niche

0-19
= sujets très obscurs, anecdotiques ou extrêmement spécialisés


Il doit être difficile d'atteindre 80.

Il doit être EXCEPTIONNEL d'atteindre 90.

Un sujet ne doit JAMAIS dépasser 90 simplement parce qu'il est :
- scientifiquement fondamental ;
- médicalement important ;
- très connu dans la vie quotidienne ;
- important dans sa spécialité ;
- durable dans le temps ;
- ou artificiellement raccordable à plusieurs thèmes.


============================================================
EXEMPLES DE CALIBRATION
============================================================

Ces exemples servent uniquement à comprendre l'échelle.
Ils ne constituent pas des notes imposées.

NAPOLEON BONAPARTE
Sujet extrêmement célèbre, omniprésent dans les quiz, historique,
géographique, politique, militaire, artistique et culturel.
Il peut légitimement approcher le sommet de l'échelle.

VICTOR HUGO
Figure fondamentale de la littérature française, mais aussi personnalité
historique, politique et culturelle, auteur de nombreuses œuvres classiques.
Score extrêmement élevé.

LOUIS XIV
Figure incontournable de l'histoire de France, Versailles, monarchie,
guerres, arts, architecture, religion, politique.
Score extrêmement élevé.

LES BEATLES
Groupe universellement connu, discographie, membres, histoire de la musique,
culture populaire, Royaume-Uni, records et nombreuses références.
Score extrêmement élevé.

ADELE EXARCHOPOULOS
Personnalité très connue du cinéma français contemporain avec plusieurs
films, récompenses, réalisateurs et références populaires.
Score élevé, mais nettement inférieur aux grandes figures historiques
universelles.

CLAUDE BERNARD
Scientifique français majeur et classique de culture générale.
Sujet important, mais beaucoup moins transversal et fréquent qu'une grande
figure historique comme Napoléon ou Victor Hugo.

INSULINE
Notion scientifique très connue, associée au diabète, au pancréas et à
l'histoire de la médecine.
Sujet important et rentable, mais qui ne doit PAS automatiquement approcher
100.

HYPOPHYSE
Notion classique de culture scientifique mais relativement spécialisée.
Elle ne doit pas être notée comme une connaissance incontournable.

ROTULE
Terme connu du grand public et susceptible d'apparaître en anatomie ou en
médecine, mais avec relativement peu d'angles indépendants.
Une forte notoriété quotidienne ne suffit pas à produire un score élevé.

PERICARDE
Terme anatomique utile mais spécialisé.
Fréquence et rendement généraliste limités.

PISIFORME
Petit os du carpe très spécialisé.
Faible priorité d'apprentissage généraliste.

UN TERME MEDICAL EXTREMEMENT RARE
Doit pouvoir obtenir des 0 et des 1 et finir très près du bas de l'échelle.


============================================================
COMPARAISON IMPLICITE
============================================================

Pour chaque sujet, compare implicitement sa rentabilité à toutes les autres
connaissances que l'on pourrait apprendre dans un coffre contenant des
dizaines de milliers de fiches.

La question n'est PAS :

"Ce sujet est-il intéressant ?"

La question est :

"Parmi des dizaines de milliers de sujets possibles, à quel point celui-ci
mérite-t-il réellement d'être appris en priorité pour devenir très fort
en culture générale ?"


============================================================
JUSTIFICATION
============================================================

Pour chaque sujet, donne UNE SEULE PHRASE très concise.

Elle doit principalement expliquer :
- pourquoi le sujet est rentable ou non ;
- sa fréquence probable dans les quiz ;
- ou ce qui limite sa note.

La justification doit être factuelle.
Elle ne doit pas simplement reformuler les cinq notes.

REGLE SUR LES HOMONYMES ET TITRES AMBIGUS

Évalue UNIQUEMENT le sujet identifié par le chemin et le contexte fournis.

N'ajoute jamais des points grâce à d'autres sens du titre.

Exemples :
- une fiche intitulée "Wellington" ne doit pas cumuler automatiquement
  la capitale de Nouvelle-Zélande, le duc de Wellington et le plat.
- une fiche "French" située dans Cinéma doit être évaluée comme l'œuvre
  précise identifiée par son contexte, pas comme l'ensemble du cinéma français.
- une fiche "Anne" ne doit pas être évaluée comme l'ensemble des personnes
  historiques portant ce prénom.

Si le contexte permet d'identifier une œuvre ou une personne précise,
ignore complètement les homonymes.


IMPORTANT :
Ne calcule PAS toi-même le score final sur 100.

Retourne uniquement :
- les cinq sous-notes entières de 0 à 5 ;
- la justification.
"""


# ============================================================
# MODELES STRUCTURES
# ============================================================

class SubjectScore(BaseModel):
    id: int

    notoriete: int = Field(
        ge=0,
        le=5,
        description="Notoriété comme référence de culture générale."
    )

    frequence_quiz: int = Field(
        ge=0,
        le=5,
        description=(
            "Probabilité que le sujet précis soit directement utile "
            "dans un quiz généraliste."
        )
    )

    transversalite: int = Field(
        ge=0,
        le=5,
        description="Nombre d'angles indépendants de questionnement."
    )

    importance: int = Field(
        ge=0,
        le=5,
        description="Importance dans un socle général de culture générale."
    )

    rendement_apprentissage: int = Field(
        ge=0,
        le=5,
        description=(
            "Rentabilité de l'apprentissage de quelques faits simples "
            "sur ce sujet."
        )
    )

    justification: str


class BatchScores(BaseModel):
    scores: list[SubjectScore]


# ============================================================
# TYPES INTERNES
# ============================================================

@dataclass
class Fiche:
    id: int
    path: Path
    relative_path: str
    title: str
    context: str


# ============================================================
# UTILITAIRES MARKDOWN
# ============================================================

FRONTMATTER_RE = re.compile(
    r"\A---\s*\n.*?\n---\s*(?:\n|$)",
    flags=re.DOTALL,
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def clean_context(text: str, max_chars: int) -> str:
    """
    Produit un court extrait destiné UNIQUEMENT à identifier
    ou désambiguïser le sujet.

    La richesse de ce texte ne doit jamais influencer la note.
    """
    text = strip_frontmatter(text)

    # Retire les blocs de code.
    text = re.sub(
        r"```.*?```",
        " ",
        text,
        flags=re.DOTALL,
    )

    # Retire les images Obsidian.
    text = re.sub(
        r"!\[\[[^\]]+\]\]",
        " ",
        text,
    )

    # Retire les images Markdown.
    text = re.sub(
        r"!\[[^\]]*\]\([^)]+\)",
        " ",
        text,
    )

    # Transforme [[Victor Hugo]] en Victor Hugo
    # et [[Victor Hugo|Hugo]] en Hugo.
    text = re.sub(
        r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
        lambda m: m.group(2) or m.group(1),
        text,
    )

    # Retire les titres Markdown.
    text = re.sub(
        r"^#+\s*",
        "",
        text,
        flags=re.MULTILINE,
    )

    # Retire quelques marqueurs Markdown.
    text = re.sub(
        r"[*_>`~]",
        " ",
        text,
    )

    # Compacte les espaces.
    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text[:max_chars]


def list_fiches(vault_path: Path) -> list[Fiche]:
    """
    Liste les fichiers Markdown du coffre.

    Si RANDOM_SAMPLE=True et MAX_FILES est renseigné,
    tire un échantillon aléatoire reproductible dans tout le coffre.
    """
    if not vault_path.exists():
        raise FileNotFoundError(
            f"Le coffre n'existe pas : {vault_path}\n"
            "Modifie VAULT_PATH en haut du script."
        )

    paths = sorted(
        p
        for p in vault_path.rglob("*.md")
        if ".obsidian" not in p.parts
    )

    total_available = len(paths)

    if MAX_FILES is not None and MAX_FILES < len(paths):
        if RANDOM_SAMPLE:
            rng = random.Random(RANDOM_SEED)
            paths = rng.sample(paths, MAX_FILES)

            # On retrie ensuite pour garder un ordre stable
            # dans les logs et les IDs.
            paths = sorted(paths)
        else:
            paths = paths[:MAX_FILES]

    fiches: list[Fiche] = []

    for i, path in enumerate(paths):
        text = read_text(path)
        relative = str(path.relative_to(vault_path))

        fiches.append(
            Fiche(
                id=i,
                path=path,
                relative_path=relative,
                title=path.stem,
                context=clean_context(
                    text,
                    CONTEXT_CHARS,
                ),
            )
        )

    print(
        f"📚 {total_available} fichiers Markdown disponibles "
        f"dans le coffre."
    )

    return fiches


# ============================================================
# CALCUL DU SCORE
# ============================================================

def calculate_score(item: SubjectScore) -> int:
    """
    Calcule un score absolu sur 100.

    Pondérations :

    - notoriété                20 %
    - fréquence quiz           40 %
    - transversalité           15 %
    - importance               20 %
    - rendement apprentissage   5 %

    La fréquence en quiz est volontairement dominante :
    notre objectif est la rentabilité pour un joueur généraliste.
    """

    weighted_0_to_5 = (
        item.notoriete * 0.20
        + item.frequence_quiz * 0.40
        + item.transversalite * 0.15
        + item.importance * 0.20
        + item.rendement_apprentissage * 0.05
    )

    return round(weighted_0_to_5 * 20)


# ============================================================
# CACHE / REPRISE
# ============================================================

def load_cache() -> dict[str, dict]:
    """
    Charge les résultats déjà calculés.

    Le cache est indexé par chemin relatif et non par titre,
    afin de gérer les éventuels doublons de noms.
    """
    results: dict[str, dict] = {}

    if not CACHE_FILE.exists():
        return results

    with CACHE_FILE.open(
        "r",
        encoding="utf-8",
    ) as f:

        for line in f:
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)

                # Protection supplémentaire :
                # ignore une entrée provenant d'une autre grille.
                if row.get("scoring_version") != SCORING_VERSION:
                    continue

                results[row["relative_path"]] = row

            except Exception:
                # Une dernière ligne partielle après crash
                # ne bloque pas la reprise.
                continue

    return results


def append_cache(row: dict) -> None:
    with CACHE_FILE.open(
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            json.dumps(
                row,
                ensure_ascii=False,
            )
            + "\n"
        )

        f.flush()


def log_error(data: dict) -> None:
    with ERROR_FILE.open(
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            json.dumps(
                data,
                ensure_ascii=False,
            )
            + "\n"
        )


# ============================================================
# APPEL API
# ============================================================

def build_batch_input(batch: list[Fiche]) -> str:
    """
    Prépare le lot envoyé au modèle.
    """
    payload = []

    for fiche in batch:
        payload.append(
            {
                "id": fiche.id,
                "titre": fiche.title,
                "chemin": fiche.relative_path,
                "contexte_desambiguïsation": fiche.context,
            }
        )

    return (
        "Évalue chacun des sujets ci-dessous selon la grille définie "
        "dans les instructions.\n\n"
        "Le contexte ne sert qu'à identifier précisément le sujet. "
        "Ne récompense jamais une fiche parce que son contexte est plus "
        "riche ou plus long.\n\n"
        "Retourne exactement une évaluation pour chaque id fourni.\n\n"
        + json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


def score_batch(
    client: OpenAI,
    batch: list[Fiche],
) -> list[SubjectScore]:

    input_text = build_batch_input(batch)

    expected_ids = {
        fiche.id
        for fiche in batch
    }

    last_error: Optional[Exception] = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            response = client.responses.parse(
                model=MODEL,
                instructions=SYSTEM_PROMPT,
                input=input_text,
                text_format=BatchScores,
            )

            parsed = response.output_parsed

            if parsed is None:
                raise RuntimeError(
                    "Réponse structurée vide."
                )

            returned_ids = {
                item.id
                for item in parsed.scores
            }

            missing = expected_ids - returned_ids
            extra = returned_ids - expected_ids

            if missing or extra:
                raise RuntimeError(
                    "IDs incohérents. "
                    f"Manquants={sorted(missing)}, "
                    f"supplémentaires={sorted(extra)}"
                )

            if len(parsed.scores) != len(returned_ids):
                raise RuntimeError(
                    "La réponse contient des IDs dupliqués."
                )

            return parsed.scores

        except Exception as exc:
            last_error = exc

            if attempt == MAX_RETRIES:
                break

            wait = (
                RETRY_BASE_SECONDS
                * (2 ** (attempt - 1))
            )

            print(
                f"  ⚠️ Échec API "
                f"{attempt}/{MAX_RETRIES}: {exc}\n"
                f"     Nouvelle tentative dans {wait}s..."
            )

            time.sleep(wait)

    raise RuntimeError(
        f"Échec du lot après {MAX_RETRIES} tentatives : "
        f"{last_error}"
    )


# ============================================================
# EXPORT CSV
# ============================================================

CSV_FIELDS = [
    "title",
    "relative_path",
    "score",
    "notoriete",
    "frequence_quiz",
    "transversalite",
    "importance",
    "rendement_apprentissage",
    "justification",
    "model",
    "scoring_version",
]


def export_csv(
    results: dict[str, dict],
) -> None:

    rows = sorted(
        results.values(),
        key=lambda x: (
            -x["score"],
            x["title"].lower(),
        ),
    )

    with CSV_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_FIELDS,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    field: row.get(field, "")
                    for field in CSV_FIELDS
                }
            )


# ============================================================
# ECRITURE YAML OPTIONNELLE
# ============================================================

def set_yaml_scalar(
    text: str,
    field: str,
    value: int,
) -> str:
    """
    Met à jour ou ajoute un champ YAML TOP-LEVEL simple.

    Exemple :

        culture_g_score: 82
    """

    field_re = re.compile(
        rf"(?m)^{re.escape(field)}\s*:\s*.*$"
    )

    if (
        text.startswith("---\n")
        or text.startswith("---\r\n")
    ):
        match = re.match(
            r"\A---\s*\n(.*?)\n---\s*(\n|$)",
            text,
            flags=re.DOTALL,
        )

        if not match:
            raise ValueError(
                "Frontmatter YAML mal formé."
            )

        yaml_body = match.group(1)
        ending = match.group(2)

        if field_re.search(yaml_body):
            yaml_body = field_re.sub(
                f"{field}: {value}",
                yaml_body,
            )

        else:
            if (
                yaml_body
                and not yaml_body.endswith("\n")
            ):
                yaml_body += "\n"

            yaml_body += (
                f"{field}: {value}"
            )

        rest = text[match.end():]

        return (
            f"---\n"
            f"{yaml_body}\n"
            f"---{ending}"
            f"{rest}"
        )

    return (
        f"---\n"
        f"{field}: {value}\n"
        f"---\n\n"
        f"{text}"
    )


def write_scores_to_yaml(
    fiches_by_relative_path: dict[str, Fiche],
    results: dict[str, dict],
) -> None:

    print(
        "\nÉcriture des scores "
        "dans les fiches Markdown..."
    )

    for relative_path, row in results.items():

        fiche = fiches_by_relative_path.get(
            relative_path
        )

        if fiche is None:
            continue

        source = fiche.path
        backup = BACKUP_DIR / relative_path

        backup.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not backup.exists():
            shutil.copy2(
                source,
                backup,
            )

        original = read_text(source)

        modified = set_yaml_scalar(
            original,
            YAML_SCORE_FIELD,
            int(row["score"]),
        )

        if modified != original:
            source.write_text(
                modified,
                encoding="utf-8",
            )

    print(
        "✅ Sauvegardes Markdown : "
        f"{BACKUP_DIR.resolve()}"
    )


# ============================================================
# STATISTIQUES FINALES
# ============================================================

def print_score_distribution(
    results: dict[str, dict],
) -> None:
    """
    Affiche rapidement la distribution des scores.
    Très utile pour vérifier que la grille n'est pas trop généreuse.
    """
    if not results:
        return

    scores = [
        row["score"]
        for row in results.values()
    ]

    buckets = {
        "90-100": 0,
        "75-89": 0,
        "60-74": 0,
        "40-59": 0,
        "20-39": 0,
        "0-19": 0,
    }

    for score in scores:

        if score >= 90:
            buckets["90-100"] += 1

        elif score >= 75:
            buckets["75-89"] += 1

        elif score >= 60:
            buckets["60-74"] += 1

        elif score >= 40:
            buckets["40-59"] += 1

        elif score >= 20:
            buckets["20-39"] += 1

        else:
            buckets["0-19"] += 1

    print("\nDistribution des scores :")

    total = len(scores)

    for label, count in buckets.items():
        percentage = (
            count / total * 100
            if total
            else 0
        )

        print(
            f"  {label:>6} : "
            f"{count:>5} "
            f"({percentage:5.1f} %)"
        )

    print(
        f"\nScore minimum : {min(scores)}"
    )

    print(
        f"Score maximum : {max(scores)}"
    )

    print(
        "Score moyen   : "
        f"{sum(scores) / len(scores):.1f}"
    )


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if WRITE_SCORE_TO_YAML:
        BACKUP_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY n'est pas défini.\n\n"
            "Vérifie que ton fichier .env contient par exemple :\n"
            'OPENAI_API_KEY="sk-..."\n'
        )

    print("==========================================")
    print("SCORING CULTURE GENERALE")
    print("==========================================")

    print(
        f"Grille : {SCORING_VERSION}"
    )

    print(
        f"Modèle : {MODEL}"
    )

    print("\nLecture du coffre...")

    fiches = list_fiches(
        VAULT_PATH
    )

    if not fiches:
        print(
            "Aucune fiche Markdown trouvée."
        )
        return

    print(
        f"✅ {len(fiches)} fiches "
        "sélectionnées pour ce lancement."
    )

    if (
        MAX_FILES is not None
        and RANDOM_SAMPLE
    ):
        print(
            "🎲 Échantillonnage aléatoire activé "
            f"(seed={RANDOM_SEED})."
        )

    cache = load_cache()

    print(
        f"✅ {len(cache)} fiches déjà "
        "présentes dans le cache de cette grille."
    )

    selected_paths = {
        fiche.relative_path
        for fiche in fiches
    }

    # On ne considère comme "faites" que les fiches
    # appartenant à la sélection actuelle.
    cached_selected = {
        path: row
        for path, row in cache.items()
        if path in selected_paths
    }

    remaining = [
        fiche
        for fiche in fiches
        if fiche.relative_path not in cache
    ]

    print(
        f"➡️ {len(remaining)} fiches "
        "restent à scorer."
    )

    print(
        f"📦 Taille des lots : "
        f"{BATCH_SIZE}"
    )

    client = OpenAI()

    total_batches = (
        len(remaining)
        + BATCH_SIZE
        - 1
    ) // BATCH_SIZE

    for batch_index, start in enumerate(
        range(
            0,
            len(remaining),
            BATCH_SIZE,
        ),
        start=1,
    ):

        batch = remaining[
            start:start + BATCH_SIZE
        ]

        print(
            f"\nLot {batch_index}/{total_batches} "
            f"({len(batch)} fiches)"
        )

        try:
            scores = score_batch(
                client,
                batch,
            )

            fiches_by_id = {
                fiche.id: fiche
                for fiche in batch
            }

            for item in scores:

                fiche = fiches_by_id[
                    item.id
                ]

                row = {
                    "title": fiche.title,
                    "relative_path": fiche.relative_path,
                    "score": calculate_score(item),

                    "notoriete": item.notoriete,
                    "frequence_quiz": item.frequence_quiz,
                    "transversalite": item.transversalite,
                    "importance": item.importance,

                    "rendement_apprentissage":
                        item.rendement_apprentissage,

                    "justification":
                        item.justification.strip(),

                    "model": MODEL,
                    "scoring_version":
                        SCORING_VERSION,
                }

                append_cache(row)

                cache[
                    fiche.relative_path
                ] = row

            # Régénère le CSV après chaque lot.
            export_csv(cache)

            done_selected = sum(
                1
                for fiche in fiches
                if fiche.relative_path in cache
            )

            print(
                f"✅ Lot enregistré. "
                f"{done_selected}/{len(fiches)} "
                "fiches de la sélection scorées."
            )

        except KeyboardInterrupt:

            print(
                "\n⏹️ Arrêt demandé. "
                "Le cache est conservé."
            )

            export_csv(cache)
            return

        except Exception as exc:

            print(
                f"❌ Lot impossible : {exc}"
            )

            log_error(
                {
                    "batch_index":
                        batch_index,

                    "files": [
                        fiche.relative_path
                        for fiche in batch
                    ],

                    "error":
                        str(exc),

                    "model":
                        MODEL,

                    "scoring_version":
                        SCORING_VERSION,
                }
            )

            print(
                "Le lot a été consigné dans "
                f"{ERROR_FILE.name}. "
                "Le script continue avec le lot suivant."
            )

    export_csv(cache)

    # Statistiques uniquement sur les fiches
    # correspondant au test / lancement actuel.
    current_results = {
        path: row
        for path, row in cache.items()
        if path in selected_paths
    }

    print_score_distribution(
        current_results
    )

    print("\n==========================================")
    print("TERMINÉ")
    print("==========================================")

    print(
        f"CSV   : {CSV_FILE.resolve()}"
    )

    print(
        f"Cache : {CACHE_FILE.resolve()}"
    )

    if ERROR_FILE.exists():
        print(
            "Erreurs éventuelles : "
            f"{ERROR_FILE.resolve()}"
        )

    if WRITE_SCORE_TO_YAML:

        fiches_by_relative_path = {
            fiche.relative_path: fiche
            for fiche in fiches
        }

        write_scores_to_yaml(
            fiches_by_relative_path,
            current_results,
        )

    else:
        print(
            "\nLes fichiers Markdown "
            "n'ont PAS été modifiés."
        )

        print(
            "Après contrôle du CSV, passe "
            "WRITE_SCORE_TO_YAML = True "
            "si tu veux injecter les scores."
        )


if __name__ == "__main__":
    main()