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
# 1. CONFIGURATION & ÉTAT
# ==============================================================================
st.set_page_config(page_title="L3 CCA Hub", page_icon="🎓", layout="wide")

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
                        "start": c.get('dtstart').dt, 
                        "end": c.get('dtend').dt,
                        "iso_start": c.get('dtstart').dt.isoformat() if hasattr(c.get('dtstart').dt, 'isoformat') else str(c.get('dtstart').dt),
                        "iso_end": c.get('dtend').dt.isoformat() if hasattr(c.get('dtend').dt, 'isoformat') else str(c.get('dtend').dt),
                        "backgroundColor": TEAL, "borderColor": NAVY
                    })
    except: pass
    return events

def get_combined_events(ics_url, sh):
    return get_ics_events_cached(ics_url)

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

def check_timer(sh):
    if st.session_state.timer_active and st.session_state.timer_end_time:
        if datetime.now() >= st.session_state.timer_end_time:
            st.session_state.timer_active = False
            st.session_state.timer_end_time = None
            if sh: save_to_history(sh, "Pomodoro", st.session_state.timer_subject, st.session_state.timer_duration)
            st.toast("Session terminée ! 🎉", icon="✅")

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
    # CSS
    st.markdown(f"""
    <style>
    .dashboard-card {{ background-color: white; border-radius: 20px; padding: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid #E2E8F0; height: 100%; transition: transform 0.2s ease; }}
    .dashboard-card:hover {{ transform: translateY(-2px); }}
    .card-label {{ font-family: 'Lato', sans-serif; font-size: 11px; font-weight: 700; text-transform: uppercase; color: #94A3B8; margin-bottom: 8px; }}
    .card-value {{ font-family: 'Libre Baskerville', serif; font-size: 32px; color: {NAVY}; font-weight: 700; margin-bottom: 16px; }}
    .card-footer {{ font-size: 13px; font-weight: 600; color: {TEAL}; display: flex; align-items: center; gap: 6px; }}
    .exam-row {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #F1F5F9; }}
    .exam-tag {{ padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; color: white; }}
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"### 👋 Dashboard • {date.today().strftime('%d %B')}")

    df_sim = pd.DataFrame()
    s1_avg_display = "0.00/20"
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

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
        <div class="dashboard-card">
            <div style="display:flex; justify-content:space-between;">
                <div><div class="card-label">MOYENNE GÉNÉRALE S1</div><div class="card-value">{s1_avg_display}</div></div>
                <div style="background:#F1F5F9; width:40px; height:40px; border-radius:50%; display:flex; align-items:center; justify-content:center;">🎓</div>
            </div>
            <div class="card-footer"><span style="background:#DCFCE7; color:#166534; padding:2px 8px; border-radius:6px; font-size:11px;">Simulateur actif</span></div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🧮 Ouvrir Simulateur", key="btn_sim", use_container_width=True):
            st.session_state.show_simulator = not st.session_state.show_simulator; st.rerun()

    with c2:
        status_txt = "Session en cours..." if st.session_state.timer_active else "Prêt à bosser ?"
        status_icon = "🔥" if st.session_state.timer_active else "⏳"
        st.markdown(f"""
        <div class="dashboard-card" style="border-left: 8px solid {GOLD};">
            <div style="display:flex; justify-content:space-between;">
                <div><div class="card-label">FOCUS ROOM</div><div class="card-value">{status_txt}</div></div>
                <div style="background:#FEF3C7; width:40px; height:40px; border-radius:50%; display:flex; align-items:center; justify-content:center;">{status_icon}</div>
            </div>
            <div class="card-footer" style="color:{GOLD};">Productivité Maximale</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🚀 Accéder à la Focus Room", key="btn_focus", use_container_width=True):
            st.session_state.current_view = "Focus Room"; st.rerun()

    if st.session_state.show_simulator and sh:
        st.write(""); st.info("Modifie tes notes ici. Le calcul se met à jour après sauvegarde.")
        try:
            tab1, tab2 = st.tabs(["S1", "S2"])
            cfg = {"Matiere": st.column_config.TextColumn(disabled=True), "Semestre": None}
            
            # Fonction pour afficher le tableau AVEC COULEURS
            def show_sim_table(df_semestre, key_s):
                edited_df = st.data_editor(df_semestre, column_config=cfg, hide_index=True, key=f"ed_{key_s}", use_container_width=True)
                
                # Calcul en direct pour affichage
                total_c = edited_df['Coef_CC'] + edited_df['Coef_Partiel']
                edited_df['Moyenne'] = ((edited_df['Note_CC'] * edited_df['Coef_CC']) + (edited_df['Note_Partiel'] * edited_df['Coef_Partiel'])) / total_c.replace(0, 1)
                edited_df.loc[total_c == 0, 'Moyenne'] = 0
                
                st.write("**Résultats :**")
                # LE RETOUR DU DÉGRADÉ DE COULEURS
                st.dataframe(
                    edited_df[['Matiere', 'Moyenne']].style.format({"Moyenne": "{:.2f}"}).background_gradient(subset=['Moyenne'], cmap="RdYlGn", vmin=0, vmax=20),
                    use_container_width=True
                )
                return edited_df

            with tab1: e1 = show_sim_table(df_sim[df_sim['Semestre']=='S1'], "s1")
            with tab2: e2 = show_sim_table(df_sim[df_sim['Semestre']=='S2'], "s2")
            
            if st.button("💾 Sauvegarder"):
                # On nettoie la colonne Moyenne avant sauvegarde
                clean_s1 = e1.drop(columns=['Moyenne'], errors='ignore')
                clean_s2 = e2.drop(columns=['Moyenne'], errors='ignore')
                full = pd.concat([clean_s1, clean_s2])
                sh.worksheet("Simulateur").update([full.columns.values.tolist()] + full.values.tolist())
                st.success("Sauvegardé !"); time.sleep(1); st.rerun()
        except Exception as e: st.error(f"Erreur Simulateur: {e}")

    st.write("")
    cl, cr = st.columns([2, 1])
    
    with cl:
        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        evs = get_ics_events_cached(ICS_CALENDAR_URL)
        cal_evs = [{"title": e['title'], "start": e['iso_start'], "end": e['iso_end'], "backgroundColor": TEAL} for e in evs]
        calendar(events=cal_evs, options={"initialView": "timeGridWeek", "height": "500px", "locale": "fr"}, custom_css=".fc-event{font-size:10px;}")

    with cr:
        st.markdown(f"#### <span style='color:{NAVY}'>⏳ Examens</span>", unsafe_allow_html=True)
        html_exams = ""
        if sh:
            df_ex = get_exams(sh)
            with st.expander("Gérer"):
                edited_exams = st.data_editor(df_ex, num_rows="dynamic", hide_index=True, key="ex_edit")
                if not df_ex.equals(edited_exams): save_exams(sh, edited_exams); st.rerun()
            
            today = date.today()
            if not edited_exams.empty:
                try:
                    edited_exams['DateObj'] = pd.to_datetime(edited_exams['Date']).dt.date
                    edited_exams = edited_exams.sort_values('DateObj')
                    html_content = "<div style='background:white; border-radius:12px; border:1px solid #E2E8F0; padding:0 15px;'>"
                    count = 0
                    for _, row in edited_exams.iterrows():
                        delta = (row['DateObj'] - today).days
                        if delta >= 0 and count < 5:
                            col = RED_URGENT if delta < 7 else ORANGE_REV if delta < 14 else TEAL
                            html_content += f"""
                            <div class="exam-row">
                                <span style="font-weight:bold; color:{NAVY}; font-size:13px;">{row['Matiere']}</span>
                                <span class="exam-tag" style="background:{col};">J-{delta}</span>
                            </div>
                            """
                            count += 1
                    html_content += "</div>"
                    if count > 0: st.markdown(html_content, unsafe_allow_html=True)
                    else: st.info("Aucun examen proche.")
                except: st.error("Erreur date exams")
            else: st.info("Ajoute des examens !")

        st.write(""); st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do</span>", unsafe_allow_html=True)
        if sh:
            ws_t = sh.worksheet("Tasks")
            tasks = pd.DataFrame(ws_t.get_all_records())
            todo = tasks[tasks['Status'] == 'À faire'] if not tasks.empty else pd.DataFrame()
            if not todo.empty:
                for i, r in todo.head(4).iterrows():
                    c_chk, c_txt = st.columns([1, 5])
                    if c_chk.button("✔", key=f"d_{r['ID']}"):
                        ws_t.update_cell(ws_t.find(r['ID']).row, 4, "Fait"); save_to_history(sh, "Task", r['Subject'], 1); st.rerun()
                    c_txt.caption(f"{r['Task']} ({r['Subject']})")
            else: st.success("Tout est fait ! 🎉")

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
                st.markdown(f"<div style='background:white;padding:15px;border-radius:10px;border-left:5px solid {NAVY};margin-bottom:10px; box-shadow:0 2px 5px rgba(0,0,0,0.05);'><b>{s}</b></div>", unsafe_allow_html=True)
                if st.button(f"Ouvrir", key=s, use_container_width=True): st.session_state.selected_subject = s; st.rerun()

def focus_page(sh):
    st.markdown("### ⏳ Focus Room")
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
            st.markdown(f"""
            <div style="text-align:center; padding:20px; background:white; border-radius:15px; border:2px solid {GOLD}; margin-bottom:20px;">
                <h3 style="color:{NAVY}; margin:0;">FOCUS EN COURS • {st.session_state.timer_subject}</h3>
                <h1 style="font-size:80px; margin:10px 0; color:{NAVY}; font-family:monospace;">{mins:02}:{secs:02}</h1>
            </div>
            """, unsafe_allow_html=True)
            st.progress(max(0.0, min(1.0, (st.session_state.timer_duration*60 - rem.total_seconds()) / (st.session_state.timer_duration*60))))
            if st.button("⏹ Abandonner"): st.session_state.timer_active = False; st.rerun()
            time.sleep(1); st.rerun()
        else:
            check_timer(sh)
            if st.button("Nouvelle Session"): st.rerun()

def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        opts = ["Dashboard", "Mes Cours", "Focus Room"]
        try: idx = opts.index(st.session_state.current_view)
        except: idx = 0
        sel = option_menu(None, opts, icons=["speedometer2", "book", "hourglass"], default_index=idx, 
                          styles={"container": {"background-color": NAVY}, "nav-link-selected": {"background-color": TEAL}})
        
        if st.session_state.timer_active and st.session_state.timer_end_time:
            rem = st.session_state.timer_end_time - datetime.now()
            if rem.total_seconds() > 0:
                mins, secs = divmod(int(rem.total_seconds()), 60)
                st.markdown("---")
                st.metric("Focus en cours", f"{mins:02}:{secs:02}")
            else: st.rerun()
    return sel

# ==============================================================================
# 4. EXÉCUTION
# ==============================================================================
if __name__ == "__main__":
    sh, drive = get_google_services()
    check_timer(sh)
    page = sidebar_menu()
    if page != st.session_state.current_view: 
        st.session_state.current_view = page
        st.session_state.selected_subject = None
        st.rerun()

    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours": courses_page(sh, drive)
    elif st.session_state.current_view == "Focus Room": focus_page(sh)
