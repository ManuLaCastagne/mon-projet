#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Score automatiquement les fiches Markdown d'un coffre Obsidian
selon leur intérêt pour un entraînement généraliste de haut niveau
en culture générale.

Le script :
- parcourt les fichiers Markdown du coffre ;
- permet d'exclure certains dossiers ;
- utilise le titre + un court extrait uniquement pour désambiguïser ;
- demande à l'IA cinq sous-notes de 0 à 5 ;
- calcule localement un score absolu sur 100 ;
- conserve un cache permettant de reprendre après interruption ;
- exporte un CSV trié par score ;
- peut écrire automatiquement le score + la justification
  dans le frontmatter YAML de chaque fiche ;
- sauvegarde les fichiers Markdown avant modification.

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

VAULT_PATH = Path(__file__).parent / "data"

MODEL = "gpt-5.6-luna"

# Change cette version dès que tu modifies fortement :
# - le prompt
# - les critères
# - les pondérations
SCORING_VERSION = "v3"

BATCH_SIZE = 50
CONTEXT_CHARS = 700

# ============================================================
# MODE TEST / ÉCHANTILLONNAGE
# ============================================================

# 200 pour tester.
# None pour traiter tout le coffre.
MAX_FILES: Optional[int] = None

RANDOM_SAMPLE = True
RANDOM_SEED = 42


# ============================================================
# SORTIES
# ============================================================

OUTPUT_DIR = Path("culture_g_scoring")

CACHE_FILE = (
    OUTPUT_DIR
    / f"scores_cache_{SCORING_VERSION}.jsonl"
)

CSV_FILE = (
    OUTPUT_DIR
    / f"scores_culture_g_{SCORING_VERSION}.csv"
)

ERROR_FILE = (
    OUTPUT_DIR
    / f"erreurs_{SCORING_VERSION}.jsonl"
)


# ============================================================
# ÉCRITURE OBSIDIAN
# ============================================================

WRITE_SCORE_TO_YAML = True

YAML_SCORE_FIELD = "culture_g_score"

YAML_JUSTIFICATION_FIELD = (
    "culture_g_justification"
)

BACKUP_DIR = (
    OUTPUT_DIR
    / f"backup_markdown_{SCORING_VERSION}"
)


# ============================================================
# API / RETRIES
# ============================================================

MAX_RETRIES = 6
RETRY_BASE_SECONDS = 2


# ============================================================
# RÉPERTOIRES À EXCLURE
# ============================================================

# Tout dossier portant exactement l'un de ces noms
# sera ignoré, quel que soit son emplacement.

EXCLUDED_DIRS = {
    "Frises",
    "Accroches personnelles",
    "Templates",
    "attachments",
    "Listes",
    "Culture générale",
    "Vocabulaire",
    "Chronologie"
}

# ATTENTION :
# Si tu ajoutes "Culture générale" ici,
# TOUT ce dossier sera ignoré.

# Pour exclure uniquement un chemin précis :

EXCLUDED_PATHS = {
    # "Culture générale/Personnel",
    # "Télévision/Archives",
}


# ============================================================
# PROMPT
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


============================================================
CRITERE 4 — IMPORTANCE
============================================================

Évalue l'importance historique, scientifique, artistique, intellectuelle,
géographique, politique, sportive ou culturelle intrinsèque du sujet.

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

La note doit refléter la place du sujet dans une culture générale large.


============================================================
CRITERE 5 — RENDEMENT_APPRENTISSAGE
============================================================

Évalue à quel point apprendre QUELQUES INFORMATIONS SIMPLES sur ce sujet
permet ensuite de répondre à plusieurs questions différentes.

0 = connaissance presque isolée, très peu réutilisable
1 = rendement très faible ; essentiellement un fait précis
2 = quelques utilisations possibles
3 = apprentissage rentable
4 = très rentable ; quelques repères permettent de résoudre de nombreuses
    questions
5 = rendement exceptionnel ; sujet extrêmement structurant ouvrant l'accès
    à de très nombreuses connaissances


============================================================
REGLE DE DISCRIMINATION DES NOTES 4 ET 5
============================================================

Ne produis PAS mécaniquement des profils homogènes du type 4/4/4/4/4.

Chaque critère doit être évalué indépendamment.

La note 4 signifie déjà que le sujet se situe nettement au-dessus de la
moyenne des connaissances de culture générale.

Pour un coffre contenant plusieurs dizaines de milliers de sujets :

- la majorité des sujets utiles doivent recevoir des 2 ou des 3 ;
- 4 doit être réservé aux sujets clairement très forts sur le critère ;
- 5 doit être exceptionnel.

Un bon sujet classique de culture générale n'a PAS automatiquement 4 partout.

Exemples :

- une grande ville étrangère connue peut avoir une notoriété de 4 mais une
  fréquence quiz de seulement 3 ;
- un acteur connu peut avoir une notoriété de 4 mais une importance de 2 ou 3 ;
- une édition précise des Jeux olympiques peut être intéressante mais sa
  transversalité reste souvent limitée ;
- un pays connu n'est pas automatiquement un sujet fréquent à 4 ;
- une œuvre connue n'est pas automatiquement une œuvre majeure à 4.


============================================================
CALIBRATION GLOBALE
============================================================

TU DOIS ETRE SEVERE.

Les scores ne doivent surtout pas se concentrer artificiellement entre
60 et 90.

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


============================================================
EXEMPLES DE CALIBRATION
============================================================

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

ROTULE
Terme connu du grand public mais avec relativement peu d'angles indépendants.

PERICARDE
Terme anatomique utile mais spécialisé.

PISIFORME
Petit os du carpe très spécialisé.


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
REGLE SUR LES HOMONYMES ET TITRES AMBIGUS
============================================================

Évalue UNIQUEMENT le sujet identifié par le chemin et le contexte fournis.

N'ajoute jamais des points grâce à d'autres sens du titre.

Exemples :

- une fiche intitulée "Wellington" ne doit pas cumuler automatiquement
  la capitale de Nouvelle-Zélande, le duc de Wellington et le plat ;

- une fiche "French" située dans Cinéma doit être évaluée comme l'œuvre
  précise identifiée par son contexte, pas comme l'ensemble du cinéma français ;

- une fiche "Anne" ne doit pas être évaluée comme l'ensemble des personnes
  historiques portant ce prénom.

Si le contexte permet d'identifier une œuvre ou une personne précise,
ignore complètement les homonymes.


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
    )

    frequence_quiz: int = Field(
        ge=0,
        le=5,
    )

    transversalite: int = Field(
        ge=0,
        le=5,
    )

    importance: int = Field(
        ge=0,
        le=5,
    )

    rendement_apprentissage: int = Field(
        ge=0,
        le=5,
    )

    justification: str


class BatchScores(BaseModel):
    scores: list[SubjectScore]


# ============================================================
# TYPE INTERNE
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
    r"\A---\s*\r?\n.*?\r?\n---\s*(?:\r?\n|$)",
    flags=re.DOTALL,
)


def read_text(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8"
        )
    except UnicodeDecodeError:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub(
        "",
        text,
        count=1,
    )


def clean_context(
    text: str,
    max_chars: int,
) -> str:

    text = strip_frontmatter(text)

    text = re.sub(
        r"```.*?```",
        " ",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"!\[\[[^\]]+\]\]",
        " ",
        text,
    )

    text = re.sub(
        r"!\[[^\]]*\]\([^)]+\)",
        " ",
        text,
    )

    text = re.sub(
        r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
        lambda m: m.group(2) or m.group(1),
        text,
    )

    text = re.sub(
        r"^#+\s*",
        "",
        text,
        flags=re.MULTILINE,
    )

    text = re.sub(
        r"[*_>`~]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text[:max_chars]


# ============================================================
# EXCLUSIONS
# ============================================================

def is_excluded(
    path: Path,
    vault_path: Path,
) -> bool:

    relative = path.relative_to(
        vault_path
    )

    # Exclusion par nom de dossier.
    if any(
        part in EXCLUDED_DIRS
        for part in relative.parts[:-1]
    ):
        return True

    relative_posix = (
        relative.as_posix()
    )

    # Exclusion par chemin précis.
    for excluded_path in EXCLUDED_PATHS:

        excluded_path = (
            excluded_path.strip("/")
        )

        if (
            relative_posix.startswith(
                excluded_path + "/"
            )
            or relative_posix
            == excluded_path
        ):
            return True

    return False


# ============================================================
# LISTE DES FICHES
# ============================================================

def list_fiches(
    vault_path: Path,
) -> list[Fiche]:

    if not vault_path.exists():
        raise FileNotFoundError(
            f"Le coffre n'existe pas : {vault_path}"
        )

    paths = sorted(
        p
        for p in vault_path.rglob("*.md")
        if ".obsidian" not in p.parts
        and not is_excluded(
            p,
            vault_path,
        )
    )

    total_available = len(paths)

    if (
        MAX_FILES is not None
        and MAX_FILES < len(paths)
    ):
        if RANDOM_SAMPLE:

            rng = random.Random(
                RANDOM_SEED
            )

            paths = rng.sample(
                paths,
                MAX_FILES,
            )

            paths = sorted(paths)

        else:
            paths = paths[:MAX_FILES]

    fiches: list[Fiche] = []

    for i, path in enumerate(paths):

        text = read_text(path)

        relative = (
            path.relative_to(
                vault_path
            ).as_posix()
        )

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
        f"📚 {total_available} fichiers Markdown "
        "disponibles après exclusions."
    )

    return fiches


# ============================================================
# SCORE FINAL
# ============================================================

def calculate_score(
    item: SubjectScore,
) -> int:

    weighted_0_to_5 = (
        item.notoriete * 0.20
        + item.frequence_quiz * 0.40
        + item.transversalite * 0.15
        + item.importance * 0.20
        + item.rendement_apprentissage * 0.05
    )

    return round(
        weighted_0_to_5 * 20
    )


# ============================================================
# CACHE
# ============================================================

def load_cache() -> dict[str, dict]:

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

                if (
                    row.get(
                        "scoring_version"
                    )
                    != SCORING_VERSION
                ):
                    continue

                results[
                    row["relative_path"]
                ] = row

            except Exception:
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
# API
# ============================================================

def build_batch_input(
    batch: list[Fiche],
) -> str:

    payload = []

    for fiche in batch:

        payload.append(
            {
                "id": fiche.id,
                "titre": fiche.title,
                "chemin": fiche.relative_path,
                "contexte_desambiguïsation":
                    fiche.context,
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

    input_text = build_batch_input(
        batch
    )

    expected_ids = {
        fiche.id
        for fiche in batch
    }

    last_error: Optional[
        Exception
    ] = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            response = (
                client.responses.parse(
                    model=MODEL,
                    instructions=SYSTEM_PROMPT,
                    input=input_text,
                    text_format=BatchScores,
                )
            )

            parsed = (
                response.output_parsed
            )

            if parsed is None:
                raise RuntimeError(
                    "Réponse structurée vide."
                )

            returned_ids = {
                item.id
                for item in parsed.scores
            }

            missing = (
                expected_ids
                - returned_ids
            )

            extra = (
                returned_ids
                - expected_ids
            )

            if missing or extra:
                raise RuntimeError(
                    "IDs incohérents. "
                    f"Manquants={sorted(missing)}, "
                    f"supplémentaires={sorted(extra)}"
                )

            if (
                len(parsed.scores)
                != len(returned_ids)
            ):
                raise RuntimeError(
                    "La réponse contient des IDs dupliqués."
                )

            return parsed.scores

        except Exception as exc:

            last_error = exc

            if (
                attempt
                == MAX_RETRIES
            ):
                break

            wait = (
                RETRY_BASE_SECONDS
                * (
                    2
                    ** (
                        attempt - 1
                    )
                )
            )

            print(
                f"  ⚠️ Échec API "
                f"{attempt}/{MAX_RETRIES}: "
                f"{exc}\n"
                f"     Nouvelle tentative "
                f"dans {wait}s..."
            )

            time.sleep(wait)

    raise RuntimeError(
        f"Échec du lot après "
        f"{MAX_RETRIES} tentatives : "
        f"{last_error}"
    )


# ============================================================
# CSV
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


def filter_results(
    results: dict[str, dict],
    allowed_paths: set[str],
) -> dict[str, dict]:

    return {
        path: row
        for path, row
        in results.items()
        if path in allowed_paths
    }


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
                    field: row.get(
                        field,
                        "",
                    )
                    for field
                    in CSV_FIELDS
                }
            )


# ============================================================
# YAML / OBSIDIAN
# ============================================================

def yaml_string(
    value: str,
) -> str:

    return json.dumps(
        str(value),
        ensure_ascii=False,
    )


def update_frontmatter_fields(
    path: Path,
    score: int,
    justification: str,
) -> None:

    text = read_text(path)

    values = {
        YAML_SCORE_FIELD:
            str(int(score)),

        YAML_JUSTIFICATION_FIELD:
            yaml_string(
                justification.strip()
            ),
    }

    # --------------------------------------------------------
    # Frontmatter existant
    # --------------------------------------------------------

    if (
        text.startswith("---\n")
        or text.startswith("---\r\n")
    ):

        match = re.match(
            r"\A---\s*\r?\n"
            r"(.*?)"
            r"\r?\n---\s*"
            r"(?:\r?\n|$)",
            text,
            flags=re.DOTALL,
        )

        if not match:
            raise ValueError(
                f"Frontmatter YAML mal formé : "
                f"{path}"
            )

        yaml_body = (
            match.group(1)
        )

        rest = (
            text[match.end():]
        )

        for (
            field,
            yaml_value,
        ) in values.items():

            field_re = re.compile(
                rf"(?m)^"
                rf"{re.escape(field)}"
                rf"\s*:.*$"
            )

            new_line = (
                f"{field}: "
                f"{yaml_value}"
            )

            if field_re.search(
                yaml_body
            ):

                yaml_body = (
                    field_re.sub(
                        lambda _:
                            new_line,
                        yaml_body,
                    )
                )

            else:

                if yaml_body:
                    yaml_body += "\n"

                yaml_body += new_line

        new_text = (
            "---\n"
            f"{yaml_body}\n"
            "---\n"
        )

        if rest:
            new_text += (
                rest.lstrip(
                    "\r\n"
                )
            )

    # --------------------------------------------------------
    # Pas de frontmatter
    # --------------------------------------------------------

    else:

        new_text = (
            "---\n"
            f"{YAML_SCORE_FIELD}: "
            f"{int(score)}\n"
            f"{YAML_JUSTIFICATION_FIELD}: "
            f"{yaml_string(justification.strip())}\n"
            "---\n\n"
            f"{text}"
        )

    path.write_text(
        new_text,
        encoding="utf-8",
    )


def write_scores_to_yaml(
    results: dict[str, dict],
) -> None:

    if not WRITE_SCORE_TO_YAML:
        return

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    written = 0
    errors = 0

    for (
        relative_path,
        row,
    ) in results.items():

        fiche_path = (
            VAULT_PATH
            / relative_path
        )

        if not fiche_path.exists():

            print(
                "⚠️ Fichier introuvable : "
                f"{fiche_path}"
            )

            errors += 1
            continue

        try:

            # Backup original
            backup_path = (
                BACKUP_DIR
                / relative_path
            )

            backup_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            if not backup_path.exists():

                shutil.copy2(
                    fiche_path,
                    backup_path,
                )

            # Écriture
            update_frontmatter_fields(
                path=fiche_path,
                score=int(
                    row["score"]
                ),
                justification=row.get(
                    "justification",
                    "",
                ),
            )

            written += 1

        except Exception as exc:

            errors += 1

            print(
                f"❌ Impossible de modifier "
                f"{relative_path} : "
                f"{exc}"
            )

    print(
        f"\n📝 {written} fiches "
        "mises à jour dans Obsidian."
    )

    print(
        f"💾 Backups : "
        f"{BACKUP_DIR.resolve()}"
    )

    if errors:

        print(
            f"⚠️ {errors} fiche(s) "
            "non modifiée(s)."
        )


# ============================================================
# STATISTIQUES
# ============================================================

def print_score_distribution(
    results: dict[str, dict],
) -> None:

    if not results:
        return

    scores = [
        row["score"]
        for row
        in results.values()
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
            buckets[
                "90-100"
            ] += 1

        elif score >= 75:
            buckets[
                "75-89"
            ] += 1

        elif score >= 60:
            buckets[
                "60-74"
            ] += 1

        elif score >= 40:
            buckets[
                "40-59"
            ] += 1

        elif score >= 20:
            buckets[
                "20-39"
            ] += 1

        else:
            buckets[
                "0-19"
            ] += 1

    print(
        "\nDistribution des scores :"
    )

    total = len(scores)

    for (
        label,
        count,
    ) in buckets.items():

        percentage = (
            count
            / total
            * 100
        )

        print(
            f"  {label:>6} : "
            f"{count:>5} "
            f"({percentage:5.1f} %)"
        )

    print(
        f"\nScore minimum : "
        f"{min(scores)}"
    )

    print(
        f"Score maximum : "
        f"{max(scores)}"
    )

    print(
        "Score moyen   : "
        f"{sum(scores) / len(scores):.1f}"
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not os.getenv(
        "OPENAI_API_KEY"
    ):

        raise RuntimeError(
            "OPENAI_API_KEY n'est pas défini.\n\n"
            "Vérifie ton fichier .env :\n"
            'OPENAI_API_KEY="sk-..."\n'
        )

    print(
        "=========================================="
    )

    print(
        "SCORING CULTURE GENERALE"
    )

    print(
        "=========================================="
    )

    print(
        f"Grille : "
        f"{SCORING_VERSION}"
    )

    print(
        f"Modèle : "
        f"{MODEL}"
    )

    print(
        "\nLecture du coffre..."
    )

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
        "sélectionnées."
    )

    if (
        MAX_FILES is not None
        and RANDOM_SAMPLE
    ):

        print(
            "🎲 Échantillonnage "
            f"(seed={RANDOM_SEED})."
        )

    selected_paths = {
        fiche.relative_path
        for fiche in fiches
    }

    cache = load_cache()

    cached_selected = (
        filter_results(
            cache,
            selected_paths,
        )
    )

    print(
        f"✅ {len(cached_selected)} fiches "
        "de cette sélection sont déjà "
        "dans le cache."
    )

    remaining = [
        fiche
        for fiche in fiches
        if fiche.relative_path
        not in cache
    ]

    print(
        f"➡️ {len(remaining)} fiches "
        "restent à scorer."
    )

    print(
        f"📦 Taille des lots : "
        f"{BATCH_SIZE}"
    )

    # --------------------------------------------------------
    # Si tout est déjà en cache, inutile d'appeler l'API.
    # --------------------------------------------------------

    if remaining:

        client = OpenAI()

        total_batches = (
            len(remaining)
            + BATCH_SIZE
            - 1
        ) // BATCH_SIZE

        for (
            batch_index,
            start,
        ) in enumerate(
            range(
                0,
                len(remaining),
                BATCH_SIZE,
            ),
            start=1,
        ):

            batch = remaining[
                start:
                start + BATCH_SIZE
            ]

            print(
                f"\nLot "
                f"{batch_index}/"
                f"{total_batches} "
                f"({len(batch)} fiches)"
            )

            try:

                scores = score_batch(
                    client,
                    batch,
                )

                fiches_by_id = {
                    fiche.id: fiche
                    for fiche
                    in batch
                }

                for item in scores:

                    fiche = (
                        fiches_by_id[
                            item.id
                        ]
                    )

                    row = {
                        "title":
                            fiche.title,

                        "relative_path":
                            fiche.relative_path,

                        "score":
                            calculate_score(
                                item
                            ),

                        "notoriete":
                            item.notoriete,

                        "frequence_quiz":
                            item.frequence_quiz,

                        "transversalite":
                            item.transversalite,

                        "importance":
                            item.importance,

                        "rendement_apprentissage":
                            item.rendement_apprentissage,

                        "justification":
                            item.justification.strip(),

                        "model":
                            MODEL,

                        "scoring_version":
                            SCORING_VERSION,
                    }

                    append_cache(row)

                    cache[
                        fiche.relative_path
                    ] = row

                # CSV uniquement avec
                # la sélection actuelle.
                export_csv(
                    filter_results(
                        cache,
                        selected_paths,
                    )
                )

                done_selected = sum(
                    1
                    for fiche
                    in fiches
                    if fiche.relative_path
                    in cache
                )

                print(
                    f"✅ Lot enregistré. "
                    f"{done_selected}/"
                    f"{len(fiches)} fiches."
                )

            except KeyboardInterrupt:

                print(
                    "\n⏹️ Arrêt demandé. "
                    "Le cache est conservé."
                )

                export_csv(
                    filter_results(
                        cache,
                        selected_paths,
                    )
                )

                return

            except Exception as exc:

                print(
                    f"❌ Lot impossible : "
                    f"{exc}"
                )

                log_error(
                    {
                        "batch_index":
                            batch_index,

                        "files": [
                            fiche.relative_path
                            for fiche
                            in batch
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
                    "Le lot a été consigné "
                    f"dans {ERROR_FILE.name}."
                )

    # --------------------------------------------------------
    # Résultats actuels
    # --------------------------------------------------------

    current_results = (
        filter_results(
            cache,
            selected_paths,
        )
    )

    export_csv(
        current_results
    )

    print_score_distribution(
        current_results
    )

    # --------------------------------------------------------
    # Injection Obsidian
    # --------------------------------------------------------

    if WRITE_SCORE_TO_YAML:

        print(
            "\nInjection dans les "
            "fiches Obsidian..."
        )

        write_scores_to_yaml(
            current_results
        )

    else:

        print(
            "\nLes fichiers Markdown "
            "n'ont PAS été modifiés."
        )

    # --------------------------------------------------------
    # Fin
    # --------------------------------------------------------

    print(
        "\n=========================================="
    )

    print(
        "TERMINÉ"
    )

    print(
        "=========================================="
    )

    print(
        f"CSV   : "
        f"{CSV_FILE.resolve()}"
    )

    print(
        f"Cache : "
        f"{CACHE_FILE.resolve()}"
    )

    if ERROR_FILE.exists():

        print(
            "Erreurs éventuelles : "
            f"{ERROR_FILE.resolve()}"
        )


if __name__ == "__main__":
    main()