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
import gc  
import psutil

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

# Selector de idioma persistente
if "idioma" not in st.session_state:
    st.session_state.idioma = "Castellano"

col_main, col_lang = st.columns([12, 1])
with col_lang:
    idioma_actual = st.selectbox("🌐", ["Castellano", "Euskera"], index=0 if st.session_state.idioma == "Castellano" else 1, key="selector_global")
    st.session_state.idioma = idioma_actual

# --- TEXTOS DE INTERFAZ ---
texts = {
    "Castellano": {
        "titulo": "Clubes de Lectura de Navarra", "subtitulo": "Nafarroako Irakurketa Klubak",
        "sidebar_tit": "🎯 Panel de Control", "f_idioma": "🌍 Idioma", "f_publico": "👥 Público",
        "f_genero": "👤 Género Autor/a", "f_editorial": "📚 Editorial", "f_paginas": "📄 Máx Páginas",
        "f_local": "🏠 Autores locales", "f_ia_gen": "📂 Categoría Principal", "f_ia_sub": "🏷️ Temas y Estilos",
        "tab1": "📖 Búsqueda por autor/título", "tab2": "✨ Búsqueda libre", "tab3": "🔍 Lotes similares", "tab4": "🎲 Búsqueda aleatoria",
        "placeholder": "Ej: Novelas sobre la historia de Navarra", "input_query": "Puedes escribir lo que quieras",
        "lote_input": "Introduce el código del lote:", "busq_titulo": "Buscar por Título:", "busq_autor": "Buscar por Autor:",
        "resumen_btn": "Ver resumen", "pags_label": "págs", "thanks": "✅ Voto registrado", "ask": "¿Te gusta esta recomendación?",
        "boton_txt": "¡Sorpréndeme!", "serendipia_txt": "Deja que el azar elija por ti:", "no_results": "Sin resultados (mín. 80%).", "kw_label": "Palabras clave"
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
t = texts[st.session_state.idioma]

# 2. CARGA DE RECURSOS (MÁXIMA OPTIMIZACIÓN)
@st.cache_resource
def load_resources():
    # 1. CARGAR PICKLE (METADATOS BASE)
    with open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_small.pkl", "rb") as f:
        df_ia = pickle.load(f)
    
    # Limpiar columnas pesadas del pickle
    for c in df_ia.columns:
        if 'embed' in c.lower() or 'vector' in c.lower():
            df_ia.drop(columns=[c], inplace=True)
    
    df_ia['Nº lote'] = df_ia['Nº lote'].astype(str).str.strip()
    
    # 2. CARGAR EXCEL (SOLO COLUMNAS IA)
    excel_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx"
    if os.path.exists(excel_path):
        # Cargamos solo lo necesario para no reventar la RAM
        df_ex = pd.read_excel(excel_path, usecols=['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA'])
        df_ex['Nº lote'] = df_ex['Nº lote'].astype(str).str.strip()
        
        # Merge y limpieza
        df = pd.merge(df_ia, df_ex, on='Nº lote', how='left')
        del df_ia, df_ex
    else:
        df = df_ia

    # 3. TIPOS DE DATOS LIGEROS
    for col in ['Idioma', 'Público', 'genero_fix', 'Editorial', 'Genero_Principal_IA']:
        if col in df.columns:
            df[col] = df[col].astype('category')
        
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
    
# 4. CARGAR INDEX Y MODELO
    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_small.index")
    
    # Importamos torch aquí mismo para configurar el ahorro de RAM
    import torch
    torch.set_num_threads(1) # Evita que la CPU intente usar demasiada memoria a la vez
    
    # Cargamos el modelo forzando limpieza
    model = SentenceTransformer('intfloat/multilingual-e5-small', device='cpu')
    
    # Limpieza agresiva de RAM
    gc.collect() 
    return df, index, model

# 3. CONEXIÓN CON GOOGLE SHEETS
def conectar_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    return gspread.authorize(creds).open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"]).sheet1

def guardar_voto(lote, titulo, valor, query):
    try:
        sheet = conectar_sheets()
        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(lote), str(titulo), "👍" if valor == 1 else "👎", str(query)])
        st.toast("✅ ¡Voto guardado!")
    except: pass

# 5. MOSTRAR TARJETA
def mostrar_card(r, context):
    with st.container(border=True):
        col_img, col_txt, col_voto = st.columns([1,3,1])
        lote_id = str(r.get('Nº lote','')).strip()
        
        with col_img:
            foto_encontrada = False
            for ext in ['.jpg', '.jpeg', '.png', '.JPG']:
                ruta = f"{RUTA_PORTADAS}/{lote_id}{ext}"
                if os.path.exists(ruta):
                    st.image(ruta, use_container_width=True)
                    foto_encontrada = True
                    break
            if not foto_encontrada: st.write("📖")

        with col_txt:
            st.subheader(r.get('Título','Sin título'))
            st.write(f"**{r.get('Autor','Autor desconocido')}**")
            pags = r.get('Páginas', r.get('Páginas_ex','--'))
            st.caption(f"Lote: {lote_id} | {r.get('Idioma','--')} | {pags} {t['pags_label']} | {r.get('Público','--')}")
            
            if pd.notnull(r.get('Genero_Principal_IA')):
                st.markdown(f"**{r.get('Genero_Principal_IA')}**: <small>{r.get('Subgeneros_Limpios_IA', '')}</small>", unsafe_allow_html=True)

            with st.expander(t["resumen_btn"]):
                st.write(r.get('Resumen_navarra','No hay resumen.'))

        with col_voto:
            kv = f"v_{lote_id}_{str(context)[:5]}"
            if kv in st.session_state: st.success(t["thanks"])
            else:
                st.write(f"<small>{t['ask']}</small>", unsafe_allow_html=True)
                if st.button("👍", key=f"u_{lote_id}_{kv}"):
                    guardar_voto(lote_id, r.get('Título',''), 1, context)
                    st.session_state[kv] = 1
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

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 Filtros IA")

f_ia_gen = []
f_ia_sub = []
if 'Genero_Principal_IA' in df.columns and not df['Genero_Principal_IA'].isna().all():
    opciones_ia_gen = sorted(df['Genero_Principal_IA'].dropna().unique())
    f_ia_gen = st.sidebar.multiselect(t["f_ia_gen"], opciones_ia_gen)
    if f_ia_gen and 'Subgeneros_Limpios_IA' in df.columns:
        df_temp_ia = df[df['Genero_Principal_IA'].isin(f_ia_gen)]
        subs = set()
        df_temp_ia['Subgeneros_Limpios_IA'].str.split(', ').dropna().apply(subs.update)
        f_ia_sub = st.sidebar.multiselect(t["f_ia_sub"], sorted(list(subs)))
else:
    st.sidebar.info("Filtros IA no disponibles")

def filtrar_dataframe(dataframe):
    temp = dataframe.copy()
    if f_idioma: temp = temp[temp['Idioma'].isin(f_idioma)]
    if f_publico: temp = temp[temp['Público'].isin(f_publico)]
    if f_gen: temp = temp[temp['genero_fix'].isin(f_gen)]
    if f_edit: temp = temp[temp['Editorial'].isin(f_edit)]
    if f_ia_gen: temp = temp[temp['Genero_Principal_IA'].isin(f_ia_gen)]
    if f_ia_sub:
        temp = temp[temp['Subgeneros_Limpios_IA'].apply(lambda x: any(tema in str(x) for tema in f_ia_sub) if pd.notnull(x) else False)]
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

with tab1:
    c1,c2 = st.columns(2)
    with c1: b_tit = st.text_input(t["busq_titulo"])
    with c2: b_aut = st.text_input(t["busq_autor"])
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
            vec = model.encode([f"query: {q}"], normalize_embeddings=True).astype('float32')
            D, I = index.search(vec, 50)
            res_ia = df.iloc[I[0]].copy()
            res_ia['score_ia'] = D[0]
            final = res_ia[res_ia['Nº lote'].isin(df_base['Nº lote'])]
            final = final[final['score_ia'] >= 0.78].sort_values('score_ia', ascending=False).head(10)
            if final.empty: st.info(t["no_results"])
            else:
                for _, r in final.iterrows(): mostrar_card(r, q)

with tab3:
    lid = st.text_input(t["lote_input"])
    if lid:
        ref = df[df['Nº lote'] == lid.strip().upper()]
        if not ref.empty:
            idx = ref.index[0]
            v_ref = index.reconstruct(int(idx)).reshape(1, -1).astype('float32')
            D, I = index.search(v_ref, 20)
            res_sim = df.iloc[I[0]].copy()
            res_sim['score_ia'] = D[0]
            sim = filtrar_dataframe(res_sim[res_sim['score_ia'] >= 0.80])
            for _, r in sim[sim['Nº lote'] != lid.strip().upper()].head(10).iterrows(): mostrar_card(r, "Sim")

with tab4:
    if st.button(t["boton_txt"]):
        posibles = filtrar_dataframe(df)
        if not posibles.empty: st.session_state.azar = posibles.sample(1).iloc[0]
    if 'azar' in st.session_state: mostrar_card(st.session_state.azar, "Seren")

# =========================
# 📊 MONITOR DE MEMORIA COMPLETO
# =========================
import psutil
import os
import tracemalloc
import gc

# Iniciar tracemalloc solo una vez
if "trace_started" not in st.session_state:
    tracemalloc.start()
    st.session_state.trace_started = True

process = psutil.Process(os.getpid())
mem_info = process.memory_full_info()

# 🔹 Memoria del sistema (proceso)
rss = mem_info.rss / 1024 / 1024
vms = mem_info.vms / 1024 / 1024

# 🔹 Memoria Python
current, peak = tracemalloc.get_traced_memory()
current_mb = current / 1024 / 1024
peak_mb = peak / 1024 / 1024

# 🔹 Colores según uso
def color_mem(val):
    if val < 700:
        return "green"
    elif val < 1000:
        return "orange"
    else:
        return "red"

# 🔹 Mostrar en sidebar
st.sidebar.markdown("## 🧠 Monitor RAM")

st.sidebar.markdown(f"**RSS (real proceso):** :{color_mem(rss)}[{rss:.2f} MB]")
st.sidebar.markdown(f"**VMS (virtual):** {vms:.2f} MB")

st.sidebar.markdown("---")

st.sidebar.markdown(f"**Python actual:** :{color_mem(current_mb)}[{current_mb:.2f} MB]")
st.sidebar.markdown(f"**Python pico:** :{color_mem(peak_mb)}[{peak_mb:.2f} MB]")

st.sidebar.markdown("---")

# 🔹 Botón para forzar limpieza
if st.sidebar.button("🧹 Forzar Garbage Collector"):
    gc.collect()
    st.sidebar.success("GC ejecutado")

# 🔹 Info interpretativa rápida
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Interpretación")
st.sidebar.caption(f"""
- RSS = memoria REAL total (incluye modelo, FAISS, etc.)
- Python = solo objetos Python (df, listas...)
- Pico = máximo alcanzado (clave para crashes)
""")
