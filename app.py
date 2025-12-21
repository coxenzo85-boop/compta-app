import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import datetime, timedelta, date, time as dt_time
import time
from pypdf import PdfReader
from docx import Document
import uuid
from streamlit_option_menu import option_menu
import plotly.express as px
import plotly.graph_objects as go
import requests
from icalendar import Calendar
from streamlit_calendar import calendar

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

# INJECTION CSS (INTERACTIVITÉ TOTALE)
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

    /* --- 1. SIDEBAR INTERACTIVE --- */
    [data-testid="stSidebar"] {{ background-color: {NAVY}; }}
    [data-testid="stSidebar"] h1 {{ color: white !important; }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{ color: #cbd5e1 !important; }}
    
    /* Animation des liens du menu */
    .nav-link {{
        transition: all 0.3s ease !important;
    }}
    .nav-link:hover {{
        background-color: rgba(255, 255, 255, 0.1) !important;
        transform: translateX(8px) !important; /* Décalage vers la droite */
        color: {GOLD} !important;
    }}

    /* --- 2. TABS INTERACTIFS (IA, Notes, Tâches) --- */
    button[data-baseweb="tab"] {{
        transition: all 0.3s ease;
        border-radius: 5px;
        margin: 0 2px;
    }}
    button[data-baseweb="tab"]:hover {{
        background-color: rgba(0, 128, 128, 0.1); /* Teal très clair */
        color: {TEAL};
        font-weight: bold;
        transform: translateY(-2px);
    }}
    /* Onglet actif */
    button[data-baseweb="tab"][aria-selected="true"] {{
        background-color: {TEAL} !important;
        color: white !important;
    }}

    /* --- 3. KPI CARDS (Hover) --- */
    .kpi-card {{
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        border-left: 5px solid {NAVY};
        transition: all 0.3s ease;
        cursor: default;
    }}
    .kpi-card:hover {{
        transform: translateY(-5px) scale(1.02);
        box-shadow: 0 10px 20px rgba(0,0,0,0.15);
        border-left-color: {TEAL};
    }}

    /* --- 4. CARTES DE COURS (Magie Cliquable) --- */
    
    .course-card-bg {{
        background-color: white;
        border-radius: 15px;
        padding: 20px;
        height: 180px; 
        border: 1px solid #e2e8f0;
        border-left: 6px solid {NAVY};
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        position: relative; /* Important pour l'alignement */
        z-index: 0;
    }}

    /* LE BOUTON INVISIBLE MAIS RÉACTIF */
    /* On cible le bouton qui a la classe 'click-cover' (injectée via le hack CSS plus bas) */
    div.stButton > button.click-cover {{
        position: absolute;
        top: -190px;
        left: 0;
        width: 100%;
        height: 200px;
        opacity: 0; /* Invisible par défaut */
        z-index: 2;
        cursor: pointer;
        transition: all 0.3s ease;
        background-color: {TEAL}; /* Couleur de fond au survol */
        border: none;
    }}

    /* L'effet au survol du bouton invisible */
    div.stButton > button.click-cover:hover {{
        opacity: 0.05; /* On le rend légèrement visible (voile coloré) */
        transform: scale(1.03); /* On fait grossir légèrement la zone */
        box-shadow: 0 15px 30px rgba(0,0,0,0.2);
    }}
    
    /* Quand on survole le bouton, on veut que le HTML en dessous semble réagir */
    /* Note: En CSS pur, on ne peut pas affecter le frère précédent (la carte HTML) en survolant le frère suivant (le bouton).
       C'est pourquoi on utilise l'opacity sur le bouton lui-même pour créer le voile coloré. */

    /* Boutons classiques */
    .stButton>button {{
        background-color: {TEAL};
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: bold;
        transition: all 0.3s;
    }}
    .stButton>button:not(.click-cover):hover {{
        background-color: {NAVY};
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        transform: translateY(-2px);
    }}

    /* TIMER */
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
    .timer-label {{
        text-align: center; 
        font-size: 24px; 
        font-weight: bold; 
        color: {TEAL};
        text-transform: uppercase;
        letter-spacing: 2px;
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

# --- CONNEXIONS & UTILS ---
@st.cache_resource 
def get_db_connection():
    try:
        if "gcp_service_account" not in st.secrets: return None
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scope)
        client = gspread.authorize(creds)
        return client.open("L3_Compta_Database")
    except Exception as e:
        print(f"Erreur DB: {e}") 
        return None

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

def extract_text(files):
    text = ""
    for f in files:
        try:
            if f.type == "application/pdf": text += PdfReader(f).pages[0].extract_text() + "\n"
            elif "word" in f.type:
                doc = Document(f)
                for p in doc.paragraphs: text += p.text + "\n"
        except: pass
    return text

def get_gemini_response(prompt, context):
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel('gemini-pro')
        return model.generate_content(f"Expert L3 Compta. Contexte: {context}. Question: {prompt}").text
    except Exception as e: return f"Erreur IA: {e}"

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

# --- NAVIGATION SIDEBAR ---
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

# --- PAGE 2: GRILLE DES COURS (CLIQUABLE + HOVER EFFECT) ---
def courses_grid_page():
    st.markdown(f"### 📚 Mes Modules")
    st.markdown("Accès rapide à tes cours.")
    st.write("")

    cols = st.columns(3)
    
    for index, subject in enumerate(SUBJECTS):
        conf = SUBJECTS_CONFIG[subject]
        col = cols[index % 3]
        
        with col:
            # 1. VISUEL (HTML)
            st.markdown(f"""
            <div class="course-card-bg">
                <div style="display:flex; justify-content:space-between; align-items:start;">
                    <span style="background-color: #f1f5f9; color: {NAVY}; padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase;">{conf['cat']}</span>
                    <div class="icon-box" style="width:30px; height:30px; border-radius:50%; background-color: {CLOUD}; display:flex; align-items:center; justify-content:center; color: {NAVY}; transition: all 0.3s ease;">
                         <i class="bi bi-{conf.get('icon', 'book')}"></i>
                    </div>
                </div>
                <h3 style="margin-top: 25px; font-size: 18px; margin-bottom: 5px; color: {NAVY};">{subject}</h3>
                <div style="height: 4px; width: 40px; background-color: {conf['color']}; border-radius: 2px;"></div>
            </div>
            """, unsafe_allow_html=True)
            
            # 2. BOUTON (Invisible Overlay)
            # On utilise une clé CSS unique pour cibler ce bouton spécifiquement
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True, type="secondary"):
                st.session_state.selected_subject = subject
                st.rerun()
            
            # 3. CSS HACK pour transformer ce bouton en "Cover" (Couverture)
            # On cible le n-ième bouton de la colonne
            st.markdown(f"""
            <style>
            div[data-testid="column"]:nth-child({(index % 3) + 1}) div.stButton > button {{
                /* On applique la classe 'click-cover' manuellement via le style inline */
                position: absolute !important;
                top: -190px !important;
                left: 0 !important;
                width: 100% !important;
                height: 200px !important;
                opacity: 0 !important;
                z-index: 2 !important;
            }}
            div[data-testid="column"]:nth-child({(index % 3) + 1}) div.stButton > button:hover {{
                opacity: 0.05 !important; /* Petit voile au survol */
                background-color: {TEAL} !important;
            }}
            </style>
            """, unsafe_allow_html=True)

# --- PAGE 3: DÉTAIL MATIÈRE ---
def subject_detail_page(sh, subject):
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

    tab1, tab2, tab3 = st.tabs(["🤖 Tuteur IA", "📝 Notes & Simu", "✅ Tâches"])

    with st.sidebar:
        st.markdown("---")
        st.markdown("**📂 Documents**")
        files = st.file_uploader("Drop PDF/Word", accept_multiple_files=True, key=subject)
        context = extract_text(files) if files else ""
        if files: st.success(f"{len(files)} docs chargés")

    with tab1:
        if "msgs" not in st.session_state: st.session_state.msgs = {}
        if subject not in st.session_state.msgs: st.session_state.msgs[subject] = []
        for m in st.session_state.msgs[subject]:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        if p := st.chat_input("Question..."):
            st.session_state.msgs[subject].append({"role": "user", "content": p})
            with st.chat_message("user"): st.markdown(p)
            r = get_gemini_response(p, context) if context else "⚠️ Upload un cours."
            with st.chat_message("assistant"): st.markdown(r)
            st.session_state.msgs[subject].append({"role": "assistant", "content": r})

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

# --- PAGE 4: FOCUS ROOM (POMODORO PRO) ---
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
            # TRAVAIL
            for remaining in range(work_min * 60, -1, -1):
                mins, secs = divmod(remaining, 60)
                with placeholder.container():
                    st.markdown(f"<p class='timer-label'>💻 CYCLE {i+1}/{total_cycles} • FOCUS</p>", unsafe_allow_html=True)
                    st.markdown(f"<div class='timer-display'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
                    st.progress((work_min*60 - remaining) / (work_min*60))
                time.sleep(1)
            
            # PAUSE
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
        
        st.balloons()
        st.success("Session terminée ! Bravo 🎉")

# --- MAIN LOGIC ---
if __name__ == "__main__":
    sh = get_db_connection()
    selected_page = sidebar_menu()
    
    if selected_page != st.session_state.current_view:
        st.session_state.current_view = selected_page
        st.session_state.selected_subject = None
        st.rerun()

    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours":
        if st.session_state.selected_subject: subject_detail_page(sh, st.session_state.selected_subject)
        else: courses_grid_page()
    elif st.session_state.current_view == "Focus Room":
        focus_room_page()
