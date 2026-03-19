import streamlit as st
import pandas as pd
import faiss
import pickle
from sentence_transformers import SentenceTransformer
import os
import unicodedata

# --- 1. CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

PATH_RECO = "recomendador"
RUTA_PORTADAS = "portadas"

# --- 2. CARGA DE RECURSOS (ESTO SALVA TU RAM) ---
@st.cache_resource
def load_all():
    # Modelo original (1024 dim) para que coincida con tu .index actual
    model = SentenceTransformer('intfloat/multilingual-e5-large')
    
    # Carga de FAISS
    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")
    
    # Carga de Metadatos
    with open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb") as f:
        df = pickle.load(f)
    
    # Merge con el Excel de IA si existe
    excel_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx"
    if os.path.exists(excel_path):
        df_ia = pd.read_excel(excel_path, usecols=['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA'])
        df_ia['Nº lote'] = df_ia['Nº lote'].astype(str).str.strip()
        df['Nº lote'] = df['Nº lote'].astype(str).str.strip()
        df = pd.merge(df, df_ia, on='Nº lote', how='left')
    
    # Optimizamos tipos de datos para ahorrar memoria
    df['Idioma'] = df['Idioma'].astype('category')
    df['Público'] = df['Público'].astype('category')
    
    return df, index, model

df, index, model = load_all()

# --- 3. DICCIONARIO DE TEXTOS (PARA EVITAR EL NAMEERROR) ---
texts = {
    "Castellano": {
        "titulo": "Clubes de Lectura de Navarra",
        "sidebar_tit": "🎯 Panel de Control",
        "f_idioma": "🌍 Idioma",
        "f_publico": "👥 Público",
        "f_genero": "👤 Género Autor/a",
        "f_ia_gen": "📂 Categoría IA",
        "tab1": "📖 Búsqueda clásica",
        "tab2": "✨ Búsqueda libre (IA)",
        "placeholder": "Ej: Novelas de misterio en el Baztán",
        "input_query": "Escribe lo que buscas:",
        "resumen_btn": "Ver resumen",
        "no_results": "No hay resultados con esos filtros."
    },
    "Euskera": {
        "titulo": "Nafarroako Irakurketa Klubak",
        "sidebar_tit": "🎯 Kontrol Panela",
        "f_idioma": "🌍 Hizkuntza",
        "f_publico": "👥 Publikoa",
        "f_genero": "👤 Egilearen generoa",
        "f_ia_gen": "📂 IA Kategoria",
        "tab1": "📖 Bilaketa klasikoa",
        "tab2": "✨ Bilaketa librea (IA)",
        "placeholder": "Adibidez: Baztango misteriozko eleberriak",
        "input_query": "Idatzi hemen zure bilaketa:",
        "resumen_btn": "Ikusi laburpena",
        "no_results": "Ez da emaitzarik aurkitu iragazki hauekin."
    }
}

# --- 4. INTERFAZ Y FILTROS ---
idioma_interfaz = st.sidebar.selectbox("🌐 Idioma / Hizkuntza", ["Castellano", "Euskera"])
t = texts[idioma_interfaz]

st.title(t["titulo"])

st.sidebar.subheader(t["sidebar_tit"])
f_idioma = st.sidebar.multiselect(t["f_idioma"], df['Idioma'].unique())
f_publico = st.sidebar.multiselect(t["f_publico"], df['Público'].unique())
f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], df['Genero_Principal_IA'].dropna().unique())

def filtrar_datos(dataframe):
    mask = pd.Series([True] * len(dataframe))
    if f_idioma: mask &= dataframe['Idioma'].isin(f_idioma)
    if f_publico: mask &= dataframe['Público'].isin(f_publico)
    if f_ia_gen: mask &= dataframe['Genero_Principal_IA'].isin(f_ia_gen)
    return dataframe[mask]

# --- 5. LÓGICA DE VISUALIZACIÓN ---
def mostrar_lote(r, context_id):
    with st.container(border=True):
        c1, c2 = st.columns([1, 4])
        lote_id = str(r['Nº lote']).strip()
        with c1:
            foto = f"{RUTA_PORTADAS}/{lote_id}.jpg"
            if os.path.exists(foto):
                st.image(foto, use_container_width=True)
            else:
                st.write("📖")
        with c2:
            st.subheader(r['Título'])
            st.write(f"**{r['Autor']}**")
            st.caption(f"Lote: {lote_id} | {r['Idioma']} | {r['Público']}")
            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra', 'Sin resumen disponible.'))

# --- 6. TABS PRINCIPALES ---
tab1, tab2 = st.tabs([t["tab1"], t["tab2"]])

with tab1:
    busq = st.text_input("Buscar por título o autor:")
    if busq:
        res = filtrar_datos(df)
        res = res[res['Título'].str.contains(busq, case=False, na=False) | 
                  res['Autor'].str.contains(busq, case=False, na=False)]
        for _, row in res.head(10).iterrows():
            mostrar_lote(row, "clasica")

with tab2:
    query = st.text_input(t["input_query"], placeholder=t["placeholder"], key="ia_query")
    if query:
        df_f = filtrar_datos(df)
        if not df_f.empty:
            # El modelo E5-Large requiere el prefijo 'query: '
            vec = model.encode([f"query: {query}"], normalize_embeddings=True).astype('float32')
            D, I = index.search(vec, 40)
            
            # Recuperar resultados y filtrar por los selectores laterales
            res_ia = df.iloc[I[0]]
            final = res_ia[res_ia['Nº lote'].isin(df_f['Nº lote'])].head(10)
            
            if final.empty:
                st.warning(t["no_results"])
            else:
                for _, row in final.iterrows():
                    mostrar_lote(row, "ia")
        else:
            st.warning(t["no_results"])
