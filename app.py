import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime, timedelta, date, time as dt_time
import time
import uuid
from streamlit_option_menu import option_menu
import plotly.express as px
import plotly.graph_objects as go
import requests
from icalendar import Calendar
from streamlit_calendar import calendar
import io
import streamlit.components.v1 as components

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="L3 CCA Dashboard", page_icon="🎓", layout="wide")

# --- GESTION DE L'ÉTAT (SESSION STATE) ---
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False
if 'pomodoro' not in st.session_state: st.session_state.pomodoro = None
# Gestion du Timer Persistant
if 'timer_active' not in st.session_state: st.session_state.timer_active = False
if 'timer_end_time' not in st.session_state: st.session_state.timer_end_time = None
if 'timer_subject' not in st.session_state: st.session_state.timer_subject = "Général"
if 'timer_duration' not in st.session_state: st.session_state.timer_duration = 25


# 🔗 LIEN EMPLOI DU TEMPS
ICS_CALENDAR_URL = "http://edt-v2.univ-nantes.fr/calendar/ics?timetables[0]=110228"

# PALETTE DE COULEURS
NAVY = "#1A2C42"
TEAL = "#008080"
GOLD = "#C5A059"
CLOUD = "#F4F6F7"
ORANGE_REV = "#ea580c"

# --- INJECTION CSS ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=Lato:wght@300;400;700&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Lato', sans-serif;
        background-color: {CLOUD};
        color: {NAVY};
    }}
    
    h1, h2, h3 {{
        font-family: 'Libre Baskerville', serif;
        color: {NAVY};
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{ background-color: {NAVY}; }}
    [data-testid="stSidebar"] h1 {{ color: white !important; }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{ color: #cbd5e1 !important; }}

    /* KPI Cards */
    .kpi-card {{
        background-color: white;
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
        border-left: 8px solid {NAVY};
        height: 100%;
    }}

    /* Boutons */
    .stButton>button {{
        background-color: {TEAL};
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: bold;
        transition: all 0.2s;
    }}
    .stButton>button:hover {{
        background-color: {NAVY};
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }}

    /* Onglets */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 10px;
        background-color: white;
        padding: 10px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 50px;
        border-radius: 5px;
        font-weight: 600;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {TEAL} !important;
        color: white !important;
    }}

    /* Timer Focus */
    .timer-display {{
        font-size: 80px;
        font-weight: bold;
        color: {NAVY};
        text-align: center;
        font-family: 'Courier New', monospace;
        background-color: white;
        padding: 20px;
        border-radius: 20px;
        border: 4px solid {GOLD};
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        margin: 20px 0;
    }}
    
    /* Cartes Fichiers Drive */
    .file-card {{
        background-color: white;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        transition: transform 0.2s;
    }}
    .file-card:hover {{
        border-color: {TEAL};
        transform: translateX(5px);
    }}
    </style>
    """, unsafe_allow_html=True)

# --- DONNÉES MATIÈRES ---
DEFAULT_S1 = [
    "Théorie des organisations", "Management Control", "Marché Financier", "TQG", 
    "Financial Analysis", "Droit des sociétés", "Droit fiscal", "Comptabilité", "Anglais"
]
DEFAULT_S2 = [
    "Diagnostic Financier", "Compta Approfondie 2", "Modélisation des Coûts", 
    "Int. Financial Accounting", "Diagnostic Général", "Droit des Sociétés 2", 
    "Droit du Crédit", "Droit Pénal Affaires", "Organisation et SI", "Info. Décisionnelle", 
    "Anglais", "Projet Professionnel"
]

SUBJECTS_CONFIG = {s: {"cat": "Cours", "color": NAVY, "icon": "book"} for s in DEFAULT_S1 + DEFAULT_S2}
SUBJECTS = list(SUBJECTS_CONFIG.keys())

# --- LIENS NOTEBOOK LM PERSONNALISÉS ---
NOTEBOOK_LINKS = {
    "Organisation et SI": "https://notebooklm.google.com/notebook/dcf2d45c-bba9-4abd-b028-b73fa041fbe0",
    "Droit Pénal Affaires": "https://notebooklm.google.com/notebook/456cd0d2-9229-4337-986d-08fbe6392520",
    "Droit du Crédit": "https://notebooklm.google.com/notebook/40ef1076-44e7-4a25-8e16-54004ff16292",
    "Droit des Sociétés 2": "https://notebooklm.google.com/notebook/afd6663d-db08-4303-aca7-20e8bfbc449f",
    "Diagnostic Général": "https://notebooklm.google.com/notebook/e65d1578-ec56-4d08-ad8e-683c74df0c7e",
    "Int. Financial Accounting": "https://notebooklm.google.com/notebook/ef2f1e79-3596-424a-8f53-20a465f4f035",
    "Modélisation des Coûts": "https://notebooklm.google.com/notebook/3a5d9eb9-b9ae-4aae-a9d4-2fc6e5c22978",
    "Compta Approfondie 2": "https://notebooklm.google.com/notebook/82f3bf4d-ed58-4d03-8174-3ade0bf36dfb",
    "Diagnostic Financier": "https://notebooklm.google.com/notebook/1f05199b-f66b-4f68-92e2-f0158a7805da"
}

# --- CONNEXIONS GOOGLE ---
@st.cache_resource 
def get_google_services():
    try:
        if "gcp_service_account" not in st.secrets: return None, None
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open("L3_Compta_Database")
        drive_service = build('drive', 'v3', credentials=creds)
        return sheet, drive_service
    except Exception as e:
        print(f"Erreur Google: {e}") 
        return None, None

# --- UTILS DRIVE & CALENDAR ---
def get_or_create_subject_folder(drive_service, subject_name):
    try:
        root_id = st.secrets["general"]["drive_root_folder_id"]
        query = f"mimeType='application/vnd.google-apps.folder' and name='{subject_name}' and '{root_id}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id)").execute()
        items = results.get('files', [])
        if items: return items[0]['id']
        file_metadata = {'name': subject_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [root_id]}
        return drive_service.files().create(body=file_metadata, fields='id').execute().get('id')
    except: return None

def list_drive_files(drive_service, folder_id):
    try:
        results = drive_service.files().list(q=f"'{folder_id}' in parents and trashed=false", fields="files(id, name, webViewLink, iconLink)").execute()
        return results.get('files', [])
    except: return []

def upload_file_to_drive(drive_service, uploaded_file, folder_id):
    try:
        # On convertit le fichier en flux binaire
        file_content = io.BytesIO(uploaded_file.getvalue())
        
        # --- LE FIX EST ICI : resumable=False ---
        # Cela force un envoi direct au lieu de couper le fichier en morceaux (ce qui causait ton erreur)
        media = MediaIoBaseUpload(file_content, mimetype=uploaded_file.type, resumable=False)
        
        file_metadata = {'name': uploaded_file.name, 'parents': [folder_id]}
        
        drive_service.files().create(body=file_metadata, media_body=media).execute()
        return True
    except Exception as e:
        st.error(f"Erreur Upload : {e}")
        return False

@st.cache_data(ttl=3600, show_spinner=False) 
def get_ics_events_cached(ics_url):
    events = []
    try:
        resp = requests.get(ics_url, timeout=10)
        if resp.status_code == 200:
            cal = Calendar.from_ical(resp.content)
            for c in cal.walk('vevent'):
                events.append({
                    "title": str(c.get('summary', 'Cours')), 
                    "start": c.get('dtstart').dt.isoformat(), 
                    "end": c.get('dtend').dt.isoformat(),
                    "backgroundColor": TEAL, "borderColor": NAVY
                })
    except: pass
    return events

def get_combined_events(ics_url, sh):
    events = get_ics_events_cached(ics_url)
    if sh:
        try:
            # Récupérer les événements depuis l'onglet "Events" du Google Sheet
            # Assurez-vous que l'onglet 'Events' existe et contient les colonnes : ID, Title, Start, End, Type
            recs = sh.worksheet("Events").get_all_records()
            for r in recs:
                events.append({
                    "title": f"📚 {r['Title']}", 
                    "start": r['Start'], 
                    "end": r['End'],
                    "backgroundColor": ORANGE_REV,  # Orange pour tes révisions
                    "borderColor": GOLD
                })
        except Exception as e:
            # Si l'onglet n'existe pas ou erreur, on continue juste avec l'ICS
            pass
    return events

# --- FONCTION KPI CARD ---
def kpi_card(title, value, subtitle, color, icon):
    st.markdown(f"""
    <div class="kpi-card" style="border-left: 8px solid {color};">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div>
                <p style="font-size: 11px; font-weight: bold; color: #94a3b8; text-transform: uppercase; margin-bottom: 5px;">{title}</p>
                <h2 style="font-size: 2.2rem; font-weight: bold; color: {NAVY}; margin: 0;">{value}</h2>
            </div>
            <div style="width: 45px; height: 45px; background-color: {color}20; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: {color}; font-size: 1.4rem;">
                {icon}
            </div>
        </div>
        <p style="font-size: 13px; color: {TEAL}; font-weight: bold; margin-top: 15px;">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

# --- CALCULATEUR MOYENNE ---
def load_simulator_data(sh):
    try:
        ws = sh.worksheet("Simulateur")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            init_data = []
            for m in DEFAULT_S1: init_data.append({"Matiere": m, "Semestre": "S1", "Coef_CC": 1, "Coef_Partiel": 2, "Note_CC": 0, "Note_Partiel": 0})
            for m in DEFAULT_S2: init_data.append({"Matiere": m, "Semestre": "S2", "Coef_CC": 1, "Coef_Partiel": 2, "Note_CC": 0, "Note_Partiel": 0})
            df = pd.DataFrame(init_data)
            ws.update([df.columns.values.tolist()] + df.values.tolist())
        return df
    except: return pd.DataFrame()

def save_simulator_data(sh, df):
    try:
        ws = sh.worksheet("Simulateur")
        cols_to_save = ["Matiere", "Semestre", "Coef_CC", "Coef_Partiel", "Note_CC", "Note_Partiel"]
        df_save = df[cols_to_save]
        ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())
    except Exception as e: st.error(f"Erreur sauvegarde: {e}")

# --- NAVIGATION ---
def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2 style='color:white; text-align:center;'>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        st.write("")
        
        # 1. On détermine l'index par défaut basé sur l'état actuel pour synchroniser
        options = ["Dashboard", "Mes Cours", "Focus Room"]
        try:
            default_ix = options.index(st.session_state.current_view)
        except:
            default_ix = 0

        # --- FIX CSS POUR MENU (Coins Blancs) ---
        selected = option_menu(
            menu_title=None,
            options=options,
            icons=["speedometer2", "grid-3x3-gap", "hourglass-split"],
            menu_icon="cast",
            default_index=default_ix, 
            styles={
                # AJOUT DE border-radius: 0 ICI 👇
                "container": {"padding": "0!important", "background-color": NAVY, "border-radius": "0"}, 
                "icon": {"color": "#94a3b8", "font-size": "14px"}, 
                "nav-link": {"font-size": "14px", "text-align": "left", "margin":"0px", "color": "#e2e8f0"},
                "nav-link-selected": {"background-color": TEAL, "color": "white", "font-weight": "bold"},
            }
        )
    return selected

# --- PAGES ---
# --- REMPLACE TOUTE LA FONCTION dashboard_page PAR CELLE-CI ---
def dashboard_page(sh):
    st.markdown(f"### 👋 Dashboard Étudiant")
    st.markdown(f"<p style='color:#64748b;'>{datetime.now().strftime('%d %B %Y')}</p>", unsafe_allow_html=True)

    df_sim = pd.DataFrame()
    s1_avg_display = "0.0/20"
    s2_avg_display = "En attente" # Par défaut, pour indiquer que c'est progressif
    
    if sh:
        try:
            df_sim = load_simulator_data(sh)
            if not df_sim.empty:
                # --- CALCUL S1 (Classique) ---
                s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
                s1['Total_Coef'] = s1['Coef_CC'] + s1['Coef_Partiel']
                s1['Moy_Mat'] = ((s1['Note_CC']*s1['Coef_CC']) + (s1['Note_Partiel']*s1['Coef_Partiel'])) / s1['Total_Coef'].replace(0, 1)
                
                valid_s1 = s1[s1['Total_Coef'] > 0]
                if not valid_s1.empty:
                    s1_avg_display = f"{valid_s1['Moy_Mat'].mean():.2f}/20"

                # --- CALCUL S2 (Progressif - LA MODIF EST ICI) ---
                s2 = df_sim[df_sim['Semestre'] == 'S2'].copy()
                s2['Total_Coef'] = s2['Coef_CC'] + s2['Coef_Partiel']
                
                # On ne garde que les matières où l'étudiant a mis des coefficients > 0
                valid_s2 = s2[s2['Total_Coef'] > 0].copy()
                
                if not valid_s2.empty:
                    # Calcul de la moyenne pour ces matières valides seulement
                    valid_s2['Moy_Mat'] = ((valid_s2['Note_CC']*valid_s2['Coef_CC']) + (valid_s2['Note_Partiel']*valid_s2['Coef_Partiel'])) / valid_s2['Total_Coef']
                    # Moyenne générale du semestre (moyenne des moyennes)
                    s2_avg_display = f"{valid_s2['Moy_Mat'].mean():.2f}/20"
                else:
                    s2_avg_display = "En attente" # Aucune matière commencée
        except: pass

    # --- KPI 2 COLONNES ---
    c1, c2 = st.columns(2)
    
    # 1. BLOC MOYENNE (Affiche S2 en priorité)
    with c1:
        kpi_card("Moyenne S2 (Progressive)", s2_avg_display, f"Moyenne S1 : {s1_avg_display}", NAVY, "🎓")
        if st.button("🧮 Ouvrir le Simulateur de Notes", key="btn_sim_top", use_container_width=True):
            st.session_state.show_simulator = not st.session_state.show_simulator
            st.rerun()

    # 2. BLOC FOCUS ROOM
    with c2:
        focus_txt = "Prêt à bosser ?"
        if st.session_state.get("pomodoro"): focus_txt = "🔥 Session en cours..."
        kpi_card("Focus Room", focus_txt, "Productivité Maximale", GOLD, "⏳")
        if st.button("🚀 Accéder à la Focus Room", key="btn_focus_top", use_container_width=True):
            st.session_state.current_view = "Focus Room"
            st.rerun()

    # --- SIMULATEUR ---
    if st.session_state.show_simulator and not df_sim.empty:
        st.write("")
        st.markdown(f"### 🧮 Simulateur de Notes")
        st.info("💡 ASTUCE S2 : Si tu n'as pas encore de note, laisse les Coefs à 0. La matière sera ignorée du calcul.")
        
        try:
            tab_s1, tab_s2 = st.tabs(["📘 Semestre 1", "📙 Semestre 2"])
            
            # Configuration des colonnes
            cols_config = {
                "Matiere": st.column_config.TextColumn("Matière", disabled=True, width="medium"),
                "Semestre": None,
                "Coef_CC": st.column_config.NumberColumn("Coef CC", min_value=0, max_value=10, step=0.5, format="%.1f", width="small"),
                "Coef_Partiel": st.column_config.NumberColumn("Coef Partiel", min_value=0, max_value=10, step=0.5, format="%.1f", width="small"),
                "Note_CC": st.column_config.NumberColumn("Note CC", min_value=0, max_value=20, step=0.5, format="%.1f", width="small"),
                "Note_Partiel": st.column_config.NumberColumn("Note Partiel", min_value=0, max_value=20, step=0.5, format="%.1f", width="small")
            }

            def display_sim_tab(df_semestre, key_suffix):
                # Affichage de l'éditeur
                edited_df = st.data_editor(df_semestre, column_config=cols_config, hide_index=True, use_container_width=True, key=f"editor_{key_suffix}")
                
                if not edited_df.empty:
                    # Calcul visuel "Live" dans le tableau
                    t_coef = edited_df['Coef_CC'] + edited_df['Coef_Partiel']
                    # On évite la division par 0 juste pour l'affichage
                    edited_df['Moyenne'] = ((edited_df['Note_CC'] * edited_df['Coef_CC']) + (edited_df['Note_Partiel'] * edited_df['Coef_Partiel'])) / t_coef.replace(0, 1)
                    # Si coef est 0, on force la moyenne à 0 visuellement
                    edited_df.loc[t_coef == 0, 'Moyenne'] = 0
                    
                    st.write("**Résultats calculés :**")
                    st.dataframe(edited_df[['Matiere', 'Moyenne']].style.format({"Moyenne": "{:.2f}"}).background_gradient(subset=['Moyenne'], cmap="RdYlGn", vmin=0, vmax=20), use_container_width=True)
                    return edited_df

            with tab_s1: edited_s1 = display_sim_tab(df_sim[df_sim['Semestre'] == 'S1'], "S1")
            with tab_s2: edited_s2 = display_sim_tab(df_sim[df_sim['Semestre'] == 'S2'], "S2")

            if st.button("💾 Sauvegarder dans Google Sheets", type="primary"):
                # Nettoyage des colonnes temporaires avant sauvegarde
                clean_s1 = edited_s1.drop(columns=['Moyenne', 'Total_Coef', 'Moy_Mat'], errors='ignore')
                clean_s2 = edited_s2.drop(columns=['Moyenne', 'Total_Coef', 'Moy_Mat'], errors='ignore')
                full_df = pd.concat([clean_s1, clean_s2])
                
                save_simulator_data(sh, full_df)
                st.success("✅ Sauvegardé ! La moyenne S2 est à jour.")
                time.sleep(1); st.rerun()
        except Exception as e: st.error(f"Erreur Simulateur: {e}")
        st.markdown("---")

    st.write("")
    c_left, c_right = st.columns([2, 1])
    with c_left:
        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        # --- RÉINTÉGRATION DE L'AJOUT ET DE LA SUPPRESSION D'ÉVÉNEMENTS ---
        events = get_combined_events(ICS_CALENDAR_URL, sh)
        calendar(events=events, options={"headerToolbar": {"left": "today prev,next", "center": "title", "right": "timeGridWeek,dayGridMonth"}, "initialView": "timeGridWeek", "height": "550px", "locale": "fr"}, custom_css=".fc-event { border-radius: 4px; font-size: 11px; }")
        
        if sh:
            with st.expander("➕ Ajouter une session de révision"):
                with st.form("add_event_form"):
                    # --- ALIGNEMENT HORIZONTAL ---
                    c_titre, c_date, c_deb, c_fin = st.columns([2, 1, 1, 1])
                    
                    with c_titre: 
                        ev_title = st.text_input("Matière/Titre")
                    with c_date:
                        ev_date = st.date_input("Date")
                    with c_deb:
                        ev_start = st.time_input("Début", dt_time(18,0))
                    with c_fin:
                        ev_end = st.time_input("Fin", dt_time(19,0))
                    
                    if st.form_submit_button("Ajouter au Calendrier"):
                        try:
                            start = datetime.combine(ev_date, ev_start).isoformat()
                            end = datetime.combine(ev_date, ev_end).isoformat()
                            # Ajout dans la feuille 'Events'
                            sh.worksheet("Events").append_row([str(uuid.uuid4())[:8], ev_title, start, end, "Revision"])
                            st.success("Ajouté !")
                            time.sleep(1); st.rerun()
                        except Exception as e:
                            st.error(f"Erreur : {e}")

            with st.expander("🗑️ Gérer mes événements perso"):
                try:
                    # On ne liste que les événements perso (ceux dans le Sheet, pas l'ICS)
                    df_ev = pd.DataFrame(sh.worksheet("Events").get_all_records())
                    if not df_ev.empty:
                        for i, row in df_ev.iterrows():
                            c_t, c_b = st.columns([4, 1])
                            c_t.markdown(f"**{row['Title']}** <span style='color:grey; font-size:12px'>{row['Start']}</span>", unsafe_allow_html=True)
                            if c_b.button("❌", key=f"del_ev_{row['ID']}"):
                                try:
                                    ids = sh.worksheet("Events").col_values(1) # ID est en colonne 1
                                    idx = ids.index(str(row['ID']).strip()) + 1
                                    sh.worksheet("Events").delete_rows(idx)
                                    st.success("Supprimé !")
                                    time.sleep(1)
                                    st.rerun()
                                except: st.error("Introuvable")
                            st.divider()
                    else: st.info("Aucun événement personnel ajouté.")
                except Exception as e:
                    pass # Silencieux si pas d'onglet Events ou vide
    
    with c_right:
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do Urgent</span>", unsafe_allow_html=True)
        if sh:
            try:
                tasks = pd.DataFrame(sh.worksheet("Tasks").get_all_records())
                todo_tasks = tasks[tasks['Status'] == 'À faire'] if not tasks.empty else pd.DataFrame()
                
                if not todo_tasks.empty:
                    for i, row in todo_tasks.head(4).iterrows():
                        with st.container(border=True):
                            c_chk, c_txt = st.columns([1, 4])
                            if c_chk.button("✔", key=f"d_{row['ID']}"):
                                cell = sh.worksheet("Tasks").find(row['ID'])
                                sh.worksheet("Tasks").update_cell(cell.row, 4, "Fait"); st.rerun()
                            c_tx.markdown(f"**{row['Task']}**<br><span style='color:grey; font-size:12px'>{row['Subject']}</span>", unsafe_allow_html=True)
                else:
                    st.success("🎉 Rien à faire ! Profite de ta pause.")
            except: st.info("Aucune tâche.")

# --- PAGE 2: GRILLE DES COURS (S2 SEULEMENT) ---
def courses_grid_page():
    st.markdown("### 📚 Mes Modules S2"); st.write("")
    cols = st.columns(3)
    for index, subject in enumerate(DEFAULT_S2):
        with cols[index % 3]:
            st.markdown(f"""<div style="background-color:white; padding:20px; border-radius:10px; border-left:5px solid {NAVY}; margin-bottom:10px; box-shadow:0 2px 5px rgba(0,0,0,0.05)"><h3>{subject}</h3></div>""", unsafe_allow_html=True)
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True):
                st.session_state.selected_subject = subject; st.rerun()

# --- PAGE 3: DÉTAIL MATIÈRE (AVEC NOTEBOOKLM PERSONNALISÉ) ---
def subject_detail_page(sh, drive, subject):
    if st.button("← Retour"): st.session_state.selected_subject = None; st.rerun()
    st.title(subject)
    tab1, tab2 = st.tabs(["📂 Fichiers & IA", "✅ Tâches"])
    
    with tab1:
        # --- BLOC NOTEBOOK LM ---
        with st.container(border=True):
            c_logo, c_txt, c_btn = st.columns([0.5, 3, 1.5])
            with c_logo: st.markdown("## 🧠")
            with c_txt:
                st.markdown(f"**Booster de révision NotebookLM**")
                st.caption(f"Accède au carnet de notes dédié pour *{subject}*.")
            with c_btn:
                notebook_url = NOTEBOOK_LINKS.get(subject, "https://notebooklm.google.com/")
                st.link_button("↗ Ouvrir NotebookLM", notebook_url, type="primary", use_container_width=True)
        st.write("")

        # --- GESTION DRIVE (MODE LECTURE SEULE) ---
        if drive:
            # On récupère l'ID du dossier
            fid = get_or_create_subject_folder(drive, subject)
            
            if fid:
                # Lien direct pour uploader manuellement
                folder_url = f"https://drive.google.com/drive/folders/{fid}"
                st.info("💡 Pour ajouter des cours, dépose-les directement dans le dossier Drive ci-dessous.")
                st.markdown(f"""
                <a href="{folder_url}" target="_blank" style="text-decoration:none;">
                    <div style="background-color:#E8F0FE; color:#1967D2; padding:10px; border-radius:8px; text-align:center; font-weight:bold; border:1px solid #D2E3FC; margin-bottom:20px;">
                        📂 Ouvrir le dossier "{subject}" sur Google Drive
                    </div>
                </a>
                """, unsafe_allow_html=True)

                # Affichage des fichiers existants
                st.markdown("### 📄 Mes documents disponibles")
                files = list_drive_files(drive, fid)
                if files:
                    for f in files:
                        icon_url = f.get('iconLink', 'https://ssl.gstatic.com/docs/doclist/images/icon_10_generic_list.png')
                        st.markdown(f"""
                        <div class="file-card">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <img src='{icon_url}' width='20'>
                                <span style='font-weight:bold; color:{NAVY}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 250px;'>{f['name']}</span>
                            </div>
                            <a href='{f['webViewLink']}' target='_blank' style='text-decoration:none; color:{TEAL}; font-size:12px; font-weight:bold; border:1px solid {TEAL}; padding:4px 8px; border-radius:4px;'>Ouvrir</a>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("Aucun fichier détecté. Ajoute-les via le lien ci-dessus !")
            else:
                st.error("Impossible de trouver le dossier sur le Drive.")
        else:
            st.warning("Connexion Drive inactive.")

    with tab2:
        if sh:
            t, d = st.columns([3, 1]); nt = t.text_input("Tâche"); nd = d.date_input("Date")
            if st.button("Ajouter"): sh.worksheet("Tasks").append_row([str(uuid.uuid4())[:8], subject, nt, "À faire", str(nd)]); st.rerun()
            
            recs = sh.worksheet("Tasks").get_all_records()
            if recs:
                df = pd.DataFrame(recs)
                if 'Subject' in df.columns and 'Status' in df.columns:
                    df = df[(df['Subject'] == subject) & (df['Status'] == 'À faire')]
                    for i, r in df.iterrows():
                        c_chk, c_info = st.columns([1, 10])
                        if c_chk.checkbox("", key=f"c_{r['ID']}"):
                            cell = sh.worksheet("Tasks").find(r['ID'])
                            sh.worksheet("Tasks").update_cell(cell.row, 4, "Fait"); st.rerun()
                        d_show = f"📅 {r['Due_Date']}" if "Due_Date" in r and r["Due_Date"] else ""
                        c_info.markdown(f"{r['Task']} <span style='color:#e11d48; margin-left:10px; font-size:0.8em'>{d_show}</span>", unsafe_allow_html=True)

# --- PAGE 4: FOCUS ROOM (RESTORED & FIXED) ---
def focus_room_page():
    st.markdown(f"### ⏳ Focus Room")
    st.markdown("Configure ta session. Le timer continuera même si tu changes de menu.")
    
    # --- INTÉGRATION APPLE MUSIC (Lofi Girl) ---
    with st.expander("🎵 Ambiance Sonore (Apple Music)", expanded=True):
        # On utilise une iframe sécurisée pour Apple Music
        embed_code = """
        <iframe allow="autoplay *; encrypted-media *; fullscreen *; clipboard-write" 
        frameborder="0" height="175" style="width:100%;max-width:660px;overflow:hidden;background:transparent;" 
        sandbox="allow-forms allow-popups allow-same-origin allow-scripts allow-storage-access-by-user-activation allow-top-navigation-by-user-activation" 
        src="https://embed.music.apple.com/fr/playlist/lofi-girl-beats-to-relax-study-to/pl.bf7a3cbca49644d8a33f09c1285aef5c">
        </iframe>
        """
        components.html(embed_code, height=180)

    # --- LOGIQUE DU TIMER PERSISTANT ---
    # Si aucun timer n'est actif, on affiche les réglages
    if not st.session_state.get('timer_active'):
        c1, c2, c3, c4 = st.columns(4)
        # On utilise DEFAULT_S2 ou une liste par défaut si non définie
        liste_matieres = DEFAULT_S2 if 'DEFAULT_S2' in globals() else ["Général", "Compta", "Droit"]
        subj = c1.selectbox("Matière", liste_matieres)
        dur = c2.number_input("Durée (min)", 1, 120, 25)
        short_break = c3.number_input("Pause courte", 1, 15, 5)
        cycles = c4.number_input("Cycles", 1, 10, 4)
        
        if st.button("▶ LANCER LA SESSION", type="primary"):
            # On enregistre l'heure de FIN prévue (C'est ça qui permet la persistance !)
            st.session_state.timer_active = True
            st.session_state.timer_end_time = datetime.now() + timedelta(minutes=dur)
            st.session_state.timer_subject = subj
            st.session_state.timer_duration = dur
            st.rerun()
            
    # Si un timer EST actif, on affiche le décompte
    else:
        # Calcul du temps restant par rapport à maintenant
        now = datetime.now()
        remaining = st.session_state.timer_end_time - now
        
        # Si temps restant > 0
        if remaining.total_seconds() > 0:
            mins, secs = divmod(int(remaining.total_seconds()), 60)
            
            st.markdown(f"<p class='timer-label'>💻 FOCUS EN COURS • {st.session_state.timer_subject}</p>", unsafe_allow_html=True)
            st.markdown(f"<div class='timer-display'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
            
            # Barre de progression
            total_seconds = st.session_state.timer_duration * 60
            elapsed = total_seconds - remaining.total_seconds()
            st.progress(max(0.0, min(1.0, elapsed / total_seconds)))
            
            if st.button("⏹ Abandonner"):
                st.session_state.timer_active = False
                st.session_state.timer_end_time = None
                st.rerun()
            
            # Rechargement automatique toutes les secondes pour l'effet visuel
            time.sleep(1)
            st.rerun()
            
        else:
            # Le temps est écoulé !
            st.balloons()
            st.success(f"Session de {st.session_state.timer_subject} terminée ! Bravo 🎉")
            
            # Sauvegarde automatique (si la fonction existe)
            # if 'save_to_history' in globals() and 'sh' in globals() and sh:
            #    save_to_history(sh, "Pomodoro", st.session_state.timer_subject, st.session_state.timer_duration)
            
            # Réinitialisation
            if st.button("Nouvelle Session"):
                st.session_state.timer_active = False
                st.session_state.timer_end_time = None
                st.rerun()

# --- MAIN ---
if __name__ == "__main__":
    sh, drive = get_google_services()
    selected_page = sidebar_menu()
    
    # Synchronisation Navigation : Si la sidebar change, on met à jour la vue
    if selected_page != st.session_state.current_view:
        st.session_state.current_view = selected_page
        st.session_state.selected_subject = None
        st.rerun()

    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours":
        if st.session_state.selected_subject: subject_detail_page(sh, drive, st.session_state.selected_subject)
        else: courses_grid_page()
    elif st.session_state.current_view == "Focus Room": focus_room_page()
