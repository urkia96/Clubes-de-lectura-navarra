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

# 1. CONFIGURACIÓN E IDIOMA (Inmediato)
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

PATH_RECO = "recomendador"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_BOTON_RANDOM = f"{PATH_RECO}/serendipia.png"
RUTA_PORTADAS = "portadas"

# --- CACHÉ DE TEXTOS (Evita recrear diccionarios) ---
@st.cache_data
def get_texts():
    return {
        "Castellano": {
            "titulo": "Clubes de Lectura de Navarra", "subtitulo": "Nafarroako Irakurketa Klubak",
            "sidebar_tit": "🎯 Panel de Control", "f_idioma": "🌍 Idioma", "f_publico": "👥 Público",
            "f_genero": "👤 Género Autor/a", "f_editorial": "📚 Editorial", "f_paginas": "📄 Máx Páginas",
            "f_local": "🏠 Autores locales", "f_ia_gen": "📂 Categoría Principal", "f_ia_sub": "🏷️ Temas y Estilos",
            "tab1": "📖 Búsqueda por autor/título", "tab2": "✨ Búsqueda libre", "tab3": "🔍 Lotes similares", "tab4": "🎲 Búsqueda aleatoria",
            "placeholder": "Ej: Novelas sobre la historia de Navarra", "input_query": "Puedes escribir lo que quieras",
            "lote_input": "Introduce el código del lote:", "busq_titulo": "Buscar por Título:", "busq_autor": "Buscar por Autor:",
            "resumen_btn": "Ver resumen", "pags_label": "págs", "thanks": "✅ Voto registrado", "ask": "¿Te gusta esta recomendación?",
            "boton_txt": "¡Sorpréndeme!", "serendipia_txt": "Deja que el azar elija por ti:", "no_results": "Sin resultados con suficiente coincidencia.", "kw_label": "Palabras clave"
        },
        "Euskera": {
            "titulo": "Nafarroako Irakurketa Klubak", "subtitulo": "Clubes de Lectura de Navarra",
            "sidebar_tit": "🎯 Kontrol Panela", "f_idioma": "🌍 Hizkuntza", "f_publico": "👥 Publikoa",
            "f_genero": "👤 Egilearen generoa", "f_editorial": "📚 Argitaletxea", "f_paginas": "📄 Orrialde kopurua",
            "f_local": "🏠 Bertakoak autoreak", "f_ia_gen": "📂 Kategoria Nagusia", "f_ia_sub": "🏷️ Gaiak eta EstiloaK",
            "tab1": "📖 Izenburu / Idazle bilaketa", "tab2": "✨ Bilaketa librea", "tab3": "🔍 Lote antzekoak", "tab4": "🎲 Zorizko bilaketa",
            "placeholder": "Adibidez: Nafarroako historiaren inguruko eleberriak", "input_query": "Nahi duzuna idatzi dezakezu",
            "lote_input": "Sartu lote kodea:", "busq_titulo": "Izenburuaren arabera bilatu:", "busq_autor": "Egilearen arabera bilatu:",
            "resumen_btn": "Ikusi laburpena", "pags_label": "orr", "thanks": "✅ Iritzia gordeta", "ask": "Gogoko duzu?",
            "boton_txt": "Harritu nazazu!", "serendipia_txt": "Utzi zoriari zure ordez aukeratzen:", "no_results": "Ez da nahikoa antzekotasun duten emaitzarik aurkitu.", "kw_label": "Gako-hitzak"
        }
    }

all_texts = get_texts()
idioma_interfaz = st.sidebar.selectbox("🌐", ["Castellano", "Euskera"])
t = all_texts[idioma_interfaz]

# --- FUNCIONES DE APOYO OPTIMIZADAS ---
@st.cache_data
def normalizar_texto(texto):
    if not isinstance(texto, str): return ""
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower().strip()

# --- 2. CARGA DE RECURSOS (MÁXIMA OPTIMIZACIÓN) ---
@st.cache_resource
def load_resources():
    # Cargar metadatos
    with open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb") as f:
        df = pickle.load(f)
    df['Nº lote'] = df['Nº lote'].astype(str).str.strip()
    
    # Carga Excel (Solo columnas necesarias para ahorrar RAM)
    excel_ia_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx"
    if os.path.exists(excel_ia_path):
        df_ex_ia = pd.read_excel(excel_ia_path, usecols=['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA'])
        df_ex_ia['Nº lote'] = df_ex_ia['Nº lote'].astype(str).str.strip()
        df = pd.merge(df, df_ex_ia, on='Nº lote', how='left')
    
    # Pre-normalizar (Una sola vez, se queda en caché)
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
    
    # Convertir a categorías (Ahorra un 80% de espacio en columnas repetitivas)
    for col in ['Idioma', 'Público', 'genero_fix', 'Editorial', 'Genero_Principal_IA']:
        if col in df.columns: df[col] = df[col].astype('category')

    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")
    model = SentenceTransformer('intfloat/multilingual-e5-large')
    return df, index, model

df, index, model = load_resources()

# --- 3. GOOGLE SHEETS (Sin cambios) ---
def conectar_sheets():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"]).sheet1

def guardar_voto(lote, titulo, valor, query):
    try:
        sheet = conectar_sheets()
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(lote), str(titulo), "👍" if valor == 1 else "👎", str(query)])
        st.toast(t["thanks"])
    except: st.error("Error al conectar con Google Sheets")

# --- 5. MOSTRAR TARJETA (Optimización de búsqueda de imágenes) ---
def mostrar_card(r, context):
    with st.container(border=True):
        col_img, col_txt, col_voto = st.columns([1,3,1])
        lote_id = str(r.get('Nº lote','')).strip()
        
        with col_img:
            img_path = f"{RUTA_PORTADAS}/{lote_id}.jpg" # Asumimos JPG por velocidad
            if os.path.exists(img_path):
                st.image(img_path, use_container_width=True)
            else:
                st.write("📖")
                st.caption(f"Lote {lote_id}")
        
        with col_txt:
            st.subheader(r.get('Título','Sin título'))
            st.write(f"**{r.get('Autor','Autor desconocido')}**")
            pags = r.get('Páginas', r.get('Páginas_ex','--'))
            st.caption(f"Lote: {lote_id} | {r.get('Idioma','--')} | {pags} {t['pags_label']} | {r.get('Público','--')}")
            
            if pd.notnull(r.get('Subgeneros_Limpios_IA')):
                st.markdown(f"**{r.get('Genero_Principal_IA')}**: <small>{r.get('Subgeneros_Limpios_IA')}</small>", unsafe_allow_html=True)

            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra','--'))
                tags = r.get('IA_Tags','')
                if pd.notnull(tags) and str(tags).strip() != "":
                    st.markdown(f"**{t['kw_label']}:** {tags}")
        
        with col_voto:
            ctx_id = str(context)[:10].replace(" ","_")
            kv = f"v_{lote_id}_{ctx_id}"
            if kv in st.session_state:
                st.success(t["thanks"])
            else:
                st.write(f"<small>{t['ask']}</small>", unsafe_allow_html=True)
                if st.button("👍", key=f"u_{lote_id}_{ctx_id}"):
                    guardar_voto(lote_id, r.get('Título','S/T'), 1, context)
                    st.session_state[kv] = 1
                    st.rerun()
                if st.button("👎", key=f"d_{lote_id}_{ctx_id}"):
                    guardar_voto(lote_id, r.get('Título','S/T'), 0, context)
                    st.session_state[kv] = 0
                    st.rerun()

# --- 6. FILTROS (Evitar .copy() innecesarios) ---
st.sidebar.title(t["sidebar_tit"])
f_idioma = st.sidebar.multiselect(t["f_idioma"], df['Idioma'].unique())
f_publico = st.sidebar.multiselect(t["f_publico"], df['Público'].unique())
f_gen = st.sidebar.multiselect(t["f_genero"], df['genero_fix'].dropna().unique())
f_edit = st.sidebar.multiselect(t["f_editorial"], df['Editorial'].dropna().unique())

col_pag_name = 'Páginas' if 'Páginas' in df.columns else 'Páginas_ex'
max_p = int(df[col_pag_name].max()) if col_pag_name in df.columns else 1500
f_pag = st.sidebar.slider(t["f_paginas"], 0, max_p, max_p)
f_local = st.sidebar.checkbox(t["f_local"])

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Filtros IA")
f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], df['Genero_Principal_IA'].dropna().unique())

def filtrar_dataframe(dataframe):
    # Usamos una máscara booleana en lugar de crear múltiples copias del DF
    mask = pd.Series(True, index=dataframe.index)
    if f_idioma: mask &= dataframe['Idioma'].isin(f_idioma)
    if f_publico: mask &= dataframe['Público'].isin(f_publico)
    if f_gen: mask &= dataframe['genero_fix'].isin(f_gen)
    if f_edit: mask &= dataframe['Editorial'].isin(f_edit)
    if f_ia_gen: mask &= dataframe['Genero_Principal_IA'].isin(f_ia_gen)
    if col_pag_name in dataframe.columns: mask &= (dataframe[col_pag_name].fillna(0) <= f_pag)
    if f_local: mask &= dataframe['Geografia_Autor'].astype(str).str.contains("Local", case=False, na=False)
    return dataframe[mask]

# --- 7. INTERFAZ ---
st.title(t["titulo"])
tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])

with tab1:
    c1, c2 = st.columns(2)
    b_tit = c1.text_input(t["busq_titulo"])
    b_aut = c2.text_input(t["busq_autor"])
    if b_tit or b_aut:
        res = filtrar_dataframe(df)
        if b_tit: res = res[res['titulo_norm'].str.contains(normalizar_texto(b_tit), na=False)]
        if b_aut: res = res[res['autor_norm'].str.contains(normalizar_texto(b_aut), na=False)]
        for _, r in res.head(10).iterrows(): mostrar_card(r, "Busq")

with tab2:
    q = st.text_input(t["input_query"], key="q_semant", placeholder=t["placeholder"])
    if q:
        vec = model.encode([f"query: {q}"], normalize_embeddings=True).astype('float32')
        D, I = index.search(vec, 50)
        res_ia = df.iloc[I[0]].copy()
        res_ia['score_ia'] = D[0]
        final = filtrar_dataframe(res_ia)
        final = final[final['score_ia'] >= 0.79].head(10)
        for _, r in final.iterrows(): mostrar_card(r, q)

with tab3:
    lid = st.text_input(t["lote_input"])
    if lid:
        ref = df[df['Nº lote'] == lid.strip().upper()]
        if not ref.empty:
            v_ref = index.reconstruct(int(ref.index[0])).reshape(1, -1)
            D, I = index.search(v_ref, 15)
            res_sim = filtrar_dataframe(df.iloc[I[0]])
            for _, r in res_sim.iterrows():
                if r['Nº lote'] != lid.strip().upper(): mostrar_card(r, "Sim")

with tab4:
    if st.button(t["boton_txt"]):
        posibles = filtrar_dataframe(df)
        if not posibles.empty: mostrar_card(posibles.sample(1).iloc[0], "Azar")
