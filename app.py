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
import json
from fpdf import FPDF

# ==============================================================================
# 1. CONFIGURATION & DESIGN SYSTEM (MODERNE)
# ==============================================================================
st.set_page_config(page_title="Student OS", page_icon="⚡", layout="wide")

# Initialisation Session State
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False
if 'timer_active' not in st.session_state: st.session_state.timer_active = False
if 'timer_end_time' not in st.session_state: st.session_state.timer_end_time = None
if 'timer_subject' not in st.session_state: st.session_state.timer_subject = "Général"
if 'timer_duration' not in st.session_state: st.session_state.timer_duration = 25

# Constantes
ICS_CALENDAR_URL = "http://edt-v2.univ-nantes.fr/calendar/ics?timetables[0]=110228"

# --- PALETTE MODERNE (GLASSMORPHISM) ---
BACKGROUND_GRADIENT = "linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)"
GLASS_WHITE = "rgba(255, 255, 255, 0.7)"
NAVY = "#1e293b"
TEAL = "#0f766e"
GOLD = "#b45309"
ACCENT = "#2563eb"

DEFAULT_S1 = ["Théorie des organisations", "Management Control", "Marché Financier", "TQG", "Financial Analysis", "Droit des sociétés", "Droit fiscal", "Comptabilité", "Anglais"]
DEFAULT_S2 = ["Diagnostic Financier", "Compta Approfondie 2", "Modélisation des Coûts", "Int. Financial Accounting", "Diagnostic Général", "Droit des Sociétés 2", "Droit du Crédit", "Droit Pénal Affaires", "Organisation et SI", "Info. Décisionnelle", "Anglais", "Projet Professionnel"]
SUBJECTS = DEFAULT_S1 + DEFAULT_S2
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

# --- CSS ULTRA MODERNE ---
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    /* GLOBAL */
    html, body, [class*="css"] {{
        font-family: 'Inter', sans-serif;
        color: {NAVY};
    }}
    
    .stApp {{
        background: {BACKGROUND_GRADIENT};
    }}

    /* SIDEBAR */
    [data-testid="stSidebar"] {{
        background-color: white;
        border-right: 1px solid rgba(255,255,255,0.5);
        box-shadow: 5px 0 15px rgba(0,0,0,0.05);
    }}
    [data-testid="stSidebar"] h2 {{
        color: {NAVY} !important;
        font-weight: 800;
        letter-spacing: -1px;
    }}

    /* CARDS */
    .glass-card {{
        background: {GLASS_WHITE};
        backdrop-filter: blur(10px);
        border-radius: 20px;
        padding: 25px;
        border: 1px solid rgba(255, 255, 255, 0.5);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.07);
        transition: transform 0.3s ease;
        height: 100%;
    }}
    .glass-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.1);
    }}

    /* TYPOGRAPHIE */
    .card-label {{
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #64748b;
        margin-bottom: 5px;
    }}
    .card-value {{
        font-size: 36px;
        font-weight: 800;
        color: {NAVY};
        margin-bottom: 10px;
    }}
    
    /* BOUTONS */
    .stButton>button {{
        background: linear-gradient(135deg, {TEAL} 0%, #0d9488 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.2s;
    }}
    .stButton>button:hover {{
        transform: scale(1.02);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }}

    /* WIDGETS SPECIFIQUES */
    .exam-row {{
        display: flex; justify-content: space-between; align-items: center;
        padding: 12px; background: white; border-radius: 10px; margin-bottom: 8px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.03);
    }}
    .tag {{
        padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: bold; color: white;
    }}
    
    .course-card-modern {{
        background: white;
        border-radius: 20px;
        padding: 20px;
        height: 160px;
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.8);
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }}
    .course-card-modern:hover {{
        transform: translateY(-5px);
        box-shadow: 0 10px 25px rgba(0,0,0,0.1);
    }}
    
    /* Hack Bouton Overlay */
    div.stButton > button.click-cover {{
        position: absolute; top: -170px; left: 0; width: 100%; height: 180px; opacity: 0; z-index: 5; cursor: pointer;
    }}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. FONCTIONS BACKEND ROBUSTES
# ==============================================================================

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
        res = drive.files().list(q=q, fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        if res.get('files'): return res.get('files')[0]['id']
        meta = {'name': subject, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [root]}
        return drive.files().create(body=meta, fields='id', supportsAllDrives=True).execute().get('id')
    except: return None

def list_drive_files(drive, folder_id):
    try:
        q = f"'{folder_id}' in parents and trashed=false"
        return drive.files().list(q=q, fields="files(id, name, webViewLink, iconLink)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get('files', [])
    except: return []

def upload_file_to_drive(drive_service, uploaded_file, folder_id):
    try:
        file_content = io.BytesIO(uploaded_file.getvalue())
        media = MediaIoBaseUpload(file_content, mimetype=uploaded_file.type, resumable=False)
        file_metadata = {'name': uploaded_file.name, 'parents': [folder_id]}
        drive_service.files().create(body=file_metadata, media_body=media, supportsAllDrives=True).execute()
        return True
    except Exception as e:
        st.error(f"Erreur Upload: {e}")
        return False

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
                        "start": c.get('dtstart').dt.isoformat() if hasattr(c.get('dtstart').dt, 'isoformat') else str(c.get('dtstart').dt), 
                        "end": c.get('dtend').dt.isoformat() if hasattr(c.get('dtend').dt, 'isoformat') else str(c.get('dtend').dt),
                        "backgroundColor": TEAL, "borderColor": NAVY
                    })
    except: pass
    return events

def get_combined_events(ics_url, sh):
    events = get_ics_events_cached(ics_url)
    if sh:
        try:
            recs = sh.worksheet("Events").get_all_records()
            for r in recs:
                events.append({
                    "title": f"📚 {r['Title']}", 
                    "start": r['Start'], "end": r['End'],
                    "backgroundColor": ORANGE_REV, "borderColor": GOLD
                })
        except: pass
    return events

# Fonctions Historique & Examens
def save_to_history(sh, action, subject, value):
    try: sh.worksheet("History").append_row([str(date.today()), action, subject, value])
    except: pass

def get_history_stats(sh):
    try: return pd.DataFrame(sh.worksheet("History").get_all_records())
    except: return pd.DataFrame()

# Gestion Timer Global
def check_timer(sh):
    if st.session_state.timer_active and st.session_state.timer_end_time:
        if datetime.now() >= st.session_state.timer_end_time:
            st.session_state.timer_active = False
            st.session_state.timer_end_time = None
            if sh: save_to_history(sh, "Pomodoro", st.session_state.timer_subject, st.session_state.timer_duration)
            st.toast("Session terminée ! 🎉", icon="✅")

# Simulateur
def load_simulator_data(sh):
    try:
        ws = sh.worksheet("Simulateur")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if df.empty or 'Semestre' not in df.columns:
            init_data = []
            for m in DEFAULT_S1: init_data.append({"Matiere": m, "Semestre": "S1", "Coef_CC": 1, "Coef_Partiel": 2, "Note_CC": 0, "Note_Partiel": 0})
            for m in DEFAULT_S2: init_data.append({"Matiere": m, "Semestre": "S2", "Coef_CC": 1, "Coef_Partiel": 2, "Note_CC": 0, "Note_Partiel": 0})
            df = pd.DataFrame(init_data)
            ws.clear(); ws.update([df.columns.values.tolist()] + df.values.tolist())
        return df
    except: return pd.DataFrame()

def save_simulator_data(sh, df):
    try:
        ws = sh.worksheet("Simulateur")
        cols = ["Matiere", "Semestre", "Coef_CC", "Coef_Partiel", "Note_CC", "Note_Partiel"]
        df_save = df[cols]
        ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())
    except: pass

# PDF Generator
def create_financial_pdf(data):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'Rapport Analyse Financiere', 0, 1, 'C')
            self.ln(5)
        def chapter_title(self, title):
            self.set_font('Arial', 'B', 12)
            self.set_fill_color(240, 240, 240)
            self.cell(0, 10, title, 0, 1, 'L', 1); self.ln(4)
        def chapter_body(self, body):
            self.set_font('Arial', '', 11)
            self.multi_cell(0, 8, body); self.ln()

    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 14)
    nom = data['nom'].encode('latin-1', 'replace').decode('latin-1')
    pdf.cell(0, 10, f"Dossier : {nom}", 0, 1, 'L'); pdf.ln(5)
    
    pdf.chapter_title('1. Equilibre')
    pdf.chapter_body(f"FRNG: {data['frng']:,.0f} | BFR: {data['bfr']:,.0f} | TN: {data['tn']:,.0f}")
    pdf.chapter_title('2. Ratios')
    pdf.chapter_body(f"Marge: {data['marge']:.1f}% | ROE: {data['roe']:.1f}% | Levier: {data['levier']:.2f}")
    
    return pdf.output(dest='S').encode('latin-1')

# ==============================================================================
# 3. PAGES
# ==============================================================================

def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        opts = ["Dashboard", "Mes Cours", "Candidatures", "Analyse Fi", "Focus Room"]
        try: idx = opts.index(st.session_state.current_view)
        except: idx = 0
        
        sel = option_menu(None, opts, icons=["speedometer2", "book", "briefcase", "calculator", "hourglass"], 
                          default_index=idx, styles={"container": {"background-color": "white"}, "nav-link-selected": {"background-color": TEAL}})
        
        if st.session_state.timer_active and st.session_state.timer_end_time:
            rem = st.session_state.timer_end_time - datetime.now()
            if rem.total_seconds() > 0:
                mins, secs = divmod(int(rem.total_seconds()), 60)
                st.markdown("---")
                st.metric("Focus en cours", f"{mins:02}:{secs:02}")
            else: st.rerun()
    return sel

def dashboard_page(sh):
    st.markdown(f"### 👋 Dashboard • {date.today().strftime('%d %B')}")

    s1_avg = "0.00/20"
    s2_avg = "En attente"
    df_sim = pd.DataFrame()
    
    if sh:
        try:
            df_sim = load_simulator_data(sh)
            if not df_sim.empty:
                s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
                s1['Moy'] = ((s1['Note_CC']*s1['Coef_CC']) + (s1['Note_Partiel']*s1['Coef_Partiel'])) / (s1['Coef_CC']+s1['Coef_Partiel']).replace(0,1)
                if (s1['Coef_CC']+s1['Coef_Partiel'] > 0).any(): s1_avg = f"{s1.loc[(s1['Coef_CC']+s1['Coef_Partiel'])>0, 'Moy'].mean():.2f}/20"
                
                s2 = df_sim[df_sim['Semestre'] == 'S2'].copy()
                s2['Tot'] = s2['Coef_CC'] + s2['Coef_Partiel']
                val_s2 = s2[s2['Tot'] > 0]
                if not val_s2.empty:
                    val_s2['Moy'] = ((val_s2['Note_CC']*val_s2['Coef_CC']) + (val_s2['Note_Partiel']*val_s2['Coef_Partiel'])) / val_s2['Tot']
                    s2_avg = f"{val_s2['Moy'].mean():.2f}/20"
        except: pass

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""<div class="glass-card"><div><div class="card-label">MOYENNE S2</div><div class="card-value">{s2_avg}</div></div><div style="font-size:12px;color:#64748b">S1 : {s1_avg}</div></div>""", unsafe_allow_html=True)
        if st.button("🧮 Ouvrir Simulateur", key="btn_sim", use_container_width=True): 
            st.session_state.show_simulator = not st.session_state.show_simulator; st.rerun()

    with c2:
        ftxt = "🔥 En cours..." if st.session_state.timer_active else "Prêt ?"
        st.markdown(f"""<div class="glass-card" style="border-left:5px solid {GOLD}"><div><div class="card-label">FOCUS</div><div class="card-value">{ftxt}</div></div><div style="font-size:12px;color:#64748b">Mode Productivité</div></div>""", unsafe_allow_html=True)
        if st.button("🚀 Focus Room", key="btn_focus", use_container_width=True): 
            st.session_state.current_view = "Focus Room"; st.rerun()

    if st.session_state.show_simulator and sh:
        st.write(""); st.info("S2 : Laisse les coefficients à 0 si la matière n'a pas commencé.")
        try:
            t1, t2 = st.tabs(["S1", "S2"])
            cfg = {"Matiere": st.column_config.TextColumn(disabled=True), "Semestre": None}
            def show_sim(df, k):
                ed = st.data_editor(df, column_config=cfg, hide_index=True, key=k, use_container_width=True)
                t = ed['Coef_CC'] + ed['Coef_Partiel']
                ed['Moy'] = ((ed['Note_CC']*ed['Coef_CC']) + (ed['Note_Partiel']*ed['Coef_Partiel'])) / t.replace(0,1)
                ed.loc[t==0, 'Moy'] = 0
                st.dataframe(ed[['Matiere', 'Moy']].style.format({"Moy": "{:.2f}"}).background_gradient(subset=['Moy'], cmap="RdYlGn", vmin=0, vmax=20), use_container_width=True)
                return ed
            with t1: e1 = show_sim(df_sim[df_sim['Semestre']=='S1'], "e1")
            with t2: e2 = show_sim(df_sim[df_sim['Semestre']=='S2'], "e2")
            if st.button("💾 Sauvegarder"):
                full = pd.concat([e1.drop(columns=['Moy']), e2.drop(columns=['Moy'])])
                save_simulator_data(sh, full); st.success("Sauvegardé !"); time.sleep(1); st.rerun()
        except: st.error("Erreur Simulateur")

    st.write("")
    cl, cr = st.columns([2, 1])
    with cl:
        st.markdown("#### 🗓️ Agenda")
        evs = get_combined_events(ICS_CALENDAR_URL, sh)
        calendar(events=[{"title":e['title'], "start":e['iso_start'], "end":e['iso_end'], "backgroundColor":TEAL} for e in evs], options={"initialView": "timeGridWeek", "height": "450px", "locale": "fr"})
        if sh:
            with st.expander("➕ / 🗑️ Gestion Agenda"):
                t1, t2 = st.tabs(["Ajouter", "Supprimer"])
                with t1:
                    with st.form("add"):
                        ct, cd, ch1, ch2 = st.columns([2,1,1,1])
                        ti = ct.text_input("Titre"); da = cd.date_input("Date"); h1 = ch1.time_input("Début"); h2 = ch2.time_input("Fin")
                        if st.form_submit_button("Ajouter"):
                            s = datetime.combine(da, h1).isoformat(); e = datetime.combine(da, h2).isoformat()
                            sh.worksheet("Events").append_row([str(uuid.uuid4())[:8], ti, s, e, "Revision"]); st.rerun()
                with t2:
                    try:
                        dev = pd.DataFrame(sh.worksheet("Events").get_all_records())
                        for i, r in dev.iterrows():
                            c1, c2 = st.columns([4,1]); c1.text(f"{r['Title']}")
                            if c2.button("X", key=f"d{r['ID']}"): 
                                ids = sh.worksheet("Events").col_values(1); sh.worksheet("Events").delete_rows(ids.index(str(r['ID']))+1); st.rerun()
                    except: pass
    
    with cr:
        st.markdown("#### 📌 To-Do")
        if sh:
            try:
                tasks = pd.DataFrame(sh.worksheet("Tasks").get_all_records())
                todo = tasks[tasks['Status']=='À faire']
                if not todo.empty:
                    for i, r in todo.head(6).iterrows():
                        with st.container(border=True):
                            c1, c2 = st.columns([1,5])
                            if c1.button("✔", key=f"ok_{r['ID']}"):
                                sh.worksheet("Tasks").update_cell(sh.worksheet("Tasks").find(r['ID']).row, 4, "Fait"); st.rerun()
                            c2.caption(f"{r['Task']} ({r['Subject']})")
                else: st.success("Rien à faire !")
            except: pass

def courses_grid_page():
    st.markdown("### 📚 Mes Modules S2"); st.write("")
    cols = st.columns(3)
    for index, subject in enumerate(DEFAULT_S2):
        with cols[index % 3]:
            st.markdown(f"""<div class="course-card-modern"><div style="background:{CLOUD};width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:{NAVY};font-size:1.2rem;">📖</div><h4 style="margin-top:20px;color:{NAVY}">{subject}</h4></div>""", unsafe_allow_html=True)
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True, type="secondary"):
                st.session_state.selected_subject = subject; st.rerun()
            st.markdown(f"""<style>div[data-testid="column"]:nth-child({(index % 3) + 1}) div.stButton > button.click-cover {{ position: absolute; top: -170px; width: 100%; height: 180px; opacity: 0; z-index: 5; }}</style>""", unsafe_allow_html=True)

def subject_detail_page(sh, drive, subject):
    if st.button("← Retour"): st.session_state.selected_subject = None; st.rerun()
    st.title(subject)
    t1, t2 = st.tabs(["📂 Drive & IA", "✅ Tâches"])
    with t1:
        with st.container(border=True):
            c1, c2, c3 = st.columns([0.5, 3, 1.5])
            c1.markdown("## 🧠"); c2.markdown("**NotebookLM**\n\nTon assistant IA."); c3.link_button("↗ Ouvrir", NOTEBOOK_LINKS.get(subject, "https://notebooklm.google.com/"), type="primary")
        
        if drive:
            fid = get_or_create_subject_folder(drive, subject)
            if fid:
                st.info("Dépose tes fichiers ci-dessous.")
                st.markdown(f"<a href='https://drive.google.com/drive/folders/{fid}' target='_blank'><div style='background:#eff6ff;color:#1e40af;padding:10px;border-radius:8px;text-align:center;font-weight:bold;margin:10px 0;'>📂 Ouvrir dossier Drive</div></a>", unsafe_allow_html=True)
                files = list_drive_files(drive, fid)
                if files:
                    for f in files: st.markdown(f"<div class='file-card'><a href='{f['webViewLink']}' target='_blank'>📄 {f['name']}</a></div>", unsafe_allow_html=True)
                else: st.caption("Dossier vide.")
    with t2:
        if sh:
            c1, c2 = st.columns([3,1]); t = c1.text_input("Tâche"); d = c2.date_input("Date")
            if st.button("Ajouter"): sh.worksheet("Tasks").append_row([str(uuid.uuid4())[:8], subject, t, "À faire", str(d)]); st.rerun()

def focus_room_page():
    st.markdown("### ⏳ Focus Room")
    with st.expander("🎵 Apple Music (Lofi)", expanded=True):
        components.html("""<iframe allow="autoplay *; encrypted-media *;" frameborder="0" height="175" style="width:100%;max-width:660px;overflow:hidden;background:transparent;" sandbox="allow-forms allow-popups allow-same-origin allow-scripts allow-storage-access-by-user-activation allow-top-navigation-by-user-activation" src="https://embed.music.apple.com/fr/playlist/lofi-girl-beats-to-relax-study-to/pl.bf7a3cbca49644d8a33f09c1285aef5c"></iframe>""", height=180)
    
    if not st.session_state.timer_active:
        c1, c2, c3 = st.columns(3)
        sub = c1.selectbox("Matière", DEFAULT_S2)
        dur = c2.number_input("Durée", 5, 120, 25)
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
            st.progress(max(0.0, min(1.0, (st.session_state.timer_duration*60 - rem.total_seconds()) / (st.session_state.timer_duration*60))))
            if st.button("⏹ Stop"): st.session_state.timer_active = False; st.rerun()
            time.sleep(1); st.rerun()
        else:
            check_timer(sh); st.button("Nouveau")

def candidatures_page(sh):
    st.markdown("### 🚀 Suivi Candidatures")
    df = pd.DataFrame()
    if sh:
        try: df = pd.DataFrame(sh.worksheet("Candidatures").get_all_records())
        except: pass
    
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", len(df))
        c2.metric("Entretiens", len(df[df['Statut']=='Entretien']))
        c3.metric("Attente", len(df[df['Statut']=='Envoyé']))
    
    with st.expander("➕ Nouvelle"):
        with st.form("new_c"):
            o = st.text_input("Orga"); t = st.selectbox("Type", ["Stage", "Master"]); s = st.selectbox("Statut", ["Envoyé", "Entretien", "Refus", "Accepté"])
            if st.form_submit_button("Ajouter") and sh:
                sh.worksheet("Candidatures").append_row([str(uuid.uuid4())[:8], o, t, "", str(date.today()), s, "", ""])
                st.success("OK"); st.rerun()
    
    if not df.empty:
        if "Date_Envoi" in df.columns: df["Date_Envoi"] = pd.to_datetime(df["Date_Envoi"], errors="coerce").dt.date
        edited = st.data_editor(df, hide_index=True, use_container_width=True, num_rows="dynamic", key="cand_ed")
        if st.button("💾 Mettre à jour"):
            sh.worksheet("Candidatures").clear()
            sh.worksheet("Candidatures").update([edited.columns.values.tolist()] + edited.astype(str).values.tolist())
            st.success("Maj !"); st.rerun()

def financial_analysis_page(sh):
    st.markdown("### 📊 Analyse Fi")
    with st.sidebar:
        ca = st.number_input("CA", step=1000.0, key="af_ca"); rex = st.number_input("REX", step=1000.0, key="af_rex")
        rn = st.number_input("RN", step=1000.0, key="af_rn"); cp = st.number_input("CP", step=1000.0, key="af_cp")
        dettes = st.number_input("Dettes", step=1000.0, key="af_dettes"); immo = st.number_input("Immo", step=1000.0, key="af_immo")
        ac = st.number_input("Actif Circ.", step=1000.0, key="af_ac"); pc = st.number_input("Passif Circ.", step=1000.0, key="af_pc")
        ta = st.number_input("Treso Actif", step=1000.0, key="af_ta"); tp = st.number_input("Treso Passif", step=1000.0, key="af_tp")
    
    frng = (cp + dettes) - immo; bfr = ac - pc; tn = frng - bfr
    roe = (rn/cp*100) if cp>0 else 0; levier = dettes/cp if cp>0 else 0
    
    c1, c2, c3 = st.columns(3)
    c1.metric("FRNG", f"{frng:,.0f}", delta="OK" if frng>0 else "KO"); c2.metric("BFR", f"{bfr:,.0f}"); c3.metric("TN", f"{tn:,.0f}", delta="OK" if tn>0 else "KO")
    st.metric("Levier", f"{levier:.2f}", delta="OK" if levier<1 else "Danger", delta_color="inverse")
    
    nom = st.text_input("Nom analyse")
    c_s, c_p = st.columns(2)
    if c_s.button("Sauvegarder") and sh and nom:
        data = {"ca":ca, "rex":rex, "rn":rn, "cp":cp, "dettes":dettes, "immo":immo, "ac":ac, "pc":pc, "ta":ta, "tp":tp}
        save_to_history(sh, "AnalyseFi_Data", nom, json.dumps(data)); st.success("OK")
    
    if c_p.button("PDF"):
        full_data = {"nom":nom or "Analyse", "frng":frng, "bfr":bfr, "tn":tn, "marge":0, "roe":roe, "roce":0, "levier":levier, "autonomie":0, "ca":ca}
        st.download_button("Télécharger", create_financial_pdf(full_data), "analyse.pdf", "application/pdf")

# ==============================================================================
# 4. ROUTEUR
# ==============================================================================
if __name__ == "__main__":
    sh, drive = get_google_services()
    check_timer(sh)
    page = sidebar_menu()
    
    if page != st.session_state.current_view: st.session_state.current_view = page; st.session_state.selected_subject = None; st.rerun()

    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours":
        if st.session_state.selected_subject: subject_detail_page(sh, drive, st.session_state.selected_subject)
        else: courses_grid_page()
    elif st.session_state.current_view == "Candidatures": candidatures_page(sh)
    elif st.session_state.current_view == "Analyse Fi": financial_analysis_page(sh)
    elif st.session_state.current_view == "Focus Room": focus_room_page()
