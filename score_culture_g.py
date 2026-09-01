#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Score automatiquement les fiches Markdown d'un coffre Obsidian
selon leur intérêt pour un entraînement généraliste de culture générale.

Fonctionnalités :
- parcourt tous les .md du coffre ;
- envoie les fiches par lots à l'API OpenAI ;
- utilise des Structured Outputs (Pydantic) ;
- sauvegarde chaque lot dans un cache JSONL ;
- reprend automatiquement après interruption ;
- exporte un CSV final ;
- peut, en option, écrire le score dans le frontmatter YAML ;
- ne dépend PAS des [[liens]] entre fiches.

Installation :
    python3 -m pip install -U openai pydantic

Clé API :
    export OPENAI_API_KEY="sk-..."

Puis :
    python3 score_culture_g.py
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Score automatiquement les fiches Markdown d'un coffre Obsidian.
"""

from __future__ import annotations

import csv
import json
import os
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
# CONFIGURATION À MODIFIER
# ============================================================

# Vault Path
VAULT_PATH = Path(__file__).parent / "data"

# Modèle conseillé :
# - gpt-5.6-luna : économique, adapté à un gros volume
# - gpt-5.6-terra : meilleur compromis qualité/coût
# - gpt-5.6-sol : qualité maximale, plus coûteux
MODEL = "gpt-5.6-luna"

# Nombre de fiches envoyées à chaque appel API.
BATCH_SIZE = 50

# Contexte pris dans chaque fiche pour lever les ambiguïtés.
# Ce contexte ne doit PAS influencer la note selon la richesse de la fiche.
CONTEXT_CHARS = 700

# Fichiers de sortie
OUTPUT_DIR = Path("culture_g_scoring")
CACHE_FILE = OUTPUT_DIR / "scores_cache.jsonl"
CSV_FILE = OUTPUT_DIR / "scores_culture_g.csv"
ERROR_FILE = OUTPUT_DIR / "erreurs.jsonl"

# Par défaut : le script ne modifie AUCUNE fiche Markdown.
WRITE_SCORE_TO_YAML = False

# Nom du champ écrit dans le frontmatter si WRITE_SCORE_TO_YAML = True
YAML_SCORE_FIELD = "culture_g_score"

# Une copie de sauvegarde des fichiers modifiés sera créée ici.
BACKUP_DIR = OUTPUT_DIR / "backup_markdown"

# Retries API
MAX_RETRIES = 6
RETRY_BASE_SECONDS = 2

# Pour tester avant de lancer les 20 000 fiches :
# mets par exemple 100, puis None quand tu es satisfait.
MAX_FILES: Optional[int] = None


# ============================================================
# GRILLE DE NOTATION
# ============================================================

SYSTEM_PROMPT = """
Tu es un expert des questions de culture générale et des jeux télévisés
francophones.

Tu dois évaluer l'intérêt d'apprendre chaque SUJET dans le cadre d'un
entraînement généraliste de haut niveau.

Tu notes le SUJET lui-même, et non la qualité de la fiche Markdown fournie.

OBJECTIF
Le score doit refléter la probabilité que connaître ce sujet permette de
répondre correctement à des questions de culture générale variées.

RÈGLES IMPÉRATIVES
- N'évalue pas la qualité de la fiche.
- N'évalue pas sa longueur.
- N'évalue pas le nombre d'informations présentes.
- N'utilise pas les liens Obsidian comme critère.
- Le contexte fourni sert uniquement à identifier précisément le sujet.
- N'évalue pas uniquement la célébrité.
- Un spécialiste très important dans un domaine étroit doit rester
  relativement bas si son intérêt généraliste est faible.
- Une personnalité, œuvre, lieu ou notion susceptible d'apparaître par
  de nombreux angles doit être mieux notée.
- Raisonne pour des jeux et quiz francophones de culture générale.
- Utilise réellement toute l'échelle 0 à 5.
- La note 5 est exceptionnelle.
- Les notes 0 et 1 doivent réellement être utilisées pour les sujets obscurs.
- Ne surnote pas un sujet simplement parce qu'il est important dans sa
  discipline spécialisée.
- Évalue une connaissance de base utile, pas un niveau d'expertise.

CRITÈRE 1 — NOTORIETE
0 = inconnu hors spécialistes
1 = très niche
2 = connu surtout des amateurs du domaine
3 = classique de culture générale
4 = très connu du grand public cultivé
5 = incontournable

CRITÈRE 2 — FREQUENCE_QUIZ
Probabilité que ce sujet, ou une information directement liée à lui,
apparaisse dans des questions généralistes.
0 = quasiment jamais
1 = très rare / niveau expert
2 = occasionnel
3 = classique
4 = fréquent
5 = marronnier incontournable

CRITÈRE 3 — TRANSVERSALITE
Nombre de portes d'entrée indépendantes permettant de tomber sur ce sujet :
œuvres, personnes liées, événements, géographie, récompenses, histoire,
étymologie, sciences, culture populaire, etc.
0 = un angle extrêmement spécialisé
1 = très peu d'angles
2 = quelques angles
3 = plusieurs angles distincts
4 = nombreuses portes d'entrée
5 = exceptionnellement transversal

CRITÈRE 4 — IMPORTANCE
Importance historique, culturelle, scientifique, géographique, artistique,
politique, sportive ou intellectuelle au-delà d'une simple actualité.
0 = anecdotique
1 = mineur
2 = notable
3 = important
4 = majeur
5 = fondamental

CRITÈRE 5 — PERENNITE
Probabilité que la connaissance reste pertinente en culture générale.
0 = intérêt presque uniquement circonstanciel
1 = risque fort d'oubli
2 = intérêt assez limité dans le temps
3 = probablement durable
4 = solidement installé
5 = intemporel

CALIBRATION
Ces exemples indiquent l'esprit de l'échelle, sans constituer des valeurs
absolues obligatoires :

- Napoléon Bonaparte : extrêmement haut sur tous les critères.
- Victor Hugo : extrêmement haut sur tous les critères.
- Adèle Exarchopoulos : forte notoriété, forte fréquence potentielle,
  très nombreux angles cinématographiques et culturels, mais importance
  historique inférieure aux figures fondamentales.
- André Bazin : important dans l'histoire du cinéma, mais relativement niche
  et moins transversal en culture générale généraliste.
- Une personnalité locale quasiment inconnue hors de son domaine doit recevoir
  des 0 et 1, même si sa fiche est très détaillée.

JUSTIFICATION
Donne une justification très concise, une seule phrase, expliquant surtout
ce qui fait monter ou baisser l'intérêt généraliste.

Ne calcule PAS toi-même le score final sur 100. Donne uniquement les cinq
sous-notes entières de 0 à 5 et la justification.
"""


# ============================================================
# MODÈLES STRUCTURÉS
# ============================================================

class SubjectScore(BaseModel):
    id: int
    notoriete: int = Field(ge=0, le=5)
    frequence_quiz: int = Field(ge=0, le=5)
    transversalite: int = Field(ge=0, le=5)
    importance: int = Field(ge=0, le=5)
    perennite: int = Field(ge=0, le=5)
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
        return path.read_text(encoding="utf-8", errors="replace")


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub("", text, count=1)


def clean_context(text: str, max_chars: int) -> str:
    """
    Produit un petit extrait informatif servant seulement à désambiguïser.
    """
    text = strip_frontmatter(text)

    # Retire les blocs de code, souvent peu utiles pour identifier le sujet.
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)

    # Simplifie les images Obsidian / Markdown.
    text = re.sub(r"!\[\[[^\]]+\]\]", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)

    # Garde le texte des wikilinks mais retire la syntaxe.
    text = re.sub(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
                  lambda m: m.group(2) or m.group(1),
                  text)

    # Enlève quelques marqueurs Markdown.
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>`~]", " ", text)

    # Compacte les espaces.
    text = re.sub(r"\s+", " ", text).strip()

    return text[:max_chars]


def list_fiches(vault_path: Path) -> list[Fiche]:
    if not vault_path.exists():
        raise FileNotFoundError(
            f"Le coffre n'existe pas : {vault_path}\n"
            "Modifie VAULT_PATH en haut du script."
        )

    paths = sorted(
        p for p in vault_path.rglob("*.md")
        if ".obsidian" not in p.parts
    )

    if MAX_FILES is not None:
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
                context=clean_context(text, CONTEXT_CHARS),
            )
        )

    return fiches


# ============================================================
# CALCUL DU SCORE
# ============================================================

def calculate_score(item: SubjectScore) -> int:
    """
    Score absolu sur 100.

    Pondérations :
    - notoriété       30 %
    - fréquence quiz  30 %
    - transversalité  20 %
    - importance      15 %
    - pérennité        5 %
    """
    weighted_0_to_5 = (
        item.notoriete * 0.30
        + item.frequence_quiz * 0.30
        + item.transversalite * 0.20
        + item.importance * 0.15
        + item.perennite * 0.05
    )

    return round(weighted_0_to_5 * 20)


# ============================================================
# CACHE / REPRISE
# ============================================================

def load_cache() -> dict[str, dict]:
    """
    Le cache est indexé par chemin relatif, et non par titre,
    pour gérer les éventuels doublons de noms.
    """
    results: dict[str, dict] = {}

    if not CACHE_FILE.exists():
        return results

    with CACHE_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
                results[row["relative_path"]] = row
            except Exception:
                # Une dernière ligne partielle après crash ne bloque pas la reprise.
                continue

    return results


def append_cache(row: dict) -> None:
    with CACHE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()


def log_error(data: dict) -> None:
    with ERROR_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


# ============================================================
# APPEL API
# ============================================================

def build_batch_input(batch: list[Fiche]) -> str:
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
        "Évalue les sujets suivants. "
        "Retourne exactement une évaluation pour chaque id fourni.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def score_batch(
    client: OpenAI,
    batch: list[Fiche],
) -> list[SubjectScore]:

    input_text = build_batch_input(batch)
    expected_ids = {f.id for f in batch}

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.responses.parse(
                model=MODEL,
                instructions=SYSTEM_PROMPT,
                input=input_text,
                text_format=BatchScores,
            )

            parsed = response.output_parsed

            if parsed is None:
                raise RuntimeError("Réponse structurée vide.")

            returned_ids = {x.id for x in parsed.scores}

            missing = expected_ids - returned_ids
            extra = returned_ids - expected_ids

            if missing or extra:
                raise RuntimeError(
                    f"IDs incohérents. Manquants={sorted(missing)}, "
                    f"supplémentaires={sorted(extra)}"
                )

            # Évite les doublons d'id.
            if len(parsed.scores) != len(returned_ids):
                raise RuntimeError("La réponse contient des IDs dupliqués.")

            return parsed.scores

        except Exception as exc:
            last_error = exc

            if attempt == MAX_RETRIES:
                break

            wait = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            print(
                f"  ⚠️  Échec API {attempt}/{MAX_RETRIES}: {exc}\n"
                f"     Nouvelle tentative dans {wait}s..."
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Échec du lot après {MAX_RETRIES} tentatives : {last_error}"
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
    "perennite",
    "justification",
    "model",
]


def export_csv(results: dict[str, dict]) -> None:
    rows = sorted(
        results.values(),
        key=lambda x: (-x["score"], x["title"].lower())
    )

    with CSV_FILE.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()

        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


# ============================================================
# ÉCRITURE YAML OPTIONNELLE
# ============================================================

def set_yaml_scalar(text: str, field: str, value: int) -> str:
    """
    Met à jour ou ajoute un champ YAML TOP-LEVEL simple,
    en préservant le reste du frontmatter.

    Exemple :
        culture_g_score: 82
    """
    field_re = re.compile(
        rf"(?m)^{re.escape(field)}\s*:\s*.*$"
    )

    if text.startswith("---\n") or text.startswith("---\r\n"):
        match = re.match(r"\A---\s*\n(.*?)\n---\s*(\n|$)", text, flags=re.DOTALL)

        if not match:
            raise ValueError("Frontmatter YAML mal formé.")

        yaml_body = match.group(1)
        ending = match.group(2)

        if field_re.search(yaml_body):
            yaml_body = field_re.sub(f"{field}: {value}", yaml_body)
        else:
            if yaml_body and not yaml_body.endswith("\n"):
                yaml_body += "\n"
            yaml_body += f"{field}: {value}"

        rest = text[match.end():]
        return f"---\n{yaml_body}\n---{ending}{rest}"

    return f"---\n{field}: {value}\n---\n\n{text}"


def write_scores_to_yaml(
    fiches_by_relative_path: dict[str, Fiche],
    results: dict[str, dict],
) -> None:

    print("\nÉcriture des scores dans les fiches Markdown...")

    for relative_path, row in results.items():
        fiche = fiches_by_relative_path.get(relative_path)
        if fiche is None:
            continue

        source = fiche.path
        backup = BACKUP_DIR / relative_path
        backup.parent.mkdir(parents=True, exist_ok=True)

        if not backup.exists():
            shutil.copy2(source, backup)

        original = read_text(source)
        modified = set_yaml_scalar(
            original,
            YAML_SCORE_FIELD,
            int(row["score"]),
        )

        if modified != original:
            source.write_text(modified, encoding="utf-8")

    print(f"✅ Sauvegardes Markdown : {BACKUP_DIR.resolve()}")


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if WRITE_SCORE_TO_YAML:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY n'est pas défini.\n\n"
            'Sur macOS/Linux :\n'
            '  export OPENAI_API_KEY="sk-..."\n\n'
            "Puis relance le script."
        )

    print("Lecture du coffre...")
    fiches = list_fiches(VAULT_PATH)

    if not fiches:
        print("Aucune fiche Markdown trouvée.")
        return

    print(f"✅ {len(fiches)} fiches trouvées.")

    cache = load_cache()
    print(f"✅ {len(cache)} fiches déjà présentes dans le cache.")

    remaining = [
        fiche for fiche in fiches
        if fiche.relative_path not in cache
    ]

    print(f"➡️  {len(remaining)} fiches restent à scorer.")
    print(f"🤖 Modèle : {MODEL}")
    print(f"📦 Taille des lots : {BATCH_SIZE}")

    client = OpenAI()

    total_batches = (len(remaining) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_index, start in enumerate(
        range(0, len(remaining), BATCH_SIZE),
        start=1,
    ):
        batch = remaining[start:start + BATCH_SIZE]

        print(
            f"\nLot {batch_index}/{total_batches} "
            f"({len(batch)} fiches)"
        )

        try:
            scores = score_batch(client, batch)

            fiches_by_id = {fiche.id: fiche for fiche in batch}

            for item in scores:
                fiche = fiches_by_id[item.id]

                row = {
                    "title": fiche.title,
                    "relative_path": fiche.relative_path,
                    "score": calculate_score(item),
                    "notoriete": item.notoriete,
                    "frequence_quiz": item.frequence_quiz,
                    "transversalite": item.transversalite,
                    "importance": item.importance,
                    "perennite": item.perennite,
                    "justification": item.justification.strip(),
                    "model": MODEL,
                }

                append_cache(row)
                cache[fiche.relative_path] = row

            # Le CSV est régénéré après chaque lot :
            # même un Ctrl+C laisse donc un résultat exploitable.
            export_csv(cache)

            done = len(cache)
            print(
                f"✅ Lot enregistré. "
                f"{done}/{len(fiches)} fiches scorées."
            )

        except KeyboardInterrupt:
            print("\n⏹️ Arrêt demandé. Le cache est conservé.")
            export_csv(cache)
            return

        except Exception as exc:
            print(f"❌ Lot impossible : {exc}")

            log_error(
                {
                    "batch_index": batch_index,
                    "files": [f.relative_path for f in batch],
                    "error": str(exc),
                }
            )

            print(
                "Le lot a été consigné dans erreurs.jsonl. "
                "Le script continue avec le lot suivant."
            )

    export_csv(cache)

    print("\n==========================================")
    print("TERMINÉ")
    print("==========================================")
    print(f"CSV :   {CSV_FILE.resolve()}")
    print(f"Cache : {CACHE_FILE.resolve()}")

    if ERROR_FILE.exists():
        print(f"Erreurs éventuelles : {ERROR_FILE.resolve()}")

    if WRITE_SCORE_TO_YAML:
        fiches_by_relative_path = {
            f.relative_path: f for f in fiches
        }
        write_scores_to_yaml(fiches_by_relative_path, cache)
    else:
        print(
            "\nLes fichiers Markdown n'ont PAS été modifiés."
            "\nAprès contrôle du CSV, passe WRITE_SCORE_TO_YAML = True "
            "si tu veux injecter les scores."
        )


if __name__ == "__main__":
    main()
