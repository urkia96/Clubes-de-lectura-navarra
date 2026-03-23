import streamlit as st
import pandas as pd
import faiss
import pickle
from sentence_transformers import SentenceTransformer
import os
import unicodedata
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import json
import gc
import numpy as np

# --- CONFIG ---
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

# --- SESSION ---
if "idioma" not in st.session_state:
    st.session_state.idioma = "Castellano"

# --- PATHS ---
PATH_RECO = "recomendador"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_SERENDIPIA = f"{PATH_RECO}/serendipia.png"
RUTA_PORTADAS = "portadas"

# --- UTILS ---
def normalizar_texto(texto):
    if not isinstance(texto, str): return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

def col_lang(col_base, dataframe):
    if st.session_state.idioma == "Euskera":
        col_eus = f"{col_base}_eus"
        if col_eus in dataframe.columns:
            return col_eus
    return col_base

# --- IDIOMA ---
col_main, col_lang_sel = st.columns([12,1])
with col_lang_sel:
    idioma_actual = st.selectbox("🌐", ["Castellano","Euskera"],
                                index=0 if st.session_state.idioma=="Castellano" else 1)
    st.session_state.idioma = idioma_actual

texts = {
    "Castellano": {
        "titulo":"Clubes de Lectura de Navarra",
        "subtitulo":"Nafarroako Irakurketa Klubak",
        "sidebar_tit":"🎯 Panel de Control",
        "exp_gral":"⚙️ Filtros generales",
        "exp_cont":"📖 Filtros de contenido",
        "f_idioma":"🌍 Idioma",
        "f_publico":"👥 Público",
        "f_genero_aut":"👤 Género Autor/a",
        "f_editorial":"📚 Editorial",
        "f_paginas":"📄 Número de páginas",
        "f_local":"🏠 Autores locales",
        "f_euskera":"📘 Disponible en euskera",
        "f_ia_gen":"📂 Género",
        "f_ia_sub":"🏷️ Subgénero",
        "tab1":"📖 Búsqueda por autor/título",
        "tab2":"✨ Búsqueda libre",
        "tab3":"🔍 Lotes similares",
        "tab4":"🎲 Búsqueda aleatoria",
        "resumen_btn":"Ver resumen",
        "pags_label":"págs",
        "boton_txt":"¡Sorpréndeme!"
    },
    "Euskera": {
        "titulo":"Nafarroako Irakurketa Klubak",
        "subtitulo":"Clubes de Lectura de Navarra",
        "sidebar_tit":"🎯 Kontrol Panela",
        "exp_gral":"⚙️ Iragazki orokorrak",
        "exp_cont":"📖 Edukiaren iragazkiak",
        "f_idioma":"🌍 Hizkuntza",
        "f_publico":"👥 Publikoa",
        "f_genero_aut":"👤 Egilearen generoa",
        "f_editorial":"📚 Argitaletxea",
        "f_paginas":"📄 Orrialde kopurua",
        "f_local":"🏠 Bertako autoreak",
        "f_euskera":"📘 Euskaraz eskuragarri",
        "f_ia_gen":"📂 Generoa",
        "f_ia_sub":"🏷️ Azpigeneroa",
        "tab1":"📖 Izenburua / Egilea",
        "tab2":"✨ Bilaketa librea",
        "tab3":"🔍 Lote antzekoak",
        "tab4":"🎲 Zorizkoa",
        "resumen_btn":"Ikusi laburpena",
        "pags_label":"orr",
        "boton_txt":"Harritu nazazu!"
    }
}
t = texts[st.session_state.idioma]

# --- DATA ---
@st.cache_resource
def load_resources():
    df = pd.read_excel(f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx")
    df.columns = df.columns.str.strip()

    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)

    with open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_small.pkl","rb") as f:
        df_ia_meta = pickle.load(f)

    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_small.index")
    model = SentenceTransformer('intfloat/multilingual-e5-small')

    return df, df_ia_meta, index, model

df, df_ia_meta, index, model = load_resources()

# --- GOOGLE SHEETS ---
@st.cache_resource
def conectar_sheets():
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        gc_client = gspread.authorize(creds)
        return gc_client.open_by_url(st.secrets["GSHEET_URL"]).sheet1
    except:
        return None

def guardar_voto(lote, titulo, valor, query):
    sheet = conectar_sheets()
    if sheet:
        sheet.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            lote, titulo,
            "👍" if valor==1 else "👎",
            query
        ])

# --- CARD ---
@st.fragment
def mostrar_card(r, context):
    lote_id = str(r.get('Nº lote',''))

    with st.container(border=True):
        col_img, col_content, col_vote = st.columns([1,3,0.5])

        with col_content:
            st.markdown(f"### {r.get('Título')}")
            st.write(r.get('Autor'))

            st.caption(
                f"{r.get('Editorial')} | "
                f"{r.get(col_lang('Idioma',df))} | "
                f"{r.get('Páginas')} {t['pags_label']} | "
                f"{r.get(col_lang('Público',df))}"
            )

            st.write(
                f"**{r.get(col_lang('Genero_Principal_IA',df))}**: "
                f"{r.get(col_lang('Subgeneros_Limpios_IA',df))}"
            )

            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra'))

        with col_vote:
            if st.button("👍", key=f"u_{lote_id}_{context}"):
                guardar_voto(lote_id, r.get('Título'),1,context)
            if st.button("👎", key=f"d_{lote_id}_{context}"):
                guardar_voto(lote_id, r.get('Título'),0,context)

# --- FILTROS ---
st.sidebar.title(t["sidebar_tit"])

with st.sidebar.expander(t["exp_gral"]):
    col_pub = col_lang('Público',df)
    col_gen = col_lang('genero_fix',df)

    f_publico = st.multiselect(t["f_publico"], df[col_pub].dropna().unique())
    f_genero = st.multiselect(t["f_genero_aut"], df[col_gen].dropna().unique())
    f_euskera = st.checkbox(t["f_euskera"])

def filtrar(dataframe):
    temp = dataframe.copy()

    if f_publico:
        temp = temp[temp[col_lang('Público',df)].isin(f_publico)]

    if f_genero:
        temp = temp[temp[col_lang('genero_fix',df)].isin(f_genero)]

    if f_euskera:
        temp = temp[temp['Idioma_eus'].notna()]

    return temp

# --- UI ---
st.title(t["titulo"])
st.caption(t["subtitulo"])

tab1,tab2,tab3,tab4 = st.tabs([t["tab1"],t["tab2"],t["tab3"],t["tab4"]])

# TAB1
with tab1:
    q = st.text_input("Buscar")
    if q:
        res = filtrar(df)
        res = res[res['titulo_norm'].str.contains(normalizar_texto(q), na=False)]
        for _,r in res.head(10).iterrows():
            mostrar_card(r,q)

# TAB4 random
with tab4:
    if st.button(t["boton_txt"]):
        mostrar_card(filtrar(df).sample(1).iloc[0],"random")
