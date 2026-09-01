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
MODEL_NAME = "gemini-1.5-flash-latest"  # Modello corretto e compatibile
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
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['it', 'en', 'es', 'fr', 'de'])
        full_text = " ".join([item['text'] for item in transcript_list])
        if not full_text:
            return None, "La trascrizione recuperata risulta vuota."
        return full_text, None
    except (TranscriptsDisabled, NoTranscriptFound):
        return None, "I sottotitoli sono disabilitati dal proprietario per questo video."
    except VideoUnavailable:
        return None, "Il video non è disponibile, è privato o è stato rimosso."
    except Exception as exc:
        return None, (
            "Impossibile contattare YouTube. È probabile che il server cloud sia "
            f"temporaneamente bloccato dall'IP-throttling di YouTube. Dettagli tecnici: {exc}"
        )


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
