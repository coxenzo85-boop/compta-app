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

# --- 1. CONFIGURATION PAGE (DOIT ÊTRE LA PREMIÈRE LIGNE) ---
st.set_page_config(page_title="L3 CCA Dashboard", page_icon="🎓", layout="wide")

# --- 2. INITIALISATION SESSION STATE (CRITIQUE POUR ÉVITER LES CRASH) ---
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False
if 'timer_active' not in st.session_state: st.session_state.timer_active = False
if 'timer_end_time' not in st.session_state: st.session_state.timer_end_time = None
if 'timer_subject' not in st.session_state: st.session_state.timer_subject = "Général"
if 'timer_duration' not in st.session_state: st.session_state.timer_duration = 25

# --- 3. CONSTANTES & CONFIGURATION ---
ICS_CALENDAR_URL = "http://edt-v2.univ-nantes.fr/calendar/ics?timetables[0]=110228"

NAVY, TEAL, GOLD, CLOUD, ORANGE_REV, RED_URGENT = "#1A2C42", "#008080", "#C5A059", "#F4F6F7", "#ea580c", "#e11d48"

DEFAULT_S1 = ["Théorie des organisations", "Management Control", "Marché Financier", "TQG", "Financial Analysis", "Droit des sociétés", "Droit fiscal", "Comptabilité", "Anglais"]
DEFAULT_S2 = ["Diagnostic Financier", "Compta Approfondie 2", "Modélisation des Coûts", "Int. Financial Accounting", "Diagnostic Général", "Droit des Sociétés 2", "Droit du Crédit", "Droit Pénal Affaires", "Organisation et SI", "Info. Décisionnelle", "Anglais", "Projet Professionnel"]

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

# --- 4. CSS ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=Lato:wght@300;400;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'Lato', sans-serif; background-color: {CLOUD}; color: {NAVY}; }}
    h1, h2, h3 {{ font-family: 'Libre Baskerville', serif; color: {NAVY}; }}
    [data-testid="stSidebar"] {{ background-color: {NAVY}; }}
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{ color: white !important; }}
    .kpi-card {{ background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-left: 5px solid {NAVY}; height: 100%; transition: transform 0.2s; }}
    .kpi-card:hover {{ transform: translateY(-5px); }}
    .stButton>button {{ background-color: {TEAL}; color: white; border-radius: 8px; border: none; font-weight: bold; transition: all 0.2s; }}
    .stButton>button:hover {{ background-color: {NAVY}; }}
    .exam-widget {{ background-color: white; padding: 10px; border-radius: 8px; border-left: 4px solid {TEAL}; margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
    .exam-days {{ font-size: 11px; padding: 3px 8px; border-radius: 10px; color: white; background-color: {NAVY}; font-weight: bold; }}
    .timer-display {{ font-size: 60px; font-weight: bold; color: {NAVY}; text-align: center; font-family: monospace; background: white; border-radius: 15px; border: 3px solid {GOLD}; padding: 10px; margin: 10px 0; }}
    .file-card {{ background: white; padding: 10px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center; }}
    </style>
    """, unsafe_allow_html=True)

# --- 5. CONNEXIONS & FONCTIONS UTILITAIRES ---
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
    except Exception as e: return None, None

def get_or_create_subject_folder(drive, subject):
    try:
        root = st.secrets["general"]["drive_root_folder_id"]
        q = f"mimeType='application/vnd.google-apps.folder' and name='{subject}' and '{root}' in parents and trashed=false"
        res = drive.files().list(q=q, fields="files(id)").execute()
        if res.get('files'): return res.get('files')[0]['id']
        meta = {'name': subject, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [root]}
        return drive.files().create(body=meta, fields='id').execute().get('id')
    except: return None

def list_drive_files(drive, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed=false"
        return drive.files().list(q=q, fields="files(id, name, webViewLink, iconLink)").execute().get('files', [])
    except: return []

def upload_file_to_drive(drive, file, folder_id):
    media = MediaIoBaseUpload(io.BytesIO(file.getvalue()), mimetype=file.type, resumable=True)
    drive.files().create(body={'name': file.name, 'parents': [folder_id]}, media_body=media).execute()

@st.cache_data(ttl=3600)
def get_ics_events_cached(url):
    events = []
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            cal = Calendar.from_ical(r.content)
            for c in cal.walk('vevent'):
                if c.get('dtstart'):
                    events.append({
                        "title": str(c.get('summary', 'Cours')), 
                        "start": c.get('dtstart').dt, 
                        "end": c.get('dtend').dt,
                        "iso_start": c.get('dtstart').dt.isoformat() if hasattr(c.get('dtstart').dt, 'isoformat') else str(c.get('dtstart').dt),
                        "iso_end": c.get('dtend').dt.isoformat() if hasattr(c.get('dtend').dt, 'isoformat') else str(c.get('dtend').dt),
                    })
    except: pass
    return events

# --- LA FONCTION QUI MANQUAIT : get_combined_events ---
def get_combined_events(ics_url, sh):
    events = get_ics_events_cached(ics_url)
    # Pour l'instant on se contente de l'ICS pour éviter les bugs si la sheet Events n'existe pas
    return events 

# --- LA FONCTION KPI QUI MANQUAIT ---
def kpi_card(title, value, subtitle, color, icon):
    st.markdown(f"""
    <div class="kpi-card" style="border-left: 5px solid {color};">
        <div style="display:flex; justify-content:space-between;">
            <div><p style="font-size:10px; font-weight:bold; color:#94a3b8;">{title}</p><h2 style="font-size:2rem; margin:0; color:{NAVY};">{value}</h2></div>
            <div style="font-size:1.5rem; color:{color};">{icon}</div>
        </div>
        <p style="font-size:12px; color:{TEAL}; margin-top:10px;">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

# --- FONCTIONS DONNÉES (Google Sheets) ---
def save_to_history(sh, action, subject, value):
    try: sh.worksheet("History").append_row([str(date.today()), action, subject, value])
    except: pass

def get_history_stats(sh):
    try: return pd.DataFrame(sh.worksheet("History").get_all_records())
    except: return pd.DataFrame()

def get_exams(sh):
    try: return pd.DataFrame(sh.worksheet("Exams").get_all_records())
    except: return pd.DataFrame(columns=["Matiere", "Date"])

def save_exams(sh, df):
    try:
        ws = sh.worksheet("Exams")
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
    except: pass

# --- GESTION DU TIMER (GLOBAL) ---
def check_timer(sh):
    if st.session_state.timer_active and st.session_state.timer_end_time:
        if datetime.now() >= st.session_state.timer_end_time:
            st.session_state.timer_active = False
            st.session_state.timer_end_time = None
            if sh: save_to_history(sh, "Pomodoro", st.session_state.timer_subject, st.session_state.timer_duration)
            st.toast("Session terminée ! 🎉", icon="✅")

# --- MENU ---
def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        opts = ["Dashboard", "Mes Cours", "Focus Room"]
        try: idx = opts.index(st.session_state.current_view)
        except: idx = 0
        sel = option_menu(None, opts, icons=["speedometer2", "book", "hourglass"], default_index=idx, 
                          styles={"container": {"background-color": NAVY}, "nav-link-selected": {"background-color": TEAL}})
        
        # Mini Timer
        if st.session_state.timer_active and st.session_state.timer_end_time:
            rem = st.session_state.timer_end_time - datetime.now()
            if rem.total_seconds() > 0:
                mins, secs = divmod(int(rem.total_seconds()), 60)
                st.markdown("---")
                st.metric("Focus en cours", f"{mins:02}:{secs:02}")
            else: st.rerun()
    return sel

# --- PAGES ---
def dashboard_page(sh):
    st.markdown(f"### 👋 Dashboard • {date.today().strftime('%d %B')}")
    
    # 1. MOYENNE & KPI
    s1_avg = "0.0/20"
    if sh:
        try:
            df_sim = pd.DataFrame(sh.worksheet("Simulateur").get_all_records())
            if not df_sim.empty:
                s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
                s1['Moy'] = ((s1['Note_CC']*s1['Coef_CC']) + (s1['Note_Partiel']*s1['Coef_Partiel'])) / (s1['Coef_CC']+s1['Coef_Partiel']).replace(0,1)
                valid = (s1['Coef_CC']+s1['Coef_Partiel']) > 0
                if valid.any(): s1_avg = f"{s1.loc[valid, 'Moy'].mean():.2f}/20"
        except: pass

    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Moyenne S1", s1_avg, "Simulateur", NAVY, "🎓")
        if st.button("🧮 Ouvrir Simulateur"): 
            st.session_state.show_simulator = not st.session_state.show_simulator; st.rerun()
    with c2:
        ftxt = "🔥 Session active" if st.session_state.timer_active else "Prêt à bosser ?"
        kpi_card("Focus Room", ftxt, "Productivité", GOLD, "⏳")
        if st.button("🚀 Go Focus"): st.session_state.current_view = "Focus Room"; st.rerun()

    # 2. SIMULATEUR
    if st.session_state.show_simulator and sh:
        st.write(""); st.info("Modifie tes notes ici.")
        try:
            df_sim = pd.DataFrame(sh.worksheet("Simulateur").get_all_records())
            tab1, tab2 = st.tabs(["S1", "S2"])
            cfg = {"Matiere": st.column_config.TextColumn(disabled=True), "Semestre": None}
            with tab1: e1 = st.data_editor(df_sim[df_sim['Semestre']=='S1'], column_config=cfg, hide_index=True, key="e1")
            with tab2: e2 = st.data_editor(df_sim[df_sim['Semestre']=='S2'], column_config=cfg, hide_index=True, key="e2")
            if st.button("Sauvegarder"):
                full = pd.concat([e1, e2])
                sh.worksheet("Simulateur").update([full.columns.values.tolist()] + full.values.tolist())
                st.success("Sauvegardé !"); time.sleep(1); st.rerun()
        except Exception as e: st.error(f"Erreur Simulateur: {e}")

    # 3. CONTENU PRINCIPAL
    st.write("")
    cl, cr = st.columns([2, 1])
    
    with cl:
        # HEATMAP / STATS
        if sh:
            df_h = get_history_stats(sh)
            if not df_h.empty:
                poms = df_h[df_h['Action'] == 'Pomodoro']
                if not poms.empty:
                    st.markdown("##### 📊 Répartition Temps")
                    fig = px.pie(poms, values='Value', names='Subject', hole=0.4, color_discrete_sequence=px.colors.sequential.Teal)
                    fig.update_layout(height=250, margin=dict(t=0,b=0,l=0,r=0)); st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("##### 🗓️ Semaine")
        evs = get_combined_events(ICS_CALENDAR_URL, sh)
        cal_evs = [{"title": e['title'], "start": e['iso_start'], "end": e['iso_end'], "backgroundColor": TEAL} for e in evs]
        calendar(events=cal_evs, options={"initialView": "timeGridWeek", "height": "450px", "locale": "fr"}, custom_css=".fc-event{font-size:10px;}")

    with cr:
        # EXAMENS (MODIFIABLE)
        st.markdown("##### ⏳ Examens")
        if sh:
            df_ex = get_exams(sh)
            # Éditeur direct pour modifier les examens
            edited_exams = st.data_editor(df_ex, num_rows="dynamic", key="ex_edit", hide_index=True)
            if not df_ex.equals(edited_exams):
                save_exams(sh, edited_exams)
                st.rerun()
            
            # Affichage J-X
            today = date.today()
            if not edited_exams.empty:
                # Convertir colonne Date en datetime si possible
                try:
                    edited_exams['DateObj'] = pd.to_datetime(edited_exams['Date']).dt.date
                    edited_exams = edited_exams.sort_values('DateObj')
                    for _, row in edited_exams.iterrows():
                        delta = (row['DateObj'] - today).days
                        if delta >= 0:
                            col = RED_URGENT if delta < 7 else ORANGE_REV if delta < 14 else TEAL
                            st.markdown(f"<div class='exam-widget' style='border-left:4px solid {col}'><div><b>{row['Matiere']}</b><br><span style='color:grey;font-size:10px'>{row['Date']}</span></div><span class='exam-days' style='background:{col}'>J-{delta}</span></div>", unsafe_allow_html=True)
                except: st.caption("Format date invalide (YYYY-MM-DD)")

        # TODO
        st.write(""); st.markdown("##### 📌 To-Do")
        if sh:
            ws_t = sh.worksheet("Tasks")
            tasks = pd.DataFrame(ws_t.get_all_records())
            todo = tasks[tasks['Status'] == 'À faire'] if not tasks.empty else pd.DataFrame()
            if not todo.empty:
                for i, r in todo.head(4).iterrows():
                    c_chk, c_txt = st.columns([1, 5])
                    if c_chk.button("✔", key=f"done_{r['ID']}"):
                        ws_t.update_cell(ws_t.find(r['ID']).row, 4, "Fait"); save_to_history(sh, "Task", r['Subject'], 1); st.rerun()
                    c_txt.caption(f"{r['Task']} ({r['Subject']})")
            else: st.success("Rien à faire !")

def courses_page(sh, drive):
    if st.session_state.selected_subject:
        sub = st.session_state.selected_subject
        if st.button("← Retour"): st.session_state.selected_subject = None; st.rerun()
        st.title(sub)
        t1, t2 = st.tabs(["📂 Drive & IA", "✅ Tâches"])
        with t1:
            st.info("💡 Utilise NotebookLM pour réviser avec ces fichiers.")
            st.link_button("🧠 Ouvrir NotebookLM", NOTEBOOK_LINKS.get(sub, "https://notebooklm.google.com/"), type="primary")
            if drive:
                fid = get_or_create_subject_folder(drive, sub)
                up = st.file_uploader("Ajouter cours", key="up")
                if up and st.button("Envoyer"): upload_file_to_drive(drive, up, fid); st.success("Envoyé !"); st.rerun()
                for f in list_drive_files(drive, fid):
                    st.markdown(f"<div class='file-card'><a href='{f['webViewLink']}' target='_blank'>📄 {f['name']}</a></div>", unsafe_allow_html=True)
        with t2:
            if sh:
                c1, c2 = st.columns([3,1])
                t = c1.text_input("Tâche"); d = c2.date_input("Date")
                if st.button("Ajouter"): sh.worksheet("Tasks").append_row([str(uuid.uuid4())[:8], sub, t, "À faire", str(d)]); st.rerun()
    else:
        st.markdown("### 📚 Mes Modules S2"); st.write("")
        cols = st.columns(3)
        for i, s in enumerate(DEFAULT_S2):
            with cols[i % 3]:
                st.markdown(f"<div style='background:white;padding:15px;border-radius:10px;border-left:5px solid {NAVY};margin-bottom:10px'><b>{s}</b></div>", unsafe_allow_html=True)
                if st.button(f"Ouvrir", key=s): st.session_state.selected_subject = s; st.rerun()

def focus_page(sh):
    st.markdown("### ⏳ Focus Room")
    with st.expander("🎵 Ambiance", expanded=True): st.video("https://www.youtube.com/watch?v=jfKfPfyJRdk")
    
    if not st.session_state.timer_active:
        c1, c2, c3 = st.columns(3)
        sub = c1.selectbox("Matière", DEFAULT_S2)
        dur = c2.number_input("Durée (min)", 5, 120, 25)
        if st.button("▶ LANCER", type="primary"):
            st.session_state.timer_active = True
            st.session_state.timer_end_time = datetime.now() + timedelta(minutes=dur)
            st.session_state.timer_subject = sub
            st.session_state.timer_duration = dur
            st.rerun()
    else:
        rem = st.session_state.timer_end_time - datetime.now()
        if rem.total_seconds() > 0:
            mins, secs = divmod(int(rem.total_seconds()), 60)
            st.markdown(f"<div class='timer-display'>{mins:02}:{secs:02}</div>", unsafe_allow_html=True)
            st.progress((st.session_state.timer_duration*60 - rem.total_seconds()) / (st.session_state.timer_duration*60))
            if st.button("⏹ Abandonner"): st.session_state.timer_active = False; st.rerun()
            time.sleep(1); st.rerun()
        else:
            check_timer(sh) # Fin timer
            if st.button("Nouvelle Session"): st.rerun()

# --- MAIN ---
if __name__ == "__main__":
    sh, drive = get_google_services()
    check_timer(sh) # Vérif timer globale
    
    page = sidebar_menu()
    if page != st.session_state.current_view: 
        st.session_state.current_view = page
        st.session_state.selected_subject = None
        st.rerun()

    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours": courses_page(sh, drive)
    elif st.session_state.current_view == "Focus Room": focus_page(sh)
