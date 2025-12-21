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

# --- CONFIGURATION PAGE & DESIGN SYSTEM ---
st.set_page_config(page_title="L3 CCA Dashboard", page_icon="🎓", layout="wide")

# 🔗 LIEN EMPLOI DU TEMPS
ICS_CALENDAR_URL = "http://edt-v2.univ-nantes.fr/calendar/ics?timetables[0]=110228"

# PALETTE DE COULEURS
NAVY = "#1A2C42"
TEAL = "#008080"
GOLD = "#C5A059"
CLOUD = "#F4F6F7"
ORANGE_REV = "#ea580c"

# INJECTION CSS
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

    /* Cartes Fichiers Drive */
    .file-card {{
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        margin-bottom: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        transition: transform 0.2s;
    }}
    .file-card:hover {{
        border-color: {TEAL};
        transform: translateX(5px);
    }}
    .file-link {{
        text-decoration: none;
        color: {NAVY};
        font-weight: bold;
        font-size: 14px;
    }}
    .file-link:hover {{
        color: {TEAL};
    }}
    </style>
    """, unsafe_allow_html=True)

# --- DONNÉES & CONSTANTES ---
SUBJECTS_CONFIG = {
    "Diagnostic Financier": {"icon": "graph-up-arrow", "cat": "Finance", "color": NAVY},
    "Compta Approfondie 2": {"icon": "calculator", "cat": "Finance", "color": NAVY},
    "Modélisation des Coûts": {"icon": "grid-3x3", "cat": "Finance", "color": NAVY},
    "Int. Financial Accounting": {"icon": "globe", "cat": "Finance", "color": NAVY},
    "Diagnostic Général": {"icon": "activity", "cat": "Finance", "color": NAVY},
    "Droit des Sociétés 2": {"icon": "hammer", "cat": "Droit", "color": "#64748b"},
    "Droit du Crédit": {"icon": "bank", "cat": "Droit", "color": "#64748b"},
    "Droit Pénal Affaires": {"icon": "shield-lock", "cat": "Droit", "color": "#64748b"},
    "Organisation et SI": {"icon": "diagram-3", "cat": "Systèmes", "color": GOLD},
    "Info. Décisionnelle": {"icon": "database", "cat": "Systèmes", "color": GOLD},
    "Anglais des Affaires": {"icon": "chat-dots", "cat": "Pro", "color": TEAL},
    "Projet Professionnel": {"icon": "briefcase", "cat": "Pro", "color": TEAL},
    "Stage et Mémoire": {"icon": "mortarboard", "cat": "Pro", "color": TEAL}
}
SUBJECTS = list(SUBJECTS_CONFIG.keys())

# --- GESTION DE L'ÉTAT ---
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None

# --- CONNEXIONS GOOGLE (SHEETS & DRIVE) ---
@st.cache_resource 
def get_google_services():
    try:
        if "gcp_service_account" not in st.secrets: return None, None
        
        # Scopes pour Sheets ET Drive
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
        
        # Service Sheets
        client = gspread.authorize(creds)
        sheet = client.open("L3_Compta_Database")
        
        # Service Drive
        drive_service = build('drive', 'v3', credentials=creds)
        
        return sheet, drive_service
    except Exception as e:
        print(f"Erreur Connexion Google: {e}") 
        return None, None

# --- FONCTIONS DRIVE ---
def get_or_create_subject_folder(drive_service, subject_name):
    """Cherche le dossier de la matière, sinon le crée dans le dossier racine"""
    root_id = st.secrets["general"]["drive_root_folder_id"]
    
    # Cherche si le dossier existe déjà dans le root
    query = f"mimeType='application/vnd.google-apps.folder' and name='{subject_name}' and '{root_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    
    if items:
        return items[0]['id']
    else:
        # Crée le dossier
        file_metadata = {
            'name': subject_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [root_id]
        }
        file = drive_service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')

def list_drive_files(drive_service, folder_id):
    query = f"'{folder_id}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id, name, webViewLink, iconLink)").execute()
    return results.get('files', [])

def upload_file_to_drive(drive_service, uploaded_file, folder_id):
    file_metadata = {'name': uploaded_file.name, 'parents': [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(uploaded_file.getvalue()), mimetype=uploaded_file.type, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file

# --- CALENDAR UTILS ---
@st.cache_data(ttl=3600, show_spinner=False) 
def get_ics_events_cached(ics_url):
    ics_events = []
    try:
        response = requests.get(ics_url, timeout=10)
        if response.status_code == 200:
            cal = Calendar.from_ical(response.content)
            for component in cal.walk('vevent'):
                start, end = component.get('dtstart').dt, component.get('dtend').dt
                summary = str(component.get('summary')) if component.get('summary') else "Cours"
                ics_events.append({
                    "title": summary,
                    "start": start.isoformat() if hasattr(start, 'isoformat') else str(start),
                    "end": end.isoformat() if hasattr(end, 'isoformat') else str(end),
                    "backgroundColor": TEAL, "borderColor": NAVY
                })
    except: pass
    return ics_events

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

# --- COMPOSANTS UI ---
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

# --- PAGE 1: DASHBOARD ---
def dashboard_page(sh):
    st.markdown(f"### 👋 Bonjour, voici ton état des lieux")
    st.markdown(f"<p style='color:#64748b;'>Semestre 2 • {datetime.now().strftime('%d %B %Y')}</p>", unsafe_allow_html=True)
    
    if not sh: st.warning("⚠️ Mode hors ligne (BDD déconnectée).")

    gpa, urgent_tasks = 0.0, 0
    if sh:
        try:
            ws_g, ws_t = sh.worksheet("Grades"), sh.worksheet("Tasks")
            grades, tasks = ws_g.get_all_records(), ws_t.get_all_records()
            df_g = pd.DataFrame(grades)
            if not df_g.empty:
                df_g['Grade'], df_g['Coefficient'] = pd.to_numeric(df_g['Grade'], errors='coerce'), pd.to_numeric(df_g['Coefficient'], errors='coerce')
                df_g.dropna(inplace=True)
                total_p, total_c = (df_g['Grade'] * df_g['Coefficient']).sum(), df_g['Coefficient'].sum()
                gpa = round(total_p / total_c, 2) if total_c > 0 else 0
            urgent_tasks = len([t for t in tasks if t['Status'] == 'À faire'])
        except: pass

    c1, c2, c3 = st.columns(3)
    with c1: kpi_card("Moyenne Générale", f"{gpa}/20", "📈 +0.5 pts vs S1", NAVY, "🎓")
    with c2: kpi_card("Tâches Urgentes", str(urgent_tasks), "🔥 Keep pushing", TEAL, "⚡")
    with c3: kpi_card("Semaine", f"S{datetime.now().isocalendar()[1]}", "🗓 Année Univ.", GOLD, "📅")

    st.write("")
    c_left, c_right = st.columns([2, 1])

    with c_left:
        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        events = get_combined_events(ICS_CALENDAR_URL, sh)
        calendar_options = {
            "headerToolbar": {"left": "today prev,next", "center": "title", "right": "timeGridWeek,dayGridMonth"},
            "initialView": "timeGridWeek", "slotMinTime": "08:00:00", "slotMaxTime": "21:00:00", "height": "550px", "allDaySlot": False, "locale": "fr"
        }
        calendar(events=events, options=calendar_options, custom_css=".fc-event { border-radius: 4px; font-size: 11px; }")
        
        if sh:
            with st.expander("➕ Ajouter une session de révision"):
                with st.form("add_event"):
                    ev_title, c_d, c_h1, c_h2 = st.text_input("Matière"), st.columns(3)[0], st.columns(3)[1], st.columns(3)[2]
                    ev_date, ev_start, ev_end = c_d.date_input("Date"), c_h1.time_input("Début", dt_time(18,0)), c_h2.time_input("Fin", dt_time(19,0))
                    if st.form_submit_button("Ajouter"):
                        try:
                            start, end = datetime.combine(ev_date, ev_start).isoformat(), datetime.combine(ev_date, ev_end).isoformat()
                            sh.worksheet("Events").append_row([str(uuid.uuid4())[:8], ev_title, start, end, "Revision"])
                            st.success("Ajouté !"); time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Erreur: {e}")

            with st.expander("🗑️ Gérer mes événements"):
                try:
                    df_ev = pd.DataFrame(sh.worksheet("Events").get_all_records())
                    if not df_ev.empty:
                        for i, row in df_ev.iterrows():
                            c_t, c_b = st.columns([4, 1])
                            c_t.markdown(f"**{row['Title']}** <span style='color:grey; font-size:12px'>{row['Start']}</span>", unsafe_allow_html=True)
                            if c_b.button("❌", key=f"del_ev_{row['ID']}"):
                                try:
                                    ids = sh.worksheet("Events").col_values(1)
                                    idx = ids.index(str(row['ID']).strip()) + 1
                                    sh.worksheet("Events").delete_rows(idx)
                                    st.success("Supprimé !"); time.sleep(1); st.rerun()
                                except: st.error("Introuvable")
                            st.divider()
                    else: st.info("Aucun événement.")
                except Exception as e:
                    if "rerun" not in str(e).lower(): st.warning("Chargement...")

    with c_right:
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do Urgent</span>", unsafe_allow_html=True)
        if sh and urgent_tasks > 0:
            todo = pd.DataFrame(tasks)[pd.DataFrame(tasks)['Status'] == 'À faire'].head(4)
            for i, row in todo.iterrows():
                with st.container(border=True):
                    c_chk, c_tx = st.columns([1, 4])
                    if c_chk.button("✔", key=f"done_{row['ID']}"):
                        cell = sh.worksheet("Tasks").find(row['ID'])
                        sh.worksheet("Tasks").update_cell(cell.row, 4, "Fait"); st.rerun()
                    d_disp = f"📅 {row['Due_Date']}" if row["Due_Date"] else ""
                    c_tx.markdown(f"**{row['Task']}**<br><span style='color:grey; font-size:12px'>{row['Subject']}</span> <span style='color:#e11d48; font-size:11px; float:right'>{d_disp}</span>", unsafe_allow_html=True)
        else: st.info("Rien à faire !")

# --- PAGE 2: GRILLE DES COURS ---
def courses_grid_page():
    st.markdown(f"### 📚 Mes Modules")
    st.markdown("Accès rapide à tes cours.")
    st.write("")

    cols = st.columns(3)
    
    for index, subject in enumerate(SUBJECTS):
        conf = SUBJECTS_CONFIG[subject]
        col = cols[index % 3]
        
        with col:
            st.markdown(f"""
            <div style="background-color: white; border-radius: 15px; padding: 20px; height: 180px; border: 1px solid #e2e8f0; border-left: 6px solid {NAVY}; box-shadow: 0 4px 6px rgba(0,0,0,0.05); position: relative; z-index: 0;">
                <div style="display:flex; justify-content:space-between; align-items:start;">
                    <span style="background-color: #f1f5f9; color: {NAVY}; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase;">{conf['cat']}</span>
                    <div class="icon-box" style="width:30px; height:30px; border-radius:50%; background-color: {CLOUD}; display:flex; align-items:center; justify-content:center; color: {NAVY};">
                         <i class="bi bi-{conf.get('icon', 'book')}"></i>
                    </div>
                </div>
                <h3 style="margin-top: 25px; font-size: 18px; margin-bottom: 5px; color: {NAVY};">{subject}</h3>
                <div style="height: 4px; width: 40px; background-color: {conf['color']}; border-radius: 2px;"></div>
            </div>
            """, unsafe_allow_html=True)
            
            # Bouton d'action
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True):
                st.session_state.selected_subject = subject
                st.rerun()

# --- PAGE 3: DÉTAIL MATIÈRE (AVEC DRIVE) ---
def subject_detail_page(sh, drive, subject):
    if st.button("← Retour à la grille"):
        st.session_state.selected_subject = None
        st.rerun()

    conf = SUBJECTS_CONFIG[subject]
    st.markdown(f"""
    <div style="background-color: white; padding: 30px; border-radius: 15px; border-top: 8px solid {conf['color']}; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px;">
        <span style="background-color: #f1f5f9; padding: 5px 10px; border-radius: 5px; font-size: 10px; font-weight: bold; text-transform: uppercase; color: #64748b;">{conf['cat']}</span>
        <h1 style="color: {NAVY}; margin-top: 10px; margin-bottom: 5px;">{subject}</h1>
    </div>
    """, unsafe_allow_html=True)

    # REMPLACEMENT IA PAR DRIVE
    tab1, tab2, tab3 = st.tabs(["📂 Fichiers & Cours", "📝 Notes & Simu", "✅ Tâches"])

    # TAB 1 : GOOGLE DRIVE
    with tab1:
        st.caption("Espace de stockage synchronisé avec Google Drive.")
        
        if drive:
            # 1. Récupération/Création dossier
            try:
                folder_id = get_or_create_subject_folder(drive, subject)
                
                # 2. Zone d'Upload
                uploaded_file = st.file_uploader("Déposer un fichier", key=f"up_{subject}")
                if uploaded_file is not None:
                    if st.button("Envoyer sur Drive"):
                        with st.spinner("Envoi en cours..."):
                            upload_file_to_drive(drive, uploaded_file, folder_id)
                        st.success("Fichier envoyé !")
                        time.sleep(1)
                        st.rerun()
                
                st.markdown("---")
                
                # 3. Liste des fichiers
                files = list_drive_files(drive, folder_id)
                if files:
                    for f in files:
                        icon = f.get('iconLink', '')
                        st.markdown(f"""
                        <div class="file-card">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <img src="{icon}" width="20">
                                <a href="{f['webViewLink']}" target="_blank" class="file-link">{f['name']}</a>
                            </div>
                            <span style="font-size:10px; color:grey;">Ouvrir ↗</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("Dossier vide. Ajoute tes premiers cours !")
                    
            except Exception as e:
                st.error(f"Erreur Drive : {e}")
                st.caption("Vérifie que tu as bien partagé le dossier racine avec l'adresse email du Service Account.")
        else:
            st.warning("Service Drive non configuré (vérifie tes secrets).")

    # TAB 2 : NOTES
    with tab2:
        c1, c2 = st.columns([1, 2])
        if sh:
            ws_g = sh.worksheet("Grades")
            with c1:
                with st.form("add_n"):
                    n, c, t = st.number_input("Note",0.0,20.0), st.number_input("Coef",0.0,10.0,1.0), st.selectbox("Type",["CC","Partiel","Examen"])
                    if st.form_submit_button("Sauvegarder"):
                        ws_g.append_row([str(uuid.uuid4())[:8], subject, n, c, t]); st.success("OK"); time.sleep(1); st.rerun()
            with c2:
                rows = ws_g.get_all_values()
                if len(rows) > 1:
                    df = pd.DataFrame(rows[1:], columns=rows[0])
                    df['real_idx'] = range(2, len(rows)+1)
                    df_s = df[df['Subject'] == subject]
                    for i, r in df_s.iterrows():
                        ca, cb, cc, cd = st.columns([2,2,2,1])
                        ca.markdown(f"**{r['Grade']}/20**")
                        cb.caption(f"Coef {r['Coefficient']}")
                        cc.caption(r['Type'])
                        if cd.button("❌", key=f"d_{r['ID']}"):
                            ws_g.delete_rows(int(r['real_idx'])); st.rerun()

    # TAB 3 : TÂCHES
    with tab3:
        if sh:
            ws_t = sh.worksheet("Tasks")
            ct, cd, cb = st.columns([3, 2, 1])
            nt, nd = ct.text_input("Tâche", key=f"nt_{subject}"), cd.date_input("Date", key=f"nd_{subject}")
            cb.write(""); cb.write("")
            if cb.button("Ajouter", key=f"bt_{subject}"):
                ws_t.append_row([str(uuid.uuid4())[:8], subject, nt, "À faire", str(nd)]); st.rerun()
            
            recs = ws_t.get_all_records()
            if recs:
                df = pd.DataFrame(recs)
                df = df[(df['Subject'] == subject) & (df['Status'] == 'À faire')]
                for i, r in df.iterrows():
                    c_chk, c_info = st.columns([1, 10])
                    if c_chk.checkbox("", key=f"c_{r['ID']}"):
                        cell = ws_t.find(r['ID'])
                        ws_t.update_cell(cell.row, 4, "Fait"); st.rerun()
                    d_show = f"📅 {r['Due_Date']}" if r["Due_Date"] else ""
                    c_info.markdown(f"{r['Task']} <span style='color:#e11d48; margin-left:10px; font-size:0.8em'>{d_show}</span>", unsafe_allow_html=True)

# --- PAGE 4: FOCUS ROOM ---
def focus_room_page():
    st.markdown(f"### ⏳ Focus Room")
    st.markdown("Configure ta session et ne ferme pas cet onglet.")
    
    c1, c2, c3, c4 = st.columns(4)
    work_min = c1.number_input("Travail (min)", 1, 60, 25)
    short_break = c2.number_input("Pause courte", 1, 15, 5)
    long_break = c3.number_input("Pause longue", 5, 30, 15)
    cycles = c4.number_input("Cycles", 1, 10, 4)

    col_center, _ = st.columns([1, 2])
    start_btn = col_center.button("▶ LANCER LA SESSION", type="primary")

    placeholder = st.empty()

    if start_btn:
        total_cycles = cycles
        for i in range(total_cycles):
            for remaining in range(work_min * 60, -1, -1):
                mins, secs = divmod(remaining, 60)
                with placeholder.container():
                    st.markdown(f"<p class='timer-label'>💻 CYCLE {i+1}/{total_cycles} • FOCUS</p>", unsafe_allow_html=True)
                    st.markdown(f"<div class='timer-display'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
                    st.progress((work_min*60 - remaining) / (work_min*60))
                time.sleep(1)
            if i < total_cycles - 1:
                is_long = (i + 1) % 4 == 0
                break_time = long_break if is_long else short_break
                label = "☕ PAUSE LONGUE" if is_long else "🍵 PAUSE COURTE"
                for remaining in range(break_time * 60, -1, -1):
                    mins, secs = divmod(remaining, 60)
                    with placeholder.container():
                        st.markdown(f"<p class='timer-label'>{label}</p>", unsafe_allow_html=True)
                        st.markdown(f"<div class='timer-display' style='color:{TEAL}; border-color:{NAVY}'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
                    time.sleep(1)
        st.balloons(); st.success("Session terminée ! Bravo 🎉")

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
