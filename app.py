import streamlit as st
import pandas as pd
import requests
import json


st.title("Suivi des joueurs — Prototype")

HF_TOKEN = st.secrets["HF_TOKEN"]
API_URL = "https://router.huggingface.co/v1/chat/completions"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

def demander_a_ia(prompt):
    payload = {
        "model": "deepseek-ai/DeepSeek-V3-0324",
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post(API_URL, headers=headers, json=payload)
    resultat = response.json()
    return resultat['choices'][0]['message']['content']



BIN_ID = st.secrets["BIN_ID"]
MASTER_KEY = st.secrets["MASTER_KEY"]
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
jsonbin_headers = {"X-Master-Key": MASTER_KEY, "Content-Type": "application/json"}

def charger_donnees():
    response = requests.get(JSONBIN_URL + "/latest", headers=jsonbin_headers)
    return response.json()["record"]

def sauvegarder_donnees(donnees):
    requests.put(JSONBIN_URL, headers=jsonbin_headers, json=donnees)

def charger_utilisateurs():
    return charger_donnees()["utilisateurs"]

def sauvegarder_utilisateurs(utilisateurs):
    donnees = charger_donnees()
    donnees["utilisateurs"] = utilisateurs
    sauvegarder_donnees(donnees)

if "utilisateur_connecte" not in st.session_state:
    st.session_state.utilisateur_connecte = None

if st.session_state.utilisateur_connecte is None:
    st.subheader("Connexion")
    mode = st.radio("Tu es un nouveau coach ou déjà inscrit ?", ["Déjà inscrit", "Nouveau coach"])
    identifiant = st.text_input("Identifiant")
    mot_de_passe = st.text_input("Mot de passe", type="password")
    utilisateurs = charger_utilisateurs()
    if mode == "Nouveau coach":
        if st.button("Créer mon compte"):
            if identifiant in utilisateurs:
                st.error("Cet identifiant existe déjà.")
            elif identifiant and mot_de_passe:
                utilisateurs[identifiant] = mot_de_passe
                sauvegarder_utilisateurs(utilisateurs)
                st.session_state.utilisateur_connecte = identifiant
                st.rerun()
    else:
        if st.button("Se connecter"):
            if identifiant in utilisateurs and utilisateurs[identifiant] == mot_de_passe:
                st.session_state.utilisateur_connecte = identifiant
                st.rerun()
            else:
                st.error("Identifiant ou mot de passe incorrect.")
    st.stop()

st.success(f"Connecté en tant que : {st.session_state.utilisateur_connecte}")
if st.button("Se déconnecter"):
    st.session_state.utilisateur_connecte = None
    st.rerun()

def charger_equipe():
    donnees = charger_donnees()
    return donnees["equipes"].get(st.session_state.utilisateur_connecte, [])

def sauvegarder_equipe(equipe):
    donnees = charger_donnees()
    donnees["equipes"][st.session_state.utilisateur_connecte] = equipe
    sauvegarder_donnees(donnees)

if "equipe" not in st.session_state:
    st.session_state.equipe = charger_equipe()

st.subheader("Ajouter un joueur")

with st.form("ajout_joueur"):
    nom = st.text_input("Nom du joueur")
    moyenne = st.number_input("Moyenne de points", min_value=0.0)
    progression = st.number_input("Progression", min_value=-50.0, max_value=50.0)
    passes = st.number_input("Passes décisives (assists)", min_value=0.0)
    rebonds = st.number_input("Rebonds", min_value=0.0)
    interceptions = st.number_input("Interceptions (steals)", min_value=0.0)
    pertes_balle = st.number_input("Pertes de balle (turnovers)", min_value=0.0)
    valider = st.form_submit_button("Ajouter")

    if valider and nom:
        st.session_state.equipe.append({
            "nom": nom, "moyenne": moyenne, "progression": progression,
            "assists": passes, "rebonds": rebonds,
            "steals": interceptions, "turnovers": pertes_balle
        })
        sauvegarder_equipe(st.session_state.equipe)
        st.success(f"{nom} ajouté et sauvegardé !")

if len(st.session_state.equipe) > 0:
    df = pd.DataFrame(st.session_state.equipe)

    st.subheader("Statistiques de l'équipe")
    df_modifiable = st.data_editor(df, num_rows="dynamic", key="editeur_stats")

    if not df_modifiable.equals(df):
        st.session_state.equipe = df_modifiable.to_dict('records')
        sauvegarder_equipe(st.session_state.equipe)

    st.subheader("Moyenne de points par joueur")
    st.bar_chart(df_modifiable.set_index('nom')['moyenne'])

    st.subheader("Analyse IA")
    joueur_choisi = st.selectbox("Choisis un joueur", df_modifiable['nom'])

    if st.button("Générer l'analyse"):
        ligne = df_modifiable[df_modifiable['nom'] == joueur_choisi].iloc[0]
        prompt = f"""
        Je suis coach N2. Voici les stats du joueur {ligne['nom']} :
        Moyenne : {ligne['moyenne']} pts, Progression : {ligne['progression']} pts,
        Assists : {ligne['assists']}, Rebonds : {ligne['rebonds']},
        Steals : {ligne['steals']}, Turnovers : {ligne['turnovers']}.
        Donne une analyse courte (2-3 phrases) de sa performance globale.
        """
        with st.spinner("Analyse en cours..."):
            reponse = demander_a_ia(prompt)
        st.write(reponse)
else:
    st.info("Ajoute au moins un joueur pour voir les statistiques.")

# --- Analyse vidéo ---
st.subheader("Analyse vidéo — Angles du bras")

video_uploadee = st.file_uploader("Upload une vidéo (tir, dribble...)", type=["mp4", "mov"])

if video_uploadee is not None:
    with open("video_temp.mp4", "wb") as f:
        f.write(video_uploadee.read())
    st.success("Vidéo reçue !")

    if st.button("Analyser le mouvement"):
        with st.spinner("Analyse de la vidéo en cours..."):
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
            import cv2
            import math
            import os
            if not os.path.exists("pose_landmarker.task"):
                import urllib.request
                urllib.request.urlretrieve(
                    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
                    "pose_landmarker.task"
                )

            base_options = python.BaseOptions(model_asset_path='pose_landmarker.task')
            options = vision.PoseLandmarkerOptions(
                base_options=base_options,
                min_pose_detection_confidence=0.1
            )
            detector = vision.PoseLandmarker.create_from_options(options)

            def calculer_angle(a, b, c):
                angle = math.degrees(
                    math.atan2(c.y - b.y, c.x - b.x) - math.atan2(a.y - b.y, a.x - b.x)
                )
                angle = abs(angle)
                if angle > 180:
                    angle = 360 - angle
                return angle

            video = cv2.VideoCapture("video_temp.mp4")
            mesures = []
            idx = 0
            while True:
                succes, image = video.read()
                if not succes:
                    break
                if idx % 20 == 0:
                    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
                    resultat = detector.detect(mp_image)
                    if resultat.pose_landmarks:
                        points = resultat.pose_landmarks[0]
                        hanche = points[24]
                        epaule = points[12]
                        coude = points[14]
                        poignet = points[16]
                        index = points[20]

                        angle_epaule = calculer_angle(hanche, epaule, coude)
                        angle_coude = calculer_angle(epaule, coude, poignet)
                        angle_poignet = calculer_angle(coude, poignet, index)

                        mesures.append({
                            "image": idx,
                            "angle_epaule": round(angle_epaule, 1),
                            "angle_coude": round(angle_coude, 1),
                            "angle_poignet": round(angle_poignet, 1)
                        })
                idx += 1

            if len(mesures) > 0:
                df_mesures = pd.DataFrame(mesures)
                st.subheader("Angles mesurés à différents moments")
                st.dataframe(df_mesures)

                texte_mesures = ""
                for m in mesures:
                    texte_mesures += f"Image {m['image']} : épaule {m['angle_epaule']}°, coude {m['angle_coude']}°, poignet {m['angle_poignet']}°\n"

                prompt_video = f"""
                Je suis coach de basketball N2. Voici des mesures d'angles du bras (épaule, coude, poignet) prises à différents moments d'une vidéo de tir :

                {texte_mesures}

                Analyse ces angles et donne, en tant que coach de basketball expérimenté, 3-4 phrases sur ce que ça révèle sur la technique de shoot du joueur (fluidité du geste, cohérence entre les angles, points à corriger).
                """
                with st.spinner("Génération de l'analyse..."):
                    analyse_video = demander_a_ia(prompt_video)
                st.subheader("Analyse IA du geste")
                st.write(analyse_video)
            else:
                st.warning("Aucun angle détecté sur cette vidéo, essaie une autre vidéo ou un autre angle de caméra.")


from streamlit_calendar import calendar

st.subheader("Programme d'entraînement personnalisé")

if len(st.session_state.equipe) > 0:
    joueur_programme = st.selectbox("Choisis un joueur", df_modifiable['nom'], key="select_programme")
    age = st.number_input("Âge du joueur", min_value=8, max_value=45, value=16)
    poste = st.selectbox("Poste principal", ["Meneur", "Arrière", "Ailier", "Ailier fort", "Pivot"])
    main_dominante = st.radio("Main dominante", ["Droite", "Gauche"])
    points_faibles = st.text_area("Points faibles spécifiques observés (optionnel)", placeholder="Ex: perd souvent le ballon en contre-attaque, main gauche faible...")
    niveau = st.selectbox("Niveau du joueur", ["Débutant", "Intermédiaire", "Avancé"])
    objectifs = st.multiselect(
        "Objectifs à travailler",
        ["Tir", "Dribble", "Finition au panier", "Défense", "Force & Pliométrie"]
    )

    blessures = ""
    experience_muscu = "Non renseigné"
    if "Force & Pliométrie" in objectifs:
        st.warning("⚠️ Le volet physique nécessite quelques précisions pour rester sûr.")
        blessures = st.text_input("Blessures récentes ou douleurs actuelles (laisse vide si aucune)")
        experience_muscu = st.selectbox("Expérience en musculation/pliométrie", ["Débutant total", "Quelques mois", "Plus d'un an"])

    frequence = st.slider("Séances par semaine", min_value=1, max_value=6, value=3)
    duree = st.slider("Durée du programme (semaines)", min_value=1, max_value=8, value=4)

    if st.button("Générer le programme"):
        if not objectifs:
            st.warning("Choisis au moins un objectif avant de générer le programme.")
        else:
            ligne = df_modifiable[df_modifiable['nom'] == joueur_programme].iloc[0]
            objectifs_texte = ", ".join(objectifs)

            consigne_physique = ""
            if "Force & Pliométrie" in objectifs:
                consigne_physique = f"""
                Pour le volet physique (force, pliométrie, isométrie) : le joueur a pour expérience "{experience_muscu}" et signale comme blessure/douleur : "{blessures if blessures else 'aucune'}".
                Reste prudent : privilégie des exercices au poids du corps ou charge légère pour un débutant, évite tout exercice à haut risque de blessure, et précise systématiquement que ce programme doit être validé par un préparateur physique ou un professionnel avant d'être suivi.
                """

            prompt_programme = f"""
            Tu es un préparateur physique et technique de haut niveau, spécialisé dans le développement de jeunes basketteurs. Tu connais les drills utilisés par les vrais programmes de développement (type IMG Academy, EYBL).

            Joueur : {ligne['nom']}, {age} ans, poste {poste}, main dominante {main_dominante}
            """
