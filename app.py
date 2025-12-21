import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from datetime import datetime
import time
from pypdf import PdfReader
from docx import Document
import uuid
from streamlit_option_menu import option_menu
import plotly.express as px
import plotly.graph_objects as go

# --- CONFIGURATION PAGE & DESIGN SYSTEM ---
st.set_page_config(page_title="L3 CCA Dashboard", page_icon="🎓", layout="wide")

# PALETTE DE COULEURS DU DESIGN
NAVY = "#1A2C42"
TEAL = "#008080"
GOLD = "#C5A059"
CLOUD = "#F4F6F7"

# INJECTION CSS (Le coeur du design)
st.markdown(f"""
    <style>
    /* Import des polices du design */
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

    /* Sidebar Custom */
    [data-testid="stSidebar"] {{
        background-color: {NAVY};
    }}
    [data-testid="stSidebar"] h1 {{
        color: white !important;
    }}
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {{
        color: #cbd5e1 !important;
    }}

    /* Cards KPI (Simulation du HTML) */
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
    
    /* Boutons Teal & Navy */
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

    /* Onglets stylisés */
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

# --- CONNEXION GOOGLE ---
def get_db_connection():
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials_dict = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("L3_Compta_Database")
        return sheet
    except Exception as e:
        return None

# --- IA LOGIC ---
def extract_text(files):
    text = ""
    for f in files:
        try:
            if f.type == "application/pdf":
                text += PdfReader(f).pages[0].extract_text() + "\n" # Simplifié pour vitesse
            elif "word" in f.type:
                doc = Document(f)
                for p in doc.paragraphs: text += p.text + "\n"
        except: pass
    return text

def get_gemini_response(prompt, context):
    try:
        api_key = st.secrets["gemini"]["api_key"]
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro') # Modèle stable
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
        
        # Widget Pomodoro
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
    # Header
    st.markdown(f"### 👋 Bonjour, voici ton état des lieux")
    st.markdown(f"<p style='color:#64748b;'>Semestre 2 • {datetime.now().strftime('%d %B %Y')}</p>", unsafe_allow_html=True)
    st.write("")

    # Data Fetching
    gpa = 0.0
    urgent_tasks = 0
    df_grades = pd.DataFrame()
    
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

    # KPI ROW
    c1, c2, c3 = st.columns(3)
    with c1: kpi_card("Moyenne Générale", f"{gpa}/20", "📈 +0.5 pts vs S1", NAVY, "🎓")
    with c2: kpi_card("Tâches Urgentes", str(urgent_tasks), "🔥 Keep pushing", TEAL, "⚡")
    with c3: kpi_card("Semaine", f"S{datetime.now().isocalendar()[1]}", "🗓 Année Univ.", GOLD, "📅")

    st.write("")
    st.write("")

    # MAIN SECTION
    c_left, c_right = st.columns([2, 1])

    with c_left:
        st.markdown(f"#### <span style='color:{NAVY}'>📊 Répartition ECTS</span>", unsafe_allow_html=True)
        # Beau graphique donut avec Plotly
        labels = ['Finance', 'Juridique', 'Systèmes', 'Pro']
        values = [14, 12, 15, 16] # Valeurs fictives ou calculées
        colors = [NAVY, '#64748b', GOLD, TEAL]
        
        fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.7, marker=dict(colors=colors))])
        fig.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0), height=300, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

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
            st.info("Aucune tâche urgente ! 🎉")

def subject_page(sh, subject):
    conf = SUBJECTS_CONFIG[subject]
    
    # Header Matière Style HTML
    st.markdown(f"""
    <div style="background-color: white; padding: 30px; border-radius: 15px; border-top: 8px solid {conf['color']}; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px;">
        <span style="background-color: #f1f5f9; padding: 5px 10px; border-radius: 5px; font-size: 10px; font-weight: bold; text-transform: uppercase; color: #64748b;">{conf['cat']}</span>
        <h1 style="color: {NAVY}; margin-top: 10px; margin-bottom: 5px;">{subject}</h1>
        <div style="display:flex; gap: 15px; font-size: 14px; color: #64748b;">
            <span>👨‍🏫 Professeur</span>
            <span>⚖️ Coefficient</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["🤖 Tuteur IA", "📝 Notes & Simu", "✅ Tâches"])

    # Sidebar Upload
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
            
            # PARTIE GAUCHE : AJOUTER UNE NOTE
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
            
            # PARTIE DROITE : LISTE + SUPPRESSION
            with c2:
                recs = ws_g.get_all_records()
                df = pd.DataFrame(recs)
                
                if not df.empty:
                    # On filtre pour ne garder que la matière actuelle
                    df_sub = df[df['Subject'] == subject]
                    
                    if not df_sub.empty:
                        st.markdown("##### 📄 Mes notes")
                        # On affiche chaque note ligne par ligne avec un bouton
                        for i, row in df_sub.iterrows():
                            with st.container(border=True):
                                col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 1])
                                col_a.markdown(f"**{row['Grade']}/20**")
                                col_b.caption(f"Coef {row['Coefficient']}")
                                col_c.caption(row['Type'])
                                
                               # --- BOUTON SUPPRIMER (MÉTHODE NUCLÉAIRE / TYPE-AGNOSTIC) ---
                                if col_d.button("❌", key=f"del_{row['ID']}"):
                                    try:
                                        st.toast("⏳ Suppression en cours...")
                                        
                                        # 1. On nettoie l'ID qu'on cherche (on le force en texte propre)
                                        target_id = str(row['ID']).strip()
                                        
                                        # 2. On récupère toute la colonne A
                                        all_ids = ws_g.col_values(1)
                                        
                                        # 3. On cherche manuellement en convertissant tout en texte
                                        row_to_delete = -1
                                        
                                        # On parcourt chaque ligne pour comparer "Texte contre Texte"
                                        for index, value in enumerate(all_ids):
                                            # On force la valeur du fichier en texte pour comparer
                                            if str(value).strip() == target_id:
                                                # Bingo ! On a trouvé l'index (0, 1, 2...)
                                                # Google Sheets commence à 1, donc on ajoute +1
                                                row_to_delete = index + 1
                                                break
                                        
                                        # 4. Action
                                        if row_to_delete != -1:
                                            ws_g.delete_rows(row_to_delete)
                                            st.success("Supprimé !")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(f"ID '{target_id}' introuvable (Problème de format).")
                                            
                                    except Exception as e:
                                        st.error(f"Erreur technique : {e}")
                                # --------------------------------
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
    if not sh: st.error("Erreur connexion Google Sheets")
    
    page = sidebar_menu()
    
    if page == "Dashboard":
        dashboard_page(sh)
    else:
        subject_page(sh, page)
