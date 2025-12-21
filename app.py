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

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="L3 CCA Dashboard", page_icon="🎓", layout="wide")

# --- GESTION DE L'ÉTAT (SESSION STATE) ---
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False # Pour ouvrir le simulateur

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
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        border-left: 5px solid {NAVY};
    }}

    /* Boutons */
    .stButton>button {{
        background-color: {TEAL};
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: bold;
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
    </style>
    """, unsafe_allow_html=True)

# --- DONNÉES MATIÈRES (PAR DÉFAUT) ---
DEFAULT_S1 = [
    "Théorie des organisations", "Management Control", "Marché Financier", "TQG", 
    "Financial Analysis", "Droit des sociétés", "Droit fiscal", "Comptabilité", "Anglais"
]
DEFAULT_S2 = [
    "Diagnostic Financier", "Compta Approfondie 2", "Modélisation des Coûts", 
    "Int. Financial Accounting", "Diagnostic Général", "Droit des Sociétés 2", 
    "Droit du Crédit", "Droit Pénal Affaires", "Organisation et SI", "Info. Décisionnelle"
]

SUBJECTS_CONFIG = {s: {"cat": "Cours", "color": NAVY, "icon": "book"} for s in DEFAULT_S1 + DEFAULT_S2}
SUBJECTS = list(SUBJECTS_CONFIG.keys())

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
    media = MediaIoBaseUpload(io.BytesIO(uploaded_file.getvalue()), mimetype=uploaded_file.type, resumable=True)
    drive_service.files().create(body={'name': uploaded_file.name, 'parents': [folder_id]}, media_body=media).execute()

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
            for r in sh.worksheet("Events").get_all_records():
                events.append({
                    "title": f"📚 {r['Title']}", "start": r['Start'], "end": r['End'],
                    "backgroundColor": ORANGE_REV, "borderColor": GOLD
                })
        except: pass
    return events

# --- FONCTION KPI CARD (CELLE QUI MANQUAIT !) ---
def kpi_card(title, value, subtitle, color, icon):
    st.markdown(f"""
    <div class="kpi-card" style="border-left: 5px solid {color};">
        <div style="display: flex; justify-content: space-between; align-items: start;">
            <div>
                <p style="font-size: 10px; font-weight: bold; color: #94a3b8; text-transform: uppercase;">{title}</p>
                <h2 style="font-size: 2rem; font-weight: bold; color: {NAVY}; margin: 0;">{value}</h2>
            </div>
            <div style="width: 40px; height: 40px; background-color: {color}20; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: {color}; font-size: 1.2rem;">
                {icon}
            </div>
        </div>
        <p style="font-size: 12px; color: {TEAL}; font-weight: bold; margin-top: 10px;">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

# --- CALCULATEUR MOYENNE ---
def load_simulator_data(sh):
    """Charge ou initialise les données du simulateur dans Google Sheets"""
    try:
        ws = sh.worksheet("Simulateur")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Si vide, on initialise
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
        # On s'assure de ne sauvegarder que les colonnes nécessaires (pas la moyenne calculée)
        cols_to_save = ["Matiere", "Semestre", "Coef_CC", "Coef_Partiel", "Note_CC", "Note_Partiel"]
        df_save = df[cols_to_save]
        ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())
    except Exception as e: st.error(f"Erreur sauvegarde: {e}")

# --- NAVIGATION ---
def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2 style='color:white; text-align:center;'>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        st.write("")
        
        selected = option_menu(
            menu_title=None,
            options=["Dashboard", "Mes Cours", "Focus Room"],
            icons=["speedometer2", "grid-3x3-gap", "hourglass-split"],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": NAVY},
                "icon": {"color": "#94a3b8", "font-size": "14px"}, 
                "nav-link": {"font-size": "14px", "text-align": "left", "margin":"0px", "color": "#e2e8f0"},
                "nav-link-selected": {"background-color": TEAL, "color": "white", "font-weight": "bold"},
            }
        )
    return selected

# --- PAGES ---
def dashboard_page(sh):
    # HEADER
    st.markdown(f"### 👋 Dashboard Étudiant")
    st.markdown(f"<p style='color:#64748b;'>{datetime.now().strftime('%d %B %Y')}</p>", unsafe_allow_html=True)

    # CHARGEMENT DONNÉES SIMULATEUR
    df_sim = pd.DataFrame()
    s1_avg_display = "0.0/20"
    
    if sh:
        df_sim = load_simulator_data(sh)
        if not df_sim.empty:
            df_s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
            # Calcul sécurisé de la moyenne
            df_s1['Moyenne_Matiere'] = ((df_s1['Note_CC'] * df_s1['Coef_CC']) + (df_s1['Note_Partiel'] * df_s1['Coef_Partiel'])) / (df_s1['Coef_CC'] + df_s1['Coef_Partiel'])
            valid_coefs = (df_s1['Coef_CC'] + df_s1['Coef_Partiel']) > 0
            if valid_coefs.any():
                global_avg = df_s1.loc[valid_coefs, 'Moyenne_Matiere'].mean()
                s1_avg_display = f"{global_avg:.2f}/20"

    # KPI ROW
    c1, c2, c3 = st.columns(3)
    
    # KPI 1 : MOYENNE (CLIQUABLE VIA UN VRAI BOUTON DESSOUS POUR ÉVITER LES BUGS)
    with c1:
        kpi_card("Moyenne S1 (Estimée)", s1_avg_display, "Basé sur le simulateur", NAVY, "🎓")
        # Bouton clair pour ouvrir le simulateur
        if st.button("🧮 Ouvrir le Simulateur de Notes", use_container_width=True):
            st.session_state.show_simulator = not st.session_state.show_simulator
            st.rerun()

    with c2: kpi_card("Tâches", "Voir", "To-Do List", TEAL, "⚡")
    with c3: kpi_card("Semaine", f"S{datetime.now().isocalendar()[1]}", "Calendrier", GOLD, "📅")

    # --- SECTION SIMULATEUR ---
    if st.session_state.show_simulator and not df_sim.empty:
        st.write("")
        st.markdown(f"### 🧮 Simulateur de Notes")
        st.info("Modifie les notes et les coefficients directement dans le tableau. La moyenne se met à jour automatiquement.")
        
        tab_s1, tab_s2 = st.tabs(["📘 Semestre 1", "📙 Semestre 2"])
        
        # Configuration des colonnes pour ressembler à ton Excel
        cols_config = {
            "Matiere": st.column_config.TextColumn("Matière", disabled=True, width="medium"),
            "Semestre": None,
            "Coef_CC": st.column_config.NumberColumn("Coef CC", min_value=0, max_value=10, step=0.5, format="%.1f", width="small"),
            "Coef_Partiel": st.column_config.NumberColumn("Coef Partiel", min_value=0, max_value=10, step=0.5, format="%.1f", width="small"),
            "Note_CC": st.column_config.NumberColumn("Note CC", min_value=0, max_value=20, step=0.5, format="%.1f", width="small"),
            "Note_Partiel": st.column_config.NumberColumn("Note Partiel", min_value=0, max_value=20, step=0.5, format="%.1f", width="small")
        }

        def display_sim_tab(df_semestre, key_suffix):
            edited_df = st.data_editor(df_semestre, column_config=cols_config, hide_index=True, use_container_width=True, key=f"editor_{key_suffix}")
            
            # Calcul en temps réel pour affichage
            if not edited_df.empty:
                edited_df['Moyenne'] = ((edited_df['Note_CC'] * edited_df['Coef_CC']) + (edited_df['Note_Partiel'] * edited_df['Coef_Partiel'])) / (edited_df['Coef_CC'] + edited_df['Coef_Partiel'])
                edited_df['Moyenne'] = edited_df['Moyenne'].fillna(0)
                
                # Affichage des résultats
                st.write("**Résultats calculés :**")
                st.dataframe(
                    edited_df[['Matiere', 'Moyenne']].style.format({"Moyenne": "{:.2f}"}).background_gradient(subset=['Moyenne'], cmap="RdYlGn", vmin=0, vmax=20),
                    use_container_width=True
                )
                
                # Moyenne Générale
                avg_sem = edited_df['Moyenne'].mean()
                st.metric(f"Moyenne Générale {key_suffix}", f"{avg_sem:.2f}/20")
                return edited_df

        with tab_s1:
            edited_s1 = display_sim_tab(df_sim[df_sim['Semestre'] == 'S1'], "S1")
        
        with tab_s2:
            edited_s2 = display_sim_tab(df_sim[df_sim['Semestre'] == 'S2'], "S2")

        if st.button("💾 Sauvegarder dans Google Sheets", type="primary"):
            # Reconstitution du DataFrame complet pour sauvegarde
            clean_s1 = edited_s1.drop(columns=['Moyenne'], errors='ignore')
            clean_s2 = edited_s2.drop(columns=['Moyenne'], errors='ignore')
            full_df = pd.concat([clean_s1, clean_s2])
            save_simulator_data(sh, full_df)
            st.success("✅ Sauvegardé !")
            time.sleep(1)
            st.rerun()
        
        st.markdown("---")

    # CALENDRIER & TACHES
    st.write("")
    c_left, c_right = st.columns([2, 1])
    with c_left:
        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        events = get_combined_events(ICS_CALENDAR_URL, sh)
        calendar(events=events, options={"headerToolbar": {"left": "today prev,next", "center": "title", "right": "timeGridWeek,dayGridMonth"}, "initialView": "timeGridWeek", "height": "550px", "locale": "fr"}, custom_css=".fc-event { border-radius: 4px; font-size: 11px; }")
    
    with c_right:
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do Urgent</span>", unsafe_allow_html=True)
        if sh:
            try:
                tasks = pd.DataFrame(sh.worksheet("Tasks").get_all_records())
                if not tasks.empty:
                    for i, row in tasks[tasks['Status'] == 'À faire'].head(4).iterrows():
                        with st.container(border=True):
                            c_chk, c_tx = st.columns([1, 4])
                            if c_chk.button("✔", key=f"d_{row['ID']}"):
                                cell = sh.worksheet("Tasks").find(row['ID'])
                                sh.worksheet("Tasks").update_cell(cell.row, 4, "Fait"); st.rerun()
                            c_tx.markdown(f"**{row['Task']}**<br><span style='color:grey; font-size:12px'>{row['Subject']}</span>", unsafe_allow_html=True)
            except: st.info("Aucune tâche.")

# --- PAGE 2 & 3 & 4 (COURS & FOCUS) ---
def courses_grid_page():
    st.markdown("### 📚 Mes Modules"); st.write("")
    cols = st.columns(3)
    for index, subject in enumerate(SUBJECTS):
        with cols[index % 3]:
            st.markdown(f"""<div style="background-color:white; padding:20px; border-radius:10px; border-left:5px solid {NAVY}; margin-bottom:10px; box-shadow:0 2px 5px rgba(0,0,0,0.05)"><h3>{subject}</h3></div>""", unsafe_allow_html=True)
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True):
                st.session_state.selected_subject = subject; st.rerun()

def subject_detail_page(sh, drive, subject):
    if st.button("← Retour"): st.session_state.selected_subject = None; st.rerun()
    st.title(subject)
    tab1, tab2 = st.tabs(["📂 Fichiers", "✅ Tâches"])
    with tab1:
        if drive:
            fid = get_or_create_subject_folder(drive, subject)
            up = st.file_uploader("Ajouter fichier", key="up")
            if up and st.button("Envoyer"): upload_file_to_drive(drive, up, fid); st.success("OK"); st.rerun()
            for f in list_drive_files(drive, fid):
                st.markdown(f"<div style='padding:10px; border:1px solid #ddd; margin:5px; border-radius:5px'><a href='{f['webViewLink']}' target='_blank' style='text-decoration:none; color:{NAVY}'>📄 {f['name']}</a></div>", unsafe_allow_html=True)
    with tab2:
        if sh:
            t, d = st.columns([3, 1]); nt = t.text_input("Tâche"); nd = d.date_input("Date")
            if st.button("Ajouter"): sh.worksheet("Tasks").append_row([str(uuid.uuid4())[:8], subject, nt, "À faire", str(nd)]); st.rerun()

def focus_room_page():
    st.title("⏳ Focus Room")
    if st.button("▶ LANCER 25 MIN", type="primary"):
        with st.empty():
            for i in range(25*60, -1, -1):
                st.markdown(f"<h1 style='text-align:center; font-size:80px;'>{i//60:02}:{i%60:02}</h1>", unsafe_allow_html=True); time.sleep(1)
        st.balloons()

# --- MAIN ---
if __name__ == "__main__":
    sh, drive = get_google_services()
    page = sidebar_menu()
    if page != st.session_state.current_view: st.session_state.current_view = page; st.session_state.selected_subject = None; st.rerun()
    
    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours":
        if st.session_state.selected_subject: subject_detail_page(sh, drive, st.session_state.selected_subject)
        else: courses_grid_page()
    elif st.session_state.current_view == "Focus Room": focus_room_page()
