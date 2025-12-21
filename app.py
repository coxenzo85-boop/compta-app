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

# ==============================================================================
# 1. CONFIGURATION & ÉTAT (CRUCIAL : EN PREMIER)
# ==============================================================================
st.set_page_config(page_title="L3 CCA Dashboard", page_icon="🎓", layout="wide")

# Initialisation de la mémoire (Session State)
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False
if 'timer_active' not in st.session_state: st.session_state.timer_active = False
if 'timer_end_time' not in st.session_state: st.session_state.timer_end_time = None
if 'timer_subject' not in st.session_state: st.session_state.timer_subject = "Général"
if 'timer_duration' not in st.session_state: st.session_state.timer_duration = 25

# Constantes
ICS_CALENDAR_URL = "http://edt-v2.univ-nantes.fr/calendar/ics?timetables[0]=110228"
NAVY, TEAL, GOLD, CLOUD, ORANGE_REV = "#1A2C42", "#008080", "#C5A059", "#F4F6F7", "#ea580c"

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

# CSS Global
st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Libre+Baskerville:wght@400;700&family=Lato:wght@300;400;700&display=swap');
    html, body, [class*="css"] {{ font-family: 'Lato', sans-serif; background-color: {CLOUD}; color: {NAVY}; }}
    h1, h2, h3 {{ font-family: 'Libre Baskerville', serif; color: {NAVY}; }}
    
    /* Sidebar Fix (Coins Blancs) */
    [data-testid="stSidebar"] {{ background-color: {NAVY}; }}
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{ color: white !important; }}
    
    /* KPI Cards */
    .kpi-card {{ background-color: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); border-left: 5px solid {NAVY}; height: 100%; }}
    
    /* Boutons */
    .stButton>button {{ background-color: {TEAL}; color: white; border-radius: 8px; border: none; font-weight: bold; transition: all 0.2s; }}
    .stButton>button:hover {{ background-color: {NAVY}; }}
    
    /* Timer Display */
    .timer-display {{ font-size: 60px; font-weight: bold; color: {NAVY}; text-align: center; font-family: monospace; background: white; border-radius: 15px; border: 3px solid {GOLD}; padding: 10px; margin: 10px 0; }}
    
    /* File Card */
    .file-card {{ background: white; padding: 10px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center; }}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 2. FONCTIONS BACKEND
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
                        "start": c.get('dtstart').dt.isoformat(), 
                        "end": c.get('dtend').dt.isoformat(),
                        "backgroundColor": TEAL, "borderColor": NAVY
                    })
    except: pass
    return events

# La fameuse fonction qui fusionne ICS et Events Perso
def get_combined_events(ics_url, sh):
    events = get_ics_events_cached(ics_url)
    if sh:
        try:
            # Récupérer les événements perso (Table 'Events' du GSheet)
            recs = sh.worksheet("Events").get_all_records()
            for r in recs:
                events.append({
                    "title": f"📚 {r['Title']}", 
                    "start": r['Start'], 
                    "end": r['End'],
                    "backgroundColor": ORANGE_REV,  # Orange pour tes révisions
                    "borderColor": GOLD
                })
        except: pass
    return events

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

# ==============================================================================
# 3. PAGES
# ==============================================================================

def dashboard_page(sh):
    st.markdown(f"### 👋 Dashboard • {date.today().strftime('%d %B')}")

    # Calcul Moyenne
    s1_avg_display = "0.0/20"
    df_sim = pd.DataFrame()
    if sh:
        try:
            df_sim = load_simulator_data(sh)
            if not df_sim.empty:
                s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
                total_coef = s1['Coef_CC'] + s1['Coef_Partiel']
                s1['Moy'] = ((s1['Note_CC']*s1['Coef_CC']) + (s1['Note_Partiel']*s1['Coef_Partiel'])) / total_coef.replace(0, 1)
                valid = total_coef > 0
                if valid.any(): s1_avg_display = f"{s1.loc[valid, 'Moy'].mean():.2f}/20"
        except: pass

    # KPI
    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Moyenne S1", s1_avg_display, "Basé sur le simulateur", NAVY, "🎓")
        if st.button("🧮 Ouvrir Simulateur", use_container_width=True):
            st.session_state.show_simulator = not st.session_state.show_simulator; st.rerun()
    with c2:
        ftxt = "🔥 Session active" if st.session_state.timer_active else "Prêt à bosser ?"
        kpi_card("Focus Room", ftxt, "Productivité", GOLD, "⏳")
        if st.button("🚀 Go Focus", use_container_width=True): 
            st.session_state.current_view = "Focus Room"; st.rerun()

    # SIMULATEUR
    if st.session_state.show_simulator and sh:
        st.write(""); st.info("Modifie tes notes ici.")
        try:
            tab1, tab2 = st.tabs(["S1", "S2"])
            cfg = {"Matiere": st.column_config.TextColumn(disabled=True), "Semestre": None}
            
            def show_sim_table(df_sem, k):
                edited = st.data_editor(df_sem, column_config=cfg, hide_index=True, key=k, use_container_width=True)
                total = edited['Coef_CC'] + edited['Coef_Partiel']
                edited['Moyenne'] = ((edited['Note_CC']*edited['Coef_CC']) + (edited['Note_Partiel']*edited['Coef_Partiel'])) / total.replace(0,1)
                edited.loc[total==0, 'Moyenne'] = 0
                st.write("**Résultats :**")
                st.dataframe(edited[['Matiere', 'Moyenne']].style.format({"Moyenne": "{:.2f}"}).background_gradient(subset=['Moyenne'], cmap="RdYlGn", vmin=0, vmax=20), use_container_width=True)
                return edited

            with tab1: e1 = show_sim_table(df_sim[df_sim['Semestre']=='S1'], "e1")
            with tab2: e2 = show_sim_table(df_sim[df_sim['Semestre']=='S2'], "e2")
            
            if st.button("💾 Sauvegarder"):
                full = pd.concat([e1.drop(columns=['Moyenne']), e2.drop(columns=['Moyenne'])])
                save_simulator_data(sh, full)
                st.success("Sauvegardé !"); time.sleep(1); st.rerun()
        except Exception as e: st.error(f"Erreur Simulateur: {e}")

    st.write("")
    cl, cr = st.columns([2, 1])
    
    with cl:
        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        events = get_combined_events(ICS_CALENDAR_URL, sh)
        calendar(events=events, options={"headerToolbar": {"left": "today prev,next", "center": "title", "right": "timeGridWeek,dayGridMonth"}, "initialView": "timeGridWeek", "height": "500px", "locale": "fr"}, custom_css=".fc-event{font-size:10px;}")
        
        # --- AJOUTER UNE SÉANCE (ALIGNEMENT CORRIGÉ) ---
        if sh:
            with st.expander("➕ Ajouter une session de révision"):
                with st.form("add_event_form"):
                    # On utilise des colonnes POUR aligner les champs horizontalement
                    c_titre, c_date, c_deb, c_fin = st.columns([2, 1, 1, 1])
                    with c_titre: 
                        ev_title = st.text_input("Titre")
                    with c_date:
                        ev_date = st.date_input("Date")
                    with c_deb:
                        ev_start = st.time_input("Début", dt_time(18,0))
                    with c_fin:
                        ev_end = st.time_input("Fin", dt_time(19,0))
                    
                    if st.form_submit_button("Ajouter"):
                        try:
                            start = datetime.combine(ev_date, ev_start).isoformat()
                            end = datetime.combine(ev_date, ev_end).isoformat()
                            # Ajout dans Google Sheet 'Events'
                            sh.worksheet("Events").append_row([str(uuid.uuid4())[:8], ev_title, start, end, "Revision"])
                            st.success("Ajouté !")
                            time.sleep(1); st.rerun()
                        except: st.error("Erreur ajout (Vérifie l'onglet 'Events')")

            with st.expander("🗑️ Supprimer un événement perso"):
                try:
                    df_ev = pd.DataFrame(sh.worksheet("Events").get_all_records())
                    if not df_ev.empty:
                        for i, row in df_ev.iterrows():
                            c1, c2 = st.columns([4,1])
                            c1.markdown(f"**{row['Title']}** ({row['Start']})")
                            if c2.button("Suppr.", key=f"del_{row['ID']}"):
                                try:
                                    ids = sh.worksheet("Events").col_values(1)
                                    sh.worksheet("Events").delete_rows(ids.index(str(row['ID'])) + 1)
                                    st.rerun()
                                except: pass
                    else: st.info("Aucun événement perso.")
                except: pass

    with cr:
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do</span>", unsafe_allow_html=True)
        if sh:
            try:
                tasks = pd.DataFrame(sh.worksheet("Tasks").get_all_records())
                todo = tasks[tasks['Status'] == 'À faire'] if not tasks.empty else pd.DataFrame()
                if not todo.empty:
                    for i, r in todo.head(4).iterrows():
                        with st.container(border=True):
                            c_chk, c_txt = st.columns([1, 4])
                            if c_chk.button("✔", key=f"d_{r['ID']}"):
                                ws_t = sh.worksheet("Tasks")
                                ws_t.update_cell(ws_t.find(r['ID']).row, 4, "Fait"); st.rerun()
                            c_txt.markdown(f"**{r['Task']}**<br><span style='color:grey; font-size:11px'>{r['Subject']}</span>", unsafe_allow_html=True)
                else: st.success("Tout est fait ! 🎉")
            except: st.info("Aucune tâche.")

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
    tab1, tab2 = st.tabs(["📂 Fichiers & IA", "✅ Tâches"])
    with tab1:
        with st.container(border=True):
            c1, c2, c3 = st.columns([0.5, 3, 1.5])
            c1.markdown("## 🧠")
            c2.markdown("**Booster NotebookLM**\n\nAccède au carnet de notes.")
            c3.link_button("↗ Ouvrir", NOTEBOOK_LINKS.get(subject, "https://notebooklm.google.com/"), type="primary")
        
        if drive:
            fid = get_or_create_subject_folder(drive, subject)
            up = st.file_uploader("Ajouter cours", key="up")
            if up and st.button("Envoyer"): upload_file_to_drive(drive, up, fid); st.success("OK"); st.rerun()
            for f in list_drive_files(drive, fid):
                st.markdown(f"<div class='file-card'><a href='{f['webViewLink']}' target='_blank'>📄 {f['name']}</a></div>", unsafe_allow_html=True)
    with tab2:
        if sh:
            t, d = st.columns([3, 1]); nt = t.text_input("Tâche"); nd = d.date_input("Date")
            if st.button("Ajouter"): sh.worksheet("Tasks").append_row([str(uuid.uuid4())[:8], subject, nt, "À faire", str(nd)]); st.rerun()

def focus_room_page():
    st.markdown(f"### ⏳ Focus Room")
    with st.expander("🎵 Ambiance Lofi (Apple Music)", expanded=True):
        embed_code = """<iframe allow="autoplay *; encrypted-media *; fullscreen *; clipboard-write" frameborder="0" height="175" style="width:100%;max-width:660px;overflow:hidden;background:transparent;" sandbox="allow-forms allow-popups allow-same-origin allow-scripts allow-storage-access-by-user-activation allow-top-navigation-by-user-activation" src="https://embed.music.apple.com/fr/playlist/lofi-girl-beats-to-relax-study-to/pl.bf7a3cbca49644d8a33f09c1285aef5c"></iframe>"""
        components.html(embed_code, height=180)

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
            st.balloons(); st.success("Terminé !"); st.session_state.timer_active = False; st.rerun()

def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        opts = ["Dashboard", "Mes Cours", "Focus Room"]
        try: idx = opts.index(st.session_state.current_view)
        except: idx = 0
        
        # --- FIX CSS POUR MENU (Coins Blancs) ---
        sel = option_menu(None, opts, icons=["speedometer2", "book", "hourglass"], default_index=idx, 
                          styles={
                              "container": {"background-color": NAVY, "border-radius": "0"},
                              "nav-link-selected": {"background-color": TEAL}
                          })
        
        if st.session_state.timer_active and st.session_state.timer_end_time:
            rem = st.session_state.timer_end_time - datetime.now()
            if rem.total_seconds() > 0:
                mins, secs = divmod(int(rem.total_seconds()), 60)
                st.markdown("---")
                st.metric("Focus en cours", f"{mins:02}:{secs:02}")
            else: st.rerun()
    return sel

# --- MAIN ---
if __name__ == "__main__":
    sh, drive = get_google_services()
    page = sidebar_menu()
    if page != st.session_state.current_view: 
        st.session_state.current_view = page
        st.session_state.selected_subject = None
        st.rerun()

    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours":
        if st.session_state.selected_subject: subject_detail_page(sh, drive, st.session_state.selected_subject)
        else: courses_grid_page()
    elif st.session_state.current_view == "Focus Room": focus_room_page()
