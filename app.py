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

# --- FUNCIÓN AUXILIAR PARA NORMALIZAR TEXTO ---
def normalizar_texto(texto):
    if not isinstance(texto, str):
        return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

# 1. CONFIGURACIÓN E IDIOMA
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

PATH_RECO = "recomendador"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_BOTON_RANDOM = f"{PATH_RECO}/serendipia.png"
RUTA_PORTADAS = "portadas"

col_main, col_lang = st.columns([12, 1])
with col_lang:
    idioma_interfaz = st.selectbox("🌐", ["Castellano", "Euskera"])

# --- TEXTOS DE INTERFAZ ---
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
        "placeholder": "Ej: Historias de espías en la guerra civil",
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
        "no_results": "No se han encontrado resultados con suficiente coincidencia (mín. 75%).",
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
        "tab1": "📖 Bilaketa klasikoa",
        "tab2": "✨ Bilaketa librea",
        "tab3": "🔍 Lote antzekoak",
        "tab4": "🎲 Zorizko bilaketa",
        "placeholder": "Adibidez: Gerra zibileko espioi istorioak",
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
        "no_results": "Ez da nahikoa antzekotasun duten emaitzarik aurkitu (%75 gutxienez).",
        "kw_label": "Gako-hitzak"
    }
}
t = texts[idioma_interfaz]

# 2. CARGA DE RECURSOS
@st.cache_resource
def load_resources():
    df_ia = pickle.load(open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb"))
    df_ia['Nº lote'] = df_ia['Nº lote'].astype(str).str.strip()
    
    # Carga del nuevo Excel procesado
    excel_ia_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version2.xlsx"
    if os.path.exists(excel_ia_path):
        df_ex_ia = pd.read_excel(excel_ia_path)
        df_ex_ia['Nº lote'] = df_ex_ia['Nº lote'].astype(str).str.strip()
        df = pd.merge(df_ia, df_ex_ia[['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA']], on='Nº lote', how='left')
    else:
        df = df_ia
        
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")
    model = SentenceTransformer('intfloat/multilingual-e5-large')
    return df, index, model

df, index, model = load_resources()

# 3. CONEXIÓN CON GOOGLE SHEETS
def conectar_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    sheet = client.open_by_url(sheet_url).sheet1
    return sheet

def guardar_voto(lote, titulo, valor, query):
    try:
        sheet = conectar_sheets()
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(lote), str(titulo), "👍" if valor == 1 else "👎", str(query)])
        st.toast("✅ ¡Voto guardado!")
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# 5. MOSTRAR TARJETA
def mostrar_card(r, context):
    with st.container(border=True):
        col_img, col_txt, col_voto = st.columns([1,3,1])
        lote_id = str(r.get('Nº lote','')).strip()
        with col_img:
            foto_encontrada = False
            if os.path.exists(RUTA_PORTADAS):
                for f in os.listdir(RUTA_PORTADAS):
                    if os.path.splitext(f)[0] == lote_id:
                        st.image(f"{RUTA_PORTADAS}/{f}", use_container_width=True)
                        foto_encontrada = True
                        break
            if not foto_encontrada:
                st.write("📖")
                st.caption(f"Lote {lote_id}")
        with col_txt:
            st.subheader(r.get('Título','Sin título'))
            st.write(f"**{r.get('Autor','Autor desconocido')}**")
            pags_val = r.get('Páginas', r.get('Páginas_ex','--'))
            try:
                pags_display = str(int(float(pags_val))) if pd.notnull(pags_val) and str(pags_val).replace('.','',1).isdigit() else str(pags_val)
            except:
                pags_display = str(pags_val)
            st.caption(f"Lote: {lote_id} | {r.get('Idioma','--')} | {pags_display} {t['pags_label']} | {r.get('Público','--')}")
            
            # Badge de subgéneros IA si existen
            if pd.notnull(r.get('Subgeneros_Limpios_IA')):
                st.markdown(f"**{r.get('Genero_Principal_IA')}**: <small>{r.get('Subgeneros_Limpios_IA')}</small>", unsafe_allow_html=True)

            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra','No hay resumen disponible.'))
                tags = r.get('IA_Tags','')
                if pd.notnull(tags) and str(tags).strip() != "":
                    st.markdown("---")
                    st.markdown(f"**{t['kw_label']}:** {tags}")
        with col_voto:
            ctx_id = str(context)[:10].replace(" ","_")
            kv = f"v_{lote_id}_{ctx_id}"
            if kv in st.session_state:
                st.success(t["thanks"])
            else:
                st.write(f"<small>{t['ask']}</small>", unsafe_allow_html=True)
                ca, cb = st.columns(2)
                if ca.button("👍", key=f"u_{lote_id}_{ctx_id}"):
                    guardar_voto(lote_id, r.get('Título','S/T'), 1, context)
                    st.session_state[kv] = 1
                    st.rerun()
                if cb.button("👎", key=f"d_{lote_id}_{ctx_id}"):
                    guardar_voto(lote_id, r.get('Título','S/T'), 0, context)
                    st.session_state[kv] = 0
                    st.rerun()

# 6. FILTROS LATERALES
st.sidebar.title(t["sidebar_tit"])
f_idioma = st.sidebar.multiselect(t["f_idioma"], sorted(df['Idioma'].dropna().unique()))
f_publico = st.sidebar.multiselect(t["f_publico"], sorted(df['Público'].dropna().unique()))
f_gen = st.sidebar.multiselect(t["f_genero"], sorted(df['genero_fix'].dropna().unique()))
f_edit = st.sidebar.multiselect(t["f_editorial"], sorted(df['Editorial'].dropna().unique()))

col_pag_name = 'Páginas' if 'Páginas' in df.columns else 'Páginas_ex'
max_p = int(df[col_pag_name].max()) if col_pag_name in df.columns else 1500
f_pag = st.sidebar.slider(t["f_paginas"], 0, max_p, max_p)
f_local = st.sidebar.checkbox(t["f_local"])

# --- SECCIÓN IA (MOVIDA ABAJO DEL TODO) ---
st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Filtros de contenido")
opciones_ia_gen = sorted(df['Genero_Principal_IA'].dropna().unique())
f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], opciones_ia_gen)

if f_ia_gen:
    df_temp_ia = df[df['Genero_Principal_IA'].isin(f_ia_gen)]
    subs_disponibles = set()
    df_temp_ia['Subgeneros_Limpios_IA'].str.split(', ').dropna().apply(subs_disponibles.update)
    f_ia_sub = st.sidebar.multiselect(t["f_ia_sub"], sorted(list(subs_disponibles)))
else:
    f_ia_sub = []

def filtrar_dataframe(dataframe):
    temp = dataframe.copy()
    if f_idioma: temp = temp[temp['Idioma'].isin(f_idioma)]
    if f_publico: temp = temp[temp['Público'].isin(f_publico)]
    if f_gen: temp = temp[temp['genero_fix'].isin(f_gen)]
    if f_edit: temp = temp[temp['Editorial'].isin(f_edit)]
    
    # Aplicar Filtros IA
    if f_ia_gen: temp = temp[temp['Genero_Principal_IA'].isin(f_ia_gen)]
    if f_ia_sub:
        temp = temp[temp['Subgeneros_Limpios_IA'].apply(
            lambda x: any(tema in str(x) for tema in f_ia_sub) if pd.notnull(x) else False
        )]
        
    if col_pag_name in temp.columns: temp = temp[temp[col_pag_name].fillna(0) <= f_pag]
    if f_local: temp = temp[temp['Geografia_Autor'].astype(str).str.contains("Local", case=False, na=False)]
    return temp

# 7. INTERFAZ PRINCIPAL
col_logo, col_tit = st.columns([1,6])
with col_logo:
    if os.path.exists(URL_LOGO): st.image(URL_LOGO, width=150)
with col_tit:
    st.title(t["titulo"])
    st.caption(t["subtitulo"])

tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])

# --- TAB 1: BÚSQUEDA CLÁSICA ---
with tab1:
    c1,c2 = st.columns(2)
    with c1: b_tit = st.text_input(t["busq_titulo"], key="b_tit")
    with c2: b_aut = st.text_input(t["busq_autor"], key="b_aut")
   
    if b_tit or b_aut:
        res_trad = filtrar_dataframe(df)
        if b_tit: res_trad = res_trad[res_trad['titulo_norm'].str.contains(normalizar_texto(b_tit), na=False)]
        if b_aut:
            palabras_busqueda = normalizar_texto(b_aut).split()
            for palabra in palabras_busqueda:
                res_trad = res_trad[res_trad['autor_norm'].str.contains(palabra, na=False)]
        st.write(f"Resultados: {len(res_trad)}")
        for _, r in res_trad.head(20).iterrows(): mostrar_card(r, "Busq_Trad")

# --- TAB 2: BÚSQUEDA SEMÁNTICA ---
with tab2:
    q = st.text_input(t["input_query"], key="q_semant", placeholder=t["placeholder"])
    if q:
        df_base = filtrar_dataframe(df)
        if not df_base.empty:
            vec = model.encode([f"query: {q}"], normalize_embeddings=True).astype('float32')
            D, I = index.search(vec, 100)
            res_ia = df.iloc[I[0]].copy()
            res_ia['score_ia'] = D[0]
            final = res_ia[res_ia['Nº lote'].isin(df_base['Nº lote'])]
            final = final[final['score_ia'] >= 0.75].sort_values('score_ia', ascending=False).head(10)
            if final.empty:
                st.info(t["no_results"])
            else:
                for _, r in final.iterrows(): mostrar_card(r, q)
        else:
            st.warning("No hay resultados con los filtros laterales aplicados.")

# --- TAB 3: LOTES SIMILARES ---
with tab3:
    lid = st.text_input(t["lote_input"], key="q_lote")
    if lid:
        lid_clean = lid.strip().upper()
        ref = df[df['Nº lote'] == lid_clean]
        if not ref.empty:
            idx_faiss = ref.index[0]
            v_ref = index.reconstruct(int(idx_faiss)).reshape(1, -1).astype('float32')
            D, I = index.search(v_ref, 25)
            res_sim = df.iloc[I[0]].copy()
            res_sim['score_ia'] = D[0]
            res_sim_score = res_sim[res_sim['score_ia'] >= 0.70]
            sim = filtrar_dataframe(res_sim_score)
            final_sim = sim[sim['Nº lote'] != lid_clean].head(10)
            if final_sim.empty:
                st.info(t["no_results"])
            else:
                for _, r in final_sim.iterrows(): mostrar_card(r, f"Sim_{lid_clean}")

# --- TAB 4: BÚSQUEDA ALEATORIA ---
with tab4:
    st.write(t["serendipia_txt"])
    if os.path.exists(URL_BOTON_RANDOM): st.image(URL_BOTON_RANDOM, width=200)
    if st.button(t["boton_txt"], type="primary"):
        posibles = filtrar_dataframe(df)
        if not posibles.empty: st.session_state.azar = posibles.sample(1).iloc[0]
    if 'azar' in st.session_state: mostrar_card(st.session_state.azar, "Seren")

