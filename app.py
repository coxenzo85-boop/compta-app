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

# --- CONFIGURATION PAGE & CSS MODERNE ---
st.set_page_config(page_title="Student Hub L3", page_icon="🎓", layout="wide")

# CSS pour le look "SaaS Moderne"
st.markdown("""
    <style>
    /* Import Font moderne */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Fond général */
    .stApp {
        background-color: #f8fafc;
    }

    /* Sidebar stylisée */
    [data-testid="stSidebar"] {
        background-color: #0f172a;
    }
    [data-testid="stSidebar"] h1 {
        color: white !important;
        font-size: 1.5rem;
        text-align: center;
        margin-bottom: 20px;
    }

    /* Cards (Cartes) Dashboard */
    .kpi-card {
        background-color: white;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        text-align: center;
        border: 1px solid #e2e8f0;
        transition: transform 0.2s;
    }
    .kpi-card:hover {
        transform: translateY(-5px);
    }
    .kpi-title {
        color: #64748b;
        font-size: 0.9rem;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 5px;
    }
    .kpi-value {
        color: #0f172a;
        font-size: 2.5rem;
        font-weight: 700;
    }

    /* Titres */
    h1, h2, h3 {
        color: #0f172a;
        font-weight: 700;
    }
    
    /* Boutons personnalisés */
    .stButton>button {
        background-color: #2563eb;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #1d4ed8;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
    }

    /* Onglets */
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
        border-bottom: 1px solid #e2e8f0;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px;
        color: #64748b;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #eff6ff;
        color: #2563eb;
    }
    
    /* Input fields */
    .stTextInput>div>div>input {
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONSTANTES ---
SUBJECTS = [
    "Organisation et SI", "Diagnostic général", "Diagnostic financier", 
    "Droit des sociétés 2", "Droit du crédit", "Droit pénal des affaires", 
    "Comptabilité approfondie 2", "Modélisation des coûts", 
    "International Financial Accounting", "Anglais des affaires", 
    "Informatique décisionnelle", "Projet professionnel", "Stage et mémoire"
]

# --- CONNEXION ---
def get_db_connection():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(credentials_dict, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("L3_Compta_Database")
    return sheet

# --- UTILITAIRES ---
def extract_text_from_file(uploaded_file):
    text = ""
    try:
        if uploaded_file.type == "application/pdf":
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = Document(uploaded_file)
            for para in doc.paragraphs:
                text += para.text + "\n"
    except Exception as e:
        return f"Erreur lecture : {e}"
    return text

def get_gemini_response(prompt, context, subject, mode="tuteur"):
    api_key = st.secrets["gemini"]["api_key"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-001')
    
    if mode == "quiz":
        system_prompt = f"Tu es un professeur expert en {subject}. Génère un QCM difficile de 3 questions basé sur le contexte. Affiche la correction à la fin."
    else:
        system_prompt = f"Tu es un tuteur expert en {subject} (L3 Compta). Réponds avec le contexte fourni."
        
    full_prompt = f"{system_prompt}\n\nCONTEXTE:\n{context}\n\nDEMANDE:\n{prompt}"
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Erreur IA : {e}"

# --- NAVIGATION MODERNE ---
def navigation():
    with st.sidebar:
        st.markdown("<h1>🎓 Student OS</h1>", unsafe_allow_html=True)
        
        # Menu Principal Stylisé
        selected = option_menu(
            menu_title=None,
            options=["Dashboard"] + SUBJECTS,
            icons=["speedometer2"] + ["book"]*len(SUBJECTS),
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "#0f172a"},
                "icon": {"color": "#94a3b8", "font-size": "14px"}, 
                "nav-link": {"font-size": "14px", "text-align": "left", "margin":"0px", "--hover-color": "#1e293b", "color": "#e2e8f0"},
                "nav-link-selected": {"background-color": "#2563eb", "color": "white", "font-weight": "600"},
            }
        )
        
        # Pomodoro Widget
        st.markdown("---")
        st.markdown("<div style='text-align: center; color: #94a3b8; font-size: 0.8rem; margin-bottom: 10px;'>FOCUS ZONE</div>", unsafe_allow_html=True)
        
        if 'pomodoro_active' not in st.session_state:
            st.session_state.pomodoro_active = False
            st.session_state.pomodoro_start = None

        col_p1, col_p2 = st.columns(2)
        if col_p1.button("▶️ 25m"):
            st.session_state.pomodoro_active = True
            st.session_state.pomodoro_start = time.time()
        
        if col_p2.button("⏹️ Stop"):
            st.session_state.pomodoro_active = False

        if st.session_state.pomodoro_active:
            elapsed = time.time() - st.session_state.pomodoro_start
            remaining = 25*60 - elapsed
            if remaining > 0:
                mins, secs = divmod(remaining, 60)
                st.metric("", f"{int(mins):02}:{int(secs):02}")
            else:
                st.success("Pause !")
                st.session_state.pomodoro_active = False
                
    return selected

# --- DASHBOARD MODERNE ---
def dashboard_page(sh):
    st.markdown("## 👋 Hello Boss, on en est où ?")
    st.markdown("<br>", unsafe_allow_html=True)
    
    try:
        ws_grades = sh.worksheet("Grades")
        grades_data = ws_grades.get_all_records()
        ws_tasks = sh.worksheet("Tasks")
        tasks_data = ws_tasks.get_all_records()
    except:
        st.error("Problème de connexion BDD.")
        return

    # Calculs
    df_grades = pd.DataFrame(grades_data)
    gpa = 0
    if not df_grades.empty:
        df_grades['Grade'] = pd.to_numeric(df_grades['Grade'], errors='coerce')
        df_grades['Coefficient'] = pd.to_numeric(df_grades['Coefficient'], errors='coerce')
        df_grades = df_grades.dropna()
        total_p = (df_grades['Grade'] * df_grades['Coefficient']).sum()
        total_c = df_grades['Coefficient'].sum()
        gpa = round(total_p / total_c, 2) if total_c > 0 else 0

    urgent_count = len([t for t in tasks_data if t['Status'] == 'À faire'])
    semaine = datetime.now().isocalendar()[1]

    # Cartes KPI
    col1, col2, col3 = st.columns(3)
    col1.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Moyenne Générale</div>
            <div class="kpi-value" style="color: {'#10b981' if gpa >= 10 else '#ef4444'}">{gpa}</div>
            <div style="color: #64748b; font-size: 0.8rem;">Objectif: 12.00</div>
        </div>
        """, unsafe_allow_html=True)
    
    col2.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Tasks en attente</div>
            <div class="kpi-value">{urgent_count}</div>
            <div style="color: #64748b; font-size: 0.8rem;">Keep pushing!</div>
        </div>
        """, unsafe_allow_html=True)
        
    col3.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Semaine</div>
            <div class="kpi-value">S{semaine}</div>
            <div style="color: #64748b; font-size: 0.8rem;">Année Universitaire</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    c_chart, c_todo = st.columns([2, 1])
    
    with c_chart:
        st.subheader("📈 Performance par matière")
        if not df_grades.empty:
            avg_by_subject = df_grades.groupby('Subject').apply(
                lambda x: (x['Grade'] * x['Coefficient']).sum() / x['Coefficient'].sum()
            ).reset_index(name='Moyenne')
            st.bar_chart(avg_by_subject, x='Subject', y='Moyenne', color="#2563eb")
        else:
            st.info("Aucune donnée.")
            
    with c_todo:
        st.subheader("📌 Urgent")
        df_tasks = pd.DataFrame(tasks_data)
        if not df_tasks.empty and 'Status' in df_tasks.columns:
            todo = df_tasks[df_tasks['Status'] == 'À faire'].head(5)
            if not todo.empty:
                for idx, row in todo.iterrows():
                    with st.container(border=True):
                        if st.button(f"✅ {row['Task']}", key=f"dash_{row['ID']}"):
                            cell = ws_tasks.find(row['ID'])
                            ws_tasks.update_cell(cell.row, 4, "Fait")
                            st.rerun()
                        st.caption(f"🗓 {row['Due_Date']}")
            else:
                st.success("Rien à faire !")

# --- PAGE MATIÈRE ---
def subject_page(sh, subject):
    st.markdown(f"## 📘 {subject}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["💬 Tuteur IA", "🧠 Quiz", "📝 Notes", "✅ Tâches"])
    
    # Sidebar Context
    with st.sidebar:
        st.markdown("---")
        st.markdown("**📂 Fichiers du cours**")
        files = st.file_uploader("Drop PDF/Word", type=['pdf', 'docx'], accept_multiple_files=True, key=f"up_{subject}")
        context = ""
        if files:
            for f in files: context += extract_text_from_file(f) + "\n"
    
    with tab1:
        st.caption("L'IA répondra en utilisant uniquement tes documents uploadés.")
        
        if "messages" not in st.session_state: st.session_state.messages = {}
        if subject not in st.session_state.messages: st.session_state.messages[subject] = []

        for msg in st.session_state.messages[subject]:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])

        if prompt := st.chat_input("Question sur le cours..."):
            if not context:
                st.warning("⚠️ Upload un document à gauche d'abord.")
            else:
                st.session_state.messages[subject].append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                
                with st.chat_message("assistant"):
                    with st.spinner("Reflexion..."):
                        resp = get_gemini_response(prompt, context, subject)
                        st.markdown(resp)
                st.session_state.messages[subject].append({"role": "assistant", "content": resp})

    with tab2:
        if st.button("✨ Générer un Quiz de révision"):
            if context:
                with st.spinner("Génération..."):
                    quiz = get_gemini_response("Quiz", context, subject, mode="quiz")
                    st.info(quiz)
            else:
                st.error("Pas de documents !")

    with tab3:
        ws_grades = sh.worksheet("Grades")
        c1, c2 = st.columns([1, 2])
        with c1:
            with st.form("new_grade"):
                st.markdown("#### Nouvelle Note")
                grade = st.number_input("Note", 0.0, 20.0, step=0.5)
                coef = st.number_input("Coef", 0.0, 10.0, value=1.0)
                g_type = st.selectbox("Type", ["CC", "Partiel", "Examen"])
                if st.form_submit_button("Ajouter"):
                    ws_grades.append_row([str(uuid.uuid4())[:8], subject, grade, coef, g_type])
                    st.success("Sauvegardé")
                    time.sleep(1)
                    st.rerun()
        
        with c2:
            all = ws_grades.get_all_records()
            df = pd.DataFrame(all)
            if not df.empty:
                df_sub = df[df['Subject'] == subject]
                if not df_sub.empty:
                    st.dataframe(df_sub[["Grade", "Coefficient", "Type"]], use_container_width=True, hide_index=True)
                else:
                    st.info("Pas encore de notes.")

    with tab4:
        ws_tasks = sh.worksheet("Tasks")
        col_inp, col_btn = st.columns([3, 1])
        with col_inp:
            task_txt = st.text_input("Nouvelle tâche", key=f"t_{subject}")
        with col_btn:
            st.write("")
            st.write("")
            if st.button("Add", key=f"b_{subject}"):
                ws_tasks.append_row([str(uuid.uuid4())[:8], subject, task_txt, "À faire", str(datetime.now().date())])
                st.rerun()
        
        # Liste Checkable
        all_t = ws_tasks.get_all_records()
        df_t = pd.DataFrame(all_t)
        if not df_t.empty:
            sub_t = df_t[(df_t['Subject'] == subject) & (df_t['Status'] == 'À faire')]
            for i, r in sub_t.iterrows():
                if st.checkbox(r['Task'], key=f"chk_{r['ID']}"):
                    cell = ws_tasks.find(r['ID'])
                    ws_tasks.update_cell(cell.row, 4, "Fait")
                    st.rerun()

# --- MAIN ---
if __name__ == "__main__":
    try:
        sh = get_db_connection()
        page = navigation() # Nouveau menu
        if page == "Dashboard":
            dashboard_page(sh)
        else:
            subject_page(sh, page)
    except Exception as e:
        st.error(f"Erreur : {e}")
