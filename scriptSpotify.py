import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import re
import os
from collections import defaultdict
import difflib
from openai import OpenAI

client = OpenAI(api_key='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')
# ⚙️ Paramètres Spotify (remplacez par vos valeurs)
CLIENT_ID = "ca399699f3c04c12916277239cbac3ab"
CLIENT_SECRET = "f3268df9656c4193a702a46fa0a972b2"
REDIRECT_URI = "https://open.spotify.com/"
USERNAME = "e.dumas24"
output_dir = '/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance'

scope = "playlist-read-private playlist-modify-public playlist-modify-private"
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                            client_secret=CLIENT_SECRET,
                                            redirect_uri=REDIRECT_URI,
                                            scope=scope))

def return_prompt_spotify(fiche_path):
    with open(fiche_path, 'r') as fiche:
        content = fiche.read()
        # Extraire la définition après "######Description"
        description = content.split('###### Description')[1]
    
    prompt = f"""
    À partir de la fiche suivante, retourne uniquement le titre d’une chanson qui reprend le titre le plus pertinent de la fiche, ou, à défaut, la bande originale d’un film mentionné.

    Le format de ta réponse doit toujours être exactement celui-ci :
    track: "<titre exact>" artist: "<nom exact>"

    Exemples :
    - Pour une fiche sur Joe Jackson et la chanson "Is She Really Going Out With Him?", tu répondras :
    track: "Is She Really Going Out With Him?" artist: "Joe Jackson"

    - Pour une fiche sur le film "L'Étudiante" de Claude Pinoteau, tu répondras :
    track: "Italienne (L'Étudiante)" artist: "Vladimir Cosma"

    Ne réponds **que** avec cette ligne, sans autre texte.

    Voici la fiche :
    {description}
    """
    
    return prompt

def exist_spotify(fiche_path):
    with open(fiche_path, 'r') as fiche:
        content = fiche.read()
    return '<iframe style="border-radius:12px" src="https://open.spotify.com/embed/track/' in content

def fiche_to_uri(fiche_path):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Tu es un assistant expert en culture générale, en jeux télévisés français et en rédaction de fiches informatives."},
            {"role": "user", "content": return_prompt_spotify(fiche_path)}
        ]
    )
    query_spotify = response.choices[0].message.content.strip()
    print(query_spotify)
    return return_uri_from_titre(query_spotify).split(":")[-1]

def update_fiche(fiche_path):
    if exist_spotify(fiche_path):
        print(f"{fiche_path} déjà modifiée")
        return
    uri = fiche_to_uri(fiche_path)
    add_uri_to_playlist(uri, "Obsidian")
    with open(fiche_path, 'r') as fiche:
        content = fiche.read()
    # Ajouter un iframe avant "###### Questions"
    iframe_code = f'<iframe style="border-radius:12px" src="https://open.spotify.com/embed/track/{uri}" width="100%" height="200" frameBorder="0" allowfullscreen="" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy"></iframe>'
    updated_content = content.replace("###### Questions", iframe_code + "\n###### Questions")
    with open(fiche_path, 'w') as fiche:
        fiche.write(updated_content)
        print(fiche_path + " mis à jour")

def supprime_playlists(txt):
    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                                client_secret=CLIENT_SECRET,
                                                redirect_uri=REDIRECT_URI,
                                                scope=scope))
    playlists = sp.current_user_playlists(limit=50)
    me = sp.current_user()
    print(f"Utilisateur connecté : {me['display_name']} ({me['id']})")

    results = sp.current_user_playlists(limit=50)
    print(f"Nombre de playlists trouvées : {results['total']}")
    while playlists:
        for playlist in playlists["items"]:
            name = playlist["name"]
            pid = playlist["id"]
            owner = playlist["owner"]["id"]
            deleted = 0
            if txt in name:
                print(f"🎯 Ciblée : {name} (owner: {owner})")
                try:
                    sp.current_user_unfollow_playlist(pid)
                    print(f"🗑️ Supprimée/désabonnée : {name}")
                    deleted += 1
                except Exception as e:
                    print(f"❌ Erreur sur {name} : {e}")

        if playlists["next"]:
            playlists = sp.next(playlists)
        else:
            break

def cree_playlist(name, desc, titres):

    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                               client_secret=CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               scope=scope))

    # 🎵 Créer une playlist
    playlist = sp.user_playlist_create(USERNAME, name, public=False, description=desc)

    # 🔎 Ajouter les morceaux à la playlist
    track_uris = []
    for chanson in titres:
        result = sp.search(q=chanson, type="track", limit=1)
        tracks = result.get("tracks", {}).get("items", [])
        
        if tracks:
            track_uris.append(tracks[0]["uri"])
            print(f"Ajouté : {chanson}")
        else:
            print(f"Non trouvé : {chanson}")
        
        time.sleep(1)  # Éviter d'être bloqué par l'API (rate limit)

    # 🚀 Ajouter les morceaux trouvés à la playlist
    if track_uris:
        sp.playlist_add_items(playlist["id"], track_uris)
        print(f"✅ Playlist '{name}' créée avec {len(track_uris)} titres !")
    else:
        print("⚠️ Aucun titre ajouté, vérifiez vos fichiers.")

def playlist_name_to_ids(playlist_name):
    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                               client_secret=CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               scope=scope))
    playlists = sp.current_user_playlists(limit=50)
    ids = []
    for p in playlists["items"]:
        if playlist_name == p["name"]:
            ids.append(p["id"])
    return ids

def add_track_to_playlist(titre, playlist_name):
    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                                   client_secret=CLIENT_SECRET,
                                                   redirect_uri=REDIRECT_URI,
                                                   scope=scope))
    
    ids = playlist_name_to_ids(playlist_name)

    if not ids:
        if not playlist_name:
            playlist_name = f"Radio {titre}"
        sp.user_playlist_create(USERNAME, playlist_name, public=False, description="")
        ids = playlist_name_to_ids(playlist_name)  # Rechercher l’ID maintenant que la playlist est créée

    playlist_id = ids[0]

    result = sp.search(q=titre[0:249], type="track", limit=1)
    tracks = result.get("tracks", {}).get("items", [])

    # Vérifier si le morceau est déjà dans la playlist
    existing_tracks = sp.playlist_tracks(playlist_id=playlist_id, fields="items(track(uri))")["items"]
    existing_uris = [item["track"]["uri"] for item in existing_tracks]

    if not tracks or titre.lower() not in tracks[0]["name"].lower():
        # Peut-être un artiste ?
        artist_results = sp.search(q=titre, type="artist", limit=1)
        artist_items = artist_results.get("artists", {}).get("items", [])
        if artist_items:
            artist_id = artist_items[0]["id"]
            top_tracks = sp.artist_top_tracks(artist_id, country="US").get("tracks", [])
            if top_tracks:
                track_uri = top_tracks[0]["uri"]
                if track_uri not in existing_uris:
                    sp.playlist_add_items(playlist_id=playlist_id, items=[track_uri])
                    print(f"✅ Ajouté : {top_tracks[0]['name']} (artiste : {titre})")
                    return True
                else:
                    print(f"⚠️ Déjà présent : {top_tracks[0]['name']} (artiste : {titre})")
                    return False
        print(f"❌ Introuvable ou non correspondant : {titre}")
        return False

    track_uri = tracks[0]["uri"]
    if track_uri in existing_uris:
        print(f"⚠️ Déjà présent : {tracks[0]['name']}")
        return False

    sp.playlist_add_items(playlist_id=playlist_id, items=[track_uri])
    print(f"✅ Ajouté : {tracks[0]['name']}")
    return True

def add_uri_to_playlist(uri, playlist_name):
    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                                    client_secret=CLIENT_SECRET,
                                                    redirect_uri=REDIRECT_URI,
                                                    scope=scope))
    
    ids = playlist_name_to_ids(playlist_name)

    if not ids:
        sp.user_playlist_create(USERNAME, playlist_name, public=False, description="")
        ids = playlist_name_to_ids(playlist_name)  # Rechercher l’ID maintenant que la playlist est créée

    playlist_id = ids[0]

    # Vérifier si l'URI est déjà dans la playlist
    existing_tracks = sp.playlist_tracks(playlist_id=playlist_id, fields="items(track(uri))")["items"]
    existing_uris = [item["track"]["uri"] for item in existing_tracks]

    if uri in existing_uris:
        print(f"⚠️ URI déjà présent dans la playlist : {uri}")
        return False

    sp.playlist_add_items(playlist_id=playlist_id, items=[uri])
    print(f"✅ URI ajouté à la playlist '{playlist_name}': {uri}")
    return True

def return_uri_from_titre(titre):
    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                                    client_secret=CLIENT_SECRET,
                                                    redirect_uri=REDIRECT_URI,
                                                    scope=scope))
    try:
        result = sp.search(q=titre, type="track", limit=1)
        tracks = result.get("tracks", {}).get("items", [])
        if tracks:
            return tracks[0]["uri"]
        else:
            print(f"❌ Aucun URI trouvé pour : {titre}")
            return None
    except Exception as e:
        print(f"Erreur lors de la recherche de l'URI pour {titre} : {e}")
        return None

def return_uri_from_structured_input(input_str):
    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=scope
    ))

    titre = None
    artiste = None

    # Parsing GPT output
    match = re.match(r'track:\s*"(.*?)"\s*artist:\s*"(.*?)"', input_str.strip())
    if match:
        titre = match.group(1)
        artiste = match.group(2)
        query = f'track:"{titre}" artist:"{artiste}"'
    else:
        # Fallback : requête brute
        query = input_str.strip()

    try:
        result = sp.search(q=query, type="track", limit=1)
        tracks = result.get("tracks", {}).get("items", [])

        if not tracks:
            print(f"❌ Aucun résultat trouvé pour : {query}")
            return None

        top_track = tracks[0]
        track_name = top_track["name"].lower()
        artist_names = [a["name"].lower() for a in top_track["artists"]]

        if titre and artiste:
            if titre.lower() in track_name and artiste.lower() in " ".join(artist_names):
                return top_track["uri"]
            else:
                print(f"⚠️ Résultat incertain pour '{titre} - {artiste}' → {track_name} / {artist_names}")
                return None
        else:
            # Pas de parsing → on accepte le 1er résultat brut
            return top_track["uri"]

    except Exception as e:
        print(f"⚠️ Erreur pendant la recherche : {e}")
        return None

def spotify_est_chanson(titre, min_popularity=50):
    scope = "playlist-read-private playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                               client_secret=CLIENT_SECRET,
                                               redirect_uri=REDIRECT_URI,
                                               scope=scope))
    try:
        resultats = sp.search(q=titre, type='track', limit=1)
        items = resultats.get("tracks", {}).get("items", [])
        if not items:
            return False
        item = items[0]
        # Popularité minimum requise
        popularite = item.get("popularity", 0)
        #print(popularite)

        return (
            (item.get("name", "").lower() == titre.lower() or titre.lower() in item.get("name", "").lower())
            and item.get("artists")
            and item.get("album")
            and popularite >= min_popularity
        )
    except Exception as e:
        print(f"Erreur Spotify pour {titre} : {e}")
        return False
    
def heuristique(results):
    titres = []
    for result in results:
        result = result.replace("[","").replace("]","")
        if spotify_est_chanson(result):
            titres.append(result)
    return titres

def extraire_candidats(dir_path):
    candidats = set()
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith('.md'):
                with open(os.path.join(root, file), 'r') as f:
                    content = file.split('.')[0] + '\n' + f.read()
                    lignes = content.splitlines()
                    candidats.add(file.split('.')[0])
                    for ligne in lignes:
                        # Entre guillemets
                        matches = re.findall(r'"([^"]+)"', ligne)
                        candidats.update(matches)
    return list(candidats)

def obsidian_to_playlist(dir_path, playlist_name):
    titres = heuristique(extraire_candidats(dir_path))
    for titre in titres:
        add_track_to_playlist(titre, playlist_name)

def create_playlist_year(min_popularity=50, limit=50, annee=1977, max_par_artiste=3):
    lettres = "abcdefghijklmnopqrstuvwxyz0123456789"
    nom_playlist = f"Chansons populaires en {annee}"

    # Vérifier si la playlist existe
    playlists = sp.current_user_playlists()["items"]
    playlist = next((pl for pl in playlists if pl["name"] == nom_playlist), None)

    if playlist:
        print(f"🎵 Playlist '{nom_playlist}' déjà existante. Mise à jour en cours.")
    else:
        playlist = sp.user_playlist_create(user=USERNAME, name=nom_playlist, public=False)
        print(f"✅ Création de la playlist '{nom_playlist}'.")

    playlist_id = playlist["id"]

    track_uris_ajoutees = set()
    morceaux_valides = []
    compteur_artistes = defaultdict(int)

    for lettre in lettres:
        query = f"{lettre} year:{annee}"
        resultats = sp.search(q=query, type="track", limit=limit)

        for item in resultats["tracks"]["items"]:
            uri = item["uri"]
            if uri in track_uris_ajoutees:
                continue

            pop = item.get("popularity", 0)
            date = item["album"].get("release_date", "")
            annee_trouvee = date[:4]
            artistes = [artist["name"] for artist in item.get("artists", [])]

            # Vérifier année, popularité, et quota par artiste
            if str(annee_trouvee) == str(annee) and int(pop) >= int(min_popularity):
                # Si un des artistes a atteint la limite, on skippe
                if any(compteur_artistes[artiste] >= max_par_artiste for artiste in artistes):
                    continue

                morceaux_valides.append({
                    "uri": uri,
                    "popularity": pop,
                    "name": item["name"],
                    "artists": artistes
                })
                track_uris_ajoutees.add(uri)

                # Incrémenter le compteur pour chaque artiste du morceau
                for artiste in artistes:
                    compteur_artistes[artiste] += 1

    # Trier les morceaux par popularité décroissante
    morceaux_valides = sorted(morceaux_valides, key=lambda x: x["popularity"], reverse=True)

    # Optionnel : vider la playlist avant mise à jour
    sp.playlist_replace_items(playlist_id, [])

    # Ajout en batchs de 100
    for i in range(0, len(morceaux_valides), 100):
        batch = morceaux_valides[i:i+100]
        uris_batch = [m["uri"] for m in batch]
        sp.playlist_add_items(playlist_id, uris_batch)
        print(f"Ajout de {len(uris_batch)} morceaux.")

    print(f"✅ Playlist '{nom_playlist}' mise à jour avec {len(morceaux_valides)} morceaux.")

def get_artist_and_album_image_urls(query):
    scope = "user-read-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=CLIENT_ID,
                                                   client_secret=CLIENT_SECRET,
                                                   redirect_uri=REDIRECT_URI,
                                                   scope=scope))

    result = sp.search(q=query[0:249], type="track,artist", limit=1)
    track_items = result.get("tracks", {}).get("items", [])
    artist_items = result.get("artists", {}).get("items", [])

    # Nettoyage de l'input pour comparaison
    def normalize(text):
        return text.lower().strip()

    input_norm = normalize(query)

    track_score = 0
    artist_score = 0

    if track_items:
        track = track_items[0]
        track_name = normalize(track["name"])
        track_artist_name = normalize(track["artists"][0]["name"])

        if input_norm in track_name or input_norm in track_artist_name:
            track_score += 1

        if difflib.SequenceMatcher(None, input_norm, track_name).ratio() > 0.7:
            track_score += 1

    if artist_items:
        artist = artist_items[0]
        artist_name = normalize(artist["name"])

        if input_norm in artist_name:
            artist_score += 1

        if difflib.SequenceMatcher(None, input_norm, artist_name).ratio() > 0.7:
            artist_score += 1

    # Décision finale : on compare les scores
    if artist_score >= track_score and artist_items:
        artist = artist_items[0]
        artist_info = sp.artist(artist["id"])
        artist_images = artist_info.get("images", [])
        artist_image_url = artist_images[0]["url"] if artist_images else None

        return {
            "input_type": "artist",
            "artist_name": artist["name"],
            "artist_image_url": artist_image_url,
            "album_name": None,
            "album_image_url": None
        }

    elif track_items:
        track = track_items[0]
        artist = track["artists"][0]
        album = track["album"]

        artist_info = sp.artist(artist["id"])
        artist_images = artist_info.get("images", [])
        artist_image_url = artist_images[0]["url"] if artist_images else None

        album_images = album.get("images", [])
        album_image_url = album_images[0]["url"] if album_images else None

        return {
            "input_type": "track",
            "track_name": track["name"],
            "artist_name": artist["name"],
            "artist_image_url": artist_image_url,
            "album_name": album["name"],
            "album_image_url": album_image_url
        }

    else:
        print(f"❌ Aucun résultat pour : {query}")
        return None

def update_directory_on_fiches(directory_path):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith('.md'):
                print(file)
                fiche_path = os.path.join(root, file)
                try:
                    update_fiche(fiche_path)
                except Exception as e:
                    print(f"Erreur lors de la mise à jour de la fiche {fiche_path} : {e}")

#update_directory_on_fiches('/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance/Musique')
#print(return_uri_from_structured_input("Chat Noir Chat Blanc Goran Bregović"))
#print(get_artist_and_album_image_urls("Pomme C"))
#create_playlist_year(70,50,2000, 2)
#obsidian_to_playlist('/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance/Cinéma', "Cinéma (Obsidian)")
#print(heuristique(extraire_candidats('/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance/Cinéma')))
#supprime_playlists("Populaires en")