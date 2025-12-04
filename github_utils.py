import base64
import requests
import streamlit as st
import unicodedata
from urllib.parse import quote

def normalize_path(path: str) -> str:
    """Force NFC normalization to avoid accented filename issues."""
    return unicodedata.normalize("NFC", path)


def get_file_sha(path):
    """
    Récupère le SHA, ou None si le fichier n'existe pas.
    """
    path = normalize_path(path)

    url = f"https://api.github.com/repos/{st.secrets['GITHUB_USERNAME']}/{st.secrets['GITHUB_REPO']}/contents/{quote(path)}"
    headers = {"Authorization": f"token {st.secrets['GITHUB_TOKEN']}"}

    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        return r.json()["sha"]
    elif r.status_code == 404:
        return None
    else:
        st.error(f"Erreur get_file_sha: {r.text}")
        return None


def create_file(path, content, message="Create file"):
    path = normalize_path(path)

    url = f"https://api.github.com/repos/{st.secrets['GITHUB_USERNAME']}/{st.secrets['GITHUB_REPO']}/contents/{quote(path)}"
    headers = {"Authorization": f"token {st.secrets['GITHUB_TOKEN']}"}

    data = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": "main"
    }

    r = requests.put(url, headers=headers, json=data)
    print("PUT URL =", url)
    print("HTTP STATUS =", r.status_code, "→", r.text)

    if r.status_code in (200, 201):
        return True
    else:
        st.error(f"Erreur GitHub (create): {r.text}")
        return False


def update_file(path, content, message="Update file"):
    """Crée ou met à jour un fichier dans GitHub."""
    path = normalize_path(path)
    content = unicodedata.normalize("NFC", content)

    sha = get_file_sha(path)

    url = f"https://api.github.com/repos/{st.secrets['GITHUB_USERNAME']}/{st.secrets['GITHUB_REPO']}/contents/{quote(path)}"
    headers = {"Authorization": f"token {st.secrets['GITHUB_TOKEN']}"}

    data = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": "main",
        "sha": sha
    }

    r = requests.put(url, headers=headers, json=data)

    if r.status_code in (200, 201):
        return True
    else:
        st.error(f"Erreur GitHub (update): {r.text}")
        return False


def write_content_to_github(path, content):
    """
    Sauvegarde un fichier dans GitHub :
    - Si le fichier existe → update
    - Si le fichier n’existe pas → create
    """
    path = normalize_path(path)
    content = unicodedata.normalize("NFC", content)

    sha = get_file_sha(path)

    if sha is None:
        success = create_file(path, content, message=f"Create {path}")
        return success
    else:
        success = update_file(path, content, message=f"Update {path}")
        return success


def read_file(path):
    """Lit un fichier dans le repository GitHub et renvoie son contenu texte."""
    path = normalize_path(path)
    url = f"https://api.github.com/repos/{st.secrets['GITHUB_USERNAME']}/{st.secrets['GITHUB_REPO']}/contents/{quote(path)}"
    headers = {"Authorization": f"token {st.secrets['GITHUB_TOKEN']}"

    }
    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return content

    elif r.status_code == 404:
        st.warning(f"📄 Fichier introuvable dans GitHub : {path}")
        return None

    else:
        st.error(f"❌ Erreur GitHub read ({path}) : {r.text}")
        return None
