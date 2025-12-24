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

import streamlit as st
import pandas as pd
# ... tes autres imports ...
import json
from fpdf import FPDF  # <--- AJOUTE ÇA

# --- FONCTION GÉNÉRATEUR PDF (CORRIGÉE) ---
def create_financial_pdf(data):
    class PDF(FPDF):
        def header(self):
            # Titre / En-tête
            self.set_font('Arial', 'B', 15)
            # On encode en latin-1 pour éviter les bugs d'accents dans le header
            self.cell(0, 10, 'Rapport d\'Analyse Financiere'.encode('latin-1', 'replace').decode('latin-1'), 0, 1, 'C')
            self.set_font('Arial', 'I', 10)
            date_str = date.today().strftime('%d/%m/%Y')
            txt = f"Genere par L3 CCA Dashboard - {date_str}"
            self.cell(0, 10, txt.encode('latin-1', 'replace').decode('latin-1'), 0, 1, 'C')
            self.ln(5)

        def chapter_title(self, title):
            self.set_font('Arial', 'B', 12)
            self.set_fill_color(200, 220, 255) # Bleu clair
            # Nettoyage préventif du titre
            clean_title = title.encode('latin-1', 'replace').decode('latin-1')
            self.cell(0, 10, clean_title, 0, 1, 'L', 1)
            self.ln(4)

        def chapter_body(self, body):
            self.set_font('Arial', '', 11)
            # Nettoyage préventif du corps de texte
            clean_body = body.encode('latin-1', 'replace').decode('latin-1')
            self.multi_cell(0, 8, clean_body)
            self.ln()

    # Initialisation
    pdf = PDF()
    pdf.add_page()
    
    # Titre du Cas (Nettoyage du nom de l'entreprise)
    pdf.set_font('Arial', 'B', 14)
    nom_dossier = data['nom'].replace("€", "EUR") # Sécurité
    clean_nom = nom_dossier.encode('latin-1', 'replace').decode('latin-1')
    pdf.cell(0, 10, f"Dossier : {clean_nom}", 0, 1, 'L')
    pdf.ln(5)

    # 1. Équilibre Financier
    # NOTE : J'ai remplacé le signe € par EUR pour éviter le crash
    pdf.chapter_title('1. Equilibre Financier (Bilan Fonctionnel)')
    text_equilibre = (
        f"FRNG (Fonds de Roulement) : {data['frng']:,.0f} EUR\n"
        f"BFR (Besoin en Fonds de Roulement) : {data['bfr']:,.0f} EUR\n"
        f"Tresorerie Nette (TN) : {data['tn']:,.0f} EUR\n\n"
        f"INTERPRETATION : {'Situation Saine. Le FRNG couvre le BFR.' if data['tn'] > 0 else 'ATTENTION : Tresorerie Negative. Le FRNG est insuffisant.'}"
    )
    pdf.chapter_body(text_equilibre)

    # 2. Rentabilité
    pdf.chapter_title('2. Performance & Rentabilite')
    text_renta = (
        f"Chiffre d'Affaires : {data['ca']:,.0f} EUR\n"
        f"Marge Nette : {data['marge']:.2f} %\n"
        f"ROE (Rentabilite Financiere) : {data['roe']:.2f} %\n"
        f"ROCE (Rentabilite Economique) : {data['roce']:.2f} %"
    )
    pdf.chapter_body(text_renta)

    # 3. Risque
    pdf.chapter_title('3. Structure & Solvabilite')
    text_risk = (
        f"Levier Financier (Dettes/CP) : {data['levier']:.2f}\n"
        f"Autonomie Financiere : {data['autonomie']:.2f} %\n\n"
        f"DIAGNOSTIC : {'Structure endettee (Levier > 1).' if data['levier'] > 1 else 'Structure financiere solide (Levier < 1).'}"
    )
    pdf.chapter_body(text_risk)

    # Output
    # On renvoie les bytes directement
    return pdf.output(dest='S').encode('latin-1')

# --- FONCTIONS CACHÉES (POUR ÉVITER L'ERREUR QUOTA) ---

@st.cache_data(ttl=60) # Garde en mémoire 60 secondes
def get_history_cached(_sh):
    try:
        return pd.DataFrame(_sh.worksheet("History").get_all_records())
    except: return pd.DataFrame()

@st.cache_data(ttl=300) # Garde en mémoire 5 minutes
def get_simulator_cached(_sh):
    try:
        return pd.DataFrame(_sh.worksheet("Simulateur").get_all_records())
    except: return pd.DataFrame()

# Fonction pour VIDER le cache quand on fait une modification (Sauvegarde)
def clear_cache():
    get_history_cached.clear()
    get_simulator_cached.clear()

# --- CONFIGURATION PAGE ---
st.set_page_config(page_title="L3 CCA Dashboard", page_icon="🎓", layout="wide")

# --- GESTION DE L'ÉTAT (SESSION STATE) ---
if 'current_view' not in st.session_state: st.session_state.current_view = 'Dashboard'
if 'selected_subject' not in st.session_state: st.session_state.selected_subject = None
if 'show_simulator' not in st.session_state: st.session_state.show_simulator = False
if 'pomodoro' not in st.session_state: st.session_state.pomodoro = None
# Gestion du Timer Persistant
if 'timer_active' not in st.session_state: st.session_state.timer_active = False
if 'timer_end_time' not in st.session_state: st.session_state.timer_end_time = None
if 'timer_subject' not in st.session_state: st.session_state.timer_subject = "Général"
if 'timer_duration' not in st.session_state: st.session_state.timer_duration = 25


# 🔗 LIEN EMPLOI DU TEMPS
ICS_CALENDAR_URL = "http://edt-v2.univ-nantes.fr/calendar/ics?timetables[0]=110228"

# PALETTE DE COULEURS
NAVY = "#1A2C42"
TEAL = "#008080"
GOLD = "#C5A059"
CLOUD = "#F4F6F7"
ORANGE_REV = "#ea580c"

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
        padding: 25px;
        border-radius: 15px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
        border-left: 8px solid {NAVY};
        height: 100%;
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

    /* Onglets */
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

# --- LIENS NOTEBOOK LM PERSONNALISÉS ---
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
    try:
        # On convertit le fichier en flux binaire
        file_content = io.BytesIO(uploaded_file.getvalue())
        
        # --- LE FIX EST ICI : resumable=False ---
        # Cela force un envoi direct au lieu de couper le fichier en morceaux (ce qui causait ton erreur)
        media = MediaIoBaseUpload(file_content, mimetype=uploaded_file.type, resumable=False)
        
        file_metadata = {'name': uploaded_file.name, 'parents': [folder_id]}
        
        drive_service.files().create(body=file_metadata, media_body=media).execute()
        return True
    except Exception as e:
        st.error(f"Erreur Upload : {e}")
        return False

@st.cache_data(ttl=3600, show_spinner=False) 
def get_ics_events_cached(ics_url):
    events = []
    try:
        resp = requests.get(ics_url, timeout=10)
        if resp.status_code == 200:
            cal = Calendar.from_ical(resp.content)
            for c in cal.walk('vevent'):
                events.append({
                    "title": str(c.get('summary', 'Cours')), 
                    "start": c.get('dtstart').dt.isoformat(), 
                    "end": c.get('dtend').dt.isoformat(),
                    "backgroundColor": TEAL, "borderColor": NAVY
                })
    except: pass
    return events

def get_combined_events(ics_url, sh):
    events = get_ics_events_cached(ics_url)
    if sh:
        try:
            # Récupérer les événements depuis l'onglet "Events" du Google Sheet
            # Assurez-vous que l'onglet 'Events' existe et contient les colonnes : ID, Title, Start, End, Type
            recs = sh.worksheet("Events").get_all_records()
            for r in recs:
                events.append({
                    "title": f"📚 {r['Title']}", 
                    "start": r['Start'], 
                    "end": r['End'],
                    "backgroundColor": ORANGE_REV,  # Orange pour tes révisions
                    "borderColor": GOLD
                })
        except Exception as e:
            # Si l'onglet n'existe pas ou erreur, on continue juste avec l'ICS
            pass
    return events

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

# --- CALCULATEUR MOYENNE ---
def load_simulator_data(sh):
    try:
        ws = sh.worksheet("Simulateur")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # FIX: Si le tableau est vide ou qu'il manque la colonne 'Semestre', on le réinitialise
        if df.empty or 'Semestre' not in df.columns:
            init_data = []
            # On utilise les listes globales définies au début du fichier
            for m in DEFAULT_S1: init_data.append({"Matiere": m, "Semestre": "S1", "Coef_CC": 1, "Coef_Partiel": 2, "Note_CC": 0, "Note_Partiel": 0})
            for m in DEFAULT_S2: init_data.append({"Matiere": m, "Semestre": "S2", "Coef_CC": 1, "Coef_Partiel": 2, "Note_CC": 0, "Note_Partiel": 0})
            
            df = pd.DataFrame(init_data)
            # On force la sauvegarde pour réparer le Sheet
            ws.clear()
            ws.update([df.columns.values.tolist()] + df.values.tolist())
            
        return df
    except: return pd.DataFrame()
# --- FONCTION UTILITAIRE : SAUVEGARDE HISTORIQUE ---
def save_to_history(sh, action, subject, value):
    try:
        # Tente d'ajouter une ligne à la feuille "History"
        sh.worksheet("History").append_row([str(date.today()), action, subject, value])
    except gspread.exceptions.WorksheetNotFound:
        # Si la feuille "History" n'existe pas, on la crée
        try:
            ws = sh.add_worksheet(title="History", rows="1000", cols="4")
            ws.append_row(["Date", "Action", "Subject", "Value"]) # En-têtes
            ws.append_row([str(date.today()), action, subject, value])
        except Exception as e:
            st.error(f"Erreur lors de la création de l'historique : {e}")
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
    
def save_simulator_data(sh, df):
    try:
        ws = sh.worksheet("Simulateur")
        cols_to_save = ["Matiere", "Semestre", "Coef_CC", "Coef_Partiel", "Note_CC", "Note_Partiel"]
        df_save = df[cols_to_save]
        ws.update([df_save.columns.values.tolist()] + df_save.values.tolist())
    except Exception as e: st.error(f"Erreur sauvegarde: {e}")
# --- NOUVELLE PAGE : SUIVI CANDIDATURES ---
def candidatures_page(sh):
    st.markdown(f"### 🚀 Suivi Candidatures (Stage & Master)")
    
    # 1. Chargement
    df = pd.DataFrame()
    if sh:
        try:
            ws = sh.worksheet("Candidatures")
            data = ws.get_all_records()
            df = pd.DataFrame(data)
        except:
            # Création onglet si inexistant
            try:
                ws = sh.add_worksheet(title="Candidatures", rows="100", cols="20")
                header = ["ID", "Organisation", "Type", "Poste", "Date_Envoi", "Statut", "Lien", "Notes"]
                ws.append_row(header)
                df = pd.DataFrame(columns=header)
            except: pass

    # 2. KPI
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("En attente", len(df[df['Statut'] == 'Envoyé']))
        c3.metric("Entretiens", len(df[df['Statut'] == 'Entretien']))
        nb_pos = len(df[df['Statut'].isin(['Entretien', 'Accepté'])])
        c4.metric("Taux Réponse", f"{(nb_pos/len(df)*100):.0f}%" if len(df)>0 else "0%")
    
    st.write("")

    # 3. FORMULAIRE
    with st.expander("➕ Nouvelle Candidature", expanded=False):
        with st.form("new_cand"):
            c_org, c_typ, c_stat = st.columns(3)
            org = c_org.text_input("Entreprise / Université")
            typ = c_typ.selectbox("Type", ["Master", "Stage", "Alternance"])
            stat = c_stat.selectbox("Statut", ["A faire", "Envoyé", "Entretien", "Refus", "Accepté"])
            
            c_pos, c_date = st.columns([2, 1])
            poste = c_pos.text_input("Intitulé")
            d_env = c_date.date_input("Date Envoi")
            note = st.text_area("Notes")
            
            if st.form_submit_button("Sauvegarder"):
                if sh:
                    sh.worksheet("Candidatures").append_row(
                        [str(uuid.uuid4())[:8], org, typ, poste, str(d_env), stat, "", note]
                    )
                    st.success("Ajouté !"); time.sleep(1); st.rerun()

    # 4. TABLEAU (CORRIGÉ)
    st.markdown("### 📋 Tableau de bord")
    if not df.empty:
        # --- LA CORRECTION EST ICI ---
        # On force la conversion de la colonne texte en objets Date
        if "Date_Envoi" in df.columns:
            df["Date_Envoi"] = pd.to_datetime(df["Date_Envoi"], errors="coerce").dt.date

        column_config = {
            "ID": None,
            "Lien": st.column_config.LinkColumn("Lien"),
            "Organisation": st.column_config.TextColumn("Organisation", width="medium"),
            "Type": st.column_config.SelectboxColumn("Type", options=["Master", "Stage", "Alternance"], width="small"),
            "Statut": st.column_config.SelectboxColumn("Statut", options=["A faire", "Envoyé", "Entretien", "Refus", "Accepté"], width="small", required=True),
            "Date_Envoi": st.column_config.DateColumn("Date Envoi", format="DD/MM/YYYY"),
            "Notes": st.column_config.TextColumn("Notes", width="large")
        }
        
        try:
            edited_df = st.data_editor(
                df, 
                column_config=column_config, 
                hide_index=True, 
                use_container_width=True, 
                num_rows="dynamic",
                key="editor_cand_fix"
            )
            
            if st.button("💾 Mettre à jour le tableau"):
                if sh:
                    try:
                        ws = sh.worksheet("Candidatures")
                        ws.clear()
                        # Astuce : on repasse tout en texte (.astype(str)) avant d'envoyer à Google pour éviter les bugs
                        ws.update([edited_df.columns.values.tolist()] + edited_df.astype(str).values.tolist())
                        st.success("Tableau mis à jour !")
                        time.sleep(1); st.rerun()
                    except Exception as e: st.error(f"Erreur : {e}")
        except Exception as e:
            st.error(f"Erreur d'affichage : {e}")
            st.dataframe(df) # Affichage de secours simple
    else:
        st.info("Aucune candidature. Commence par en ajouter une !")
# --- NAVIGATION ---
def sidebar_menu():
    with st.sidebar:
        st.markdown(f"<h2 style='color:white; text-align:center;'>L3 CCA <span style='color:{TEAL}'>HUB</span></h2>", unsafe_allow_html=True)
        st.write("")
        
        # 1. On détermine l'index par défaut basé sur l'état actuel pour synchroniser
        options = ["Dashboard", "Mes Cours", "Candidatures", "Analyse Fi", "Bibliothèque", "Focus Room"]
        try:
            default_ix = options.index(st.session_state.current_view)
        except:
            default_ix = 0

        # --- FIX CSS POUR MENU (Coins Blancs) ---
        selected = option_menu(
            menu_title=None,
            options=options,
           icons=["speedometer2", "book", "briefcase", "calculator", "archive", "hourglass"],
            menu_icon="cast",
            default_index=default_ix, 
            styles={
                # AJOUT DE border-radius: 0 ICI 👇
                "container": {"padding": "0!important", "background-color": NAVY, "border-radius": "0"}, 
                "icon": {"color": "#94a3b8", "font-size": "14px"}, 
                "nav-link": {"font-size": "14px", "text-align": "left", "margin":"0px", "color": "#e2e8f0"},
                "nav-link-selected": {"background-color": TEAL, "color": "white", "font-weight": "bold"},
            }
        )
    return selected

# --- PAGES ---
# --- REMPLACE TOUTE LA FONCTION dashboard_page PAR CELLE-CI ---
# --- REMPLACE TOUTE LA FONCTION dashboard_page PAR CELLE-CI ---
def dashboard_page(sh):
    mois_fr = {
        1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin", 
        7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
    }
    auj = date.today()
    date_str = f"{auj.day} {mois_fr[auj.month]} {auj.year}"
    
    st.markdown(f"### 👋 Dashboard • {date_str}")

    # --- 1. CALCULS DES MOYENNES (S1 & S2 PROGRESSIF) ---
    s1_display = "0.00/20"
    s2_display = "En attente"
    df_sim = pd.DataFrame()
    
    if sh:
        try:
            df_sim = load_simulator_data(sh)
            if not df_sim.empty:
                # S1
                s1 = df_sim[df_sim['Semestre'] == 'S1'].copy()
                s1['Total_Coef'] = s1['Coef_CC'] + s1['Coef_Partiel']
                s1['Moy'] = ((s1['Note_CC']*s1['Coef_CC']) + (s1['Note_Partiel']*s1['Coef_Partiel'])) / s1['Total_Coef'].replace(0, 1)
                valid_s1 = s1[s1['Total_Coef'] > 0]
                if not valid_s1.empty: s1_display = f"{valid_s1['Moy'].mean():.2f}/20"

                # S2 Progressif
                s2 = df_sim[df_sim['Semestre'] == 'S2'].copy()
                s2['Total_Coef'] = s2['Coef_CC'] + s2['Coef_Partiel']
                valid_s2 = s2[s2['Total_Coef'] > 0].copy()
                
                if not valid_s2.empty:
                    valid_s2['Moy'] = ((valid_s2['Note_CC']*valid_s2['Coef_CC']) + (valid_s2['Note_Partiel']*valid_s2['Coef_Partiel'])) / valid_s2['Total_Coef']
                    s2_display = f"{valid_s2['Moy'].mean():.2f}/20"
        except: pass

    # --- 2. KPI CARDS ---
    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Moyenne S2 (Progressive)", s2_display, f"Moyenne S1 : {s1_display}", NAVY, "🎓")
        if st.button("🧮 Ouvrir/Fermer Simulateur", key="btn_sim_main", use_container_width=True):
            st.session_state.show_simulator = not st.session_state.show_simulator
            st.rerun()
    with c2:
        status_txt = "Session en cours..." if st.session_state.timer_active else "Prêt à bosser ?"
        kpi_card("Focus Room", status_txt, "Productivité Maximale", GOLD, "⏳")
        if st.button("🚀 Accéder à la Focus Room", key="btn_focus_main", use_container_width=True):
            st.session_state.current_view = "Focus Room"; st.rerun()

    # --- 3. SIMULATEUR & CALCULATEUR D'OBJECTIF ---
    if st.session_state.show_simulator and sh:
        st.write(""); st.info("ℹ️ S2 : Laisse les coefficients à 0 si tu n'as pas encore de note.")
        try:
            tab1, tab2 = st.tabs(["📘 Semestre 1", "📙 Semestre 2"])
            cfg = {"Matiere": st.column_config.TextColumn(disabled=True), "Semestre": None}
            
            def show_sim(df_s, k):
                ed = st.data_editor(df_s, column_config=cfg, hide_index=True, key=k, use_container_width=True)
                t = ed['Coef_CC'] + ed['Coef_Partiel']
                ed['Moyenne'] = ((ed['Note_CC']*ed['Coef_CC']) + (ed['Note_Partiel']*ed['Coef_Partiel'])) / t.replace(0, 1)
                ed.loc[t == 0, 'Moyenne'] = 0
                st.dataframe(ed[['Matiere', 'Moyenne']].style.format({"Moyenne": "{:.2f}"}).background_gradient(subset=['Moyenne'], cmap="RdYlGn", vmin=0, vmax=20), use_container_width=True)
                return ed

            with tab1: e1 = show_sim(df_sim[df_sim['Semestre']=='S1'], "e1")
            with tab2: e2 = show_sim(df_sim[df_sim['Semestre']=='S2'], "e2")
            
            # --- SAUVEGARDE ---
            if st.button("💾 Sauvegarder"):
                full = pd.concat([e1.drop(columns=['Moyenne'], errors='ignore'), e2.drop(columns=['Moyenne'], errors='ignore')])
                save_simulator_data(sh, full)
                st.success("Sauvegardé !"); time.sleep(1); st.rerun()

            # --- NOUVEAU : CALCULATEUR D'OBJECTIF (REVERSE SIMULATOR) ---
            st.write("")
            with st.expander("🎯 Calculateur d'Objectif (Reverse Simulator)", expanded=True):
                st.markdown("##### Quel est ton objectif pour le S2 ?")
                
                # 1. Sélection de l'objectif
                col_obj, col_res = st.columns([1, 2])
                target = col_obj.number_input("Moyenne visée (/20)", min_value=10.0, max_value=20.0, value=12.0, step=0.5)
                
                # 2. Algorithme de calcul
                # On travaille sur les données éditées (e2) pour être à jour
                df_calc = e2.copy()
                
                # Total des coeffs du semestre (Théorique)
                # On suppose que tous les cours listés comptent
                total_coef_semestre = (df_calc['Coef_CC'] + df_calc['Coef_Partiel']).sum()
                
                if total_coef_semestre > 0:
                    # Points TOTAL à atteindre
                    points_cible = target * total_coef_semestre
                    
                    # Points DÉJÀ ACQUIS (Là où la note > 0)
                    # Note : On considère qu'une note à 0 est "pas encore passée"
                    points_acquis = (df_calc['Note_CC'] * df_calc['Coef_CC']).sum() + (df_calc['Note_Partiel'] * df_calc['Coef_Partiel']).sum()
                    
                    # Coeffs "Consommés" (là où note > 0)
                    coef_conso_cc = df_calc.loc[df_calc['Note_CC'] > 0, 'Coef_CC'].sum()
                    coef_conso_ct = df_calc.loc[df_calc['Note_Partiel'] > 0, 'Coef_Partiel'].sum()
                    
                    # Coeffs Restants
                    coef_restant = total_coef_semestre - (coef_conso_cc + coef_conso_ct)
                    
                    # Points Manquants
                    points_manquants = points_cible - points_acquis
                    
                    # RÉSULTAT
                    with col_res:
                        if coef_restant <= 0:
                            if points_acquis >= points_cible:
                                st.success(f"🎉 BRAVO ! Tu as déjà atteint ton objectif (Moyenne actuelle : {points_acquis/total_coef_semestre:.2f})")
                            else:
                                st.error(f"Terminé. Moyenne finale : {points_acquis/total_coef_semestre:.2f}. Objectif raté.")
                        else:
                            moyenne_requise = points_manquants / coef_restant
                            
                            st.write(f"Points manquants : **{points_manquants:.1f}** sur les coeff. restants ({coef_restant:.1f})")
                            
                            if moyenne_requise > 20:
                                st.error(f"🛑 Mission Impossible... Il te faudrait **{moyenne_requise:.2f}/20** de moyenne sur le reste.")
                            elif moyenne_requise < 0:
                                st.success(f"🎉 C'est gagné ! Même avec 0/20 tu as ton objectif.")
                            else:
                                color = "green" if moyenne_requise < 12 else "orange" if moyenne_requise < 16 else "red"
                                st.markdown(f"""
                                <div style="background-color:white; padding:15px; border-radius:10px; border-left: 5px solid {color}; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
                                    <h3 style="margin:0; color:{NAVY}">🎯 Objectif : {target}/20</h3>
                                    <p style="margin:5px 0 0 0; font-size:16px;">
                                        Tu dois avoir une moyenne de <strong style="color:{color}; font-size:20px">{moyenne_requise:.2f}/20</strong>
                                        sur toutes les épreuves restantes.
                                    </p>
                                </div>
                                """, unsafe_allow_html=True)
                else:
                    st.warning("Remplis les coefficients dans le simulateur pour activer le calcul.")

        except Exception as e: st.error(f"Erreur Simulateur : {e}")
        st.markdown("---")

    # --- 4. CONTENU PRINCIPAL ---
    st.write("")
    cl, cr = st.columns([2, 1])
    
    with cl:
        # A. CALENDRIER
        st.markdown(f"#### <span style='color:{NAVY}'>🗓️ Emploi du Temps</span>", unsafe_allow_html=True)
        events = get_combined_events(ICS_CALENDAR_URL, sh)
        calendar(events=events, options={"initialView": "timeGridWeek", "height": "450px", "locale": "fr"}, custom_css=".fc-event{font-size:10px;}")
        
        # Ajout événements perso
        if sh:
            with st.expander("➕ Ajouter une révision / 🗑️ Gérer"):
                t1, t2 = st.tabs(["Ajouter", "Supprimer"])
                with t1:
                    with st.form("add_ev"):
                        c_t, c_d, c_h1, c_h2 = st.columns([2, 1, 1, 1])
                        titre = c_t.text_input("Titre")
                        d_ev = c_d.date_input("Date")
                        h_deb = c_h1.time_input("Début", dt_time(18,0))
                        h_fin = c_h2.time_input("Fin", dt_time(19,0))
                        if st.form_submit_button("Ajouter"):
                            try:
                                s = datetime.combine(d_ev, h_deb).isoformat()
                                e = datetime.combine(d_ev, h_fin).isoformat()
                                sh.worksheet("Events").append_row([str(uuid.uuid4())[:8], titre, s, e, "Revision"])
                                st.success("Ajouté !"); time.sleep(1); st.rerun()
                            except: st.error("Erreur Ajout (Vérifie onglet 'Events')")
                with t2:
                    try:
                        my_ev = pd.DataFrame(sh.worksheet("Events").get_all_records())
                        if not my_ev.empty:
                            for i, r in my_ev.iterrows():
                                c_a, c_b = st.columns([4,1])
                                c_a.text(f"{r['Title']} ({r['Start']})")
                                if c_b.button("Suppr.", key=f"del_{r['ID']}"):
                                    ids = sh.worksheet("Events").col_values(1)
                                    sh.worksheet("Events").delete_rows(ids.index(str(r['ID'])) + 1)
                                    st.rerun()
                        else: st.info("Vide.")
                    except: pass

        # B. ANALYTICS
        st.write("")
        st.markdown(f"#### <span style='color:{NAVY}'>📊 Mes Stats de Focus</span>", unsafe_allow_html=True)
        if sh:
            try:
                raw_data = sh.worksheet("History").get_all_values()
                if len(raw_data) > 0:
                    df_history = pd.DataFrame(raw_data, columns=["Date", "Action", "Subject", "Value"])
                    pomodoros = df_history[df_history['Action'] == 'Pomodoro'].copy()
                    if not pomodoros.empty:
                        pomodoros['Value'] = pd.to_numeric(pomodoros['Value'], errors='coerce')
                        fig = px.pie(pomodoros, values='Value', names='Subject', color_discrete_sequence=px.colors.sequential.Tealgrn, hole=0.4)
                        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250)
                        st.plotly_chart(fig, use_container_width=True)
                        total_h = pomodoros['Value'].sum() / 60
                        st.caption(f"⏱️ Total travaillé : **{total_h:.1f} heures**")
                    else: st.info("Pas encore de stats.")
                else: st.info("Historique vide.")
            except: pass

    with cr:
        # C. TO-DO LIST
        st.markdown(f"#### <span style='color:{NAVY}'>📌 To-Do Urgent</span>", unsafe_allow_html=True)
        if sh:
            try:
                tasks = pd.DataFrame(sh.worksheet("Tasks").get_all_records())
                todo = tasks[tasks['Status'] == 'À faire']
                if not todo.empty:
                    for i, r in todo.head(10).iterrows(): # Affiche les 10 premières tâches
                        with st.container(border=True):
                            c_chk, c_txt = st.columns([1, 5])
                            if c_chk.button("✔", key=f"do_{r['ID']}"):
                                sh.worksheet("Tasks").update_cell(sh.worksheet("Tasks").find(r['ID']).row, 4, "Fait"); st.rerun()
                            c_txt.markdown(f"**{r['Task']}**<br><span style='color:grey; font-size:11px'>{r['Subject']}</span>", unsafe_allow_html=True)
                else: st.success("Rien à faire ! 🎉")
            except: st.info("Liste vide ou erreur chargement.")

# --- PAGE 2: GRILLE DES COURS (S2 SEULEMENT) ---
def courses_grid_page():
    st.markdown("### 📚 Mes Modules S2"); st.write("")
    cols = st.columns(3)
    for index, subject in enumerate(DEFAULT_S2):
        with cols[index % 3]:
            st.markdown(f"""<div style="background-color:white; padding:20px; border-radius:10px; border-left:5px solid {NAVY}; margin-bottom:10px; box-shadow:0 2px 5px rgba(0,0,0,0.05)"><h3>{subject}</h3></div>""", unsafe_allow_html=True)
            if st.button(f"Ouvrir {subject}", key=f"btn_{subject}", use_container_width=True):
                st.session_state.selected_subject = subject; st.rerun()

# --- PAGE 3: DÉTAIL MATIÈRE (AVEC NOTEBOOKLM PERSONNALISÉ) ---
def subject_detail_page(sh, drive, subject):
    if st.button("← Retour"): st.session_state.selected_subject = None; st.rerun()
    st.title(subject)
    tab1, tab2 = st.tabs(["📂 Fichiers & IA", "✅ Tâches"])
    
    with tab1:
        # --- BLOC NOTEBOOK LM ---
        with st.container(border=True):
            c_logo, c_txt, c_btn = st.columns([0.5, 3, 1.5])
            with c_logo: st.markdown("## 🧠")
            with c_txt:
                st.markdown(f"**Booster de révision NotebookLM**")
                st.caption(f"Accède au carnet de notes dédié pour *{subject}*.")
            with c_btn:
                notebook_url = NOTEBOOK_LINKS.get(subject, "https://notebooklm.google.com/")
                st.link_button("↗ Ouvrir NotebookLM", notebook_url, type="primary", use_container_width=True)
        st.write("")

        # --- GESTION DRIVE (MODE LECTURE SEULE) ---
        if drive:
            # On récupère l'ID du dossier
            fid = get_or_create_subject_folder(drive, subject)
            
            if fid:
                # Lien direct pour uploader manuellement
                folder_url = f"https://drive.google.com/drive/folders/{fid}"
                st.info("💡 Pour ajouter des cours, dépose-les directement dans le dossier Drive ci-dessous.")
                st.markdown(f"""
                <a href="{folder_url}" target="_blank" style="text-decoration:none;">
                    <div style="background-color:#E8F0FE; color:#1967D2; padding:10px; border-radius:8px; text-align:center; font-weight:bold; border:1px solid #D2E3FC; margin-bottom:20px;">
                        📂 Ouvrir le dossier "{subject}" sur Google Drive
                    </div>
                </a>
                """, unsafe_allow_html=True)

                # Affichage des fichiers existants
                st.markdown("### 📄 Mes documents disponibles")
                files = list_drive_files(drive, fid)
                if files:
                    for f in files:
                        icon_url = f.get('iconLink', 'https://ssl.gstatic.com/docs/doclist/images/icon_10_generic_list.png')
                        st.markdown(f"""
                        <div class="file-card">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <img src='{icon_url}' width='20'>
                                <span style='font-weight:bold; color:{NAVY}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 250px;'>{f['name']}</span>
                            </div>
                            <a href='{f['webViewLink']}' target='_blank' style='text-decoration:none; color:{TEAL}; font-size:12px; font-weight:bold; border:1px solid {TEAL}; padding:4px 8px; border-radius:4px;'>Ouvrir</a>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.warning("Aucun fichier détecté. Ajoute-les via le lien ci-dessus !")
            else:
                st.error("Impossible de trouver le dossier sur le Drive.")
        else:
            st.warning("Connexion Drive inactive.")

    with tab2:
        if sh:
            t, d = st.columns([3, 1]); nt = t.text_input("Tâche"); nd = d.date_input("Date")
            if st.button("Ajouter"): sh.worksheet("Tasks").append_row([str(uuid.uuid4())[:8], subject, nt, "À faire", str(nd)]); st.rerun()
            
            recs = sh.worksheet("Tasks").get_all_records()
            if recs:
                df = pd.DataFrame(recs)
                if 'Subject' in df.columns and 'Status' in df.columns:
                    df = df[(df['Subject'] == subject) & (df['Status'] == 'À faire')]
                    for i, r in df.iterrows():
                        c_chk, c_info = st.columns([1, 10])
                        if c_chk.checkbox("", key=f"c_{r['ID']}"):
                            cell = sh.worksheet("Tasks").find(r['ID'])
                            sh.worksheet("Tasks").update_cell(cell.row, 4, "Fait"); st.rerun()
                        d_show = f"📅 {r['Due_Date']}" if "Due_Date" in r and r["Due_Date"] else ""
                        c_info.markdown(f"{r['Task']} <span style='color:#e11d48; margin-left:10px; font-size:0.8em'>{d_show}</span>", unsafe_allow_html=True)

# --- PAGE 4: FOCUS ROOM (RESTORED & FIXED) ---
def focus_room_page():
    st.markdown(f"### ⏳ Focus Room")
    st.markdown("Configure ta session. Le timer continuera même si tu changes de menu.")
    
    # --- INTÉGRATION APPLE MUSIC (Lofi Girl) ---
    with st.expander("🎵 Ambiance Sonore (Apple Music)", expanded=True):
        # On utilise une iframe sécurisée pour Apple Music
        embed_code = """
        <iframe allow="autoplay *; encrypted-media *; fullscreen *; clipboard-write" 
        frameborder="0" height="175" style="width:100%;max-width:660px;overflow:hidden;background:transparent;" 
        sandbox="allow-forms allow-popups allow-same-origin allow-scripts allow-storage-access-by-user-activation allow-top-navigation-by-user-activation" 
        src="https://embed.music.apple.com/fr/playlist/lofi-girl-beats-to-relax-study-to/pl.bf7a3cbca49644d8a33f09c1285aef5c">
        </iframe>
        """
        components.html(embed_code, height=180)

    # --- LOGIQUE DU TIMER PERSISTANT ---
    # Si aucun timer n'est actif, on affiche les réglages
    if not st.session_state.get('timer_active'):
        c1, c2, c3, c4 = st.columns(4)
        # On utilise DEFAULT_S2 ou une liste par défaut si non définie
        liste_matieres = DEFAULT_S2 if 'DEFAULT_S2' in globals() else ["Général", "Compta", "Droit"]
        subj = c1.selectbox("Matière", liste_matieres)
        dur = c2.number_input("Durée (min)", 1, 120, 25)
        short_break = c3.number_input("Pause courte", 1, 15, 5)
        cycles = c4.number_input("Cycles", 1, 10, 4)
        
        if st.button("▶ LANCER LA SESSION", type="primary"):
            # On enregistre l'heure de FIN prévue (C'est ça qui permet la persistance !)
            st.session_state.timer_active = True
            st.session_state.timer_end_time = datetime.now() + timedelta(minutes=dur)
            st.session_state.timer_subject = subj
            st.session_state.timer_duration = dur
            st.rerun()
            
    # Si un timer EST actif, on affiche le décompte
    else:
        # Calcul du temps restant par rapport à maintenant
        now = datetime.now()
        remaining = st.session_state.timer_end_time - now
        
        # Si temps restant > 0
        if remaining.total_seconds() > 0:
            mins, secs = divmod(int(remaining.total_seconds()), 60)
            
            st.markdown(f"<p class='timer-label'>💻 FOCUS EN COURS • {st.session_state.timer_subject}</p>", unsafe_allow_html=True)
            st.markdown(f"<div class='timer-display'>{mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
            
            # Barre de progression
            total_seconds = st.session_state.timer_duration * 60
            elapsed = total_seconds - remaining.total_seconds()
            st.progress(max(0.0, min(1.0, elapsed / total_seconds)))
            
            if st.button("⏹ Abandonner"):
                st.session_state.timer_active = False
                st.session_state.timer_end_time = None
                st.rerun()
            
            # Rechargement automatique toutes les secondes pour l'effet visuel
            time.sleep(1)
            st.rerun()
            
        else:
            # Le temps est écoulé !
            st.balloons()
            st.success(f"Session de {st.session_state.timer_subject} terminée ! Bravo 🎉")
            
            # Sauvegarde automatique (si la fonction existe)
            # if 'save_to_history' in globals() and 'sh' in globals() and sh:
            #    save_to_history(sh, "Pomodoro", st.session_state.timer_subject, st.session_state.timer_duration)
            
            # Réinitialisation
            if st.button("Nouvelle Session"):
                st.session_state.timer_active = False
                st.session_state.timer_end_time = None
                st.rerun()
import json # Assure-toi que cet import est présent au tout début du fichier app.py, sinon ajoute-le.

# --- REMPLACE TOUTE LA FONCTION financial_analysis_page PAR CELLE-CI ---
def financial_analysis_page(sh):
    st.markdown("### 📊 Diagnostic & Ratios Financiers")
    st.markdown("Rentre les masses de ton bilan, l'outil calcule le reste.")

    # --- 0. FONCTION DE CALLBACK (POUR ÉVITER L'ERREUR WIDGET) ---
    # Cette fonction s'exécute AVANT le rechargement de la page
    def charger_analyse(data):
        for k, v in data.items():
            st.session_state[f"af_{k}"] = float(v)

    # --- 1. ZONE DE SAISIE (GAUCHE) ---
    with st.sidebar:
        st.header("1. Compte de Résultat")
        # Note: On enlève 'value=...' car on utilise le session_state via la clé
        ca = st.number_input("Chiffre d'Affaires (CA)", step=1000.0, key="af_ca")
        rex = st.number_input("Résultat d'Exploitation (REX)", step=1000.0, key="af_rex")
        rn = st.number_input("Résultat Net (RN)", step=1000.0, key="af_rn")
        
        st.header("2. Bilan (Haut)")
        cap_propres = st.number_input("Capitaux Propres (CP)", step=1000.0, key="af_cp")
        dettes_fi = st.number_input("Dettes Financières (LMT)", step=1000.0, key="af_dettes")
        actif_immo = st.number_input("Actif Immobilisé Brut", step=1000.0, key="af_immo")
        
        st.header("3. Bilan (Bas - BFR)")
        actif_circ = st.number_input("Actif Circulant", step=1000.0, key="af_ac")
        passif_circ = st.number_input("Passif Circulant", step=1000.0, key="af_pc")
        
        st.header("4. Trésorerie")
        treso_actif = st.number_input("Trésorerie Actif", step=1000.0, key="af_ta")
        treso_passif = st.number_input("Trésorerie Passif", step=1000.0, key="af_tp")

    # --- 2. CALCULS ---
    frng = (cap_propres + dettes_fi) - actif_immo
    bfr = actif_circ - passif_circ
    tn = frng - bfr
    
    # Ratios (Calculs sécurisés contre la division par 0)
    roe = (rn / cap_propres * 100) if cap_propres > 0 else 0
    cap_engages = cap_propres + dettes_fi
    roce = (rex / cap_engages * 100) if cap_engages > 0 else 0
    marge = (rn / ca * 100) if ca > 0 else 0
    levier = dettes_fi / cap_propres if cap_propres > 0 else 0
    autonomie = cap_propres / (cap_propres + dettes_fi + passif_circ + treso_passif) * 100 if (cap_propres + dettes_fi + passif_circ) > 0 else 0

    # --- 3. AFFICHAGE DASHBOARD ---
    st.markdown("#### 🏗️ Équilibre Financier")
    c1, c2, c3 = st.columns(3)
    c1.metric("FRNG", f"{frng:,.0f} €", delta="Sain" if frng > 0 else "Fragile")
    c2.metric("BFR", f"{bfr:,.0f} €", delta_color="inverse", delta="Besoin" if bfr > 0 else "Ressource")
    c3.metric("Trésorerie Nette", f"{tn:,.0f} €", delta="Excédent" if tn > 0 else "Déficit")

    if tn < 0: st.error("⚠️ Trésorerie négative.")
    else: st.success("✅ Situation saine.")

    st.markdown("---")
    st.markdown("#### 🚀 Performance & Risque")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Marge Nette", f"{marge:.1f} %")
    k2.metric("ROE", f"{roe:.1f} %")
    k3.metric("Levier", f"{levier:.2f}", delta_color="inverse", delta="⚠️" if levier > 1 else "Ok")
    k4.metric("Autonomie", f"{autonomie:.0f} %")

    # --- 4. SAUVEGARDE & EXPORT ---
    st.markdown("---")
    with st.container(border=True):
        st.markdown("##### 💾 Sauvegarder & Exporter")
        c_in, c_save, c_export = st.columns([3, 1, 1]) # On fait 3 colonnes
        
        nom = c_in.text_input("Nom de l'analyse", placeholder="Ex: Cas Danone 2024")
        
        # Données complètes pour sauvegarde et PDF
        data_full = {
            "nom": nom if nom else "Analyse Sans Nom",
            "ca": ca, "rex": rex, "rn": rn,
            "cp": cap_propres, "dettes": dettes_fi, "immo": actif_immo,
            "ac": actif_circ, "pc": passif_circ,
            "ta": treso_actif, "tp": treso_passif,
            # On ajoute les résultats calculés pour le PDF
            "frng": frng, "bfr": bfr, "tn": tn,
            "marge": marge, "roe": roe, "roce": roce,
            "levier": levier, "autonomie": autonomie
        }

        # BOUTON 1 : SAUVEGARDER (JSON)
        if c_save.button("💾 Sauver", use_container_width=True):
            if sh and nom:
                # Pour l'historique, on garde le format technique pour rechargement
                json_data = json.dumps({k: v for k,v in data_full.items() if k in ["ca","rex","rn","cp","dettes","immo","ac","pc","ta","tp"]})
                save_to_history(sh, "AnalyseFi_Data", nom, json_data)
                clear_cache()
                st.success("Sauvegardé !")
                time.sleep(1); st.rerun()
            elif not nom:
                st.warning("Nom manquant !")

        # BOUTON 2 : TÉLÉCHARGER PDF (NOUVEAU !)
        # On génère le PDF en mémoire
        pdf_bytes = create_financial_pdf(data_full)
        
        c_export.download_button(
            label="📄 PDF",
            data=pdf_bytes,
            file_name=f"Analyse_{nom.replace(' ', '_') if nom else 'Financiere'}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    # --- 5. HISTORIQUE & CHARGEMENT (CORRIGÉ AVEC CALLBACK) ---
    if sh:
        st.markdown("### 📜 Historique & Chargement")
        try:
            # On utilise le cache ici
            df_history = get_history_cached(sh)
            
            if not df_history.empty:
                # Parcours inversé pour les plus récents en haut
                for index, row in df_history.iloc[::-1].iterrows():
                    if row.get('Action') in ["Analyse Fi", "AnalyseFi_Data"]:
                        
                        label = f"📅 {row.get('Date')} - {row.get('Subject')}"
                        with st.expander(label):
                            try:
                                saved_data = json.loads(row.get('Value'))
                                
                                # Résumé
                                r_frng = (saved_data['cp'] + saved_data['dettes']) - saved_data['immo']
                                r_tn = r_frng - (saved_data['ac'] - saved_data['pc'])
                                st.caption(f"Aperçu : FRNG {r_frng:,.0f} | TN {r_tn:,.0f}")
                                
                                # --- LA CORRECTION EST ICI 👇 ---
                                st.button(
                                    "🔄 Charger ces données", 
                                    key=f"btn_load_{index}",
                                    on_click=charger_analyse,  # On appelle la fonction AVANT le rerun
                                    args=(saved_data,)         # On lui passe les données
                                )
                                # --------------------------------
                                    
                            except (json.JSONDecodeError, TypeError):
                                st.info("ℹ️ Ancienne sauvegarde (Texte seul)")
                                st.text(row.get('Value'))
            else: st.info("Historique vide.")
        except Exception as e:
            if "Quota exceeded" in str(e): st.warning("⚠️ Trop de requêtes. Attends un peu...")
            else: st.warning(f"Erreur historique : {e}")

# --- PAGE BIBLIOTHÈQUE COMPTABLE (VERSION CATALOGUE) ---
def accounting_library_page(sh):
    st.markdown("### 📖 Bibliothèque d'Écritures Comptables")
    st.markdown("Base de données collaborative des schémas d'écritures.")

    # 1. CHARGEMENT / INITIALISATION AUTOMATIQUE
    df = pd.DataFrame()
    if sh:
        try:
            ws = sh.worksheet("Bibliotheque")
            data = ws.get_all_records()
            df = pd.DataFrame(data)
        except:
            # Initialisation (code identique à la version précédente)
            try:
                ws = sh.add_worksheet(title="Bibliotheque", rows="1000", cols="6")
                ws.append_row(["Schema", "Compte", "Libelle", "Sens", "Journal", "Condition"]) 
                
                # ... (Ton pack de démarrage reste ici, je ne le répète pas pour alléger la réponse) ...
                # Si tu as déjà initialisé ton sheet, ce bloc ne s'exécutera pas de toute façon.
                
                st.warning("⚠️ Onglet créé. Recharge la page si besoin.")
            except Exception as e: st.error(f"Erreur init : {e}")

    # FONCTION D'AFFICHAGE (Pour éviter de répéter le code)
    def afficher_schema(nom_schema, dataframe_source):
        # On filtre les lignes
        lines = dataframe_source[dataframe_source["Schema"] == nom_schema]
        
        # Infos contextuelles
        journal_type = lines.iloc[0]['Journal'] if 'Journal' in lines.columns else "OD"
        condition_globale = lines.iloc[0]['Condition'] if 'Condition' in lines.columns else ""
        
        # Badge
        st.markdown(f"#### ✍️ {nom_schema} <span style='background-color:{TEAL}; color:white; padding:2px 8px; border-radius:4px; font-size:12px; vertical-align:middle;'>{journal_type}</span>", unsafe_allow_html=True)
        
        # Tableau visuel
        st.markdown("""<div style="background-color:white; padding:15px; border-radius:10px; border:1px solid #e5e7eb;">""", unsafe_allow_html=True)
        
        for index, row in lines.iterrows():
            c1, c2, c3 = st.columns([1, 4, 1])
            sens = row['Sens']
            
            if sens == "Debit":
                c1.markdown(f"**{row['Compte']}**")
                c2.markdown(f"{row['Libelle']}")
                c3.markdown("🟢 Débit")
            else:
                c1.markdown(f"<div style='text-align:right'>**{row['Compte']}**</div>", unsafe_allow_html=True)
                c2.markdown(f"<div style='text-align:right'>{row['Libelle']}</div>", unsafe_allow_html=True)
                c3.markdown("🔴 Crédit")
            
            # Condition spécifique à la ligne
            if 'Condition' in row and row['Condition'] and row['Condition'] != condition_globale:
                    st.caption(f"└─ 💡 *{row['Condition']}*")
                    
            st.markdown("<hr style='margin:5px 0; border-top: 1px dashed #eee;'>", unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        if condition_globale and len(str(condition_globale)) > 3:
            st.info(f"💡 **Note technique :** {condition_globale}")


    # 2. INTERFACE
    if not df.empty:
        # Nettoyage des données pour éviter les bugs de tri
        df = df.astype(str)
        schemas = sorted(list(set(df["Schema"])))
        
        c_search, c_add = st.columns([3, 1])
        with c_search:
            # Option vide par défaut
            search = st.selectbox("🔍 Rechercher une écriture (ou laisser vide pour tout voir)", [""] + schemas)

        # 3. AFFICHAGE INTELLIGENT
        if search:
            # CAS A : UNE RECHERCHE EST SÉLECTIONNÉE -> On affiche juste celle-là
            st.write("")
            afficher_schema(search, df)
            
        else:
            # CAS B : RIEN SÉLECTIONNÉ -> On affiche TOUT le catalogue
            st.write("")
            st.markdown("### 📑 Catalogue complet")
            st.caption(f"{len(schemas)} schémas disponibles")
            
            for s in schemas:
                # On utilise des expanders pour ne pas polluer la page
                with st.expander(f"📂 {s}"):
                    afficher_schema(s, df)

    # 4. FORMULAIRE D'AJOUT
    st.write("")
    st.markdown("---")
    with st.expander("➕ Ajouter un nouveau schéma"):
        with st.form("add_ecriture"):
            c_nom, c_journ = st.columns([3, 1])
            f_nom = c_nom.text_input("Nom du Schéma", value=search if search else "")
            f_journ = c_journ.selectbox("Type Journal", ["ACHATS", "VENTES", "OD", "BANQUE", "CAISSE", "ANOUVEAUX"])
            
            c_f1, c_f2, c_f3 = st.columns([1, 2, 1])
            f_cpt = c_f1.text_input("Compte (Ex: 44571)")
            f_lib = c_f2.text_input("Libellé")
            f_sens = c_f3.selectbox("Sens", ["Debit", "Credit"])
            
            f_cond = st.text_input("Condition / Formule")
            
            if st.form_submit_button("Ajouter cette ligne"):
                if sh and f_nom and f_cpt:
                    sh.worksheet("Bibliotheque").append_row([f_nom, f_cpt, f_lib, f_sens, f_journ, f_cond])
                    st.success("Ligne ajoutée !"); time.sleep(1); st.rerun()
# --- MAIN ---
if __name__ == "__main__":
    sh, drive = get_google_services()
    selected_page = sidebar_menu()
    
    # Synchronisation Navigation : Si la sidebar change, on met à jour la vue
    if selected_page != st.session_state.current_view:
        st.session_state.current_view = selected_page
        st.session_state.selected_subject = None
        st.rerun()

    # --- DANS LE MAIN (En bas du fichier) ---
    if st.session_state.current_view == "Dashboard": dashboard_page(sh)
    elif st.session_state.current_view == "Mes Cours":
        if st.session_state.selected_subject: subject_detail_page(sh, drive, st.session_state.selected_subject)
        else: courses_grid_page()
    elif st.session_state.current_view == "Candidatures": candidatures_page(sh)
    # AJOUTER CETTE LIGNE 👇
    elif st.session_state.current_view == "Analyse Fi": financial_analysis_page(sh)

    elif st.session_state.current_view == "Bibliothèque": accounting_library_page(sh)
    # --------------------
    elif st.session_state.current_view == "Focus Room": focus_room_page()
