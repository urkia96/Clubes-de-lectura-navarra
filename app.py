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

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

# Función de normalización optimizada
@st.cache_data
def normalizar_texto(texto):
    if not isinstance(texto, str): return ""
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower().strip()

# --- 2. CARGA DE RECURSOS (OPTIMIZADA) ---
@st.cache_resource
def load_resources():
    # Usamos un modelo más ligero pero muy capaz para ahorrar RAM
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    
    # Carga de datos
    with open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb") as f:
        df = pickle.load(f)
    
    df['Nº lote'] = df['Nº lote'].astype(str).str.strip()
    
    excel_ia_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx"
    if os.path.exists(excel_ia_path):
        df_ex_ia = pd.read_excel(excel_ia_path, usecols=['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA'])
        df_ex_ia['Nº lote'] = df_ex_ia['Nº lote'].astype(str).str.strip()
        df = pd.merge(df, df_ex_ia, on='Nº lote', how='left')
    
    # Optimizamos tipos para ahorrar RAM
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
    
    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")
    
    return df, index, model

PATH_RECO = "recomendador"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_BOTON_RANDOM = f"{PATH_RECO}/serendipia.png"
RUTA_PORTADAS = "portadas"

df, index, model = load_resources()

# --- 3. TEXTOS INTERFAZ ---
# (Se mantiene igual que tu original para no romper nada)
col_main, col_lang = st.columns([12, 1])
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
        "f_local": "🏠 Autores locales",
        "f_ia_gen": "📂 Categoría Principal",
        "f_ia_sub": "🏷️ Temas y Estilos",
        "tab1": "📖 Búsqueda por autor/título",
        "tab2": "✨ Búsqueda libre",
        "tab3": "🔍 Lotes similares",
        "tab4": "🎲 Búsqueda aleatoria",
        "placeholder": "Ej: Novelas sobre la historia de Navarra",
        "input_query": "Puedes escribir lo que quieras",
        "lote_input": "Introduce el código del lote:",
        "busq_titulo": "Buscar por Título:",
        "busq_autor": "Buscar por Autor:",
        "resumen_btn": "Ver resumen",
        "pags_label": "págs",
        "thanks": "✅ Voto registrado",
        "ask": "¿Te gusta esta recomendación?",
        "boton_txt": "¡Sorpréndeme!",
        "serendipia_txt": "Deja que el azar elija por ti:",
        "no_results": "No se han encontrado resultados con suficiente coincidencia (mín. 80%).",
        "kw_label": "Palabras clave"
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
        "f_local": "🏠 Bertakoak autoreak",
        "f_ia_gen": "📂 Kategoria Nagusia",
        "f_ia_sub": "🏷️ Gaiak eta EstiloaK",
        "tab1": "📖 Izenburu / Idazle bilaketa",
        "tab2": "✨ Bilaketa librea",
        "tab3": "🔍 Lote antzekoak",
        "tab4": "🎲 Zorizko bilaketa",
        "placeholder": "Adibidez: Nafarroako historiaren inguruko eleberriak",
        "input_query": "Nahi duzuna idatzi dezakezu",
        "lote_input": "Sartu lote kodea:",
        "busq_titulo": "Izenburuaren arabera bilatu:",
        "busq_autor": "Egilearen arabera bilatu:",
        "resumen_btn": "Ikusi laburpena",
        "pags_label": "orr",
        "thanks": "✅ Iritzia gordeta",
        "ask": "Gogoko duzu?",
        "boton_txt": "Harritu nazazu!",
        "serendipia_txt": "Utzi zoriari zure ordez aukeratzen:",
        "no_results": "Ez da nahikoa antzekotasun duten emaitzarik aurkitu (%80 gutxienez).",
        "kw_label": "Gako-hitzak"
    }
}
t = texts[idioma_interfaz]

# --- 4. FUNCIONES AUXILIARES ---
def conectar_sheets():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"]).sheet1

def guardar_voto(lote, titulo, valor, query):
    try:
        sheet = conectar_sheets()
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(lote), str(titulo), "👍" if valor == 1 else "👎", str(query)])
        st.toast("✅ ¡Voto guardado!")
    except Exception as e:
        st.error(f"Error: {e}")

def mostrar_card(r, context):
    with st.container(border=True):
        col_img, col_txt, col_voto = st.columns([1,3,1])
        lote_id = str(r.get('Nº lote','')).strip()
        with col_img:
            # Solo buscamos la imagen si existe la carpeta, para no sobrecargar el sistema de archivos
            foto_path = f"{RUTA_PORTADAS}/{lote_id}.jpg" 
            if os.path.exists(foto_path):
                st.image(foto_path, use_container_width=True)
            else:
                st.write("📖")
                st.caption(f"Lote {lote_id}")
        with col_txt:
            st.subheader(r.get('Título','Sin título'))
            st.write(f"**{r.get('Autor','Autor desconocido')}**")
            st.caption(f"{r.get('Idioma','--')} | {r.get('Público','--')}")
            
            if pd.notnull(r.get('Subgeneros_Limpios_IA')):
                st.markdown(f"**{r.get('Genero_Principal_IA')}**: <small>{r.get('Subgeneros_Limpios_IA')}</small>", unsafe_allow_html=True)

            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra','No hay resumen disponible.'))
        
        with col_voto:
            ctx_id = str(context)[:10].replace(" ","_")
            kv = f"v_{lote_id}_{ctx_id}"
            if kv not in st.session_state:
                ca, cb = st.columns(2)
                if ca.button("👍", key=f"u_{lote_id}_{ctx_id}"):
                    guardar_voto(lote_id, r.get('Título','S/T'), 1, context)
                    st.session_state[kv] = 1
                    st.rerun()
                if cb.button("👎", key=f"d_{lote_id}_{ctx_id}"):
                    guardar_voto(lote_id, r.get('Título','S/T'), 0, context)
                    st.session_state[kv] = 0
                    st.rerun()
            else:
                st.success(t["thanks"])

# --- 5. FILTROS Y LÓGICA ---
st.sidebar.title(t["sidebar_tit"])
f_idioma = st.sidebar.multiselect(t["f_idioma"], sorted(df['Idioma'].dropna().unique()))
f_publico = st.sidebar.multiselect(t["f_publico"], sorted(df['Público'].dropna().unique()))
f_gen = st.sidebar.multiselect(t["f_genero"], sorted(df['genero_fix'].dropna().unique()))

col_pag_name = 'Páginas' if 'Páginas' in df.columns else 'Páginas_ex'
max_p = int(df[col_pag_name].max()) if col_pag_name in df.columns else 1000
f_pag = st.sidebar.slider(t["f_paginas"], 0, max_p, max_p)

st.sidebar.markdown("---")
opciones_ia_gen = sorted(df['Genero_Principal_IA'].dropna().unique())
f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], opciones_ia_gen)

def filtrar_dataframe(dataframe):
    temp = dataframe
    if f_idioma: temp = temp[temp['Idioma'].isin(f_idioma)]
    if f_publico: temp = temp[temp['Público'].isin(f_publico)]
    if f_gen: temp = temp[temp['genero_fix'].isin(f_gen)]
    if f_ia_gen: temp = temp[temp['Genero_Principal_IA'].isin(f_ia_gen)]
    if col_pag_name in temp.columns: temp = temp[temp[col_pag_name].fillna(0) <= f_pag]
    return temp

# --- 6. INTERFAZ ---
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
    q = st.text_input(t["input_query"], placeholder=t["placeholder"])
    if q:
        df_base = filtrar_dataframe(df)
        if not df_base.empty:
            vec = model.encode([q], normalize_embeddings=True).astype('float32')
            D, I = index.search(vec, 50) # Buscamos menos para ahorrar
            res_ia = df.iloc[I[0]].copy()
            final = res_ia[res_ia['Nº lote'].isin(df_base['Nº lote'])].head(10)
            for _, r in final.iterrows(): mostrar_card(r, q)

with tab3:
    lid = st.text_input(t["lote_input"])
    if lid:
        ref = df[df['Nº lote'] == lid.strip().upper()]
        if not ref.empty:
            v_ref = index.reconstruct(int(ref.index[0])).reshape(1, -1)
            D, I = index.search(v_ref, 10)
            for _, r in df.iloc[I[0]].iterrows(): 
                if str(r['Nº lote']) != lid.strip().upper(): mostrar_card(r, "Sim")

with tab4:
    if st.button(t["boton_txt"]):
        res = filtrar_dataframe(df)
        if not res.empty: mostrar_card(res.sample(1).iloc[0], "Azar")
