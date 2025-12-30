output_dir = "/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance/attachments/"
dir = "/Users/edumas/Library/Mobile Documents/iCloud~md~obsidian/Documents/Mon réseau de connaissance/"

import time
import os
from html2image import Html2Image
import folium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import time
import urllib.parse
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from PIL import Image
import time
from urllib.request import pathname2url
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import numpy as np
from PIL import Image
from geopy.geocoders import Nominatim

def return_clusters():
    # Exemples de coordonnées latitude et longitude
    coordonnées = np.array([
        [52.2297, 21.0122], # Pologne
        [48.1849, 16.3122], # Schönbrunn
        [19.4326, -99.1332], # Tenochtitlan
        [3.1579, 101.7113] # Petronas
    ])

    # Mise à l'échelle des données
    scaler = StandardScaler()
    coordonnées_scaled = scaler.fit_transform(coordonnées)

    # Application de DBSCAN
    dbscan = DBSCAN(eps=0.5, min_samples=2)
    clusters = dbscan.fit_predict(coordonnées_scaled)

    # Résultats
    print("Clusters:", clusters)

def fiche_to_carte(nom):
        
    # -----------------------
    # Config
    lieu = nom
    zooms = [2, 5, 8, 11, 13, 15]  # Différents niveaux de zoom
    taille = (800, 600)  # 🖼️ largeur x hauteur en pixels
    html_filename_template = "map_zoom_{}.html"
    png_filename_template = "map_zoom_{}.png"
    # -----------------------
    from PIL import Image
    from geopy.geocoders import Nominatim
    geolocator = Nominatim(user_agent="map_capture", timeout=10)
    location = geolocator.geocode(lieu)

    if not location:
        print("Lieu non trouvé.")
        return

    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Mode sans affichage
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Lancer Selenium avec les options
    driver = webdriver.Chrome(options=chrome_options)

    for zoom in zooms:
        # Étape 2 : créer carte folium avec taille HTML définie
        carte = folium.Map(
            location=[location.latitude, location.longitude],
            zoom_start=zoom,
            width=taille[0],
            height=taille[1],
            tiles="OpenStreetMap"
        )
        # folium.TileLayer(
        # tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        # attr='Esri',
        # name='Satellite',
        # overlay=False,
        # control=True
        # ).add_to(carte)
        
        folium.Marker(
            [location.latitude, location.longitude],
            popup=lieu,
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(carte)

        html_filename = html_filename_template.format(zoom)
        carte.save(html_filename)
        print(f"✅ Carte HTML générée pour zoom {zoom}.")

        html_url = "file://" + pathname2url(os.path.abspath(html_filename))
        driver.get(html_url)

        time.sleep(2)  # Laisse le temps au site de se charger

        # Prendre une capture d'écran complète
        screenshot_filename = f"full_screenshot_zoom_{zoom}.png"
        driver.save_screenshot(screenshot_filename)

        # Ouvrir l'image complète et recadrer la zone de l’élément
        image = Image.open(screenshot_filename)

        # Recadrer et sauvegarder
        cropped_image = image.crop((500, 300, 1100, 900))
        cropped_filename = png_filename_template.format(zoom)
        cropped_image.save(cropped_filename)
        print(f"✅ Capture d'écran recadrée sauvegardée pour zoom {zoom}.")

    from PIL import Image
    from geopy.geocoders import Nominatim

    # 🔢 Configuration
    fichiers = [
        "map_zoom_2.png",
        "map_zoom_5.png",
        "map_zoom_8.png",
        "map_zoom_11.png",
        "map_zoom_13.png",
        "map_zoom_15.png"
    ]
    colonnes = 3
    lignes = 2

    # 📥 Charger toutes les images (en supposant qu'elles sont de même taille)
    images = [Image.open(f) for f in fichiers]

    # 📏 Récupérer largeur/hauteur d'une image (toutes doivent avoir la même taille)
    img_width, img_height = images[0].size

    # 🖼️ Créer une nouvelle image vide (grande mosaïque)
    mosaic = Image.new("RGB", (img_width * colonnes, img_height * lignes), color=(255, 255, 255))

    # 🧩 Coller chaque image à sa position
    for index, img in enumerate(images):
        x = (index % colonnes) * img_width
        y = (index // colonnes) * img_height
        mosaic.paste(img, (x, y))

    # 💾 Sauvegarder le résultat
    mosaic.save(f"/data/attachments/Carte_{nom}.png")
    compresser_image_jpeg(f"/data/attachments/Carte_{nom}.png", f"/data/attachments/Carte_{nom}.png", quality=90)
    print(f"/data/attachments/Carte_{nom}.png enregistrée.")

    # Fermer le navigateur
    driver.quit()

def attache_carte_to_fiche(fiche_name, category):
    # Chemin du fichier de la carte
    
    carte_path = os.path.join(output_dir, f"Carte_{fiche_name}.png")
    fiche_path = dir+category+"/"+fiche_name+".md"
    # Vérifier si le fichier existe
    if os.path.exists(carte_path):
        # Ajouter la carte à la fiche
        with open(fiche_path, 'r') as fiche:
            content = fiche.read()
            new_content = content.replace("###### Questions", f"![[Carte_{fiche_name}.png]]\n###### Questions")
        with open(fiche_path, 'w') as fiche:
            fiche.write(new_content)
            print(f"✅ Carte ajoutée à {fiche_path}")
    else:
        print(f"❌ La carte {carte_path} n'existe pas.")

def process_repertoire(repertoire):
    # Lister tous les fichiers dans le répertoire
    for filename in os.listdir(repertoire):
        if filename.endswith(".md"):  # Vérifier si le fichier est un fichier Markdown
            fiche_name = os.path.splitext(filename)[0]  # Récupérer le nom sans extension
            print(f"📄 Traitement de la fiche : {fiche_name}")
            fiche_path = os.path.join(output_dir, f"Carte_{fiche_name}.png")
            if os.path.exists(fiche_path):
                print(f"⚠️ La fiche {fiche_name} a déjà été traitée. Passage à la suivante.")
                continue
            fiche_to_carte(fiche_name)  # Générer la carte
            attache_carte_to_fiche(fiche_name)  # Attacher la carte à la fiche

def compresser_image_jpeg(fichier_entree, fichier_sortie, quality=40):
    image = Image.open(fichier_entree).convert("RGB")  # JPEG = RGB obligatoire
    image.save(
        fichier_sortie,
        format="JPEG",
        optimize=True,
        quality=quality,
        progressive=True  # utile pour affichage web progressif
    )
    print(f"✅ Image compressée (JPEG) : {fichier_sortie}")

def ajoute_latitude_et_longitude_as_an_attribute(fiche_name):
        # Chemin du fichier de la fiche
        dir = "/data/"
        fiche_path = os.path.join(dir+"/Architecture", fiche_name + ".md")

        # Vérifier si le fichier existe
        if not os.path.exists(fiche_path):
            print(f"❌ La fiche {fiche_name} n'existe pas.")
            return

        # Géolocalisation
        geolocator = Nominatim(user_agent="geo_attribute", timeout=10)
        location = geolocator.geocode(fiche_name)

        if not location:
            print(f"❌ Impossible de trouver les coordonnées pour {fiche_name}.")
            return

        # Ajouter latitude et longitude à la fiche
        with open(fiche_path, 'r') as fiche:
            content = fiche.read()
            if not "location:" in content and "indice_1" in content and not "GPS_mano" in content:
                new_content = content.replace(
                    "tags",
                    f"latitude: {location.latitude}\nlongitude: {location.longitude}\nlocation: {str(location.latitude).replace(',','.')},{str(location.longitude).replace(',','.')}\ntags"
                )
            else:
                print(f"⚠️ La fiche {fiche_name} a déjà des coordonnées GPS. Passage à la suivante.")
                return
        with open(fiche_path, 'w') as fiche:
            fiche.write(new_content)
            print(f"✅ Latitude et longitude ajoutées à {fiche_path}")

#ajoute_latitude_et_longitude_as_an_attribute("Pont du Gard")
#process_repertoire(dir)
#return_clusters()
#fiche_to_carte("Sarthe")
#attache_carte_to_fiche("Sarthe", "Géographie")
