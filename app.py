import streamlit as st
import pandas as pd
import faiss
import pickle
from sentence_transformers import SentenceTransformer
import os
import unicodedata
from datetime import datetime

# --- 1. CONFIGURACIÓN E IDIOMA ---
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

PATH_RECO = "recomendador"
RUTA_PORTADAS = "portadas"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_BOTON_RANDOM = f"{PATH_RECO}/serendipia.png"

# --- 2. CARGA DE RECURSOS (CACHÉ PARA 30+ USUARIOS) ---
@st.cache_resource
def load_resources():
    # Modelo y FAISS (Carga única en RAM)
    model = SentenceTransformer('intfloat/multilingual-e5-large')
    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")
    
    # Datos base
    with open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb") as f:
        df = pickle.load(f)
    
    # Merge con IA y limpieza
    excel_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx"
    if os.path.exists(excel_path):
        df_ia = pd.read_excel(excel_path)
        df_ia['Nº lote'] = df_ia['Nº lote'].astype(str).str.strip()
        df['Nº lote'] = df['Nº lote'].astype(str).str.strip()
        # Unimos solo lo necesario para no engordar la RAM
        cols_to_fix = ['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA', 'Páginas_ex']
        df = pd.merge(df, df_ia[[c for c in cols_to_fix if c in df_ia.columns]], on='Nº lote', how='left')

    # Optimizamos tipos para que 30 personas no saturen el servidor
    df['Idioma'] = df['Idioma'].astype('category')
    df['Público'] = df['Público'].astype('category')
    return df, index, model

df, index, model = load_resources()

# --- 3. DICCIONARIO COMPLETO DE TEXTOS ---
texts = {
    "Castellano": {
        "titulo": "Clubes de Lectura de Navarra", "subtitulo": "Nafarroako Irakurketa Klubak",
        "sidebar_tit": "🎯 Panel de Control", "f_idioma": "🌍 Idioma", "f_publico": "👥 Público",
        "f_genero": "👤 Género Autor/a", "f_editorial": "📚 Editorial", "f_paginas": "📄 Máx Páginas",
        "f_local": "🏠 Autores locales", "f_ia_gen": "📂 Categoría IA", "f_ia_sub": "🏷️ Temas",
        "tab1": "📖 Autor/Título", "tab2": "✨ Búsqueda libre", "tab3": "🔍 Similares", "tab4": "🎲 Azar",
        "placeholder": "Ej: Novelas sobre la historia de Navarra", "lote_input": "Código del lote:",
        "resumen_btn": "Ver resumen", "pags_label": "págs", "boton_txt": "¡Sorpréndeme!",
        "no_results": "No hay resultados con estos filtros."
    },
    "Euskera": {
        "titulo": "Nafarroako Irakurketa Klubak", "subtitulo": "Clubes de Lectura de Navarra",
        "sidebar_tit": "🎯 Kontrol Panela", "f_idioma": "🌍 Hizkuntza", "f_publico": "👥 Publikoa",
        "f_genero": "👤 Egilearen generoa", "f_editorial": "📚 Argitaletxea", "f_paginas": "📄 Orrialdeak",
        "f_local": "🏠 Bertakoak", "f_ia_gen": "📂 IA Kategoria", "f_ia_sub": "🏷️ Gaiak",
        "tab1": "📖 Idazle/Izenburua", "tab2": "✨ Bilaketa librea", "tab3": "🔍 Antzekoak", "tab4": "🎲 Zoriz",
        "placeholder": "Adibidez: Nafarroako historiaren inguruko eleberriak", "lote_input": "Lote kodea:",
        "resumen_btn": "Ikusi laburpena", "pags_label": "orr", "boton_txt": "Harritu nazazu!",
        "no_results": "Ez da emaitzarik aurkitu."
    }
}

idioma_interfaz = st.sidebar.selectbox("🌐", ["Castellano", "Euskera"])
t = texts[idioma_interfaz]

# --- 4. FILTROS LATERALES (TODOS RECUPERADOS) ---
st.sidebar.title(t["sidebar_tit"])
f_idioma = st.sidebar.multiselect(t["f_idioma"], sorted(df['Idioma'].unique()))
f_publico = st.sidebar.multiselect(t["f_publico"], sorted(df['Público'].unique()))
f_gen = st.sidebar.multiselect(t["f_genero"], sorted(df['genero_fix'].dropna().unique()))
f_edit = st.sidebar.multiselect(t["f_editorial"], sorted(df['Editorial'].dropna().unique()))

col_p = 'Páginas' if 'Páginas' in df.columns else 'Páginas_ex'
max_p = int(df[col_p].max()) if col_p in df.columns else 1000
f_pag = st.sidebar.slider(t["f_paginas"], 0, max_p, max_p)
f_local = st.sidebar.checkbox(t["f_local"])

st.sidebar.markdown("---")
f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], sorted(df['Genero_Principal_IA'].dropna().unique()))

def filtrar_dataframe(dataframe):
    temp = dataframe
    if f_idioma: temp = temp[temp['Idioma'].isin(f_idioma)]
    if f_publico: temp = temp[temp['Público'].isin(f_publico)]
    if f_gen: temp = temp[temp['genero_fix'].isin(f_gen)]
    if f_edit: temp = temp[temp['Editorial'].isin(f_edit)]
    if f_ia_gen: temp = temp[temp['Genero_Principal_IA'].isin(f_ia_gen)]
    if col_p in temp.columns: temp = temp[temp[col_p].fillna(0) <= f_pag]
    if f_local: temp = temp[temp['Geografia_Autor'].astype(str).str.contains("Local", na=False)]
    return temp

# --- 5. INTERFAZ Y TARJETAS ---
st.title(t["titulo"])
st.caption(t["subtitulo"])

def mostrar_card(r, ctx):
    with st.container(border=True):
        c1, c2 = st.columns([1, 4])
        l_id = str(r['Nº lote']).strip()
        with c1:
            foto = f"{RUTA_PORTADAS}/{l_id}.jpg"
            if os.path.exists(foto): st.image(foto, use_container_width=True)
            else: st.write("📖")
        with c2:
            st.subheader(r['Título'])
            st.write(f"**{r['Autor']}**")
            st.caption(f"Lote: {l_id} | {r['Idioma']} | {r.get(col_p,'--')} {t['pags_label']}")
            if pd.notnull(r.get('Subgeneros_Limpios_IA')):
                st.markdown(f"<small>Categoría: {r['Genero_Principal_IA']} | {r['Subgeneros_Limpios_IA']}</small>", unsafe_allow_html=True)
            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra', 'No hay resumen.'))

# --- 6. LAS 4 PESTAÑAS (TODAS RECUPERADAS) ---
tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])

with tab1: # Búsqueda clásica
    c1, c2 = st.columns(2)
    b_t = c1.text_input("Título:", key="bt")
    b_a = c2.text_input("Autor:", key="ba")
    if b_t or b_a:
        res = filtrar_dataframe(df)
        if b_t: res = res[res['Título'].str.contains(b_t, case=False, na=False)]
        if b_a: res = res[res['Autor'].str.contains(b_a, case=False, na=False)]
        for _, r in res.head(10).iterrows(): mostrar_card(r, "C")

with tab2: # Búsqueda libre IA
    q = st.text_input(t["placeholder"], key="bq")
    if q:
        df_f = filtrar_dataframe(df)
        if not df_f.empty:
            vec = model.encode([f"query: {q}"], normalize_embeddings=True).astype('float32')
            D, I = index.search(vec, 40)
            res_ia = df.iloc[I[0]]
            final = res_ia[res_ia['Nº lote'].isin(df_f['Nº lote'])].head(10)
            for _, r in final.iterrows(): mostrar_card(r, "IA")

with tab3: # Similares
    lid = st.text_input(t["lote_input"], key="bl")
    if lid:
        ref = df[df['Nº lote'] == lid.strip().upper()]
        if not ref.empty:
            v_ref = index.reconstruct(int(ref.index[0])).reshape(1, -1)
            D, I = index.search(v_ref, 15)
            for _, r in filtrar_dataframe(df.iloc[I[0]]).iterrows():
                if str(r['Nº lote']) != lid.strip().upper(): mostrar_card(r, "S")

with tab4: # Azar
    if st.button(t["boton_txt"]):
        posibles = filtrar_dataframe(df)
        if not posibles.empty: mostrar_card(posibles.sample(1).iloc[0], "R")
