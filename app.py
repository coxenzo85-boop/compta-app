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
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False
if 'pomodoro' not in st.session_state: st.session_state.pomodoro = None

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
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
        border-left: 8px solid {NAVY};
        height: 100%;
        transition: transform 0.2s;
    }}
    .kpi-card:hover {{ transform: translateY(-5px); }}

    /* Exam Countdown Widget */
    .exam-widget {{
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        margin-bottom: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .exam-days {{
        font-weight: bold;
        font-size: 14px;
        padding: 5px 10px;
        border-radius: 20px;
        color: white;
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

# --- LIENS NOTEBOOK LM ---
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
                        "start": c.get('dtstart').dt, # On garde l'objet date pour le tri
                        "end": c.get('dtend').dt,
                        "iso_start": c.get('dtstart').dt.isoformat() if hasattr(c.get('dtstart').dt, 'isoformat') else str(c.get('dtstart').dt),
                        "iso_end": c.get('dtend').dt.isoformat() if hasattr(c.get('dtend').dt, 'isoformat') else str(c.get('dtend').dt),
                        "backgroundColor": TEAL, "borderColor": NAVY
                    })
    except: pass
    return events

# --- HISTORIQUE & STATS ---
def save_to_history(sh, action, subject, value):
    try:
        ws = sh.worksheet("History")
        ws.append_row([str(date.today()), action, subject, value])
    except: pass

def get_history_stats(sh):
    try:
        ws = sh.worksheet("History")
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except: return pd.DataFrame()

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

# --- NAVIGATION ---
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
    return selected

# --- PAGES ---
def dashboard_page(sh):
    st.markdown(f"### 👋 Dashboard Étudiant")
    st.markdown(f"<p style='color:#64748b;'>{datetime.now().strftime('%d %B %Y')}</p>", unsafe_allow_html=True)

    # 1. HEATMAP DE PRODUCTIVITÉ (Gamification)
    if sh:
        df_hist = get_history_stats(sh)
        if not df_hist.empty:
            df_hist['Date'] = pd.to_datetime(df_hist['Date'])
            daily_activity = df_hist.groupby('Date').size().reset_index(name='Activités')
            # Filtre 30 derniers jours
            last_30 = daily_activity[daily_activity['Date'] >= pd.to_datetime(date.today() - timedelta(days=30))]
            
            fig = px.bar(last_30, x='Date', y='Activités', title="🔥 Ta Productivité (30 derniers jours)", color_discrete_sequence=[TEAL])
            fig.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

    # Données Simulateur
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
        except: df_sim = pd.DataFrame()

    # KPI 2 COLONNES
    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Moyenne S1", s1_avg_display, "Basé sur le simulateur", NAVY, "🎓")
        if st.button("🧮 Ouvrir le Simulateur", use_container_width=True):
            st.session_state.show_simulator = not st.session_state.show_simulator
            st.rerun()
    with c2:
        focus_txt = "🔥 Session en cours..." if st.session_state.get("pomodoro") else "Prêt à bosser ?"
        kpi_card("Focus Room", focus_txt, "Productivité Maximale", GOLD, "⏳")
        if st.button("🚀 Go Focus", use_container_width=True):
            st.session_state.current_view = "Focus Room"
            st.rerun()

    # SECTION SIMULATEUR + REVERSE SIMULATOR (Calcul Objectif)
    if st.session_state.show_simulator and not df_sim.empty:
        st.write("")
        with st.expander("🎯 Calculateur d'Objectif (Reverse Simulator)", expanded=True):
            target = st.number_input("Je veux cette moyenne générale :", 10.0, 20.0, 12.0, step=0.5)
            # Logique simplifiée pour l'exemple (Calcul global)
            current_avg = float(s1_avg_display.split('/')[0])
            if current_avg >= target:
                st.success(f"Bravo ! Tu as déjà {current_avg}, objectif atteint !")
            else:
                st.warning(f"Il te manque encore un petit effort pour atteindre {target}/20 !")
        
        # ... (Tableaux Simulateur Code existant inchangé pour abréger, mais inclus dans la logique complète) ...
        # (J'inclus la version courte fonctionnelle du tableau ici)
        tab_s1, tab_s2 = st.tabs(["📘 S1", "📙 S2"])
        cols_cfg = {
            "Matiere": st.column_config.TextColumn("Matière", disabled=True),
            "Semestre": None,
            "Coef_CC": st.column_config.NumberColumn("Coef CC", min_value=0, max_value=10, step=0.5),
            "Coef_Partiel": st.column_config.NumberColumn("Coef Partiel", min_value=0, max_value=10, step=0.5),
            "Note_CC": st.column_config.NumberColumn("Note CC", min_value=0, max_value=20, step=0.5),
            "Note_Partiel": st.column_config.NumberColumn("Note Partiel", min_value=0, max_value=20, step=0.5)
        }
        with tab_s1:
            edited_s1 = st.data_editor(df_sim[df_sim['Semestre'] == 'S1'], column_config=cols_cfg, hide_index=True, use_container_width=True)
        with tab_s2:
            edited_s2 = st.data_editor(df_sim[df_sim['Semestre'] == 'S2'], column_config=cols_cfg, hide_index=True, use_container_width=True)
        
        if st.button("💾 Sauvegarder"):
            # Sauvegarde propre
            cl_s1 = edited_s1.drop(columns=['Moyenne', 'Moyenne_Matiere'], errors='ignore')
            cl_s2 = edited_s2.drop(columns=['Moyenne', 'Moyenne_Matiere'], errors='ignore')
            full = pd.concat([cl_s1, cl_s2])
            try:
                sh.worksheet("Simulateur").update([full.columns.values.tolist()] + full.values.tolist())
                st.success("Sauvegardé !")
                time.sleep(1); st.rerun()
            except: st.error("Erreur sauvegarde")

    st.write("")
    c_left, c_right = st.columns([2, 1])

    # GAUCHE : CALENDRIER + STATS TEMPS
    with c_left:
        # STATS REPARTITION TEMPS (Pie Chart)
        if sh:
            df_h = get_history_stats(sh)
            if not df_h.empty:
                pomodoros = df_h[df_h['Action'] == 'Pomodoro']
                if not pomodoros.empty:
                    st.markdown(f"#### <span style='color:{NAVY}'>📊 Répartition du Temps</span>", unsafe_allow_html=True)
                    # Nettoyage des valeurs pour être sûr que ce sont des nombres
                    pomodoros['Value'] = pd.to_numeric(pomodoros['Value'], errors='coerce')
                    fig_pie = px.pie(pomodoros, values='Value', names='Subject', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                    fig_pie.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        events_ics = get_ics_events_cached(ICS_CALENDAR_URL)
        # Adaptation format events pour calendar
        cal_events = []
        for e in events_ics:
            cal_events.append({
                "title": e['title'], 
                "start": e['iso_start'], 
                "end": e['iso_end'], 
                "backgroundColor": TEAL, "borderColor": NAVY
            })
        calendar(events=cal_events, options={"headerToolbar": {"left": "today prev,next", "center": "title", "right": "timeGridWeek,dayGridMonth"}, "initialView": "timeGridWeek", "height": "550px", "locale": "fr"}, custom_css=".fc-event { border-radius: 4px; font-size: 11px; }")

    # DROITE : COMPTE A REBOURS + TO DO
    with c_right:
        # WIDGET COMPTE A REBOURS EXAMENS
        st.markdown(f"#### <span style='color:{NAVY}'>⏳ Prochains Examens</span>", unsafe_allow_html=True)
        
        # Détection mot clé "Exam" ou "Partiel" dans ICS
        upcoming_exams = []
        now = datetime.now().astimezone() # Timezone aware pour comparaison
        for e in events_ics:
            # Conversion date ICS en datetime comparable
            try:
                start_dt = e['start']
                if not hasattr(start_dt, 'tzinfo') or start_dt.tzinfo is None:
                    # Si naif, on assume local
                    start_dt = start_dt.replace(tzinfo=now.tzinfo)
                
                if start_dt > now and ("exam" in e['title'].lower() or "partiel" in e['title'].lower() or "cc" in e['title'].lower()):
                    days_left = (start_dt - now).days
                    upcoming_exams.append({"title": e['title'], "days": days_left, "date": start_dt})
            except: pass
        
        # Tri et affichage
        upcoming_exams.sort(key=lambda x: x['days'])
        if upcoming_exams:
            for ex in upcoming_exams[:3]: # Top 3
                color = RED_URGENT if ex['days'] < 7 else ORANGE_REV if ex['days'] < 14 else TEAL
                st.markdown(f"""
                <div class="exam-widget" style="border-left: 5px solid {color};">
                    <span style="font-weight:bold; color:{NAVY}; font-size:14px;">{ex['title']}</span>
                    <span class="exam-days" style="background-color:{color};">J-{ex['days']}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Aucun examen détecté prochainement.")

        st.write("")
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do Urgent</span>", unsafe_allow_html=True)
        if sh:
            try:
                ws_t = sh.worksheet("Tasks")
                tasks = pd.DataFrame(ws_t.get_all_records())
                todo_tasks = tasks[tasks['Status'] == 'À faire'] if not tasks.empty else pd.DataFrame()
                
                if not todo_tasks.empty:
                    for i, row in todo_tasks.head(4).iterrows():
                        with st.container(border=True):
                            c_chk, c_tx = st.columns([1, 4])
                            if c_chk.button("✔", key=f"d_{row['ID']}"):
                                cell = ws_t.find(row['ID'])
                                ws_t.update_cell(cell.row, 4, "Fait"); 
                                # Ajout historique task
                                save_to_history(sh, "Task", row['Subject'], 1)
                                st.rerun()
                            c_tx.markdown(f"**{row['Task']}**<br><span style='color:grey; font-size:12px'>{row['Subject']}</span>", unsafe_allow_html=True)
                else:
                    st.success("🎉 Rien à faire ! Profite de ta pause.")
            except: st.info("Aucune tâche.")

# --- PAGE 2: GRILLE DES COURS ---
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
            c_l, c_t, c_b = st.columns([0.5, 3, 1.5])
            c_l.markdown("## 🧠")
            c_t.markdown("**Booster de révision IA**\n\nAccède au carnet dédié.")
            url = NOTEBOOK_LINKS.get(subject, "https://notebooklm.google.com/")
            c_b.link_button("↗ Ouvrir NotebookLM", url, type="primary", use_container_width=True)
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

# --- PAGE 4: FOCUS ROOM ---
def focus_room_page():
    st.markdown(f"### ⏳ Focus Room")
    
    # Intégration Audio Lofi Girl
    with st.expander("🎵 Ambiance Sonore", expanded=True):
        st.video("https://www.youtube.com/watch?v=jfKfPfyJRdk")

    c1, c2, c3, c4 = st.columns(4)
    # Sélection de la matière pour les stats
    subject_focus = c1.selectbox("Matière travaillée", DEFAULT_S2)
    work_min = c2.number_input("Travail (min)", 1, 60, 25)
    short_break = c3.number_input("Pause courte", 1, 15, 5)
    cycles = c4.number_input("Cycles", 1, 10, 4)

    start_btn = st.button("▶ LANCER LA SESSION", type="primary", use_container_width=True)
    placeholder = st.empty()

    if start_btn:
        # On sauvegarde le fait qu'on lance un pomodoro pour l'état global si on veut
        st.session_state.pomodoro = True
        total_cycles = cycles
        for i in range(total_cycles):
            for remaining in range(work_min * 60, -1, -1):
                mins, secs = divmod(remaining, 60)
                with placeholder.container():
                    st.markdown(f"<p class='timer-label'>💻 CYCLE {i+1}/{total_cycles} • {subject_focus}</p>", unsafe_allow_html=True)
                    st.markdown(f"<div class='timer-display'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
                    st.progress((work_min*60 - remaining) / (work_min*60))
                time.sleep(1)
            
            # Fin du cycle de travail : on enregistre les stats !
            sh, _ = get_google_services()
            if sh: save_to_history(sh, "Pomodoro", subject_focus, work_min)

            if i < total_cycles - 1:
                is_long = (i + 1) % 4 == 0
                break_time = 15 if is_long else short_break
                label = "☕ PAUSE LONGUE" if is_long else "🍵 PAUSE COURTE"
                for remaining in range(break_time * 60, -1, -1):
                    mins, secs = divmod(remaining, 60)
                    with placeholder.container():
                        st.markdown(f"<p class='timer-label'>{label}</p>", unsafe_allow_html=True)
                        st.markdown(f"<div class='timer-display' style='color:{TEAL}; border-color:{NAVY}'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
                    time.sleep(1)
        
        st.session_state.pomodoro = False
        st.balloons()
        st.success("Session terminée ! Bravo 🎉")

# --- MAIN ---
if __name__ == "__main__":
    sh, drive = get_google_services()
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
