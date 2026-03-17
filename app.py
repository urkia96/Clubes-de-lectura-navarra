import streamlit as st
import pandas as pd
import faiss
import pickle
from sentence_transformers import SentenceTransformer
import numpy as np
import os
import torch
import glob
import re
from datetime import datetime

# 1. CONFIGURACIÓN E IDIOMA
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

# ESTRUCTURA DE RUTAS (app.py en la raíz)
PATH_RECO = "recomendador"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_BOTON_RANDOM = f"{PATH_RECO}/serendipia.png"
PATH_FEEDBACK = f"{PATH_RECO}/feedback_tesis.csv"
RUTA_PORTADAS = "portadas"

col_main, col_lang = st.columns([12, 5])
with col_lang:
    idioma_interfaz = st.selectbox("🌐", ["Castellano", "Euskera"])

texts = {
    "Castellano": {
        "titulo": "Clubes de Lectura de Navarra", 
        "subtitulo": "Nafarroako Irakurketa Klubak",
        "sidebar_tit": "🎯 Panel de Control", 
        "f_idioma": "🌍 Idioma", 
        "f_publico": "👥 Público",
        "f_genero": "👤 Género Autor/a", 
        "f_editorial": "📚 Editorial",
        "f_paginas": "📄 Máx Páginas",
        "f_local": "🏠 Solo Locales", 
        "tab1": "✨ Semántica", 
        "tab2": "🔍 Por Lote", 
        "tab3": "🎲 Serendipia",
        "placeholder": "Ej: Novela histórica en Navarra", 
        "input_query": "¿Qué quieres leer hoy?",
        "lote_input": "Introduce el código del lote:", 
        "resumen_btn": "Ver resumen", 
        "pags_label": "págs", 
        "thanks": "✅ Voto registrado", 
        "ask": "¿Te gusta esta recomendación?",
        "boton_txt": "¡Sorpréndeme!",
        "serendipia_txt": "Deja que el azar elija por ti:"
    },
    "Euskera": {
        "titulo": "Nafarroako Irakurketa Klubak", 
        "subtitulo": "Clubes de Lectura de Navarra",
        "sidebar_tit": "🎯 Kontrol Panela", 
        "f_idioma": "🌍 Hizkuntza", 
        "f_publico": "👥 Publikoa",
        "f_genero": "👤 Egilearen generoa", 
        "f_editorial": "📚 Argitaletxea",
        "f_paginas": "📄 Orrialde kopurua",
        "f_local": "🏠 Bertakoak soilik", 
        "tab1": "✨ Semantikoa", 
        "tab2": "🔍 Lote bidez", 
        "tab3": "🎲 Kasualitatea",
        "placeholder": "Adibidez: Abentura liburuak", 
        "input_query": "Zer irakurri nahi duzu gaur?",
        "lote_input": "Sartu lote kodea:", 
        "resumen_btn": "Ikusi laburpena", 
        "pags_label": "orr", 
        "thanks": "✅ Iritzia gordeta", 
        "ask": "Gogoko duzu?",
        "boton_txt": "Harritu nazazu!",
        "serendipia_txt": "Utzi zoriari zure ordez aukeratzen:"
    }
}
t = texts[idioma_interfaz]

# 2. CARGA DE RECURSOS (Entrando en la carpeta recomendador)
@st.cache_resource
def load_resources():
    df_ia = pickle.load(open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb"))
    df_ia['Nº lote'] = df_ia['Nº lote'].astype(str).str.strip()
    
    excel_path = f"{PATH_RECO}/CATALOGO_VALIDADO_FINAL1.xlsx"
    if os.path.exists(excel_path):
        df_ex = pd.read_excel(excel_path)
        df_ex['Nº lote'] = df_ex['Nº lote'].astype(str).str.strip()
        df = pd.merge(df_ia, df_ex, on='Nº lote', how='left', suffixes=('', '_ex'))
    else: 
        df = df_ia
        
    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")
    model = SentenceTransformer('intfloat/multilingual-e5-small')
    return df, index, model

df, index, model = load_resources()

# 3. SIDEBAR Y FILTROS
st.sidebar.title(t["sidebar_tit"])
f_idioma = st.sidebar.multiselect(t["f_idioma"], sorted(df['Idioma'].dropna().unique()))
f_publico = st.sidebar.multiselect(t["f_publico"], sorted(df['Público'].dropna().unique()))
f_gen = st.sidebar.multiselect(t["f_genero"], sorted(df['genero_fix'].dropna().unique()))
f_edit = st.sidebar.multiselect(t["f_editorial"], sorted(df['Editorial'].dropna().unique()))

col_pag = 'Páginas' if 'Páginas' in df.columns else 'Páginas_ex'
f_pag = st.sidebar.slider(t["f_paginas"], 0, 1500, 1500)
f_local = st.sidebar.checkbox(t["f_local"])

def filtrar(dataframe):
    temp = dataframe.copy()
    if f_idioma: temp = temp[temp['Idioma'].isin(f_idioma)]
    if f_publico: temp = temp[temp['Público'].isin(f_publico)]
    if f_gen: temp = temp[temp['genero_fix'].isin(f_gen)]
    if f_edit: temp = temp[temp['Editorial'].isin(f_edit)]
    if col_pag in temp.columns: temp = temp[temp[col_pag] <= f_pag]
    if f_local: temp = temp[temp['Geografia_Autor'].astype(str).str.contains("Local", case=False, na=False)]
    return temp

# 4. CARDS
from streamlit_gsheets import GSheetsConnection

def guardar_voto(lote, titulo, valor, query):
    try:
        # Conectar con la hoja definida en Secrets
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Leer datos que ya existan
        df_existente = conn.read()
        
        # Crear la nueva fila de feedback
        nuevo_voto = pd.DataFrame([{
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "lote": str(lote),
            "titulo": titulo,
            "voto": "👍" if valor == 1 else "👎",
            "query": query
        }])
        
        # Unir y subir
        df_final = pd.concat([df_existente, nuevo_voto], ignore_index=True)
        conn.update(data=df_final)
        st.toast("✅ ¡Voto guardado en el Excel!")
    except Exception as e:
        st.error(f"No se pudo guardar: {e}")

# 5. CABECERA E INTERFAZ
col_logo, col_tit = st.columns([1, 6])
with col_logo:
    if os.path.exists(URL_LOGO):
        st.image(URL_LOGO, width=150)
with col_tit:
    st.title(t["titulo"])
    st.caption(t["subtitulo"])

tab1, tab2, tab3 = st.tabs([t["tab1"], t["tab2"], t["tab3"]])

with tab1:
    q = st.text_input(t["input_query"], key="q1")
    if q:
        vec = model.encode([f"query: {q}"], normalize_embeddings=True).astype('float32')
        D, I = index.search(vec, 50)
        res = df.iloc[I[0]].copy()
        res['score_ia'] = D[0]
        final = filtrar(res).sort_values('score_ia', ascending=False).head(10)
        for _, r in final.iterrows(): mostrar_card(r, q)

with tab2:
    lid = st.text_input(t["lote_input"], key="q2")
    if lid:
        ref = df[df['Nº lote'] == lid.strip().upper()]
        if not ref.empty:
            v_ref = index.reconstruct(int(ref.index[0])).reshape(1,-1).astype('float32')
            D, I = index.search(v_ref, 20)
            sim = filtrar(df.iloc[I[0]])
            for _, r in sim[sim['Nº lote']!=lid.upper()].head(10).iterrows(): 
                mostrar_card(r, f"Sim {lid}")

with tab3:
    st.write(t["serendipia_txt"])
    if os.path.exists(URL_BOTON_RANDOM):
        st.image(URL_BOTON_RANDOM, width=200)
    if st.button(t["boton_txt"], type="primary"):
        posibles = filtrar(df)
        if not posibles.empty:
            st.session_state.azar = posibles.sample(1).iloc[0]
    if 'azar' in st.session_state: 
        mostrar_card(st.session_state.azar, "Seren")

