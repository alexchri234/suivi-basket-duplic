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

def charger_programmes():
    donnees = charger_donnees()
    return donnees.get("programmes", {}).get(st.session_state.utilisateur_connecte, {})

def sauvegarder_programme(nom_joueur, seances):
    donnees = charger_donnees()
    donnees.setdefault("programmes", {})
    donnees["programmes"].setdefault(st.session_state.utilisateur_connecte, {})
    donnees["programmes"][st.session_state.utilisateur_connecte][nom_joueur] = seances
    sauvegarder_donnees(donnees)

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

    blessures = ""
    experience_muscu = "Non renseigné"
    if "Force & Pliométrie" in objectifs:
        st.warning("⚠️ Le volet physique nécessite quelques précisions pour rester sûr.")
        blessures = st.text_input("Blessures récentes ou douleurs actuelles (laisse vide si aucune)")
        experience_muscu = st.selectbox("Expérience en musculation/pliométrie", ["Débutant total", "Quelques mois", "Plus d'un an"])

    duree = st.slider("Durée du programme (semaines)", min_value=1, max_value=8, value=4)
    duree_seance = st.slider("Durée de chaque séance (minutes)", min_value=15, max_value=180, value=60, step=5)

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
                Pour le volet physique (force, pliométrie, isométrie) : le joueur a pour expérience "{experience_muscu}" et signale comme blessure/douleur : "{blessures if blessures else 'aucune'}".
                Applique les principes recommandés par la NSCA pour les jeunes athlètes : développement multilatéral, technique avant charge, exercices au poids du corps ou à charge légère pour un débutant, mouvements pliométriques multi-directionnels (verticaux, horizontaux, latéraux) réalisés à effort maximal, et au moins 24 à 48h de récupération entre deux séances à dominante physique.
                RÈGLE STRICTE : chaque séance qui inclut du travail physique doit comporter AU MINIMUM 4 exercices distincts de ce volet (idéalement 4 à 6), jamais seulement 1 ou 2 — sinon ce n'est pas un vrai volume d'entraînement. Si le nombre de séances disponibles dans la semaine le permet, privilégie plutôt de DÉDIER certaines séances entièrement au physique (4 à 6 exercices ce jour-là, rien d'autre) et de garder les autres séances entièrement pour les compétences basket, plutôt que de disperser un ou deux exercices physiques dans chaque séance. Répartis ce choix intelligemment selon le nombre de jours disponibles chaque semaine.
                RÈGLE STRICTE (équilibre des groupes musculaires) : chaque séance à dominante physique doit couvrir les TROIS zones — bas du corps, haut du corps ET gainage/core — ce n'est jamais uniquement des squats/sauts avec une planche en guise de seul exercice de core. Varie aussi les exercices d'une séance à l'autre au fil du programme, ne répète pas systématiquement la même sélection.
                Évite tout exercice à haut risque de blessure, et précise systématiquement que ce programme doit être validé par un préparateur physique ou un professionnel avant d'être suivi.
                """

            jours_texte = "\n".join(
                f"- Semaine {s} : {', '.join(jours) if jours else 'aucune séance'} ({len(jours)} séance(s)), dans cet ordre"
                for s, jours in jours_par_semaine.items()
            )

            conseils_poste = {
                "Meneur": "ball-handling sous pression, vision de jeu, prise de décision en transition, tir en sortie de dribble",
                "Arrière": "tir en catch-and-shoot et en sortie de dribble, finition en contre-attaque, défense sur joueur extérieur",
                "Ailier": "polyvalence : tir mi/longue distance, pénétration, finition, défense sur plusieurs postes",
                "Ailier fort": "post moves, rebond, écrans, jeu dans la raquette, tir mi-distance / pick-and-pop",
                "Pivot": "post moves, contre, rebond, finition près du cercle, agilité pour les rotations défensives"
            }
            consigne_poste = conseils_poste.get(poste, "les exigences générales de son poste")

            banque_drills = """
            Exemples de drills reconnus à utiliser ou à t'en inspirer (piocher largement dedans, ne pas se limiter à un ou deux) :
            - Tir : Form Shooting près du panier (à intégrer en DÉBUT de programme, quel que soit le niveau), BEEF Shooting Drill, Catch and Shoot 5 spots, Off the Dribble Pull-up, Free Throw Routine, Around the World, Shooting off screens, Catch and Shoot 3-Point Series, Off-Dribble 3-Point Pull-up, Spot-Up 3-Point Shooting, Elevator Screen 3PT.
            - Dribble : Two-Ball Dribbling, Cone Weave Dribbling, Tennis Ball Dribbling (main faible), Full Speed Crossover Series, Figure 8 Dribble, In-and-Out Series.
            - Finition : Mikan Drill, Reverse Mikan, Euro Step Finishing, Floater Drill, Contact Finishing (avec un partenaire ou un pad).
            - Défense : Defensive Slide Drill, Closeout Drill, Shell Drill, Mirror Drill, Zig-Zag Defense.
            - Situations de match : 1v1 Live, 2v2 Live, 3v3 Half Court, Shell Drill 4v4, Small-Sided Game (score limité), Transition 3v2.
            - Force & Pliométrie (bas du corps) : Squat au poids du corps, Box Jump, Broad Jump, Lateral Bound, Depth Jump (avancé), Single-leg RDL, Split Squat Jump, Bulgarian Split Squat.
            - Force & Pliométrie (haut du corps) : Pompes (Push-ups), Pompes plyométriques (Plyo Push-ups), Medicine Ball Chest Pass, Medicine Ball Overhead Slam, Rowing élastique (Band Row), Tirage vertical élastique (Band Pull-down), Dips sur banc, Pike Push-ups.
            - Force & Pliométrie (gainage/core) : Plank, Side Plank, Superman, Dead Bug, Medicine Ball Rotational Throw, Russian Twist, Hollow Hold.
            """

            prompt_programme = f"""
            Tu es un préparateur physique et technique de haut niveau, spécialisé dans le développement de jeunes basketteurs. Tu t'appuies sur les méthodes des programmes de développement reconnus (type IMG Academy, EYBL) et sur les recommandations de la NSCA pour la préparation physique.

            Profil du joueur :
            - {ligne['nom']}, {age} ans, poste {poste}, main dominante {main_dominante} (donnée informative uniquement — ne construis pas le programme autour de la main forte)
            - Niveau : {niveau}
            - Statistiques actuelles : moyenne {ligne['moyenne']} pts, progression {ligne['progression']}, {ligne['assists']} assists, {ligne['rebonds']} rebonds, {ligne['steals']} steals, {ligne['turnovers']} pertes de balle
            - Observations du coach (à pondérer avec les stats ci-dessus, pas à traiter comme LA priorité) : {points_faibles if points_faibles else "aucune observation particulière"}
            - Objectifs à travailler : {objectifs_texte}
            - Chaque séance dure environ {duree_seance} minutes.

            Principe fondamental : fais progresser le joueur sur l'ENSEMBLE de son jeu. Renforce aussi ses points forts (pour qu'ils deviennent des armes encore plus fiables) et ses points moyens, pas seulement ses points faibles.

            {consigne_physique}

            Calendrier exact voulu par le coach (jours d'entraînement par semaine) :
            {jours_texte}

            Génère une séance pour chacun de ces jours, dans l'ordre indiqué pour chaque semaine, en respectant strictement le nombre de séances par semaine.

            IMPORTANT sur la durée : chaque séance doit RÉELLEMENT remplir les {duree_seance} minutes prévues (à 10-15 minutes près), échauffement inclus — ce n'est pas un plafond à ne pas dépasser, c'est un volume à atteindre. Avant de finaliser une séance, additionne mentalement le temps de chaque exercice (exécution + repos entre séries) et vérifie que le total correspond aux {duree_seance} minutes. Si {duree_seance} est élevé (par exemple 90 minutes ou plus), cela veut dire qu'il faut PLUS d'exercices et/ou plus de séries, jamais des exercices artificiellement allongés. Une séance de {duree_seance} minutes qui ne contient que 3-4 exercices courts est un échec de calibration.

            {banque_drills}

            Méthodologie de construction des séances :
            1. PRIORITÉ aux situations de match : la majorité de chaque séance doit reposer sur des exercices en situation réelle (1v1, 2v2, 3v3, jeux réduits, exercices avec défenseur actif, transitions, prises de décision sous pression) plutôt que sur des répétitions techniques isolées sans opposition.
            2. Garde une base technique solide et PROFESSIONNELLE avec des drills PRÉCIS ET NOMMÉS (pas de généralités comme "travail du tir"). Utilise le nom internationalement reconnu de chaque drill (généralement en anglais, tel qu'utilisé dans le coaching, ex "Mikan Drill", "Shell Drill") même si le reste de la séance est décrit en français : ce sont des noms standards pour lesquels il existe de vraies vidéos de démonstration. Si "Tir" fait partie des objectifs, un exercice de Form Shooting (ou équivalent de calibrage technique) doit apparaître dès les premières séances du programme, quel que soit le niveau.
            3. Adapte au poste du joueur : {consigne_poste}.
            4. Adapte la difficulté et la complexité des drills au niveau du joueur décrit ci-dessus ({niveau_choisi}) : plus de drills fondamentaux et de répétitions guidées pour un profil débutant, plus de variantes avancées, de contraintes (temps, opposition, prise de décision) et de combinaisons de mouvements pour un profil avancé.
            5. Calibre le niveau de progression annoncé à la durée réelle du programme ({duree} semaines) : sur un programme court, privilégie les progrès techniques et la lecture de jeu (les gains athlétiques significatifs prennent du temps) ; sur un programme plus long, une progression physique plus marquée devient crédible et peut être visée plus franchement. Dans tous les cas, n'annonce jamais de transformation spectaculaire d'une semaine à l'autre.
            6. Varie les exercices d'une séance à l'autre pour éviter la monotonie.
            7. Couvre l'ENSEMBLE des sous-aspects de chaque objectif sélectionné sur la durée du programme, pas seulement une partie. Exemple pour "Tir" : varie les distances (près du cercle, mi-distance, ET tir à 3 points si le niveau du joueur le permet) et les situations (catch and shoot, sortie de dribble, sous contestation défensive) — un joueur de niveau avancé qui travaille son tir doit voir du tir à 3 points dans son programme. Le même principe s'applique aux autres objectifs (Dribble, Finition, Défense) : ne te limite pas à un seul type de situation ou de distance répété d'une séance à l'autre.

            Pour chaque séance, décompose les exercices en une LISTE d'objets structurés (pas un seul bloc de texte), chacun avec :
            - "nom" : le nom précis du drill
            - "series_reps" : le nombre de séries/répétitions ou la durée (ex : "4x10 répétitions", "3x30 secondes", "3 possessions")
            - "description" : 1 à 2 phrases claires expliquant COMMENT exécuter l'exercice, écrites pour qu'un débutant puisse comprendre et réaliser le mouvement sans supervision.

            Réponds UNIQUEMENT avec un JSON valide, sans aucun texte avant ou après, sous la forme exacte suivante (une entrée par séance, "jour" étant la position 1-indexée de la séance dans la liste de jours de sa semaine ci-dessus) :
            [{{"semaine": 1, "jour": 1, "exercices": [{{"nom": "...", "series_reps": "...", "description": "..."}}, {{"nom": "...", "series_reps": "...", "description": "..."}}]}}]
            """

            with st.spinner("Génération du programme..."):
                reponse_programme = demander_a_ia(prompt_programme)

            texte_json = reponse_programme.strip()
            if texte_json.startswith("```"):
                texte_json = texte_json.strip("`")
                if texte_json.lower().startswith("json"):
                    texte_json = texte_json[4:]

            try:
                seances = json.loads(texte_json)
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

                st.session_state.programmes[joueur_programme] = pd.DataFrame(seances)
                sauvegarder_programme(joueur_programme, seances)
                st.session_state.seance_selectionnee.pop(joueur_programme, None)
                st.success("Programme généré et sauvegardé !")
            except (json.JSONDecodeError, TypeError, KeyError):
                st.error("L'IA n'a pas renvoyé un JSON valide, réessaie.")
                st.text(reponse_programme)

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
                    requete_video = urllib.parse.quote(f'"{exercice.get("nom", "")}" basketball drill')
                    st.markdown(f"[Voir des vidéos de démonstration](https://www.youtube.com/results?search_query={requete_video})")
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
