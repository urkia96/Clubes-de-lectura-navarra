
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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Clubes de Lectura de Navarra / Nafarroko Irakurketa Klubak", layout="wide")

@st.cache_resource
def load_resources():
    df_pkl_path = "/content/drive/MyDrive/doctorado_scripts/metadatos_promptss_infloat_ponderado_genero.pkl"
    excel_path = "/content/drive/MyDrive/doctorado_scripts/CATALOGO_VALIDADO_FINAL1.xlsx"
    index_path = "/content/drive/MyDrive/doctorado_scripts/biblioteca_prompts_infloat_ponderado_genero.index"
    
    with open(df_pkl_path, "rb") as f:
        df_ia = pickle.load(f)
    df_ia['Nº lote'] = df_ia['Nº lote'].astype(str).str.strip()

    if os.path.exists(excel_path):
        df_excel = pd.read_excel(excel_path)
        df_excel.columns = df_excel.columns.str.strip()
        df_excel['Nº lote'] = df_excel['Nº lote'].astype(str).str.strip()
        df = pd.merge(df_ia, df_excel, on='Nº lote', how='left', suffixes=('', '_ex'))
    else:
        df = df_ia
    
    index = faiss.read_index(index_path)
    model = SentenceTransformer('intfloat/multilingual-e5-large', device="cuda" if torch.cuda.is_available() else "cpu")
    return df, index, model

try:
    df, index, model = load_resources()
except Exception as e:
    st.error(f"Error: {e}")
    st.stop()

# --- BARRA LATERAL (PANEL DE CONTROL COMPLETO) ---
st.sidebar.title("🎯 Panel de Control")

# 1. Filtros de Selección Múltiple
idioma_sel = st.sidebar.multiselect("🌍 Idioma", options=sorted(df['Idioma'].dropna().unique().tolist()))
publico_sel = st.sidebar.multiselect("👥 Público", options=sorted(df['Público'].dropna().unique().tolist()))
gen_sel = st.sidebar.multiselect("👤 Género del Autor/a", options=sorted(df['genero_fix'].dropna().unique().tolist()))
editorial_sel = st.sidebar.multiselect("📚 Editorial", options=sorted(df['Editorial'].dropna().unique().tolist()))

# 2. Filtro de Extensión (Páginas)
col_pag = 'Páginas' if 'Páginas' in df.columns else 'Páginas_ex'
max_p = int(df[col_pag].max()) if col_pag in df.columns and pd.notna(df[col_pag].max()) else 1000
pag_sel = st.sidebar.slider("📄 Máximo de páginas", 0, max_p, max_p)

# 3. Checkboxes
solo_local = st.sidebar.checkbox("🏠 Solo Autores Locales")

# --- FUNCIONES DE APOYO ---

def aplicar_filtros_globales(dataframe):
    temp = dataframe.copy()
    
    if idioma_sel:
        temp = temp[temp['Idioma'].isin(idioma_sel)]
    if publico_sel:
        temp = temp[temp['Público'].isin(publico_sel)]
    if gen_sel:
        temp = temp[temp['genero_fix'].isin(gen_sel)]
    if editorial_sel:
        temp = temp[temp['Editorial'].isin(editorial_sel)]
    if col_pag in temp.columns:
        temp = temp[temp[col_pag] <= pag_sel]
    if solo_local and 'Geografia_Autor' in temp.columns:
        temp = temp[temp['Geografia_Autor'].astype(str).str.contains("Local", case=False, na=False)]
    
    return temp

def mostrar_resultados(dataframe, titulo_seccion="Resultados"):
    st.subheader(titulo_seccion)
    if dataframe.empty:
        st.warning("No hay libros que coincidan con los filtros seleccionados.")
        return

    for _, r in dataframe.iterrows():
        with st.container(border=True):
            col1, col2 = st.columns([1, 4])
            with col1:
                img_glob = f"/content/drive/MyDrive/doctorado_scripts/portadas_biblioteca/{r['Nº lote']}.*"
                archivos = glob.glob(img_glob)
                if archivos:
                    st.image(archivos[0], use_container_width=True)
                else:
                    st.write("📖")
            with col2:
                st.subheader(r['Título'])
                st.write(f"**{r['Autor']}** | Ed. {r.get('Editorial', '---')}")
                
                # Info en línea compacta
                pags = f"{int(r.get(col_pag,0))} págs" if pd.notna(r.get(col_pag)) else "--- págs"
                st.caption(f"Lote: {r['Nº lote']} | Público: {r.get('Público','---')} | {pags} | {r.get('Idioma','---')}")
                
                with st.expander("Ver resumen"):
                    st.write(f"**Época:** {r.get('Época_Limpio', 'N/A')}")
                    st.write(r.get('Resumen_navarra', 'Sin resumen oficial disponible.'))

# --- INTERFAZ PRINCIPAL ---
st.title("Clubes de Lectura de Navarra / Nafarroako Irakurketa Klubak")
tab1, tab2 = st.tabs(["✨ Búsqueda Semántica", "🔍 Similitud por Lote"])

with tab1:
    query = st.text_input("¿Qué quieres leer hoy?", key="q1", placeholder="Ej: Libro de aventuras para jóvenes")
    if query:
        query_lc = query.lower()
        
        vec = model.encode([f"query: {query}"], normalize_embeddings=True).astype('float32')
        D, I = index.search(vec, 200)
        res = df.iloc[I[0]].copy()
        res['score_ia'] = D[0]

        # Filtro de Siglo (Regex)
        siglo_match = re.search(r'siglo\s+([ivxlcd0-9]+)', query_lc)
        if siglo_match:
            siglo_buscado = siglo_match.group(1).upper()
            def validar_siglo(row):
                txt = (str(row.get('Época_Limpio','')) + str(row.get('Resumen_navarra',''))).upper()
                return siglo_buscado in txt
            res = res[res.apply(validar_siglo, axis=1)]

        # Aplicar filtros globales (incluyendo el nuevo de Público)
        res = aplicar_filtros_globales(res)
        
        # Bonus Navarra
        menciona_navarra = "navarra" in query_lc
        res['score_final'] = res.apply(lambda r: r['score_ia'] * 1.5 if menciona_navarra and "NAVARRA" in (str(r.get('Resumen_navarra','')) + str(r.get('Título',''))).upper() else r['score_ia'], axis=1)
        
        mostrar_resultados(res.sort_values('score_final', ascending=False).head(10), "Sugerencias seleccionadas")

with tab2:
    st.info("Introduce un lote para ver recomendaciones basadas en su 'ADN' temático.")
    lote_id = st.text_input("Código de lote:", key="q2")
    
    if lote_id:
        lote_id = lote_id.strip().upper()
        ref_row = df[df['Nº lote'] == lote_id]
        
        if not ref_row.empty:
            st.success(f"Analizando libros similares a: **{ref_row.iloc[0]['Título']}**")
            
            idx_original = ref_row.index[0]
            vector_ref = index.reconstruct(int(idx_original)).reshape(1, -1).astype('float32')
            
            D, I = index.search(vector_ref, 100)
            similares = df.iloc[I[0]].copy()
            similares['score_ia'] = D[0]
            
            similares = similares[similares['Nº lote'] != lote_id]
            similares_filtrados = aplicar_filtros_globales(similares)
            
            mostrar_resultados(similares_filtrados.head(10), "Temáticas parecidas")
        else:
            st.error("Lote no encontrado.")
