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

@st.cache_data
def normalizar_texto(texto):
    if not isinstance(texto, str): return ""
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower().strip()

# --- 2. CARGA DE RECURSOS ---
@st.cache_resource
def load_resources():
    # Volvemos al modelo original para que coincida con tu archivo .index (1024 dim)
    model = SentenceTransformer('intfloat/multilingual-e5-large')
    
    # Carga de datos optimizada
    with open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb") as f:
        df = pickle.load(f)
    
    df['Nº lote'] = df['Nº lote'].astype(str).str.strip()
    
    # Unimos solo las columnas necesarias para no inflar la RAM
    excel_ia_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx"
    if os.path.exists(excel_ia_path):
        df_ex_ia = pd.read_excel(excel_ia_path, usecols=['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA'])
        df_ex_ia['Nº lote'] = df_ex_ia['Nº lote'].astype(str).str.strip()
        df = pd.merge(df, df_ex_ia, on='Nº lote', how='left')
    
    # Normalización
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
    
    # Carga de FAISS
    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")
    
    return df, index, model

PATH_RECO = "recomendador"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_BOTON_RANDOM = f"{PATH_RECO}/serendipia.png"
RUTA_PORTADAS = "portadas"

# Ejecutar carga
df, index, model = load_resources()

# --- 3. TEXTOS INTERFAZ ---
# (Se mantiene tu bloque original de 'texts')
idioma_interfaz = st.sidebar.selectbox("🌐 Idioma / Hizkuntza", ["Castellano", "Euskera"])
# ... (aquí iría tu diccionario 'texts' completo que ya tienes)
# NOTA: Para ahorrar espacio aquí, asumo que el diccionario 't' se genera igual que antes.
t = texts[idioma_interfaz]

# --- 4. FUNCIONES ---
def filtrar_dataframe(dataframe):
    temp = dataframe
    if f_idioma: temp = temp[temp['Idioma'].isin(f_idioma)]
    if f_publico: temp = temp[temp['Público'].isin(f_publico)]
    if f_gen: temp = temp[temp['genero_fix'].isin(f_gen)]
    if f_ia_gen: temp = temp[temp['Genero_Principal_IA'].isin(f_ia_gen)]
    return temp

def mostrar_card(r, context):
    with st.container(border=True):
        col_img, col_txt, col_voto = st.columns([1,3,1])
        lote_id = str(r.get('Nº lote','')).strip()
        with col_img:
            foto_path = f"{RUTA_PORTADAS}/{lote_id}.jpg"
            if os.path.exists(foto_path):
                st.image(foto_path, use_container_width=True)
            else:
                st.write("📖")
        with col_txt:
            st.subheader(r.get('Título','Sin título'))
            st.write(f"**{r.get('Autor','Autor desconocido')}**")
            if pd.notnull(r.get('Subgeneros_Limpios_IA')):
                st.markdown(f"**{r.get('Genero_Principal_IA')}**: <small>{r.get('Subgeneros_Limpios_IA')}</small>", unsafe_allow_html=True)
            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra','--'))

# --- 5. SIDEBAR ---
st.sidebar.title(t["sidebar_tit"])
f_idioma = st.sidebar.multiselect(t["f_idioma"], sorted(df['Idioma'].dropna().unique()))
f_publico = st.sidebar.multiselect(t["f_publico"], sorted(df['Público'].dropna().unique()))
f_gen = st.sidebar.multiselect(t["f_genero"], sorted(df['genero_fix'].dropna().unique()))
st.sidebar.markdown("---")
f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], sorted(df['Genero_Principal_IA'].dropna().unique()))

# --- 6. TABS ---
tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])

with tab2: # Búsqueda Semántica
    q = st.text_input(t["input_query"], key="q_sem", placeholder=t["placeholder"])
    if q:
        df_base = filtrar_dataframe(df)
        # IMPORTANTE: El prefijo "query: " es necesario para el modelo E5
        query_eficiente = f"query: {q}"
        vec = model.encode([query_eficiente], normalize_embeddings=True).astype('float32')
        D, I = index.search(vec, 20) 
        
        res_ia = df.iloc[I[0]].copy()
        # Filtramos los resultados de la IA por los filtros laterales
        final = res_ia[res_ia['Nº lote'].isin(df_base['Nº lote'])].head(10)
        for _, r in final.iterrows(): mostrar_card(r, q)

# ... (Tab 1, 3 y 4 se mantienen con la lógica de filtrado anterior)
