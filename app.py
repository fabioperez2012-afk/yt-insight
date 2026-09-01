"""
YT Insight — AI Video Report Generator
========================================
Applicazione Streamlit enterprise-grade che estrae la trascrizione di un
video YouTube e genera, tramite Google Gemini, un report di sintesi
professionale con tabelle, glossario e una mappa concettuale (Mermaid.js).

Architettura di sicurezza:
- Nessuna API Key hardcoded nel codice sorgente.
- Modello "Bring Your Own Key" (BYOK): la chiave viene inserita dall'utente
  in un campo password nella sidebar e vive esclusivamente in
  st.session_state (memoria volatile della sessione corrente).
- La chiave non viene mai scritta su disco, log, database o file di
  configurazione.

Autore: generato come deliverable per deploy pubblico su GitHub /
Streamlit Community Cloud.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple, List

import requests
import streamlit as st
import streamlit.components.v1 as components

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

from google import genai
from google.genai import types


# ============================================================================
# CONFIGURAZIONE GLOBALE
# ============================================================================

APP_TITLE = "YT Insight"
APP_TAGLINE = "AI Video Report Generator"
MODEL_NAME = "gemini-1.5-flash"  # Modello gratuito, ottenibile senza carta di credito
MAX_TRANSCRIPT_CHARS = 150_000   # Soglia di sicurezza per evitare payload eccessivi
GEMINI_API_KEY_URL = "https://aistudio.google.com/app/apikey"

st.set_page_config(
    page_title=f"{APP_TITLE} — {APP_TAGLINE}",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================================
# CUSTOM CSS — DARK MODE SAAS DASHBOARD
# ============================================================================

def inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Sfondo generale */
        .stApp {
            background: radial-gradient(circle at 15% 0%, #171a26 0%, #0d0f16 45%, #0a0b10 100%);
            color: #e6e8f0;
        }

        /* Header principale nascosto (usiamo header custom) */
        header[data-testid="stHeader"] {
            background: transparent;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #12141f 0%, #0d0f17 100%);
            border-right: 1px solid #23263a;
        }
        section[data-testid="stSidebar"] .stMarkdown p {
            color: #b6bacb;
        }

        /* Titolo hero */
        .hero-wrap {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 4px;
        }
        .hero-icon {
            font-size: 2.4rem;
            filter: drop-shadow(0 0 18px rgba(124, 92, 255, 0.55));
        }
        .hero-title {
            font-size: 2.05rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            background: linear-gradient(90deg, #a48bff 0%, #6f9bff 55%, #4fd8c4 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
        }
        .hero-sub {
            color: #8b90a6;
            font-size: 0.98rem;
            margin-top: 2px;
            margin-bottom: 22px;
        }

        /* Badge pill */
        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            border: 1px solid #2c3049;
        }
        .badge-purple { background: rgba(124, 92, 255, 0.14); color: #b9a4ff; border-color: rgba(124,92,255,0.35); }
        .badge-green  { background: rgba(53, 214, 156, 0.14); color: #6fe3b8; border-color: rgba(53,214,156,0.35); }
        .badge-amber  { background: rgba(255, 176, 59, 0.14); color: #ffcb80; border-color: rgba(255,176,59,0.35); }
        .badge-blue   { background: rgba(79, 155, 255, 0.14); color: #8fbaff; border-color: rgba(79,155,255,0.35); }

        /* Card generica */
        .glass-card {
            background: linear-gradient(160deg, rgba(255,255,255,0.035), rgba(255,255,255,0.01));
            border: 1px solid #23263a;
            border-radius: 18px;
            padding: 22px 24px;
            margin-bottom: 18px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.25);
        }

        /* Input di testo */
        .stTextInput input, .stTextArea textarea {
            background-color: #12141f !important;
            border: 1px solid #2a2e45 !important;
            border-radius: 12px !important;
            color: #e6e8f0 !important;
        }
        .stTextInput input:focus, .stTextArea textarea:focus {
            border-color: #7c5cff !important;
            box-shadow: 0 0 0 1px #7c5cff !important;
        }

        /* Bottoni */
        .stButton > button, .stDownloadButton > button {
            background: linear-gradient(90deg, #7c5cff 0%, #5c8dff 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            padding: 0.55rem 1.1rem;
            transition: all 0.15s ease-in-out;
            box-shadow: 0 4px 18px rgba(124, 92, 255, 0.28);
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 22px rgba(124, 92, 255, 0.4);
        }
        .stButton > button:disabled {
            background: #23263a;
            color: #5a5f77;
            box-shadow: none;
        }

        /* Tabs */
        button[data-baseweb="tab"] {
            font-weight: 600;
            color: #8b90a6;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: #b9a4ff !important;
        }
        div[data-baseweb="tab-highlight"] {
            background-color: #7c5cff !important;
        }
        div[data-baseweb="tab-border"] {
            background-color: #23263a !important;
        }

        /* Tabelle Markdown */
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 12px 0 20px 0;
            font-size: 0.92rem;
        }
        table th {
            background: #171a28;
            color: #b9a4ff;
            text-align: left;
            padding: 10px 14px;
            border-bottom: 1px solid #2a2e45;
        }
        table td {
            padding: 9px 14px;
            border-bottom: 1px solid #1d2032;
            color: #d3d6e4;
        }
        table tr:hover td {
            background: rgba(124, 92, 255, 0.05);
        }

        /* Divider più discreto */
        hr {
            border-color: #21243a !important;
        }

        /* Alert boxes coerenti col tema */
        div[data-testid="stAlert"] {
            border-radius: 14px;
            border: 1px solid #23263a;
        }

        /* Expander */
        details {
            background: rgba(255,255,255,0.02);
            border: 1px solid #23263a !important;
            border-radius: 12px !important;
        }

        /* Footer discreto */
        .app-footer {
            text-align: center;
            color: #4c5069;
            font-size: 0.78rem;
            margin-top: 40px;
            padding-top: 16px;
            border-top: 1px solid #1c1f30;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================================
# UTILITY — ESTRAZIONE ID VIDEO E METADATI
# ============================================================================

def extract_video_id(url: str) -> Optional[str]:
    """Estrae l'ID a 11 caratteri di un video YouTube da vari formati di URL."""
    patterns = [
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/live/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",  # solo ID incollato direttamente
    ]
    for pattern in patterns:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    return None


def fetch_video_title(video_id: str) -> Optional[str]:
    """Recupera il titolo del video tramite l'endpoint oEmbed pubblico (nessuna API key richiesta)."""
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=6,
        )
        if resp.status_code == 200:
            return resp.json().get("title")
    except Exception:
        pass
    return None


# ============================================================================
# ESTRAZIONE TRASCRIZIONE — CON GESTIONE ERRORE ZERO
# ============================================================================

def _segment_text(segment) -> str:
    """Compatibilità tra le diverse versioni di youtube-transcript-api
    (alcune restituiscono dict, altre oggetti FetchedTranscriptSnippet)."""
    if isinstance(segment, dict):
        return segment.get("text", "")
    return getattr(segment, "text", "")


def fetch_youtube_transcript(video_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Tenta l'estrazione automatica della trascrizione.
    Restituisce (testo, None) in caso di successo oppure (None, messaggio_errore).
    """
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except TranscriptsDisabled:
        return None, "I sottotitoli sono disabilitati dal proprietario per questo video."
    except VideoUnavailable:
        return None, "Il video non è disponibile, è privato o è stato rimosso."
    except Exception as exc:
        return None, (
            "Impossibile contattare YouTube. È probabile che il server cloud sia "
            f"temporaneamente bloccato dall'IP-throttling di YouTube. Dettagli tecnici: {exc}"
        )

    preferred_languages = ["it", "en"]
    chosen = None

    try:
        chosen = transcript_list.find_transcript(preferred_languages)
    except NoTranscriptFound:
        try:
            chosen = transcript_list.find_generated_transcript(preferred_languages)
        except NoTranscriptFound:
            for t in transcript_list:
                chosen = t
                break

    if chosen is None:
        return None, "Nessuna trascrizione disponibile in alcuna lingua per questo video."

    try:
        fetched = chosen.fetch()
    except Exception as exc:
        return None, f"Errore durante il download della trascrizione: {exc}"

    full_text = " ".join(
        _segment_text(seg).strip() for seg in fetched if _segment_text(seg).strip()
    )

    if not full_text:
        return None, "La trascrizione recuperata risulta vuota."

    return full_text, None


# ============================================================================
# GENERAZIONE REPORT — GOOGLE GEMINI
# ============================================================================

SYSTEM_PROMPT = """Sei un analista didattico ed esperto di comunicazione visiva. Il tuo compito è trasformare la trascrizione di un video YouTube in un report professionale in lingua italiana, perfettamente formattato in Markdown, che sarà mostrato all'interno di una dashboard web.

Segui SCRUPOLOSAMENTE questa struttura, usando esattamente questi titoli di sezione (##):

## 1. Executive Summary
Scrivi una panoramica completa, dettagliata ed esaustiva del contenuto del video (minimo 150 parole). Deve permettere a chi legge di capire l'intero contenuto senza guardare il video.

## 2. Indice Tematico & Punti Salienti
Organizza i concetti chiave in sottosezioni tematiche (usa titoli ###). Per ogni sottosezione usa elenchi puntati con parole chiave in **grassetto** per massimizzare la scansionabilità. Sii approfondito ed esaustivo, non limitarti a poche righe.

## 3. Tabelle Dati & Comparative
Se nel video vengono menzionati numeri, statistiche, confronti, pro/contro, step di un processo, timeline o caratteristiche di prodotti/strumenti, riportali SEMPRE in una o più tabelle Markdown ben formattate (usa il carattere pipe |). Se non ci sono dati numerici espliciti, crea comunque almeno una tabella riassuntiva dei concetti principali con colonne "Concetto" e "Descrizione". Non lasciare mai questa sezione vuota.

## 4. Mappa Concettuale
Genera un diagramma Mermaid.js valido (flowchart o mindmap) che rappresenti visivamente la struttura logica e le relazioni tra i concetti chiave del video. Il codice deve essere racchiuso in un blocco di codice con linguaggio "mermaid", ad esempio:
```mermaid
flowchart TD
    A[Concetto Centrale] --> B[Sotto-concetto 1]
    A --> C[Sotto-concetto 2]
```
Usa la sintassi `flowchart TD` (top-down) per garantire la massima compatibilità di rendering. Usa nomi di nodo brevi e testo tra parentesi quadre. Includi almeno 6-10 nodi collegati in modo logico. NON usare caratteri speciali che possano rompere la sintassi Mermaid (evita parentesi tonde dentro le etichette, virgolette doppie annidate, punto e virgola).

## 5. Glossario Tecnico
Elenca in formato puntato i termini tecnici, gli acronimi o i concetti complessi citati nel video, ciascuno con una spiegazione chiara e sintetica in massimo due righe. Formato: **Termine** — spiegazione.

Regole generali:
- Scrivi sempre in italiano, indipendentemente dalla lingua originale del video.
- Sii fedele al contenuto della trascrizione: non inventare dati, cifre o fatti non presenti nel testo.
- Se la trascrizione è incompleta, breve o poco chiara, fai comunque del tuo meglio producendo un report proporzionato alla quantità di informazioni disponibili, senza inventare contenuti.
- Non aggiungere introduzioni tipo "Ecco il report": inizia direttamente con "## 1. Executive Summary".
- Non uscire mai dalla struttura Markdown richiesta.
"""


def generate_report(api_key: str, transcript: str, video_title: Optional[str]) -> str:
    """Invia la trascrizione a Gemini e restituisce il report Markdown completo."""
    client = genai.Client(api_key=api_key)

    truncated = transcript
    truncation_notice = ""
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        truncated = transcript[:MAX_TRANSCRIPT_CHARS]
        truncation_notice = (
            "\n\n[NOTA: la trascrizione originale era molto più lunga ed è stata troncata "
            "per motivi tecnici. Basa l'analisi sulla porzione fornita.]"
        )

    title_block = f"Titolo del video: {video_title}\n\n" if video_title else ""

    user_prompt = (
        f"{title_block}Trascrizione completa del video da analizzare:\n"
        f'"""\n{truncated}\n"""{truncation_notice}'
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.4,
            max_output_tokens=8192,
        ),
    )

    if not response.text:
        raise RuntimeError("Il modello non ha restituito alcun contenuto testuale.")

    return response.text


# ============================================================================
# PARSING E RENDERING DEL REPORT
# ============================================================================

def extract_mermaid_blocks(markdown_text: str) -> List[str]:
    pattern = r"```mermaid\s*\n(.*?)```"
    return [m.strip() for m in re.findall(pattern, markdown_text, re.DOTALL)]


def extract_tables(markdown_text: str) -> List[str]:
    """Estrae i blocchi di tabelle Markdown (righe consecutive che iniziano/finiscono con |)."""
    lines = markdown_text.split("\n")
    tables: List[str] = []
    current: List[str] = []
    in_table = False

    for line in lines:
        if re.match(r"^\s*\|.*\|\s*$", line):
            current.append(line)
            in_table = True
        else:
            if in_table and current:
                tables.append("\n".join(current))
                current = []
            in_table = False

    if current:
        tables.append("\n".join(current))

    return tables


def render_mermaid(code: str, height: int = 480) -> None:
    """Renderizza un diagramma Mermaid.js come vero grafico visivo tramite components.html."""
    safe_code = code.replace("</script>", "<\\/script>")
    html = f"""
    <div style="background:#12141f;border-radius:16px;padding:22px;border:1px solid #262a3a;">
        <div class="mermaid" style="display:flex;justify-content:center;">
{safe_code}
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: "dark",
            securityLevel: "loose",
            themeVariables: {{
                primaryColor: "#7c5cff",
                primaryTextColor: "#e6e8f0",
                primaryBorderColor: "#a48bff",
                lineColor: "#5c8dff",
                secondaryColor: "#12141f",
                tertiaryColor: "#171a28",
                background: "#12141f",
                mainBkg: "#171a28",
                nodeBorder: "#7c5cff",
                clusterBkg: "#171a28",
                fontFamily: "Inter, sans-serif"
            }}
        }});
    </script>
    """
    components.html(html, height=height, scrolling=True)


def render_report_with_diagrams(report_text: str) -> None:
    """Renderizza il report sezione per sezione, sostituendo i blocchi ```mermaid
    con il diagramma visivo effettivo invece del codice grezzo."""
    parts = re.split(r"(```mermaid\s*\n.*?```)", report_text, flags=re.DOTALL)
    for part in parts:
        mermaid_match = re.match(r"```mermaid\s*\n(.*?)```", part, re.DOTALL)
        if mermaid_match:
            st.markdown("#### 🗺️ Mappa Concettuale interattiva")
            render_mermaid(mermaid_match.group(1).strip())
        elif part.strip():
            st.markdown(part, unsafe_allow_html=False)


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


# ============================================================================
# SESSION STATE
# ============================================================================

def init_session_state() -> None:
    defaults = {
        "api_key": "",
        "report": None,
        "transcript": None,
        "video_title": None,
        "video_id": None,
        "manual_mode": False,
        "last_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_results() -> None:
    st.session_state.report = None
    st.session_state.transcript = None
    st.session_state.video_title = None
    st.session_state.manual_mode = False
    st.session_state.last_error = None


# ============================================================================
# SIDEBAR — GESTIONE API KEY (BYOK)
# ============================================================================

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                <span style="font-size:1.6rem;">🔑</span>
                <span style="font-weight:700;font-size:1.1rem;color:#e6e8f0;">Autenticazione</span>
            </div>
            <p style="color:#8b90a6;font-size:0.85rem;margin-top:-4px;">
                Modello BYOK — la tua chiave resta solo in questa sessione.
            </p>
            """,
            unsafe_allow_html=True,
        )

        api_key_input = st.text_input(
            "Google Gemini API Key",
            type="password",
            value=st.session_state.api_key,
            placeholder="AIzaSy...",
            help="La chiave viene mantenuta solo in memoria per la sessione corrente e non è mai salvata su disco.",
        )
        st.session_state.api_key = api_key_input.strip()

        if not st.session_state.api_key:
            st.markdown(
                """
                <div class="glass-card" style="padding:16px 18px;">
                    <span class="badge badge-amber">🆓 Chiave gratuita</span>
                    <p style="margin-top:10px;color:#c7cadb;font-size:0.86rem;line-height:1.5;">
                        Per generare i report ti serve una API Key gratuita di Google Gemini
                        (nessuna carta di credito richiesta):
                    </p>
                    <ol style="color:#c7cadb;font-size:0.86rem;padding-left:18px;line-height:1.6;">
                        <li>Vai su <b>Google AI Studio</b></li>
                        <li>Accedi con il tuo account Google</li>
                        <li>Clicca su <b>"Create API Key"</b> e copiala qui sopra</li>
                    </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button("🔗 Ottieni la tua API Key gratuita", GEMINI_API_KEY_URL, use_container_width=True)
        else:
            st.markdown(
                '<span class="badge badge-green">✅ Chiave impostata per questa sessione</span>',
                unsafe_allow_html=True,
            )

        st.divider()

        with st.expander("🔒 Privacy & Sicurezza"):
            st.markdown(
                """
                - La chiave API **non è mai** scritta su file, log o database.
                - Vive esclusivamente in `st.session_state`, in memoria volatile.
                - Alla chiusura o al refresh della scheda, la chiave viene **eliminata**.
                - Il codice sorgente di questa app **non contiene alcun segreto**.
                """
            )

        st.divider()
        st.markdown(
            """
            <p style="color:#4c5069;font-size:0.75rem;">
            YT Insight v1.0 · Powered by Google Gemini 1.5 Flash
            </p>
            """,
            unsafe_allow_html=True,
        )


# ============================================================================
# HEADER
# ============================================================================

def render_header() -> None:
    st.markdown(
        f"""
        <div class="hero-wrap">
            <span class="hero-icon">🎬</span>
            <span class="hero-title">{APP_TITLE}</span>
        </div>
        <p class="hero-sub">{APP_TAGLINE} — trasforma qualsiasi video YouTube in un report professionale con tabelle, glossario e mappa concettuale.</p>
        """,
        unsafe_allow_html=True,
    )


# ============================================================================
# BLOCCO DI GENERAZIONE (COMUNE A FLUSSO AUTOMATICO E MANUALE)
# ============================================================================

def run_generation(transcript_text: str) -> None:
    with st.spinner("🤖 L'IA sta analizzando il contenuto e componendo il report..."):
        try:
            report = generate_report(
                st.session_state.api_key, transcript_text, st.session_state.video_title
            )
            st.session_state.report = report
            st.session_state.transcript = transcript_text
            st.session_state.manual_mode = False
            st.session_state.last_error = None
        except Exception as exc:
            st.session_state.last_error = str(exc)
            st.session_state.report = None


# ============================================================================
# MAIN APP
# ============================================================================

def main() -> None:
    inject_custom_css()
    init_session_state()
    render_sidebar()
    render_header()

    # -------------------------------------------------------------- Input --
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    col_url, col_btn = st.columns([4, 1.1])
    with col_url:
        url = st.text_input(
            "URL del video YouTube",
            placeholder="https://www.youtube.com/watch?v=...",
            label_visibility="collapsed",
        )
    with col_btn:
        generate_clicked = st.button(
            "🚀 Genera Report",
            use_container_width=True,
            type="primary",
            disabled=not st.session_state.api_key,
        )
    if not st.session_state.api_key:
        st.caption("⚠️ Inserisci una API Key valida nella sidebar per abilitare la generazione.")
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------------------------------------------- Flusso automatico --
    if generate_clicked:
        reset_results()
        if not url.strip():
            st.warning("Inserisci un URL YouTube valido prima di procedere.")
        else:
            video_id = extract_video_id(url)
            if not video_id:
                st.error("L'URL inserito non sembra essere un link YouTube valido.")
            else:
                st.session_state.video_id = video_id
                with st.spinner("📡 Recupero della trascrizione da YouTube..."):
                    transcript_text, error_msg = fetch_youtube_transcript(video_id)
                    st.session_state.video_title = fetch_video_title(video_id)

                if transcript_text:
                    run_generation(transcript_text)
                else:
                    st.session_state.manual_mode = True
                    st.warning(f"⚠️ Estrazione automatica non riuscita: {error_msg}")

    # ------------------------------------------------------ Fallback manuale --
    if st.session_state.manual_mode and not st.session_state.report:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown(
            '<span class="badge badge-blue">🛟 Modalità di recupero</span>',
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <p style="color:#c7cadb;margin-top:10px;">
            L'estrazione automatica dei sottotitoli non è riuscita (sottotitoli disabilitati
            oppure blocco temporaneo dell'IP del server cloud da parte di YouTube).
            Incolla qui sotto la trascrizione del video, oppure carica un file <code>.txt</code>,
            per generare comunque il report con l'IA.
            </p>
            """,
            unsafe_allow_html=True,
        )

        manual_text = st.text_area(
            "Incolla qui la trascrizione",
            height=240,
            placeholder="Incolla il testo della trascrizione del video...",
        )
        uploaded_file = st.file_uploader("...oppure carica un file .txt", type=["txt"])
        if uploaded_file is not None:
            manual_text = uploaded_file.read().decode("utf-8", errors="ignore")

        manual_clicked = st.button(
            "✨ Genera Report da testo manuale",
            type="primary",
            disabled=not st.session_state.api_key,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if manual_clicked:
            if manual_text and manual_text.strip():
                run_generation(manual_text.strip())
            else:
                st.warning("Incolla del testo o carica un file prima di continuare.")

    # ------------------------------------------------------------- Errori --
    if st.session_state.last_error:
        st.error(
            "❌ Errore nella generazione del report. Verifica che la API Key sia corretta "
            f"e riprova.\n\nDettagli: {st.session_state.last_error}"
        )

    # ---------------------------------------------------------- Risultati --
    if st.session_state.report:
        report = st.session_state.report
        transcript = st.session_state.transcript or ""

        # Badge riassuntivi
        badges_html = (
            f'<span class="badge badge-purple">📄 {word_count(report)} parole nel report</span> '
            f'<span class="badge badge-green">🗣️ {word_count(transcript)} parole trascritte</span>'
        )
        if st.session_state.video_title:
            badges_html += f' <span class="badge badge-blue">🎬 {st.session_state.video_title}</span>'
        st.markdown(badges_html, unsafe_allow_html=True)
        st.write("")

        tab1, tab2, tab3 = st.tabs(
            ["📊 Report AI & Diagrammi", "📑 Tabelle Dati & Dettagli", "📝 Trascrizione Testuale"]
        )

        with tab1:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            render_report_with_diagrams(report)
            st.markdown("</div>", unsafe_allow_html=True)

            st.divider()
            col_a, col_b = st.columns(2)
            with col_a:
                st.download_button(
                    "⬇️ Scarica Report completo (.md)",
                    data=report,
                    file_name=f"report_{st.session_state.video_id or 'youtube'}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with col_b:
                with st.expander("📋 Copia Markdown grezzo"):
                    st.code(report, language="markdown")

        with tab2:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            tables = extract_tables(report)
            if tables:
                st.markdown(f"**{len(tables)} tabella/e rilevata/e nel report:**")
                for i, table in enumerate(tables, start=1):
                    st.markdown(f"###### Tabella {i}")
                    st.markdown(table)
            else:
                st.info("Nessuna tabella Markdown rilevata automaticamente nel report generato.")

            mermaid_blocks = extract_mermaid_blocks(report)
            if mermaid_blocks:
                st.markdown("###### Codice sorgente Mermaid.js")
                for block in mermaid_blocks:
                    st.code(block, language="text")
            st.markdown("</div>", unsafe_allow_html=True)

        with tab3:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.text_area(
                "Trascrizione completa utilizzata per l'analisi",
                value=transcript,
                height=480,
            )
            st.download_button(
                "⬇️ Scarica Trascrizione (.txt)",
                data=transcript,
                file_name=f"trascrizione_{st.session_state.video_id or 'youtube'}.txt",
                mime="text/plain",
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="app-footer">YT Insight — nessun dato personale o chiave API viene mai memorizzato lato server.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
