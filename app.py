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

# --- 1. CONFIGURACIÓN E IDIOMA ---
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

# Rutas robustas
BASE_DIR = os.path.dirname(__file__)
PATH_RECO = os.path.join(BASE_DIR, "recomendador")
RUTA_PORTADAS = os.path.join(BASE_DIR, "portadas")

# Nombres de archivos de imagen (Asegúrate de que coincidan en GitHub)
URL_LOGO = os.path.join(PATH_RECO, "logo_B. Navarra.jpg")
URL_BOTON_RANDOM = os.path.join(PATH_RECO, "serendipia.png")

@st.cache_data
def get_texts():
    return {
        "Castellano": {
            "titulo": "Clubes de Lectura de Navarra", "subtitulo": "Nafarroako Irakurketa Klubak",
            "sidebar_tit": "🎯 Panel de Control", "f_idioma": "🌍 Idioma", "f_publico": "👥 Público",
            "f_genero": "👤 Género Autor/a", "f_editorial": "📚 Editorial", "f_paginas": "📄 Máx Páginas",
            "f_local": "🏠 Autores locales", "f_ia_gen": "📂 Categoría Principal", "f_ia_sub": "🏷️ Temas y Estilos",
            "tab1": "📖 Autor/Título", "tab2": "✨ Búsqueda libre", "tab3": "🔍 Similares", "tab4": "🎲 Azar",
            "placeholder": "Ej: Novelas de misterio en el Baztán", "input_query": "Búsqueda semántica:",
            "lote_input": "Código del lote:", "busq_titulo": "Título:", "busq_autor": "Autor:",
            "resumen_btn": "Ver resumen", "pags_label": "págs", "thanks": "✅ Voto registrado", 
            "ask": "¿Te gusta?", "boton_txt": "¡Sorpréndeme!", "serendipia_txt": "Deja que el azar elija:",
            "no_results": "Sin resultados coincidentes.", "kw_label": "Palabras clave"
        },
        "Euskera": {
            "titulo": "Nafarroako Irakurketa Klubak", "subtitulo": "Clubes de Lectura de Navarra",
            "sidebar_tit": "🎯 Kontrol Panela", "f_idioma": "🌍 Hizkuntza", "f_publico": "👥 Publikoa",
            "f_genero": "👤 Egilearen generoa", "f_editorial": "📚 Argitaletxea", "f_paginas": "📄 Orrialdeak",
            "f_local": "🏠 Bertakoak", "f_ia_gen": "📂 Kategoria Nagusia", "f_ia_sub": "🏷️ Gaiak",
            "tab1": "📖 Idazle/Izenburua", "tab2": "✨ Bilaketa librea", "tab3": "🔍 Antzekoak", "tab4": "🎲 Zoriz",
            "placeholder": "Adibidez: Baztango misteriozko eleberriak", "input_query": "Bilaketa semantikoa:",
            "lote_input": "Lote kodea:", "busq_titulo": "Izenburua:", "busq_autor": "Egilea:",
            "resumen_btn": "Ikusi laburpena", "pags_label": "orr", "thanks": "✅ Iritzia gordeta", 
            "ask": "Gogoko duzu?", "boton_txt": "Harritu nazazu!", "serendipia_txt": "Utzi zoriari aukeratzen:",
            "no_results": "Emaitzarik gabe.", "kw_label": "Gako-hitzak"
        }
    }

t = get_texts()[st.sidebar.selectbox("🌐", ["Castellano", "Euskera"])]

# --- 2. CARGA DE RECURSOS (OPTIMIZADO) ---
@st.cache_data
def normalizar_texto(texto):
    if not isinstance(texto, str): return ""
    return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower().strip()

@st.cache_resource
def load_resources():
    # Metadatos base
    with open(os.path.join(PATH_RECO, "metadatos_promptss_infloat_ponderado_genero.pkl"), "rb") as f:
        df = pickle.load(f)
    df['Nº lote'] = df['Nº lote'].astype(str).str.strip()
    
    # Merge con IA
    ex_path = os.path.join(PATH_RECO, "CATALOGO_PROCESADO_version3.xlsx")
    if os.path.exists(ex_path):
        df_ex = pd.read_excel(ex_path, usecols=['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA'])
        df_ex['Nº lote'] = df_ex['Nº lote'].astype(str).str.strip()
        df = pd.merge(df, df_ex, on='Nº lote', how='left')
    
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
    
    # Reducción de memoria
    for c in ['Idioma', 'Público', 'genero_fix', 'Editorial', 'Genero_Principal_IA']:
        if c in df.columns: df[c] = df[c].astype('category')

    idx = faiss.read_index(os.path.join(PATH_RECO, "biblioteca_prompts_infloat_ponderado_genero.index"))
    mdl = SentenceTransformer('intfloat/multilingual-e5-large')
    return df, idx, mdl

df, index, model = load_resources()

# --- 3. GOOGLE SHEETS ---
def guardar_voto(lote, titulo, valor, query):
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"]).sheet1
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(lote), str(titulo), "👍" if valor == 1 else "👎", str(query)])
        st.toast(t["thanks"])
    except: pass

# --- 4. FILTROS LATERALES ---
st.sidebar.title(t["sidebar_tit"])
st.sidebar.subheader("📌 Filtros Generales")
f_idioma = st.sidebar.multiselect(t["f_idioma"], sorted(df['Idioma'].unique().tolist()))
f_publico = st.sidebar.multiselect(t["f_publico"], sorted(df['Público'].unique().tolist()))
f_gen = st.sidebar.multiselect(t["f_genero"], sorted(df['genero_fix'].dropna().unique().tolist()))

col_p = 'Páginas' if 'Páginas' in df.columns else 'Páginas_ex'
max_p = int(df[col_p].max()) if col_p in df.columns else 1500
f_pag = st.sidebar.slider(t["f_paginas"], 0, max_p, max_p)
f_local = st.sidebar.checkbox(t["f_local"])

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Filtros Inteligentes")
f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], sorted(df['Genero_Principal_IA'].dropna().unique().tolist()))

f_ia_sub = []
if f_ia_gen:
    st.sidebar.write(f"🔍 {t['f_ia_sub']}")
    subs = set()
    df[df['Genero_Principal_IA'].isin(f_ia_gen)]['Subgeneros_Limpios_IA'].str.split(', ').dropna().apply(subs.update)
    f_ia_sub = st.sidebar.multiselect("", sorted(list(subs)))

def filtrar_dataframe(dataframe):
    m = pd.Series(True, index=dataframe.index)
    if f_idioma: m &= dataframe['Idioma'].isin(f_idioma)
    if f_publico: m &= dataframe['Público'].isin(f_publico)
    if f_gen: m &= dataframe['genero_fix'].isin(f_gen)
    if f_ia_gen: m &= dataframe['Genero_Principal_IA'].isin(f_ia_gen)
    if f_ia_sub: m &= dataframe['Subgeneros_Limpios_IA'].apply(lambda x: any(s in str(x) for s in f_ia_sub) if pd.notnull(x) else False)
    if col_p in dataframe.columns: m &= (dataframe[col_p].fillna(0) <= f_pag)
    if f_local: m &= dataframe['Geografia_Autor'].astype(str).str.contains("Local", case=False, na=False)
    return dataframe[m]

# --- 5. TARJETAS ---
def mostrar_card(r, context):
    with st.container(border=True):
        col_img, col_txt, col_voto = st.columns([1,3,1])
        lote_id = str(r.get('Nº lote','')).strip()
        with col_img:
            img_p = os.path.join(RUTA_PORTADAS, f"{lote_id}.jpg")
            if os.path.exists(img_p): st.image(img_p, use_container_width=True)
            else: st.write("📖")
        with col_txt:
            st.subheader(r.get('Título','--'))
            st.write(f"**{r.get('Autor','--')}**")
            st.caption(f"Lote: {lote_id} | {r.get('Idioma','--')} | {r.get(col_p,'--')} {t['pags_label']}")
            if pd.notnull(r.get('Subgeneros_Limpios_IA')):
                st.markdown(f"<small>**{r['Genero_Principal_IA']}**: {r['Subgeneros_Limpios_IA']}</small>", unsafe_allow_html=True)
            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra','--'))
        with col_voto:
            kv = f"v_{lote_id}_{str(context)[:5]}"
            if kv in st.session_state: st.success(t["thanks"])
            else:
                if st.button("👍", key=f"u_{lote_id}_{kv}"):
                    guardar_voto(lote_id, r['Título'], 1, context)
                    st.session_state[kv]=1; st.rerun()
                if st.button("👎", key=f"d_{lote_id}_{kv}"):
                    guardar_voto(lote_id, r['Título'], 0, context)
                    st.session_state[kv]=0; st.rerun()

# --- 6. INTERFAZ ---
c_logo, c_tit = st.columns([1,6])
with c_logo:
    if os.path.exists(URL_LOGO): st.image(URL_LOGO, width=150)
    else: st.write("🏛️")
with c_tit:
    st.title(t["titulo"])
    st.caption(t["subtitulo"])

tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])

with tab1: # Clásica
    c1, c2 = st.columns(2)
    b_t, b_a = c1.text_input(t["busq_titulo"]), c2.text_input(t["busq_autor"])
    if b_t or b_a:
        res = filtrar_dataframe(df)
        if b_t: res = res[res['titulo_norm'].str.contains(normalizar_texto(b_t), na=False)]
        if b_a: res = res[res['autor_norm'].str.contains(normalizar_texto(b_a), na=False)]
        for _, r in res.head(10).iterrows(): mostrar_card(r, "Busq")

with tab2: # IA
    q = st.text_input(t["input_query"], placeholder=t["placeholder"])
    if q:
        vec = model.encode([f"query: {q}"], normalize_embeddings=True).astype('float32')
        D, I = index.search(vec, 50)
        res_ia = df.iloc[I[0]].copy()
        res_ia['score'] = D[0]
        final = filtrar_dataframe(res_ia)
        final = final[final['score'] >= 0.79].head(10)
        for _, r in final.iterrows(): mostrar_card(r, q)

with tab3: # Similares
    lid = st.text_input(t["lote_input"])
    if lid:
        ref = df[df['Nº lote'] == lid.strip().upper()]
        if not ref.empty:
            v_ref = index.reconstruct(int(ref.index[0])).reshape(1, -1)
            D, I = index.search(v_ref, 15)
            for _, r in filtrar_dataframe(df.iloc[I[0]]).iterrows():
                if r['Nº lote'] != lid.strip().upper(): mostrar_card(r, "Sim")

with tab4: # Azar
    st.markdown("### " + t["serendipia_txt"])
    c_img, c_btn = st.columns([1,3])
    with c_img:
        if os.path.exists(URL_BOTON_RANDOM): st.image(URL_BOTON_RANDOM, use_container_width=True)
    with c_btn:
        if st.button(t["boton_txt"], type="primary"):
            pos = filtrar_dataframe(df)
            if not pos.empty: st.session_state.azar = pos.sample(1).iloc[0]
    if 'azar' in st.session_state: mostrar_card(st.session_state.azar, "Azar")
