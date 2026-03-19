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

# =========================
# 🔤 NORMALIZACIÓN
# =========================
def normalizar_texto(texto):
    if not isinstance(texto, str):
        return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

PATH_RECO = "recomendador"
RUTA_PORTADAS = "portadas"

# =========================
# 🚀 CARGA BASE
# =========================
@st.cache_resource
def load_base():
    df_ia = pickle.load(open(f"{PATH_RECO}/metadatos_promptss_infloat_ponderado_genero.pkl", "rb"))
    df_ia['Nº lote'] = df_ia['Nº lote'].astype(str).str.strip()

    excel_ia_path = f"{PATH_RECO}/CATALOGO_PROCESADO_version3.xlsx"
    if os.path.exists(excel_ia_path):
        df_ex_ia = pd.read_excel(excel_ia_path)
        df_ex_ia['Nº lote'] = df_ex_ia['Nº lote'].astype(str).str.strip()
        df = pd.merge(df_ia, df_ex_ia[['Nº lote', 'Genero_Principal_IA', 'Subgeneros_Limpios_IA']], on='Nº lote', how='left')
    else:
        df = df_ia

    # Optimización tipos
    for col in ['Idioma', 'Público', 'Editorial', 'genero_fix']:
        if col in df.columns:
            df[col] = df[col].astype('category')

    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)

    index = faiss.read_index(f"{PATH_RECO}/biblioteca_prompts_infloat_ponderado_genero.index")

    return df, index

# =========================
# 🧠 MODELO
# =========================
@st.cache_resource
def load_model():
    return SentenceTransformer('intfloat/multilingual-e5-large')

# =========================
# 🖼️ PORTADAS
# =========================
@st.cache_data
def get_portadas():
    if not os.path.exists(RUTA_PORTADAS):
        return {}
    return {os.path.splitext(f)[0]: f for f in os.listdir(RUTA_PORTADAS)}

# =========================
# 📊 GOOGLE SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    return client.open_by_url(sheet_url).sheet1

def guardar_voto(lote, titulo, valor, query):
    try:
        sheet = conectar_sheets()
        sheet.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            lote, titulo,
            "👍" if valor == 1 else "👎",
            query
        ])
        st.toast("✅ ¡Voto guardado!")
    except Exception as e:
        st.error(f"Error al guardar: {e}")

# =========================
# 📦 INIT
# =========================
df, index = load_base()
portadas = get_portadas()

# =========================
# 🎯 FILTROS
# =========================
st.sidebar.title("🎯 Panel de Control")

f_idioma = st.sidebar.multiselect("Idioma", sorted(df['Idioma'].dropna().unique()))
f_publico = st.sidebar.multiselect("Público", sorted(df['Público'].dropna().unique()))
f_gen = st.sidebar.multiselect("Género Autor/a", sorted(df['genero_fix'].dropna().unique()))
f_edit = st.sidebar.multiselect("Editorial", sorted(df['Editorial'].dropna().unique()))

def filtrar_dataframe(dataframe):
    temp = dataframe
    if f_idioma:
        temp = temp[temp['Idioma'].isin(f_idioma)]
    if f_publico:
        temp = temp[temp['Público'].isin(f_publico)]
    if f_gen:
        temp = temp[temp['genero_fix'].isin(f_gen)]
    if f_edit:
        temp = temp[temp['Editorial'].isin(f_edit)]
    return temp

# =========================
# 📖 TARJETA
# =========================
def mostrar_card(r, context):
    with st.container(border=True):
        col1, col2, col3 = st.columns([1,3,1])
        lote_id = str(r.get('Nº lote','')).strip()

        with col1:
            if lote_id in portadas:
                st.image(f"{RUTA_PORTADAS}/{portadas[lote_id]}", use_container_width=True)
            else:
                st.write("📖")

        with col2:
            st.subheader(r.get('Título','Sin título'))
            st.write(f"**{r.get('Autor','Autor desconocido')}**")

        with col3:
            key = f"v_{lote_id}_{context}"
            if key not in st.session_state:
                if st.button("👍", key=f"u_{key}"):
                    guardar_voto(lote_id, r.get('Título','S/T'), 1, context)
                    st.session_state[key] = 1
                    st.rerun()

# =========================
# 🧭 TABS
# =========================
tab1, tab2, tab3, tab4 = st.tabs([
    "📖 Búsqueda clásica",
    "✨ Búsqueda semántica",
    "🔍 Lotes similares",
    "🎲 Aleatoria"
])

# =========================
# 📖 TAB 1
# =========================
with tab1:
    t1, t2 = st.columns(2)
    b_tit = t1.text_input("Título")
    b_aut = t2.text_input("Autor")

    if b_tit or b_aut:
        res = filtrar_dataframe(df)

        if b_tit:
            res = res[res['titulo_norm'].str.contains(normalizar_texto(b_tit), na=False)]

        if b_aut:
            for palabra in normalizar_texto(b_aut).split():
                res = res[res['autor_norm'].str.contains(palabra, na=False)]

        for _, r in res.head(20).iterrows():
            mostrar_card(r, "trad")

# =========================
# ✨ TAB 2
# =========================
with tab2:
    q = st.text_input("Consulta libre")

    if q:
        if "model" not in st.session_state:
            st.session_state.model = load_model()

        model = st.session_state.model

        df_base = filtrar_dataframe(df)

        vec = model.encode([f"query: {q}"], normalize_embeddings=True)
        vec = vec.astype('float16').astype('float32')

        D, I = index.search(vec, 30)

        res = df.iloc[I[0]]
        res['score'] = D[0]

        final = res[
            (res['score'] >= 0.79) &
            (res['Nº lote'].isin(df_base['Nº lote']))
        ].head(10)

        for _, r in final.iterrows():
            mostrar_card(r, q)

# =========================
# 🔍 TAB 3
# =========================
with tab3:
    lid = st.text_input("Código de lote")

    if lid:
        ref = df[df['Nº lote'] == lid.strip()]

        if not ref.empty:
            idx = ref.index[0]

            v = index.reconstruct(int(idx)).reshape(1, -1).astype('float32')

            D, I = index.search(v, 25)

            res = df.iloc[I[0]]
            res['score'] = D[0]

            final = res[
                (res['score'] >= 0.80) &
                (res['Nº lote'] != lid)
            ].head(10)

            for _, r in final.iterrows():
                mostrar_card(r, lid)

# =========================
# 🎲 TAB 4
# =========================
with tab4:
    if st.button("Sorpréndeme"):
        posibles = filtrar_dataframe(df)
        if not posibles.empty:
            st.session_state.rand = posibles.sample(1).iloc[0]

    if "rand" in st.session_state:
        mostrar_card(st.session_state.rand, "random")
