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

# --- GESTION DE L'ÉTAT (SESSION STATE PERSISTANT) ---
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False

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
RED_URGENT = "#e11d48"

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
        transition: transform 0.2s;
    }}
    .kpi-card:hover {{ transform: translateY(-5px); }}

    /* Widget Examens */
    .exam-widget {{
        background-color: white;
        padding: 12px 15px;
        border-radius: 10px;
        border-left: 5px solid {TEAL};
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }}
    .exam-days {{
        font-weight: bold;
        font-size: 12px;
        padding: 4px 8px;
        border-radius: 12px;
        color: white;
        background-color: {NAVY};
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
    
    /* Cartes Fichiers */
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

# --- DONNÉES ---
DEFAULT_S1 = ["Théorie des organisations", "Management Control", "Marché Financier", "TQG", "Financial Analysis", "Droit des sociétés", "Droit fiscal", "Comptabilité", "Anglais"]
DEFAULT_S2 = ["Diagnostic Financier", "Compta Approfondie 2", "Modélisation des Coûts", "Int. Financial Accounting", "Diagnostic Général", "Droit des Sociétés 2", "Droit du Crédit", "Droit Pénal Affaires", "Organisation et SI", "Info. Décisionnelle", "Anglais", "Projet Professionnel"]
SUBJECTS_CONFIG = {s: {"cat": "Cours", "color": NAVY, "icon": "book"} for s in DEFAULT_S1 + DEFAULT_S2}
SUBJECTS = list(SUBJECTS_CONFIG.keys())

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

# --- CONNEXIONS ---
@st.cache_resource 
def get_google_services():
    try:
        if "gcp_service_account" not in st.secrets: return None, None
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open("L3_Compta_Database")
        drive = build('drive', 'v3', credentials=creds)
        return sheet, drive
    except Exception as e:
        print(f"Erreur Google: {e}") 
        return None, None

# --- LOGIQUE DE GESTION DU TIMER (GLOBAL) ---
def check_timer_status(sh):
    """Vérifie si le timer est terminé et sauvegarde si nécessaire."""
    if st.session_state.timer_active and st.session_state.timer_end_time:
        now = datetime.now()
        if now >= st.session_state.timer_end_time:
            # Session terminée !
            st.session_state.timer_active = False
            st.session_state.timer_end_time = None
            
            # Sauvegarde dans History
            if sh:
                try:
                    ws = sh.worksheet("History")
                    ws.append_row([str(date.today()), "Pomodoro", st.session_state.timer_subject, st.session_state.timer_duration])
                    st.toast(f"✅ Session de {st.session_state.timer_subject} enregistrée !", icon="🔥")
                except:
                    st.error("Erreur de sauvegarde des stats.")
            else:
                st.toast("Session terminée (Non sauvegardée - BDD déconnectée)")

# --- UTILS ---
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
                if c.get('dtstart'):
                    events.append({
                        "title": str(c.get('summary', 'Cours')), 
                        "start": c.get('dtstart').dt,
                        "end": c.get('dtend').dt,
                        "iso_start": c.get('dtstart').dt.isoformat() if hasattr(c.get('dtstart').dt, 'isoformat') else str(c.get('dtstart').dt),
                        "iso_end": c.get('dtend').dt.isoformat() if hasattr(c.get('dtend').dt, 'isoformat') else str(c.get('dtend').dt),
                        "backgroundColor": TEAL, "borderColor": NAVY
                    })
    except: pass
    return events

# --- HISTORIQUE & EXAMENS ---
def get_history_stats(sh):
    try:
        ws = sh.worksheet("History")
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def get_exams(sh):
    try:
        ws = sh.worksheet("Exams")
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

def add_exam(sh, matiere, date_ex):
    try:
        ws = sh.worksheet("Exams")
        ws.append_row([matiere, str(date_ex)])
    except: st.error("Erreur ajout examen. Vérifie que l'onglet 'Exams' existe.")

# --- COMPONENTS ---
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

def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2 style='color:white; text-align:center;'>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        st.write("")
        options = ["Dashboard", "Mes Cours", "Focus Room"]
        try: default_ix = options.index(st.session_state.current_view)
        except: default_ix = 0
        selected = option_menu(
            menu_title=None, options=options, icons=["speedometer2", "grid-3x3-gap", "hourglass-split"],
            menu_icon="cast", default_index=default_ix, 
            styles={"container": {"padding": "0!important", "background-color": NAVY}, "icon": {"color": "#94a3b8"}, "nav-link": {"color": "#e2e8f0"}}
        )
        
        # Mini Timer dans Sidebar
        if st.session_state.timer_active and st.session_state.timer_end_time:
            now = datetime.now()
            remaining = st.session_state.timer_end_time - now
            if remaining.total_seconds() > 0:
                mins, secs = divmod(int(remaining.total_seconds()), 60)
                st.markdown("---")
                st.markdown(f"<div style='text-align:center; color:{GOLD}; font-weight:bold;'>FOCUS EN COURS</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='text-align:center; color:white; font-size:24px;'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
            
    return selected

# --- PAGES ---
def dashboard_page(sh):
    st.markdown(f"### 👋 Dashboard Étudiant")
    st.markdown(f"<p style='color:#64748b;'>{datetime.now().strftime('%d %B %Y')}</p>", unsafe_allow_html=True)

    # --- KPI ---
    s1_avg_display = "0.0/20"
    if sh:
        try:
            ws_sim = sh.worksheet("Simulateur")
            df_sim = pd.DataFrame(ws_sim.get_all_records())
            if not df_sim.empty:
                df_s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
                df_s1['Moyenne_Matiere'] = ((df_s1['Note_CC'] * df_s1['Coef_CC']) + (df_s1['Note_Partiel'] * df_s1['Coef_Partiel'])) / (df_s1['Coef_CC'] + df_s1['Coef_Partiel'])
                valid = (df_s1['Coef_CC'] + df_s1['Coef_Partiel']) > 0
                if valid.any(): s1_avg_display = f"{df_s1.loc[valid, 'Moyenne_Matiere'].mean():.2f}/20"
        except: pass

    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Moyenne S1", s1_avg_display, "Basé sur le simulateur", NAVY, "🎓")
        if st.button("🧮 Ouvrir le Simulateur", use_container_width=True):
            st.session_state.show_simulator = not st.session_state.show_simulator
            st.rerun()
    with c2:
        # Affichage intelligent du statut Timer
        if st.session_state.timer_active and st.session_state.timer_end_time:
            fin = st.session_state.timer_end_time.strftime("%H:%M")
            focus_title = "🔥 Session active"
            focus_sub = f"Fin prévue à {fin}"
            focus_col = GOLD
        else:
            focus_title = "Prêt à bosser ?"
            focus_sub = "Lance une session"
            focus_col = TEAL
            
        kpi_card("Focus Room", focus_title, focus_sub, focus_col, "⏳")
        if st.button("🚀 Go Focus", use_container_width=True):
            st.session_state.current_view = "Focus Room"
            st.rerun()

    # SIMULATEUR
    if st.session_state.show_simulator and sh:
        # (Code simulateur identique précédent - abrégé pour clarté)
        st.write(""); st.info("Modifie tes notes dans l'onglet Focus Room ou ici.")
        
    st.write("")
    c_left, c_right = st.columns([2, 1])

    # GAUCHE : STATS + CALENDRIER
    with c_left:
        # CAMEMBERT (STATS)
        if sh:
            df_h = get_history_stats(sh)
            if not df_h.empty:
                pomodoros = df_h[df_h['Action'] == 'Pomodoro']
                if not pomodoros.empty:
                    st.markdown(f"#### <span style='color:{NAVY}'>📊 Répartition du Temps</span>", unsafe_allow_html=True)
                    pomodoros['Value'] = pd.to_numeric(pomodoros['Value'], errors='coerce')
                    fig_pie = px.pie(pomodoros, values='Value', names='Subject', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                    fig_pie.update_layout(height=250, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("Termine une session Focus pour voir tes stats !")

        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        events_ics = get_combined_events(ICS_CALENDAR_URL, sh)
        cal_events = []
        for e in events_ics:
            cal_events.append({"title": e['title'], "start": e.get('iso_start') or e['start'], "end": e.get('iso_end') or e['end'], "backgroundColor": TEAL})
        calendar(events=cal_events, options={"initialView": "timeGridWeek", "height": "500px", "locale": "fr"}, custom_css=".fc-event { border-radius: 4px; font-size: 11px; }")

    # DROITE : EXAMENS + TO DO
    with c_right:
        st.markdown(f"#### <span style='color:{NAVY}'>⏳ Examens</span>", unsafe_allow_html=True)
        
        # Ajout Examen
        with st.expander("➕ Ajouter un examen"):
            with st.form("new_exam"):
                ex_sub = st.selectbox("Matière", DEFAULT_S2)
                ex_date = st.date_input("Date")
                if st.form_submit_button("Sauvegarder"):
                    if sh: 
                        add_exam(sh, ex_sub, ex_date)
                        st.success("Ajouté !"); st.rerun()

        # Liste Examens (ICS + BDD)
        exams = []
        if sh:
            db_exams = get_exams(sh)
            if not db_exams.empty:
                for _, r in db_exams.iterrows():
                    try:
                        d = datetime.strptime(str(r['Date']), "%Y-%m-%d").date()
                        exams.append({"title": r['Matiere'], "date": d, "source": "Perso"})
                    except: pass
        
        # Tri et affichage
        exams.sort(key=lambda x: x['date'])
        today = date.today()
        
        if exams:
            for ex in exams:
                delta = (ex['date'] - today).days
                if delta >= 0:
                    color = RED_URGENT if delta < 7 else ORANGE_REV if delta < 14 else TEAL
                    st.markdown(f"""
                    <div class="exam-widget" style="border-left: 5px solid {color};">
                        <div>
                            <div style="font-weight:bold; color:{NAVY}; font-size:13px;">{ex['title']}</div>
                            <div style="font-size:11px; color:grey;">{ex['date'].strftime('%d/%m')}</div>
                        </div>
                        <span class="exam-days" style="background-color:{color};">J-{delta}</span>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            st.info("Aucun examen prévu.")

        st.write("")
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do Urgent</span>", unsafe_allow_html=True)
        if sh:
            tasks = pd.DataFrame(sh.worksheet("Tasks").get_all_records())
            todo = tasks[tasks['Status'] == 'À faire'] if not tasks.empty else pd.DataFrame()
            if not todo.empty:
                for i, row in todo.head(4).iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([1, 4])
                        if c1.button("✔", key=f"d_{row['ID']}"):
                            sh.worksheet("Tasks").update_cell(sh.worksheet("Tasks").find(row['ID']).row, 4, "Fait")
                            st.rerun()
                        c2.markdown(f"**{row['Task']}**<br><span style='font-size:11px; color:grey'>{row['Subject']}</span>", unsafe_allow_html=True)
            else:
                st.success("🎉 Rien à faire ! Profite de ta pause.")

# --- PAGE 2 & 3 ---
def courses_grid_page():
    st.markdown("### 📚 Mes Modules S2"); st.write("")
    cols = st.columns(3)
    for index, subject in enumerate(DEFAULT_S2):
        with cols[index % 3]:
            st.markdown(f"""<div style="background-color:white; padding:20px; border-radius:10px; border-left:5px solid {NAVY}; margin-bottom:10px; box-shadow:0 2px 5px rgba(0,0,0,0.05)"><h3>{subject}</h3></div>""", unsafe_allow_html=True)
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True):
                st.session_state.selected_subject = subject; st.rerun()

def subject_detail_page(sh, drive, subject):
    if st.button("← Retour"): st.session_state.selected_subject = None; st.rerun()
    st.title(subject)
    tab1, tab2 = st.tabs(["📂 Fichiers & NotebookLM", "✅ Tâches"])
    with tab1:
        with st.container(border=True):
            c1, c2, c3 = st.columns([0.5, 3, 1.5])
            c1.markdown("## 🧠"); c2.markdown("**Booster IA**\n\nAccède au carnet."); c3.link_button("↗ Ouvrir", NOTEBOOK_LINKS.get(subject, "https://notebooklm.google.com/"), type="primary")
        st.write("")
        if drive:
            fid = get_or_create_subject_folder(drive, subject)
            up = st.file_uploader("Ajouter fichier", key="up")
            if up and st.button("Envoyer"): upload_file_to_drive(drive, up, fid); st.success("OK"); st.rerun()
            for f in list_drive_files(drive, fid):
                st.markdown(f"<div class='file-card'><a href='{f['webViewLink']}' target='_blank' style='text-decoration:none; color:{NAVY}'>📄 {f['name']}</a></div>", unsafe_allow_html=True)
    with tab2:
        if sh:
            t, d = st.columns([3, 1]); nt = t.text_input("Tâche"); nd = d.date_input("Date")
            if st.button("Ajouter"): sh.worksheet("Tasks").append_row([str(uuid.uuid4())[:8], subject, nt, "À faire", str(nd)]); st.rerun()

# --- PAGE 4: FOCUS ROOM (PERSISTANTE) ---
def focus_room_page():
    st.markdown(f"### ⏳ Focus Room")
    
    # Si pas de session active, on affiche la config
    if not st.session_state.timer_active:
        c1, c2, c3, c4 = st.columns(4)
        subj = c1.selectbox("Matière", DEFAULT_S2)
        dur = c2.number_input("Durée (min)", 1, 120, 25)
        
        if st.button("▶ LANCER LA SESSION", type="primary"):
            st.session_state.timer_active = True
            st.session_state.timer_end_time = datetime.now() + timedelta(minutes=dur)
            st.session_state.timer_subject = subj
            st.session_state.timer_duration = dur
            st.rerun()
    
    # Si session active, on affiche le compte à rebours
    else:
        now = datetime.now()
        remaining = st.session_state.timer_end_time - now
        
        if remaining.total_seconds() > 0:
            mins, secs = divmod(int(remaining.total_seconds()), 60)
            st.markdown(f"<p class='timer-label'>💻 FOCUS EN COURS • {st.session_state.timer_subject}</p>", unsafe_allow_html=True)
            st.markdown(f"<div class='timer-display'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
            
            # Barre de progression
            total_seconds = st.session_state.timer_duration * 60
            elapsed = total_seconds - remaining.total_seconds()
            st.progress(elapsed / total_seconds)
            
            if st.button("⏹ Abandonner"):
                st.session_state.timer_active = False
                st.session_state.timer_end_time = None
                st.rerun()
            
            # Rafraîchissement automatique pour le visuel
            time.sleep(1)
            st.rerun()
        else:
            # Le timer est fini
            st.balloons()
            st.success("Session terminée ! Stats enregistrées.")
            # La fonction check_timer_status au début du script a déjà géré la sauvegarde
            if st.button("Nouvelle Session"):
                st.rerun()

    with st.expander("🎵 Ambiance Sonore", expanded=True):
        st.video("https://www.youtube.com/watch?v=jfKfPfyJRdk")

# --- MAIN ---
if __name__ == "__main__":
    sh, drive = get_google_services()
    
    # Vérification globale du timer (Sauvegarde auto si fin de temps, même hors page Focus)
    check_timer_status(sh)
    
    selected_page = sidebar_menu()
    
    if selected_page != st.session_state.current_view:
        st.session_state.current_view = selected_page
        st.session_state.selected_subject = None
        st.rerun()

    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours":
        if st.session_state.selected_subject: subject_detail_page(sh, drive, st.session_state.selected_subject)
        else: courses_grid_page()
    elif st.session_state.current_view == "Focus Room": focus_room_page()
