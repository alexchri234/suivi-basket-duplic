import streamlit as st
import pandas as pd
import requests
import json
import datetime
import urllib.parse


st.title("Suivi des joueurs — Prototype")

HF_TOKEN = st.secrets["HF_TOKEN"]
API_URL = "https://router.huggingface.co/v1/chat/completions"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

def demander_a_ia(prompt):
    payload = {
        "model": "deepseek-ai/DeepSeek-V3-0324",
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=240)
        resultat = response.json()
        if "choices" not in resultat:
            return f"ERREUR_IA: L'API Hugging Face a renvoyé une erreur : {resultat.get('error', resultat)}"
        return resultat['choices'][0]['message']['content']
    except requests.exceptions.JSONDecodeError:
        return f"ERREUR_IA: L'API n'a pas renvoyé de réponse exploitable (code HTTP {response.status_code}). Réessaie dans un instant ; si ça persiste, essaie avec moins de semaines ou d'objectifs à la fois.\n\nDétail brut : {response.text[:300]}"
    except requests.exceptions.Timeout:
        return "ERREUR_IA: L'API a mis trop de temps à répondre (délai dépassé). Réessaie, ou réduis le volume demandé (moins de semaines/séances)."
    except (requests.RequestException, KeyError, IndexError) as erreur:
        return f"ERREUR_IA: {erreur}"



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

def charger_programmes():
    donnees = charger_donnees()
    return donnees.get("programmes", {}).get(st.session_state.utilisateur_connecte, {})

def sauvegarder_programme(nom_joueur, seances):
    donnees = charger_donnees()
    donnees.setdefault("programmes", {})
    donnees["programmes"].setdefault(st.session_state.utilisateur_connecte, {})
    donnees["programmes"][st.session_state.utilisateur_connecte][nom_joueur] = seances
    sauvegarder_donnees(donnees)

def charger_cache_videos():
    donnees = charger_donnees()
    return donnees.get("cache_videos", {})

def sauvegarder_cache_videos(cache_videos):
    donnees = charger_donnees()
    donnees["cache_videos"] = cache_videos
    sauvegarder_donnees(donnees)

def rechercher_video_youtube(nom_exercice, cle_api):
    try:
        reponse = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": f"{nom_exercice} basketball drill",
                "type": "video",
                "maxResults": 1,
                "key": cle_api
            },
            timeout=5
        )
        resultats = reponse.json().get("items", [])
        if resultats:
            return f"https://www.youtube.com/watch?v={resultats[0]['id']['videoId']}"
    except (requests.RequestException, KeyError, IndexError, ValueError):
        pass
    return None

def enrichir_avec_videos(seances):
    cle_youtube = st.secrets.get("YOUTUBE_API_KEY")
    if not cle_youtube:
        return
    cache_videos = charger_cache_videos()
    cache_modifie = False
    for seance in seances:
        for exercice in seance.get("exercices", []):
            cle_cache = exercice.get("nom", "").strip().lower()
            if not cle_cache:
                continue
            if cle_cache in cache_videos:
                exercice["video_url"] = cache_videos[cle_cache]
                continue
            url_trouvee = rechercher_video_youtube(exercice["nom"], cle_youtube)
            if url_trouvee:
                cache_videos[cle_cache] = url_trouvee
                exercice["video_url"] = url_trouvee
                cache_modifie = True
    if cache_modifie:
        sauvegarder_cache_videos(cache_videos)

def generer_schema_exercice(schema):
    try:
        couleurs = {"joueur": "#1d4ed8", "defenseur": "#c0392b", "plot": "#e67e22", "ballon": "#f39c12"}
        elements_svg = []
        for element in schema.get("elements", []):
            x = max(0, min(100, float(element.get("x", 50))))
            y = max(0, min(94, float(element.get("y", 50))))
            type_element = element.get("type", "joueur")
            couleur = couleurs.get(type_element, "#333333")
            if type_element == "plot":
                elements_svg.append(f'<rect x="{x - 1.5}" y="{y - 1.5}" width="3" height="3" fill="{couleur}"/>')
            elif type_element == "ballon":
                elements_svg.append(f'<circle cx="{x}" cy="{y}" r="1.5" fill="{couleur}"/>')
            else:
                label = element.get("label", "J" if type_element == "joueur" else "D")
                elements_svg.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{couleur}"/>')
                elements_svg.append(f'<text x="{x}" y="{y + 1}" font-size="3" fill="white" text-anchor="middle">{label}</text>')

        fleches_svg = []
        for deplacement in schema.get("deplacements", []):
            de = deplacement.get("de", [50, 50])
            vers = deplacement.get("vers", [50, 40])
            style = deplacement.get("style", "course")
            pointilles = 'stroke-dasharray="2,1.5"' if style == "dribble" else ('stroke-dasharray="0.5,1.5"' if style == "passe" else "")
            fleches_svg.append(
                f'<line x1="{de[0]}" y1="{de[1]}" x2="{vers[0]}" y2="{vers[1]}" stroke="#333333" stroke-width="0.6" {pointilles} marker-end="url(#fleche)"/>'
            )

        return f"""<svg viewBox="0 0 100 94" xmlns="http://www.w3.org/2000/svg" style="width:100%; max-width:320px; height:auto; background:#e8dcc8; border:1px solid #999; border-radius:4px;">
            <defs>
                <marker id="fleche" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto">
                    <path d="M0,0 L4,2 L0,4 z" fill="#333333"/>
                </marker>
            </defs>
            <rect x="0" y="0" width="100" height="94" fill="none" stroke="#333333" stroke-width="0.5"/>
            <line x1="0" y1="0.3" x2="100" y2="0.3" stroke="#333333" stroke-width="0.5" stroke-dasharray="2,2"/>
            <rect x="34" y="56" width="32" height="38" fill="none" stroke="#333333" stroke-width="0.5"/>
            <circle cx="50" cy="56" r="12" fill="none" stroke="#333333" stroke-width="0.5"/>
            <path d="M 3 94 A 47 47 0 0 1 97 94" fill="none" stroke="#333333" stroke-width="0.5"/>
            <line x1="44" y1="90" x2="56" y2="90" stroke="#333333" stroke-width="1"/>
            <circle cx="50" cy="85" r="1.5" fill="none" stroke="#c0392b" stroke-width="0.8"/>
            {''.join(fleches_svg)}
            {''.join(elements_svg)}
        </svg>"""
    except (TypeError, ValueError, KeyError, AttributeError):
        return None

if "equipe" not in st.session_state:
    st.session_state.equipe = charger_equipe()

if "programmes" not in st.session_state:
    st.session_state.programmes = {
        nom_joueur: pd.DataFrame(seances)
        for nom_joueur, seances in charger_programmes().items()
    }

if "seance_selectionnee" not in st.session_state:
    st.session_state.seance_selectionnee = {}

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

    if "afficher_form_match" not in st.session_state:
        st.session_state.afficher_form_match = False

    if st.button("Ajouter un match"):
        st.session_state.afficher_form_match = True

    if st.session_state.afficher_form_match:
        with st.form("ajout_match"):
            joueur_match = st.selectbox("Joueur", df_modifiable['nom'], key="select_joueur_match")
            points_match = st.number_input("Points marqués", min_value=0.0)
            assists_match = st.number_input("Passes décisives", min_value=0.0)
            rebonds_match = st.number_input("Rebonds", min_value=0.0)
            steals_match = st.number_input("Interceptions", min_value=0.0)
            turnovers_match = st.number_input("Pertes de balle", min_value=0.0)
            valider_match = st.form_submit_button("Enregistrer le match")

            if valider_match:
                for joueur in st.session_state.equipe:
                    if joueur["nom"] == joueur_match:
                        nb_matchs = joueur.get("nb_matchs", 1)
                        ancienne_moyenne = joueur["moyenne"]
                        joueur["moyenne"] = round((ancienne_moyenne * nb_matchs + points_match) / (nb_matchs + 1), 2)
                        joueur["assists"] = round((joueur["assists"] * nb_matchs + assists_match) / (nb_matchs + 1), 2)
                        joueur["rebonds"] = round((joueur["rebonds"] * nb_matchs + rebonds_match) / (nb_matchs + 1), 2)
                        joueur["steals"] = round((joueur["steals"] * nb_matchs + steals_match) / (nb_matchs + 1), 2)
                        joueur["turnovers"] = round((joueur["turnovers"] * nb_matchs + turnovers_match) / (nb_matchs + 1), 2)
                        joueur["progression"] = round(joueur["moyenne"] - ancienne_moyenne, 2)
                        joueur["nb_matchs"] = nb_matchs + 1
                        break
                sauvegarder_equipe(st.session_state.equipe)
                st.session_state.afficher_form_match = False
                st.success(f"Match ajouté pour {joueur_match}, statistiques mises à jour !")
                st.rerun()

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
st.subheader("Analyse vidéo — Angles du bras et de la hanche")

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
                        genou = points[26]

                        angle_epaule = calculer_angle(hanche, epaule, coude)
                        angle_coude = calculer_angle(epaule, coude, poignet)
                        angle_poignet = calculer_angle(coude, poignet, index)
                        angle_hanche = calculer_angle(epaule, hanche, genou)

                        mesures.append({
                            "image": idx,
                            "angle_epaule": round(angle_epaule, 1),
                            "angle_coude": round(angle_coude, 1),
                            "angle_poignet": round(angle_poignet, 1),
                            "angle_hanche": round(angle_hanche, 1)
                        })
                idx += 1

            if len(mesures) > 0:
                df_mesures = pd.DataFrame(mesures)
                st.subheader("Angles mesurés à différents moments")
                st.dataframe(df_mesures)

                texte_mesures = ""
                for m in mesures:
                    texte_mesures += f"Image {m['image']} : épaule {m['angle_epaule']}°, coude {m['angle_coude']}°, poignet {m['angle_poignet']}°, hanche {m['angle_hanche']}°\n"

                prompt_video = f"""
                Je suis coach de basketball N2. Voici des mesures d'angles du bras et de la hanche (épaule, coude, poignet, hanche) prises à différents moments d'une vidéo de tir :

                {texte_mesures}

                Analyse ces angles et donne, en tant que coach de basketball expérimenté, 3-4 phrases sur ce que ça révèle sur la technique de shoot du joueur : fluidité du geste du bras, cohérence entre les angles, et en particulier ce que l'angle de hanche indique sur l'extension des jambes/du bassin dans le tir (transfert d'énergie des jambes vers le tir). Termine par des points concrets à corriger.
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

    with st.expander("Plus de détails pour un programme sur mesure (optionnel)"):
        st.markdown("**Matériel & contexte d'entraînement**")
        materiel_disponible = st.multiselect(
            "Matériel disponible",
            ["Plots", "Échelle d'agilité", "Élastiques de résistance", "Medicine ball", "Salle de musculation", "Panier seulement (rien d'autre)"]
        )
        partenaire_disponible = st.radio("Partenaire d'entraînement ou coach disponible pour les exercices en opposition ?", ["Oui", "Non, s'entraîne seul"])
        lieu_entrainement = st.selectbox("Lieu d'entraînement habituel", ["Terrain complet", "Demi-terrain", "Panier seul (allée, garage...)", "Salle de sport / gymnase"])

        st.markdown("**Profil physique & sportif**")
        taille_cm = st.number_input("Taille (cm)", min_value=0, max_value=230, value=0, help="Laisse à 0 si tu ne veux pas renseigner.")
        blessures_generales = st.text_area("Historique de blessures ou limitations physiques (concerne tout le programme, pas seulement le volet Force)", placeholder="Ex: entorse de cheville récurrente, tendinite au genou...")
        frequence_matchs = st.selectbox("Fréquence de matchs actuellement", ["Aucun match en ce moment", "1 match toutes les 2 semaines", "1 match par semaine", "2 matchs ou plus par semaine"])
        echeance = st.text_input("Échéance ou objectif précis (optionnel)", placeholder="Ex: sélection régionale dans 6 semaines, tournoi le 12 octobre...")

        st.markdown("**Style de jeu & polyvalence**")
        postes_secondaires = st.multiselect("Poste(s) secondaire(s) / polyvalence (optionnel)", ["Meneur", "Arrière", "Ailier", "Ailier fort", "Pivot"])
        style_jeu = st.selectbox("Style de jeu recherché", ["Non renseigné", "Scoreur", "Facilitateur / passeur", "Défenseur", "Polyvalent / two-way"])
        jambe_appui_defense = st.radio("Jambe d'appui dominante en défense (optionnel)", ["Non renseigné", "Droite", "Gauche"])

    niveaux_definitions = {
        "Débutant": "Débutant : moins de 2 ans de pratique organisée. Ne maîtrise pas encore les fondamentaux de façon fiable — perd parfois le ballon sur un dribble simple, la forme de tir n'est pas stable, ne connaît pas encore les schémas défensifs de base.",
        "Intermédiaire": "Intermédiaire : 2 à 4 ans de pratique en club/compétition. Exécute les fondamentaux avec une bonne consistance (dribble des deux mains, forme de tir correcte, passes précises) mais manque encore de fiabilité sous pression ou en match serré.",
        "Avancé": "Avancé : 4 ans ou plus de pratique en compétition régulière. Maîtrise les fondamentaux de façon fiable même sous pression, exécute des mouvements avancés (crossover, stepback, post moves, lecture de la défense) et cherche à peaufiner des détails techniques ou tactiques fins."
    }
    niveau_choisi = st.selectbox("Niveau du joueur", list(niveaux_definitions.keys()))
    st.caption(niveaux_definitions[niveau_choisi])
    niveau = niveaux_definitions[niveau_choisi]

    objectifs = st.multiselect(
        "Objectifs à travailler",
        ["Tir", "Dribble", "Finition au panier", "Défense", "Force & Pliométrie"]
    )

    types_tir_cibles = []
    if "Tir" in objectifs:
        types_tir_cibles = st.multiselect(
            "Type de tir à cibler en particulier (optionnel)",
            ["Tir statique (spot-up)", "Tir en mouvement (off the dribble)", "Tir sous contestation défensive", "Tir en transition", "Lancers francs"]
        )

    experience_muscu = "Non renseigné"
    if "Force & Pliométrie" in objectifs:
        st.warning("⚠️ Le volet physique nécessite quelques précisions pour rester sûr.")
        experience_muscu = st.selectbox("Expérience en musculation/pliométrie", ["Débutant total", "Quelques mois", "Plus d'un an"])

    duree = st.slider("Durée du programme (semaines)", min_value=1, max_value=8, value=4)
    duree_seance = st.slider("Durée de chaque séance (minutes)", min_value=15, max_value=180, value=60, step=5)

    duree_physique = 0
    if "Force & Pliométrie" in objectifs:
        duree_physique = st.slider(
            "Temps à dédier au volet physique par séance (minutes)",
            min_value=5, max_value=duree_seance, value=min(15, duree_seance), step=5,
            help="Le reste de la séance sera consacré aux compétences basket."
        )
        st.caption(f"→ {duree_physique} min de physique, {duree_seance - duree_physique} min de basket, sur chaque séance.")

    st.markdown("**Jours d'entraînement**")
    st.caption("Choisis les jours semaine par semaine — ils n'ont pas besoin d'être les mêmes d'une semaine à l'autre.")
    jours_semaine_liste = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    jours_par_semaine = {}
    for num_semaine in range(1, duree + 1):
        with st.expander(f"Semaine {num_semaine}", expanded=(num_semaine == 1)):
            jours_par_semaine[num_semaine] = st.multiselect(
                "Jours d'entraînement",
                jours_semaine_liste,
                default=["Lundi", "Mercredi", "Vendredi"],
                key=f"jours_semaine_{num_semaine}"
            )

    if st.button("Générer le programme"):
        nb_seances_total = sum(len(jours) for jours in jours_par_semaine.values())
        if not objectifs:
            st.warning("Choisis au moins un objectif avant de générer le programme.")
        elif nb_seances_total == 0:
            st.warning("Choisis au moins un jour d'entraînement sur au moins une semaine.")
        else:
            ligne = df_modifiable[df_modifiable['nom'] == joueur_programme].iloc[0]
            objectifs_texte = ", ".join(objectifs)

            consigne_physique = ""
            if "Force & Pliométrie" in objectifs:
                consigne_physique = f"""
                Pour le volet physique (force, pliométrie, isométrie) : le joueur a pour expérience "{experience_muscu}" et signale comme blessure/douleur : "{blessures_generales if blessures_generales else 'aucune'}".
                Applique les principes recommandés par la NSCA pour les jeunes athlètes : développement multilatéral, technique avant charge, exercices au poids du corps ou à charge légère pour un débutant, mouvements pliométriques multi-directionnels (verticaux, horizontaux, latéraux) réalisés à effort maximal, et au moins 24 à 48h de récupération entre deux séances à dominante physique.
                PHILOSOPHIE BASKET, PAS BODYBUILDING : un basketteur n'a pas besoin d'un entraînement d'isolation façon musculation esthétique (pas de séries de biceps curls ou de développé couché comme seul objectif). Le basket se joue majoritairement en appui UNILATÉRAL (une jambe à la fois lors des courses, sauts, changements de direction) : privilégie donc les mouvements unilatéraux (fentes, squats sur une jambe, sauts sur une jambe) par rapport aux mouvements bilatéraux classiques. Privilégie aussi la puissance rotationnelle (medicine ball), l'explosivité (pliométrie), le gainage anti-rotation, l'équilibre/proprioception, la mobilité/prévention des blessures et le conditionnement spécifique basket (catégories dédiées dans la banque) — ce sont les qualités physiques qui transfèrent réellement sur le terrain, pas le volume musculaire pur.
                RÈGLE STRICTE DE DOSAGE (BUDGET TEMPS FIXÉ PAR LE COACH) : sur les {duree_seance} minutes totales de la séance, le coach a explicitement fixé {duree_physique} minutes pour le volet physique — PAS PLUS. Les {duree_seance - duree_physique} minutes restantes sont pour les compétences basket. N'ajoute PAS d'exercices physiques au-delà de ce budget, même si tu penses qu'il en faudrait plus : calibre le nombre d'exercices (2-3 si le budget est court, 4-6 s'il est plus généreux) pour remplir précisément {duree_physique} minutes, ni plus ni moins.
                RÈGLE (équilibre des groupes musculaires, dans la limite du budget temps ci-dessus) : quand le budget le permet, couvre plusieurs zones parmi bas du corps, haut du corps, gainage/core, équilibre/proprioception et mobilité — ce n'est jamais uniquement des squats/sauts avec une planche en guise de seul exercice de core. Varie aussi les exercices d'une séance à l'autre au fil du programme, ne répète pas systématiquement la même sélection.
                Évite tout exercice à haut risque de blessure, et précise systématiquement que ce programme doit être validé par un préparateur physique ou un professionnel avant d'être suivi.
                """

            conseils_poste = {
                "Meneur": "ball-handling sous pression, vision de jeu, prise de décision en transition, tir en sortie de dribble",
                "Arrière": "tir en catch-and-shoot et en sortie de dribble, finition en contre-attaque, défense sur joueur extérieur",
                "Ailier": "polyvalence : tir mi/longue distance, pénétration, finition, défense sur plusieurs postes",
                "Ailier fort": "post moves, rebond, écrans, jeu dans la raquette, tir mi-distance / pick-and-pop",
                "Pivot": "post moves, contre, rebond, finition près du cercle, agilité pour les rotations défensives"
            }
            consigne_poste = conseils_poste.get(poste, "les exigences générales de son poste")

            infos_complementaires = []
            if materiel_disponible:
                infos_complementaires.append(f"Matériel disponible : {', '.join(materiel_disponible)}. N'utilise pas de matériel non listé ici ; si rien n'est coché ou seulement 'Panier seulement', reste sur des exercices au poids du corps ou ne nécessitant qu'un ballon et un panier.")
            if partenaire_disponible == "Non, s'entraîne seul":
                infos_complementaires.append("Le joueur s'entraîne SEUL, sans partenaire ni coach disponible : adapte ou retire les drills nécessitant un défenseur/passeur actif (1v1 live, shell drill, exercices de passe à deux...), ou propose une variante solo réaliste (ex : chrono ou plot à la place d'un défenseur, mur pour les passes, rebond sur soi-même).")
            if lieu_entrainement:
                infos_complementaires.append(f"Lieu d'entraînement habituel : {lieu_entrainement}.")
            if taille_cm > 0:
                infos_complementaires.append(f"Taille : {taille_cm} cm.")
            if frequence_matchs != "Aucun match en ce moment":
                infos_complementaires.append(f"Fréquence de matchs actuelle : {frequence_matchs} — adapte l'intensité et le volume total pour ne pas surcharger le joueur en période de compétition.")
            if echeance:
                infos_complementaires.append(f"Échéance/objectif précis du coach : {echeance} — priorise en conséquence si c'est pertinent pour la durée du programme.")
            if postes_secondaires:
                infos_complementaires.append(f"Poste(s) secondaire(s) / polyvalence : {', '.join(postes_secondaires)}.")
            if style_jeu != "Non renseigné":
                infos_complementaires.append(f"Style de jeu recherché : {style_jeu}.")
            if jambe_appui_defense != "Non renseigné":
                infos_complementaires.append(f"Jambe d'appui dominante en défense : {jambe_appui_defense}.")
            if types_tir_cibles:
                infos_complementaires.append(f"Types de tir à cibler en particulier : {', '.join(types_tir_cibles)}.")

            infos_complementaires_texte = "\n".join(f"- {ligne}" for ligne in infos_complementaires) if infos_complementaires else "- Aucune information complémentaire renseignée."

            banque_categories = {
                "Échauffement (OBLIGATOIRE en premier exercice de CHAQUE séance)": [
                    "Walking High Knees", "Knee Hugs", "Glute Walk", "Jumping Jacks", "Airplane/Superman Drill",
                    "Frankenstein Drill", "Leg Swings (avant-arrière et latéral)", "Carioca", "Ball Slaps",
                    "Dribble d'échauffement (Two-Ball ou Figure 8 léger)", "World's Greatest Stretch", "Arm Circles"
                ],
                "Tir": [
                    "Form Shooting près du panier", "BEEF Shooting Drill", "Catch and Shoot 5 spots",
                    "Off the Dribble Pull-up", "Free Throw Routine", "Around the World", "Shooting off screens",
                    "Catch and Shoot 3-Point Series", "Off-Dribble 3-Point Pull-up", "Spot-Up 3-Point Shooting",
                    "Elevator Screen 3PT", "Changing Spots Shooting Drill", "Elbow Shooting Drill",
                    "Ray Allen Shooting Drill", "Shooting Off the Pass in Motion", "Quick-Release Shooting Drill",
                    "Close-out Contested Shooting Drill", "One-Dribble Pull-up Series (aile, sommet, angle)",
                    "Pound Dribble Step-Back Shooting Drill", "Shooting off the Gather (catch en course puis tir)",
                    "Shot Fake puis Tir (One-Two Step)"
                ],
                "Dribble / Ball Handling": [
                    "Two-Ball Dribbling", "Cone Weave Dribbling", "Tennis Ball Dribbling (main faible)",
                    "Full Speed Crossover Series", "Figure 8 Dribble", "In-and-Out Series", "Spider Dribble",
                    "Zig-Zag Dribble Drill", "Round the Body Drill", "Round the Head Drill", "Round the Legs Drill",
                    "Double Behind the Back Crossover", "Spin Dribble Series", "Weighted Ball Combo Series",
                    "Two-Ball Alternating Crossover"
                ],
                "Combo Moves (enchaînement dribble → tir ou finition, style workout pro)": [
                    "Hésitation → Crossover → Pull-up", "Pound Dribble → Step-Back 3 points",
                    "Crossover → Euro Step Finish", "Hésitation → Éclat (burst) → Finition au cercle",
                    "In-and-Out → Attaque directe du cercle", "Behind the Back → Pull-up mi-distance",
                    "Crossover → Behind the Back → Entre les jambes → Finition (combo Brickley)",
                    "Sonnette (Rocker Step) → Attaque ou Tir"
                ],
                "Écrans / Jeu sans ballon (adapté solo avec un plot ou une chaise en guise d'écran)": [
                    "Curl Cut sur écran (Down Screen)", "Pin Down puis Catch and Shoot",
                    "Fade sur écran (Flare Screen simulé)", "Dribble Screen (faux écran porteur) puis attaque du cercle",
                    "Pop sur écran puis Catch and Shoot", "Back Cut sur refus d'écran"
                ],
                "Finition (dont prise de balle avancée)": [
                    "Mikan Drill", "Reverse Mikan", "Euro Step Finishing", "Floater Drill",
                    "Contact Finishing (avec un partenaire ou un pad)", "2-Step Layup Drill", "Extension Layup Drill",
                    "Zig-Zag Layups", "Around the Arc 1v1 Finishing", "One Step Lay In",
                    "Inside-Foot Layup Cone Drill", "Power Layup/Bank Shot Drill", "Hop Step Finish",
                    "Reverse Layup", "Gather Step Finish (0 step) au ramassé de dribble", "Scoop Shot sous le cercle",
                    "Floater après Euro Step (combo)"
                ],
                "Défense (réalisable seul ou avec 1 partenaire)": [
                    "Defensive Slide Drill", "Closeout Drill", "Mirror Drill", "Zig-Zag Defense",
                    "1v1 Wing Defense Drill", "Defend the Dribble Drill", "Kick the Can Drill",
                    "Closeout Assignments Drill", "1v1 Zig-Zag Full Court to Post Defense"
                ],
                "Passes (solo ou avec 1 partenaire)": [
                    "Wall Pass (solo)", "Partner Chest Pass Series", "Partner Bounce Pass Series",
                    "Two-Man Give-and-Go Passing", "Pass the Rock (version 2 joueurs)", "One-Handed Push Pass Drill"
                ],
                "Rebond (solo ou avec 1 partenaire)": [
                    "Mikan Box-Out Drill", "Box Out 1v1 Drill", "Rebond et finition immédiate (solo, contre planche)"
                ],
                "Post moves (utile Pivot/Ailier fort)": [
                    "Up and Under", "Drop Step", "Jump Hook", "Baby Hook", "Spin Move", "Turnaround Jumper",
                    "Chamberlain Low Post Move Series", "Rapid Fire Post Moves Drill", "Crab Dribble Series",
                    "Jab Step → Face-up Attack", "Up Fake → Jump Hook"
                ],
                "Agilité / Footwork": [
                    "One Foot In (échelle)", "Two Feet In (échelle)", "Two-Foot In-and-Out (échelle)",
                    "Ickey Shuffle", "Lateral Shuffle (échelle)", "Linear Speed Ladder Drill",
                    "Crossover Ladder Drill", "Carioca Ladder Drill", "Figure 8 Cone Sprint"
                ],
                "Équilibre / Proprioception": [
                    "Single-Leg Balance Hold (yeux ouverts puis fermés)", "Star Excursion Reach",
                    "Single-Leg Balance avec réception de passe", "Bulgarian Split Squat contrôlé (équilibre + force)",
                    "Atterrissage contrôlé de saut (Box Landing / Stick the Landing)", "Tandem Stance Hold",
                    "Single-Leg RDL en équilibre"
                ],
                "Situations de match (1v1 par défaut ; au-delà, uniquement si le coach a confirmé plusieurs partenaires disponibles)": [
                    "1v1 Live", "1v1 Closeout Live", "Progression 1v1 à 2v2 (si partenaires disponibles)",
                    "Transition Solo Chronométrée"
                ],
                "Force & Pliométrie (bas du corps, priorité aux mouvements UNILATÉRAUX)": [
                    "Squat au poids du corps", "Goblet Squat", "Box Jump", "Broad Jump", "Lateral Bound",
                    "Depth Jump (avancé)", "Single-leg RDL", "Split Squat Jump", "Bulgarian Split Squat",
                    "Walking Lunges", "Pistol Squat (avancé)", "Power Skips", "Stair Jumps",
                    "Single-Leg Box Squat", "Lateral Lunge avec réachat", "Ankle Jumps (débutant)",
                    "Rotational Hops (débutant/intermédiaire)", "Squat Jump léger (débutant)",
                    "Zigzag Hops (avancé)", "Rotational Broad Jump (avancé)"
                ],
                "Force & Pliométrie (haut du corps, fonctionnel/explosif)": [
                    "Pompes (Push-ups)", "Pompes plyométriques (Plyo Push-ups)", "Medicine Ball Chest Pass",
                    "Medicine Ball Overhead Slam", "Rowing élastique (Band Row)", "Tirage vertical élastique (Band Pull-down)",
                    "Dips sur banc", "Pike Push-ups", "Diamond Push-ups", "Renegade Row (avancé)",
                    "Medicine Ball Rotational Slam (avancé)"
                ],
                "Force & Pliométrie (gainage/core, priorité anti-rotation et rotationnel)": [
                    "Plank", "Side Plank", "Superman", "Dead Bug", "Medicine Ball Rotational Throw",
                    "Russian Twist", "Hollow Hold", "Bird Dog", "Hanging Leg Raise (avancé)",
                    "Pallof Press (anti-rotation, élastique)", "Medicine Ball Woodchopper"
                ],
                "Conditioning / Endurance spécifique basket": [
                    "Suicides (sprints progressifs ligne par ligne)", "17s (sprints latéraux ligne à ligne)",
                    "Defensive Slide Conditioning (couloir de plots)", "Shuttle Run", "Sprint Intervalles (course/récupération)"
                ],
                "Mobilité / Prévention des blessures": [
                    "Ankle Circles", "Hip Circles (à quatre pattes et debout)", "Pigeon Stretch", "Cat-Camel",
                    "Deep Split Squat (mobilité de hanche)", "Dynamic Hip Extension", "Calf Raises (renforcement cheville)",
                    "Single Leg Jump to Double Leg Landing (prehab)", "Single Leg Hop to Single Leg Landing (prehab)"
                ],
            }

            banque_complete_texte = "\n".join(
                f"- {categorie} : {', '.join(liste)}" for categorie, liste in banque_categories.items()
            )

            def construire_prompt_semaine(num_semaine, jours_semaine, historique_texte, exclusions_texte):
                jours_semaine_texte = ", ".join(jours_semaine)
                return f"""
                Tu es un préparateur physique et technique de haut niveau, spécialisé dans le développement de jeunes basketteurs. Tu t'appuies sur les méthodes des programmes de développement reconnus (type IMG Academy, EYBL) et sur les recommandations de la NSCA pour la préparation physique.

                Profil du joueur :
                - {ligne['nom']}, {age} ans, poste {poste}, main dominante {main_dominante} (donnée informative uniquement — ne construis pas le programme autour de la main forte)
                - Niveau : {niveau}
                - Statistiques actuelles : moyenne {ligne['moyenne']} pts, progression {ligne['progression']}, {ligne['assists']} assists, {ligne['rebonds']} rebonds, {ligne['steals']} steals, {ligne['turnovers']} pertes de balle
                - Observations du coach (à pondérer avec les stats ci-dessus, pas à traiter comme LA priorité) : {points_faibles if points_faibles else "aucune observation particulière"}
                - Objectifs à travailler : {objectifs_texte}
                - Chaque séance dure environ {duree_seance} minutes.

                Informations complémentaires données par le coach :
                {infos_complementaires_texte}

                Principe fondamental : fais progresser le joueur sur l'ENSEMBLE de son jeu. Renforce aussi ses points forts (pour qu'ils deviennent des armes encore plus fiables) et ses points moyens, pas seulement ses points faibles.

                {consigne_physique}

                IMPORTANT — CETTE GÉNÉRATION NE CONCERNE QUE LA SEMAINE {num_semaine} SUR UN TOTAL DE {duree} SEMAINES (les autres semaines du programme sont générées séparément, dans d'autres appels — ne parle pas des autres semaines, concentre-toi uniquement sur celle-ci) :
                Jours d'entraînement pour cette semaine : {jours_semaine_texte}. Génère une séance pour CHACUN de ces jours, dans cet ordre.

                Historique des séances déjà générées lors des semaines précédentes de CE MÊME programme (pour information et pour assurer une vraie progression) :
                {historique_texte}

                EXERCICES INTERDITS pour cette semaine — liste noire précise, à respecter STRICTEMENT (contrainte automatique, pas une suggestion) : pour chaque jour ci-dessous, n'utilise AUCUN des noms d'exercices déjà utilisés ce même jour de la semaine lors d'une semaine précédente. Choisis autre chose dans la banque complète (fournie plus bas), en gardant la pertinence pour le profil du joueur — tu as tout le reste de la banque à disposition, ce n'est pas une restriction de choix, juste une interdiction de recopier :
                {exclusions_texte}

                IMPORTANT sur la durée : chaque séance doit RÉELLEMENT remplir les {duree_seance} minutes prévues (à 10-15 minutes près), échauffement inclus — ce n'est pas un plafond à ne pas dépasser, c'est un volume à atteindre. Avant de finaliser une séance, additionne mentalement le temps de chaque exercice (exécution + repos entre séries) et vérifie que le total correspond aux {duree_seance} minutes. Si {duree_seance} est élevé (par exemple 90 minutes ou plus), cela veut dire qu'il faut PLUS d'exercices et/ou plus de séries, jamais des exercices artificiellement allongés. Une séance de {duree_seance} minutes qui ne contient que 3-4 exercices courts est un échec de calibration.

                Banque de drills complète, choisis librement dedans (en respectant la liste noire ci-dessus) selon ce qui est le plus pertinent pour CE joueur précis :
                {banque_complete_texte}

                Méthodologie de construction des séances :
                1. PRIORITÉ aux situations de match : la majorité de chaque séance doit reposer sur des exercices en situation réelle (1v1, 2v2, 3v3, jeux réduits, exercices avec défenseur actif, transitions, prises de décision sous pression) plutôt que sur des répétitions techniques isolées sans opposition.
                2. Garde une base technique solide et PROFESSIONNELLE avec des drills PRÉCIS ET NOMMÉS (pas de généralités comme "travail du tir"). Utilise le nom internationalement reconnu de chaque drill (généralement en anglais, tel qu'utilisé dans le coaching, ex "Mikan Drill", "Shell Drill") même si le reste de la séance est décrit en français : ce sont des noms standards pour lesquels il existe de vraies vidéos de démonstration. Si "Tir" fait partie des objectifs, un exercice de Form Shooting (ou équivalent de calibrage technique) doit apparaître dès les premières séances du programme, quel que soit le niveau.
                3. Adapte au poste du joueur : {consigne_poste}.
                4. Adapte la difficulté et la complexité des drills au niveau du joueur décrit ci-dessus ({niveau_choisi}) : plus de drills fondamentaux et de répétitions guidées pour un profil débutant, plus de variantes avancées, de contraintes (temps, opposition, prise de décision) et de combinaisons de mouvements pour un profil avancé.
                5. Calibre le niveau de progression annoncé à la durée réelle du programme ({duree} semaines, nous générons actuellement la semaine {num_semaine}) : sur un programme court, privilégie les progrès techniques et la lecture de jeu (les gains athlétiques significatifs prennent du temps) ; sur un programme plus long, une progression physique plus marquée devient crédible et peut être visée plus franchement. Dans tous les cas, n'annonce jamais de transformation spectaculaire d'une semaine à l'autre.
                6. Varie les exercices d'une séance à l'autre pour éviter la monotonie.
                7. Couvre l'ENSEMBLE des sous-aspects de chaque objectif sélectionné sur la durée du programme, pas seulement une partie. Exemple pour "Tir" : varie les distances (près du cercle, mi-distance, ET tir à 3 points si le niveau du joueur le permet) et les situations (catch and shoot, sortie de dribble, sous contestation défensive) — un joueur de niveau avancé qui travaille son tir doit voir du tir à 3 points dans son programme. Le même principe s'applique aux autres objectifs (Dribble, Finition, Défense) : ne te limite pas à un seul type de situation ou de distance répété d'une séance à l'autre.
                8. Ne sois PAS trop rigide dans les associations poste/profil ↔ exercice : un joueur peut et doit progresser sur des compétences en dehors du profil traditionnel de son poste (ex : un Pivot peut tout à fait travailler le tir à 3 points si "Tir" est un objectif sélectionné, un Meneur peut travailler des post moves, etc.) — ne filtre jamais les objectifs choisis par le coach selon des stéréotypes de poste. En revanche, reste réaliste sur la PERTINENCE SITUATIONNELLE des combinaisons que tu inventes : par exemple, un tir à 3 points enchaîné après un pick-and-roll mené par un pivot n'est pas une situation de jeu crédible pour son rôle réel — ce n'est qu'un exemple parmi d'autres combinaisons peu réalistes à éviter. Distingue donc le TRAVAIL D'UNE COMPÉTENCE (toujours légitime, quel que soit le poste ou le profil) de la SITUATION DE JEU dans laquelle tu la mets en scène (qui doit rester crédible par rapport au rôle réel du joueur sur le terrain).
                9. ÉCHAUFFEMENT OBLIGATOIRE : le tout premier exercice de CHAQUE séance, sans exception, doit être un échauffement dynamique (5 à 10 minutes selon la durée totale de la séance), tiré de la catégorie "Échauffement" de la banque de drills ci-dessous. Ne commence JAMAIS une séance directement par un exercice technique ou physique intense (ex : ne pas démarrer directement par du tir à 3 points ou un exercice de pliométrie à froid).
                10. PROGRESSION INTERNE À LA SÉANCE : après l'échauffement, ordonne les exercices du plus simple/proche/fondamental vers le plus complexe/loin/exigeant. Par exemple pour une séance de tir, commence par du tir proche du panier (Form Shooting, Mikan) avant d'enchaîner vers le mi-distance puis le tir à 3 points ou sous contestation — ne mets jamais un exercice avancé (tir à 3 points, drill sous forte opposition) en tout début de séance juste après l'échauffement.
                11. RÉALISME LOGISTIQUE : ce programme est destiné à UN SEUL joueur. Tous les exercices doivent être réalisables par ce joueur SEUL ou avec AU MAXIMUM un partenaire d'entraînement, sauf si le coach a explicitement indiqué disposer d'un groupe/d'une équipe dans les informations complémentaires ci-dessus. N'utilise donc JAMAIS d'exercice nécessitant plusieurs partenaires supplémentaires ou une équipe complète (pas de 2v2/3v3/4v4, pas de "Shell Drill" classique à 8 joueurs, pas d'exercice de passes à 3 lignes ou plus) — remplace systématiquement par l'équivalent 1v1, en solo (contre un mur, un chrono ou une cible), ou avec un seul partenaire.
                12. NIVEAU DE JEU RÉEL, PAS SEULEMENT DES DRILLS ISOLÉS : pour un joueur de niveau Intermédiaire ou Avancé, intègre régulièrement des exercices de la catégorie "Combo Moves" (enchaînement dribble → tir/finition, comme dans un vrai workout pro type Chris Brickley ou Drew Hanlen) plutôt que de rester sur des répétitions techniques isolées. Utilise aussi la catégorie "Écrans / Jeu sans ballon" (un plot ou une chaise fait office d'écran) pour travailler le jeu sans ballon même en entraînement individuel — un joueur ne joue jamais uniquement en 1v1 avec ballon dans un vrai match.
                13. Les catégories "Équilibre / Proprioception", "Mobilité / Prévention des blessures" et "Conditioning / Endurance spécifique basket" ne sont pas liées uniquement à l'objectif "Force & Pliométrie" : pioche dedans ponctuellement pour n'importe quel joueur (prévention de blessure, endurance de match), même si "Force & Pliométrie" n'est pas sélectionné — dans ce cas, ça reste léger (1 exercice occasionnel), sans consommer de temps dédié au physique.

                Pour chaque séance, décompose les exercices en une LISTE d'objets structurés (pas un seul bloc de texte), chacun avec :
                - "nom" : le nom précis du drill
                - "series_reps" : le nombre de séries/répétitions ou la durée (ex : "4x10 répétitions", "3x30 secondes", "3 possessions")
                - "description" : 1 à 2 phrases claires expliquant COMMENT exécuter l'exercice, écrites pour qu'un débutant puisse comprendre et réaliser le mouvement sans supervision.
                - "schema" (optionnel, uniquement si utile pour visualiser un positionnement ou un déplacement sur le terrain — omets-le pour un exercice de musculation/gainage/tir répétitif au même endroit) : un petit schéma de demi-terrain avec :
                  - "elements" : liste de {{"type": "joueur"|"defenseur"|"plot", "x": nombre 0-100, "y": nombre 0-94, "label": "1 ou 2 caractères"}}
                  - "deplacements" (optionnel) : liste de {{"de": [x, y], "vers": [x, y], "style": "dribble"|"passe"|"course"}}
                  - Repère : x=0 (gauche) à x=100 (droite) ; y=0 (ligne médiane, en haut) à y=94 (ligne de fond sous le panier, en bas) ; le panier est environ en (50, 85). Reste cohérent avec un vrai demi-terrain (ex : un exercice de finition part de la zone raquette près du panier, un exercice de tir extérieur place le joueur au-delà de y=56).

                Réponds UNIQUEMENT avec un JSON valide, sans aucun texte avant ou après, sous la forme exacte suivante (une entrée par séance de CETTE semaine, "semaine" doit valoir {num_semaine} pour toutes les entrées, "jour" étant la position 1-indexée de la séance dans la liste de jours ci-dessus) :
                [{{"semaine": {num_semaine}, "jour": 1, "exercices": [{{"nom": "Mikan Drill", "series_reps": "3x10 répétitions", "description": "...", "schema": {{"elements": [{{"type": "joueur", "x": 50, "y": 80, "label": "J"}}, {{"type": "plot", "x": 44, "y": 88}}, {{"type": "plot", "x": 56, "y": 88}}], "deplacements": [{{"de": [44, 88], "vers": [56, 88], "style": "course"}}]}}}}, {{"nom": "...", "series_reps": "...", "description": "..."}}]}}]
                """

            def nettoyer_json(texte):
                texte = texte.strip()
                if texte.startswith("```"):
                    texte = texte.strip("`")
                    if texte.lower().startswith("json"):
                        texte = texte[4:]
                return texte

            semaines_a_generer = [(s, j) for s, j in jours_par_semaine.items() if j]
            seances = []
            historique_exercices = []
            deja_utilises_par_jour = {}
            erreur_generation = None
            barre_progression = st.progress(0, text="Génération du programme...")

            for i, (num_semaine, jours_semaine) in enumerate(semaines_a_generer):
                historique_texte = "\n".join(historique_exercices) if historique_exercices else "Aucune séance précédente (c'est la première semaine générée pour ce programme)."

                lignes_exclusions = []
                for jour_nom in jours_semaine:
                    deja_utilises = deja_utilises_par_jour.get(jour_nom, [])
                    if deja_utilises:
                        lignes_exclusions.append(f"- {jour_nom} : {', '.join(deja_utilises)}")
                exclusions_texte = "\n".join(lignes_exclusions) if lignes_exclusions else "Aucun exercice interdit (c'est la première fois que ces jours sont générés)."

                with st.spinner(f"Génération de la semaine {num_semaine}/{duree}..."):
                    reponse_semaine = demander_a_ia(construire_prompt_semaine(num_semaine, jours_semaine, historique_texte, exclusions_texte))

                if reponse_semaine.startswith("ERREUR_IA:"):
                    erreur_generation = f"Échec à la semaine {num_semaine} : {reponse_semaine}"
                    break

                try:
                    seances_semaine = json.loads(nettoyer_json(reponse_semaine))
                    seances.extend(seances_semaine)
                except (json.JSONDecodeError, TypeError):
                    erreur_generation = f"L'IA n'a pas renvoyé un JSON valide pour la semaine {num_semaine}, réessaie.\n\nRéponse brute : {reponse_semaine[:500]}"
                    break

                for seance_semaine in seances_semaine:
                    position_jour = seance_semaine.get("jour", 1)
                    nom_jour_reel = jours_semaine[position_jour - 1] if 0 < position_jour <= len(jours_semaine) else "?"
                    noms_exercices_liste = [exo.get("nom", "?") for exo in seance_semaine.get("exercices", []) if isinstance(exo, dict)]
                    historique_exercices.append(f"- Semaine {num_semaine}, {nom_jour_reel} : {', '.join(noms_exercices_liste)}")
                    deja_utilises_par_jour.setdefault(nom_jour_reel, []).extend(noms_exercices_liste)

                barre_progression.progress((i + 1) / len(semaines_a_generer), text=f"Semaine {num_semaine}/{duree} générée.")

            barre_progression.empty()

            if erreur_generation:
                st.error(erreur_generation)
            else:
                try:
                    indice_jour_semaine = {"Lundi": 0, "Mardi": 1, "Mercredi": 2, "Jeudi": 3, "Vendredi": 4, "Samedi": 5, "Dimanche": 6}
                    aujourdhui = datetime.date.today()
                    lundi_semaine_1 = aujourdhui - datetime.timedelta(days=aujourdhui.weekday())

                    for seance in seances:
                        semaine = seance.get("semaine", 1)
                        jour = seance.get("jour", 1)
                        jours_choisis = jours_par_semaine.get(semaine, [])
                        nom_jour = jours_choisis[jour - 1] if 0 < jour <= len(jours_choisis) else (jours_choisis[0] if jours_choisis else "Lundi")
                        lundi_semaine = lundi_semaine_1 + datetime.timedelta(weeks=semaine - 1)
                        seance["date"] = (lundi_semaine + datetime.timedelta(days=indice_jour_semaine[nom_jour])).isoformat()
                        seance["note"] = ""
                        if isinstance(seance.get("exercices"), str):
                            seance["exercices"] = [{"nom": "Séance", "series_reps": "", "description": seance["exercices"]}]

                    with st.spinner("Recherche des vidéos de démonstration..."):
                        enrichir_avec_videos(seances)

                    st.session_state.programmes[joueur_programme] = pd.DataFrame(seances)
                    sauvegarder_programme(joueur_programme, seances)
                    st.session_state.seance_selectionnee.pop(joueur_programme, None)
                    st.success("Programme généré et sauvegardé !")
                except (TypeError, KeyError):
                    st.error("Le programme généré a une structure inattendue, réessaie.")

    if joueur_programme in st.session_state.programmes:
        df_programme = st.session_state.programmes[joueur_programme]

        evenements = [
            {
                "title": f"Semaine {row['semaine']} — Séance {row['jour']}",
                "start": row["date"],
                "end": row["date"],
                "extendedProps": {"index": int(index)}
            }
            for index, row in df_programme.iterrows()
        ]

        etat_calendrier = calendar(
            events=evenements,
            options={"initialView": "dayGridMonth", "locale": "fr"},
            key=f"calendrier_programme_{joueur_programme}"
        )

        if etat_calendrier.get("eventClick"):
            st.session_state.seance_selectionnee[joueur_programme] = etat_calendrier["eventClick"]["event"]["extendedProps"]["index"]

        idx_selectionne = st.session_state.seance_selectionnee.get(joueur_programme)
        if idx_selectionne is not None and idx_selectionne in df_programme.index:
            idx = idx_selectionne
            seance = df_programme.loc[idx]
            date_seance = datetime.date.fromisoformat(seance["date"])
            jours_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

            with st.container(border=True):
                col_titre, col_date = st.columns([3, 2])
                with col_titre:
                    st.markdown(f"#### Semaine {seance['semaine']} — Séance {seance['jour']}")
                with col_date:
                    st.markdown(f"<div style='text-align:right; color:gray;'>{jours_fr[date_seance.weekday()]} {date_seance.strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)

                st.divider()

                for position, exercice in enumerate(seance["exercices"], start=1):
                    st.markdown(f"**{position}. {exercice.get('nom', 'Exercice')}**")
                    if exercice.get("series_reps"):
                        st.caption(exercice["series_reps"])
                    st.write(exercice.get("description", ""))

                    if exercice.get("schema"):
                        svg_schema = generer_schema_exercice(exercice["schema"])
                        if svg_schema:
                            st.markdown(svg_schema, unsafe_allow_html=True)

                    if exercice.get("video_url"):
                        st.markdown(f"[Vidéo complémentaire]({exercice['video_url']})")
                    else:
                        requete_video = urllib.parse.quote(f'"{exercice.get("nom", "")}" basketball drill')
                        st.markdown(f"[Rechercher une vidéo complémentaire](https://www.youtube.com/results?search_query={requete_video})")
                    st.markdown("")

                st.divider()

                nouvelle_note = st.text_area("Note (douleur, ressenti, résultat)", value=seance["note"], key=f"note_{joueur_programme}_{idx}")

                col_save, col_analyse = st.columns(2)
                with col_save:
                    if st.button("Sauvegarder la note", key=f"save_note_{joueur_programme}_{idx}"):
                        st.session_state.programmes[joueur_programme].loc[idx, "note"] = nouvelle_note
                        sauvegarder_programme(joueur_programme, st.session_state.programmes[joueur_programme].to_dict('records'))
                        st.success("Note sauvegardée.")
                with col_analyse:
                    if st.button("Faire analyser par l'IA", key=f"analyse_note_{joueur_programme}_{idx}"):
                        texte_exercices_seance = "\n".join(
                            f"- {e.get('nom', '')} ({e.get('series_reps', '')}) : {e.get('description', '')}"
                            for e in seance["exercices"]
                        )
                        prompt_analyse = f"""
                        Tu es un coach de basketball expérimenté qui suit un joueur sur la durée.

                        Séance prévue (semaine {seance['semaine']}, séance {seance['jour']}) :
                        {texte_exercices_seance}

                        Retour du joueur après la séance (douleur, ressenti, résultat) : {nouvelle_note if nouvelle_note else "aucun retour renseigné"}

                        Donne une analyse courte (3-4 phrases) : le ressenti est-il cohérent avec la séance prévue, y a-t-il un signal d'alerte (douleur, fatigue anormale) à surveiller, et un conseil concret pour la prochaine séance.
                        """
                        with st.spinner("Analyse en cours..."):
                            analyse_note = demander_a_ia(prompt_analyse)
                        st.info(analyse_note)
