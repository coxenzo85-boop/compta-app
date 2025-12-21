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

# --- GESTION DE L'ÉTAT ---
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
    html, body, [class*="css"] {{ font-family: 'Lato', sans-serif; background-color: {CLOUD}; color: {NAVY}; }}
    h1, h2, h3 {{ font-family: 'Libre Baskerville', serif; color: {NAVY}; }}
    
    [data-testid="stSidebar"] {{ background-color: {NAVY}; }}
    [data-testid="stSidebar"] h1 {{ color: white !important; }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{ color: #cbd5e1 !important; }}

    /* KPI Cards interactives */
    .kpi-card {{
        background-color: white; padding: 20px; border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-left: 5px solid {NAVY};
        transition: all 0.3s ease; cursor: pointer; position: relative;
    }}
    .kpi-card:hover {{ transform: translateY(-5px); border-left-color: {TEAL}; box-shadow: 0 10px 15px rgba(0,0,0,0.1); }}

    /* Bouton invisible sur KPI pour cliquer */
    .kpi-btn {{
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        z-index: 10; opacity: 0; cursor: pointer;
    }}

    /* Tableaux Éditeurs */
    [data-testid="stDataFrameResizable"] {{ border-radius: 10px; overflow: hidden; border: 1px solid #e2e8f0; }}
    
    .stButton>button {{ background-color: {TEAL}; color: white; border-radius: 8px; border: none; font-weight: bold; }}
    .course-card-bg {{
        background-color: white; border-radius: 15px; padding: 20px; height: 180px; 
        border: 1px solid #e2e8f0; border-left: 6px solid {NAVY};
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); position: relative; z-index: 0; transition: transform 0.3s ease;
    }}
    .element-container:hover .course-card-bg {{ transform: translateY(-5px); border-left-color: {TEAL} !important; }}
    
    div.stButton > button.click-cover {{
        position: absolute; top: -190px; left: 0; width: 100%; height: 200px; opacity: 0; z-index: 2; cursor: pointer;
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

# --- CONNEXIONS ---
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
    root_id = st.secrets["general"]["drive_root_folder_id"]
    query = f"mimeType='application/vnd.google-apps.folder' and name='{subject_name}' and '{root_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id)").execute()
    items = results.get('files', [])
    if items: return items[0]['id']
    file_metadata = {'name': subject_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [root_id]}
    return drive_service.files().create(body=file_metadata, fields='id').execute().get('id')

def list_drive_files(drive_service, folder_id):
    results = drive_service.files().list(q=f"'{folder_id}' in parents and trashed=false", fields="files(id, name, webViewLink, iconLink)").execute()
    return results.get('files', [])

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

# --- CALCULATEUR MOYENNE ---
def load_simulator_data(sh):
    """Charge ou initialise les données du simulateur dans Google Sheets"""
    try:
        ws = sh.worksheet("Simulateur")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # Si vide, on initialise avec les matières par défaut
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
        ws.update([df.columns.values.tolist()] + df.values.tolist())
    except Exception as e: st.error(f"Erreur sauvegarde: {e}")

# --- NAVIGATION ---
def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2 style='margin-bottom:20px;'>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        page = st.radio("Menu", ["Dashboard", "Mes Cours", "Focus Room"], label_visibility="collapsed")
        st.markdown("---")
        if st.button("▶ 25m Focus", use_container_width=True): st.session_state.pomodoro = time.time()
        if st.session_state.get("pomodoro"):
            left = 25*60 - (time.time() - st.session_state.pomodoro)
            if left > 0: st.markdown(f"<h1 style='text-align:center; color:white;'>{int(left//60):02}:{int(left%60):02}</h1>", unsafe_allow_html=True)
    return page

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
            # Calcul Moyenne Globale S1 pour le KPI
            df_s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
            df_s1['Moyenne_Matiere'] = ((df_s1['Note_CC'] * df_s1['Coef_CC']) + (df_s1['Note_Partiel'] * df_s1['Coef_Partiel'])) / (df_s1['Coef_CC'] + df_s1['Coef_Partiel'])
            # On ignore les matières où les coefs sont 0
            valid_coefs = (df_s1['Coef_CC'] + df_s1['Coef_Partiel']) > 0
            if valid_coefs.any():
                global_avg = df_s1.loc[valid_coefs, 'Moyenne_Matiere'].mean() # Moyenne simple des moyennes
                s1_avg_display = f"{global_avg:.2f}/20"

    # KPI ROW
    c1, c2, c3 = st.columns(3)
    
    # KPI 1 : MOYENNE (CLIQUABLE)
    with c1:
        st.markdown(f"""
        <div class="kpi-card">
            <p style="font-size: 10px; font-weight: bold; color: #94a3b8; text-transform: uppercase;">Moyenne S1 (Estimée)</p>
            <h2 style="font-size: 2rem; font-weight: bold; color: {NAVY}; margin: 0;">{s1_avg_display}</h2>
            <p style="font-size: 12px; color: {TEAL}; font-weight: bold; margin-top: 10px;">🖱️ Clique pour éditer</p>
        </div>
        """, unsafe_allow_html=True)
        # Bouton invisible qui active le simulateur
        if st.button("OpenSim", key="kpi_avg_btn", type="secondary"):
            st.session_state.show_simulator = not st.session_state.show_simulator
            st.rerun()
        st.markdown("""<style>div[data-testid="column"]:nth-child(1) div.stButton > button { position: absolute; top: -110px; height: 120px; width: 100%; opacity: 0; z-index: 5; }</style>""", unsafe_allow_html=True)

    # KPI 2 & 3
    with c2: kpi_card("Tâches", "Voir", "To-Do List", TEAL, "⚡")
    with c3: kpi_card("Semaine", f"S{datetime.now().isocalendar()[1]}", "Calendrier", GOLD, "📅")

    # --- SECTION SIMULATEUR (S'AFFICHE SI CLIQUÉ) ---
    if st.session_state.show_simulator and not df_sim.empty:
        st.write("")
        st.markdown(f"### 🧮 Simulateur de Notes")
        st.info("Modifie les notes et coefficients directement dans le tableau. Appuie sur 'Sauvegarder' pour mettre à jour.")
        
        tab_s1, tab_s2 = st.tabs(["📘 Semestre 1", "📙 Semestre 2"])
        
        # LOGIQUE D'ÉDITION
        cols_config = {
            "Matiere": st.column_config.TextColumn("Matière", disabled=True),
            "Semestre": None, # On cache cette colonne
            "Coef_CC": st.column_config.NumberColumn("Coef CC", min_value=0, max_value=10, step=0.5, format="%.1f"),
            "Coef_Partiel": st.column_config.NumberColumn("Coef Partiel", min_value=0, max_value=10, step=0.5, format="%.1f"),
            "Note_CC": st.column_config.NumberColumn("Note CC", min_value=0, max_value=20, step=0.5, format="%.1f"),
            "Note_Partiel": st.column_config.NumberColumn("Note Partiel", min_value=0, max_value=20, step=0.5, format="%.1f")
        }

        with tab_s1:
            df_s1 = df_sim[df_sim['Semestre'] == 'S1']
            edited_s1 = st.data_editor(df_s1, column_config=cols_config, hide_index=True, use_container_width=True, key="editor_s1")
            
            # Calcul en temps réel pour l'affichage (Visualisation seulement)
            if not edited_s1.empty:
                edited_s1['Moyenne'] = ((edited_s1['Note_CC'] * edited_s1['Coef_CC']) + (edited_s1['Note_Partiel'] * edited_s1['Coef_Partiel'])) / (edited_s1['Coef_CC'] + edited_s1['Coef_Partiel'])
                edited_s1['Moyenne'] = edited_s1['Moyenne'].fillna(0)
                
                # Joli tableau de résultats
                st.caption("Aperçu des résultats :")
                st.dataframe(edited_s1[['Matiere', 'Moyenne']].style.format({"Moyenne": "{:.2f}"}).background_gradient(subset=['Moyenne'], cmap="RdYlGn", vmin=0, vmax=20), use_container_width=True)
                
                final_avg_s1 = edited_s1['Moyenne'].mean()
                st.metric("Moyenne Générale S1 (Simulée)", f"{final_avg_s1:.2f}/20")

        with tab_s2:
            df_s2 = df_sim[df_sim['Semestre'] == 'S2']
            edited_s2 = st.data_editor(df_s2, column_config=cols_config, hide_index=True, use_container_width=True, key="editor_s2")
            
            if not edited_s2.empty:
                edited_s2['Moyenne'] = ((edited_s2['Note_CC'] * edited_s2['Coef_CC']) + (edited_s2['Note_Partiel'] * edited_s2['Coef_Partiel'])) / (edited_s2['Coef_CC'] + edited_s2['Coef_Partiel'])
                edited_s2['Moyenne'] = edited_s2['Moyenne'].fillna(0)
                st.caption("Aperçu des résultats :")
                st.dataframe(edited_s2[['Matiere', 'Moyenne']].style.format({"Moyenne": "{:.2f}"}).background_gradient(subset=['Moyenne'], cmap="RdYlGn", vmin=0, vmax=20), use_container_width=True)
                final_avg_s2 = edited_s2['Moyenne'].mean()
                st.metric("Moyenne Générale S2 (Simulée)", f"{final_avg_s2:.2f}/20")

        # BOUTON SAUVEGARDE GLOBALE
        if st.button("💾 Sauvegarder les modifications dans le Cloud", type="primary"):
            # On fusionne S1 et S2 édités pour la sauvegarde
            # Attention: edited_s1 a une colonne 'Moyenne' en plus qu'on ne veut pas sauvegarder
            clean_s1 = edited_s1.drop(columns=['Moyenne'], errors='ignore')
            clean_s2 = edited_s2.drop(columns=['Moyenne'], errors='ignore')
            full_df = pd.concat([clean_s1, clean_s2])
            save_simulator_data(sh, full_df)
            st.success("Notes mises à jour !")
            time.sleep(1)
            st.rerun()
        
        st.markdown("---")

    # REST OF DASHBOARD
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
            st.markdown(f"""<div class="course-card-bg"><h3 style="margin-top:40px; color:{NAVY}">{subject}</h3></div>""", unsafe_allow_html=True)
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True, type="secondary"):
                st.session_state.selected_subject = subject; st.rerun()
            st.markdown(f"""<style>div[data-testid="column"]:nth-child({(index % 3) + 1}) div.stButton > button {{ position: absolute; top: -190px; height: 200px; width: 100%; opacity: 0; z-index: 2; }}</style>""", unsafe_allow_html=True)

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
