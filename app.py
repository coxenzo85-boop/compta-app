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

# 🔗 TON LIEN EMPLOI DU TEMPS (NANTES)
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

    [data-testid="stSidebar"] {{
        background-color: {NAVY};
    }}
    [data-testid="stSidebar"] h1 {{
        color: white !important;
    }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{
        color: #cbd5e1 !important;
    }}

    .kpi-card {{
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        border-left: 5px solid {NAVY};
        transition: transform 0.2s;
    }}
    .kpi-card:hover {{
        transform: translateY(-5px);
    }}
    
    .stButton>button {{
        background-color: {TEAL};
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: bold;
        transition: all 0.3s;
    }}
    .stButton>button:hover {{
        background-color: {NAVY};
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }}

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

# --- CONNEXION GOOGLE (AVEC CACHE 🧠) ---
@st.cache_resource 
def get_db_connection():
    try:
        if "gcp_service_account" not in st.secrets:
            return None
            
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("L3_Compta_Database")
        return sheet
    except Exception as e:
        print(f"Erreur DB: {e}") 
        return None

# --- CALENDAR ENGINE ---
@st.cache_data(ttl=3600, show_spinner=False) 
def get_ics_events_cached(ics_url):
    ics_events = []
    try:
        response = requests.get(ics_url, timeout=10)
        if response.status_code == 200:
            cal = Calendar.from_ical(response.content)
            for component in cal.walk('vevent'):
                start = component.get('dtstart').dt
                end = component.get('dtend').dt
                
                raw_summary = component.get('summary')
                summary = str(raw_summary) if raw_summary else "Cours"
                
                start_str = start.isoformat() if hasattr(start, 'isoformat') else str(start)
                end_str = end.isoformat() if hasattr(end, 'isoformat') else str(end)

                ics_events.append({
                    "title": summary,
                    "start": start_str,
                    "end": end_str,
                    "backgroundColor": TEAL,
                    "borderColor": NAVY
                })
    except Exception as e:
        print(f"Erreur ICS: {e}")
    return ics_events

def get_combined_events(ics_url, sh):
    final_events = get_ics_events_cached(ics_url)
    if sh:
        try:
            ws_ev = sh.worksheet("Events")
            rows = ws_ev.get_all_records()
            for r in rows:
                final_events.append({
                    "title": f"📚 {r['Title']}", 
                    "start": r['Start'],
                    "end": r['End'],
                    "backgroundColor": ORANGE_REV,
                    "borderColor": GOLD
                })
        except:
            pass
    return final_events

# --- IA LOGIC ---
def extract_text(files):
    text = ""
    for f in files:
        try:
            if f.type == "application/pdf":
                text += PdfReader(f).pages[0].extract_text() + "\n"
            elif "word" in f.type:
                doc = Document(f)
                for p in doc.paragraphs: text += p.text + "\n"
        except: pass
    return text

def get_gemini_response(prompt, context):
    try:
        api_key = st.secrets["gemini"]["api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        full_prompt = f"Tu es expert L3 Compta. Contexte: {context}. Question: {prompt}"
        return model.generate_content(full_prompt).text
    except Exception as e:
        return f"Erreur IA: {e}"

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
            options=["Dashboard"] + SUBJECTS,
            icons=["speedometer2"] + [SUBJECTS_CONFIG[s]["icon"] for s in SUBJECTS],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": NAVY},
                "icon": {"color": "#94a3b8", "font-size": "14px"}, 
                "nav-link": {"font-size": "14px", "text-align": "left", "margin":"0px", "color": "#e2e8f0"},
                "nav-link-selected": {"background-color": TEAL, "color": "white", "font-weight": "bold"},
            }
        )
        
        st.markdown("---")
        st.markdown(f"<p style='text-align:center; color:{GOLD}; font-size:12px; font-weight:bold;'>FOCUS ZONE</p>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if c1.button("▶ 25m"):
            st.session_state.pomodoro = time.time()
        if c2.button("⏹ Stop"):
            st.session_state.pomodoro = None
        
        if st.session_state.get("pomodoro"):
            elapsed = time.time() - st.session_state.pomodoro
            left = 25*60 - elapsed
            if left > 0:
                mins, secs = divmod(left, 60)
                st.markdown(f"<h1 style='text-align:center; color:white;'>{int(mins):02}:{int(secs):02}</h1>", unsafe_allow_html=True)

    return selected

# --- PAGES ---
def dashboard_page(sh):
    st.markdown(f"### 👋 Bonjour, voici ton état des lieux")
    st.markdown(f"<p style='color:#64748b;'>Semestre 2 • {datetime.now().strftime('%d %B %Y')}</p>", unsafe_allow_html=True)
    st.write("")
    
    if not sh:
        st.warning("⚠️ Connexion BDD inactive. Recharge la page si cela persiste.")

    gpa = 0.0
    urgent_tasks = 0
    
    if sh:
        try:
            ws_g = sh.worksheet("Grades")
            ws_t = sh.worksheet("Tasks")
            grades = ws_g.get_all_records()
            tasks = ws_t.get_all_records()
            
            df_grades = pd.DataFrame(grades)
            if not df_grades.empty:
                df_grades['Grade'] = pd.to_numeric(df_grades['Grade'], errors='coerce')
                df_grades['Coefficient'] = pd.to_numeric(df_grades['Coefficient'], errors='coerce')
                df_grades.dropna(inplace=True)
                total_p = (df_grades['Grade'] * df_grades['Coefficient']).sum()
                total_c = df_grades['Coefficient'].sum()
                gpa = round(total_p / total_c, 2) if total_c > 0 else 0
            
            urgent_tasks = len([t for t in tasks if t['Status'] == 'À faire'])
        except: pass

    c1, c2, c3 = st.columns(3)
    with c1: kpi_card("Moyenne Générale", f"{gpa}/20", "📈 +0.5 pts vs S1", NAVY, "🎓")
    with c2: kpi_card("Tâches Urgentes", str(urgent_tasks), "🔥 Keep pushing", TEAL, "⚡")
    with c3: kpi_card("Semaine", f"S{datetime.now().isocalendar()[1]}", "🗓 Année Univ.", GOLD, "📅")

    st.write("")
    st.write("")

    c_left, c_right = st.columns([2, 1])

    # --- PARTIE CALENDRIER ---
    with c_left:
        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        
        events = get_combined_events(ICS_CALENDAR_URL, sh)
        
        calendar_options = {
            "headerToolbar": {"left": "today prev,next", "center": "title", "right": "timeGridWeek,dayGridMonth,listWeek"},
            "initialView": "timeGridWeek",
            "slotMinTime": "08:00:00",
            "slotMaxTime": "21:00:00",
            "height": "550px",
            "allDaySlot": False,
            "locale": "fr",
        }
        
        calendar(events=events, options=calendar_options, custom_css=".fc-event { border-radius: 4px; font-size: 11px; }")
        
        if sh:
            # AJOUT
            with st.expander("➕ Ajouter une session de révision"):
                with st.form("add_event"):
                    ev_title = st.text_input("Matière / Titre")
                    c_d, c_h1, c_h2 = st.columns(3)
                    ev_date = c_d.date_input("Date", date.today())
                    ev_start = c_h1.time_input("Début", dt_time(18, 0))
                    ev_end = c_h2.time_input("Fin", dt_time(19, 0))
                    
                    if st.form_submit_button("Ajouter"):
                        try:
                            start_iso = datetime.combine(ev_date, ev_start).isoformat()
                            end_iso = datetime.combine(ev_date, ev_end).isoformat()
                            ws_ev = sh.worksheet("Events")
                            ws_ev.append_row([str(uuid.uuid4())[:8], ev_title, start_iso, end_iso, "Revision"])
                            st.success("Ajouté !")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur : {e}")

            # SUPPRESSION (CORRIGÉE !)
            with st.expander("🗑️ Gérer / Supprimer mes événements"):
                try:
                    ws_ev = sh.worksheet("Events")
                    rows = ws_ev.get_all_records()
                    df_ev = pd.DataFrame(rows)
                    
                    if not df_ev.empty:
                        for i, row in df_ev.iterrows():
                            c_titre, c_btn = st.columns([4, 1])
                            
                            try:
                                d_start = datetime.fromisoformat(row['Start'])
                                date_str = d_start.strftime("%d/%m à %H:%M")
                            except: date_str = row['Start']
                                
                            c_titre.markdown(f"**{row['Title']}** <span style='font-size:12px; color:grey'>({date_str})</span>", unsafe_allow_html=True)
                            
                            if c_btn.button("❌", key=f"del_ev_{row['ID']}"):
                                try:
                                    target_id = str(row['ID']).strip()
                                    all_ids = ws_ev.col_values(1)
                                    row_to_del = -1
                                    for idx, val in enumerate(all_ids):
                                        if str(val).strip() == target_id:
                                            row_to_del = idx + 1
                                            break
                                    if row_to_del != -1:
                                        ws_ev.delete_rows(row_to_del)
                                        st.success("Supprimé !")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Introuvable.")
                                except Exception as e:
                                    st.error(f"Erreur : {e}")
                            st.divider()
                    else:
                        st.info("Aucun événement personnel.")
                except Exception as e: # <--- LE CORRECTIF EST ICI (On ignore les erreurs de rerun)
                    # On affiche l'erreur seulement si ce n'est pas un rechargement
                    if "rerun" not in str(e).lower():
                         st.warning("Chargement...")

    # --- PARTIE TO-DO ---
    with c_right:
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do Urgent</span>", unsafe_allow_html=True)
        if sh and urgent_tasks > 0:
            df_t = pd.DataFrame(tasks)
            todo = df_t[df_t['Status'] == 'À faire'].head(4)
            for i, row in todo.iterrows():
                with st.container(border=True):
                    c_check, c_txt = st.columns([1, 4])
                    if c_check.button("✔", key=f"done_{row['ID']}"):
                        cell = ws_t.find(row['ID'])
                        ws_t.update_cell(cell.row, 4, "Fait")
                        st.rerun()
                    c_txt.markdown(f"**{row['Task']}**<br><span style='font-size:12px; color:grey'>{row['Subject']}</span>", unsafe_allow_html=True)
        else:
            if not sh:
                st.info("Reconnecte la BDD pour voir les tâches.")
            else:
                st.info("Aucune tâche urgente ! 🎉")

def subject_page(sh, subject):
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
        st.markdown("**📂 Documents du cours**")
        files = st.file_uploader("PDF/Word", accept_multiple_files=True, key=subject)
        context = ""
        if files: 
            context = extract_text(files)
            st.success(f"{len(files)} fichiers chargés")

    # TAB 1: IA
    with tab1:
        st.caption("Pose tes questions à l'expert. Basé sur tes documents.")
        if "msgs" not in st.session_state: st.session_state.msgs = {}
        if subject not in st.session_state.msgs: st.session_state.msgs[subject] = []

        for m in st.session_state.msgs[subject]:
            with st.chat_message(m["role"]): st.markdown(m["content"])
        
        if prompt := st.chat_input("Ex: Résume le chapitre 2..."):
            st.session_state.msgs[subject].append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            with st.chat_message("assistant"):
                resp = get_gemini_response(prompt, context) if context else "⚠️ Upload un cours d'abord."
                st.markdown(resp)
            st.session_state.msgs[subject].append({"role": "assistant", "content": resp})

    # TAB 2: NOTES
    with tab2:
        c1, c2 = st.columns([1, 2])
        if sh:
            ws_g = sh.worksheet("Grades")
            
            with c1:
                with st.form("add_n"):
                    st.write("**Ajouter une note**")
                    note = st.number_input("Note /20", 0.0, 20.0, step=0.5)
                    coef = st.number_input("Coef", 0.0, 10.0, value=1.0)
                    type_eval = st.selectbox("Type", ["CC", "Partiel", "Examen"])
                    if st.form_submit_button("Enregistrer"):
                        ws_g.append_row([str(uuid.uuid4())[:8], subject, note, coef, type_eval])
                        st.success("Sauvegardé !")
                        time.sleep(1)
                        st.rerun()
            
            # LISTE DES NOTES
            with c2:
                raw_data = ws_g.get_all_values()
                if len(raw_data) > 1:
                    header = raw_data[0]
                    rows = raw_data[1:]
                    df = pd.DataFrame(rows, columns=header)
                    df['real_row_index'] = [i + 2 for i in range(len(rows))]
                    df_sub = df[df['Subject'] == subject]
                    
                    if not df_sub.empty:
                        st.markdown("##### 📄 Mes notes")
                        for i, row in df_sub.iterrows():
                            with st.container(border=True):
                                col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 1])
                                col_a.markdown(f"**{row['Grade']}/20**")
                                col_b.caption(f"Coef {row['Coefficient']}")
                                col_c.caption(row['Type'])
                                
                                if col_d.button("❌", key=f"del_{row['ID']}"):
                                    try:
                                        row_num = int(row['real_row_index'])
                                        ws_g.delete_rows(row_num)
                                        st.success("✅ Supprimé !")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Erreur : {e}")
                    else:
                        st.info("Aucune note pour cette matière.")
                else:
                    st.info("Tableau vide.")

    # TAB 3: TACHES
    with tab3:
        if sh:
            ws_t = sh.worksheet("Tasks")
            col_in, col_btn = st.columns([3, 1])
            new_t = col_in.text_input("Nouvelle tâche", key=f"t_{subject}")
            if col_btn.button("Ajouter", key=f"b_{subject}"):
                ws_t.append_row([str(uuid.uuid4())[:8], subject, new_t, "À faire", ""])
                st.rerun()
            
            recs = ws_t.get_all_records()
            df = pd.DataFrame(recs)
            if not df.empty:
                df = df[(df['Subject'] == subject) & (df['Status'] == 'À faire')]
                for i, r in df.iterrows():
                    if st.checkbox(r['Task'], key=f"chk_{r['ID']}"):
                        cell = ws_t.find(r['ID'])
                        ws_t.update_cell(cell.row, 4, "Fait")
                        st.rerun()

# --- MAIN ---
if __name__ == "__main__":
    sh = get_db_connection()
    page = sidebar_menu()
    
    if page == "Dashboard":
        dashboard_page(sh)
    else:
        subject_page(sh, page)
