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
import json
import gc
import numpy as np
import sqlite3
import hashlib


# --- 0. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

# --- 1. INICIALIZAR ESTADO TEMPRANO ---
if "idioma" not in st.session_state:
    st.session_state.idioma = "Castellano"
if "auth" not in st.session_state:
    st.session_state.auth = False

# --- FUNCIONES DE AUTENTICACIÓN (NUEVAS) ---

def conectar_sheets():
    try:
        # --- PRIORIDAD 1: Hugging Face / Variables de Entorno (Settings > Secrets) ---
        if "GCP_SERVICE_ACCOUNT" in os.environ and "GSHEET_URL" in os.environ:
            creds_info = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
            sheet_url = os.environ["GSHEET_URL"]

        # --- PRIORIDAD 2: Streamlit Cloud secrets (Si usaras share.streamlit.io) ---
        elif "gcp_service_account" in st.secrets:
            creds_info = st.secrets["gcp_service_account"]
            # En Streamlit secrets a veces se usa minúscula o mayúscula, 
            # aseguramos capturar la URL:
            sheet_url = st.secrets.get("GSHEET_URL") or st.secrets.get("gsheet_url")

        else:
            st.error("❌ No se encontraron las credenciales en os.environ ni en st.secrets")
            return None

        # Configuración de las credenciales de Google
        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )

        gc_client = gspread.authorize(creds)
        sheet = gc_client.open_by_url(sheet_url).sheet1

        return sheet

    except Exception as e:
        st.error(f"❌ Error conectando a Sheets: {e}")
        return None


def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def registrar_usuario_en_sheets(username, password):
    sheet_control = conectar_sheets()
    if not sheet_control: return False
    try:
        spreadsheet = sheet_control.spreadsheet
        try:
            ws_user = spreadsheet.worksheet("usuarios")
        except:
            # Crea la pestaña si no existe
            ws_user = spreadsheet.add_worksheet(title="usuarios", rows="100", cols="2")
            ws_user.append_row(["username", "password"])

        # Evitar duplicados
        usuarios_registrados = ws_user.col_values(1)
        if username in usuarios_registrados:
            return False

        ws_user.append_row([username, hash_password(password)])
        return True
    except Exception as e:
        st.error(f"Error en registro: {e}")
        return False

def verificar_usuario_en_sheets(username, password):
    sheet_control = conectar_sheets()
    if not sheet_control: return False
    try:
        spreadsheet = sheet_control.spreadsheet
        ws_user = spreadsheet.worksheet("usuarios")
        datos = ws_user.get_all_records()
        for fila in datos:
            if str(fila['username']) == str(username):
                return fila['password'] == hash_password(password)
        return False
    except Exception as e:
        # Si la pestaña no existe aún, nadie puede loguearse
        return False

# --- INTERFAZ DE ACCESO ---

if not st.session_state.auth:
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        st.title("🔐 Acceso")
        opcion = st.radio("Acción", ["Login", "Registro"], horizontal=True)
        
        if opcion == "Login":
            with st.form("f_login"):
                u = st.text_input("Usuario")
                p = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Entrar"):
                    if verificar_usuario_en_sheets(u, p): # <--- Llamada a Sheets
                        st.session_state.auth = True
                        st.session_state.usuario_actual = u
                        st.rerun()
                    else:
                        st.error("Error en credenciales o usuario inexistente")
        else:
            with st.form("f_reg"):
                nu = st.text_input("Nuevo Usuario")
                np = st.text_input("Nueva Contraseña", type="password")
                if st.form_submit_button("Registrarse"):
                    if registrar_usuario_en_sheets(nu, np): # <--- Llamada a Sheets
                        st.success("¡Usuario creado en la nube!")
                    else:
                        st.error("El usuario ya existe o hubo un problema técnico")
    
    st.stop()
    
    #st.stop() # <--- ESTO ES LO QUE BLOQUEA EL RESTO DEL CÓDIGO. Se puede quitar para no obligar a autenticarse


# --- 1. CONFIGURACIÓN E IDIOMAS ---
PATH_RECO = "recomendador"
URL_LOGO = f"{PATH_RECO}/logo_B. Navarra.jpg"
URL_SERENDIPIA = f"{PATH_RECO}/serendipia.png"
RUTA_PORTADAS = "portadas"

def normalizar_texto(texto):
    if not isinstance(texto, str): return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

# --- APOYO PARA FECHAS ---
def comprobar_disponibilidad(texto_reserva, rango_usuario):
    if not isinstance(texto_reserva, str) or texto_reserva.lower() in ["nan", ""]:
        return True 
    if len(rango_usuario) != 2:
        return True 
    try:
        import re
        fechas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto_reserva)
        if len(fechas) < 2: return False 
        inicio_res = datetime.strptime(fechas[0], "%d/%m/%Y").date()
        fin_res = datetime.strptime(fechas[-1], "%d/%m/%Y").date()
        ini_u, fin_u = rango_usuario
        return not ((ini_u <= fin_res) and (fin_u >= inicio_res))
    except:
        return False

# --- SELECTOR DE IDIOMA (Antes de los textos) ---
col_main, col_lang = st.columns([12, 1])
with col_lang:
    idioma_actual = st.selectbox("🌐", ["Castellano", "Euskera"], index=0 if st.session_state.idioma == "Castellano" else 1, key="selector_global")
    st.session_state.idioma = idioma_actual

texts = {
    "Castellano": {
        "titulo": "Clubes de Lectura de Navarra", 
        "subtitulo": "Nafarroako Irakurketa Klubak",
        "sidebar_tit": "🎯 Panel de Control",
        "exp_gral": "⚙️ Filtros generales", 
        "exp_cont": "📖 Filtros de contenido",
        "exp_disp": "📅 Disponibilidad", # <--- NUEVA
        "f_actualizacion": "Última actualización: 25/03/2026", # <--- NUEVA
        "f_solo_disp": "Solo disponibles ahora", # <--- NUEV
        "f_idioma": "🌍 Idioma", 
        "f_publico": "👥 Público",
        "f_genero_aut": "👤 Género Autor/a", 
        "f_editorial": "📚 Editorial", 
        "f_paginas": "📄 Número de páginas",
        "f_local": "🏠 Autores locales", 
        "f_ia_gen": "📂 Género", 
        "f_ia_sub": "🏷️ Subgénero",
        "tab1": "📖 Búsqueda por autor/título", 
        "tab2": "✨ Búsqueda libre", 
        "tab3": "🔍 Lotes similares", 
        "tab4": "🎲 Búsqueda aleatoria",
        "placeholder": "Ej: Novelas sobre la historia de Navarra", 
        "input_query": "Puedes escribir lo que quieras",
        "lote_input": "Introduce el código del lote. Puedes introducir más de un lote para buscar lotes intermedios. Por ejemplo, 121N, 445N, etc.:", 
        "busq_titulo": "Buscar por Título:", 
        "busq_autor": "Buscar por Autor:",
        "resumen_btn": "Ver resumen", 
        "pags_label": "págs", 
        "thanks": "✅ Voto registrado", 
        "ask": "¿Te gusta esta recomendación?",
        "voto_pregunta": "Te parece relevante?",
        "boton_txt": "¡Sorpréndeme!", 
        "no_results": "Sin resultados con esos filtros.",
        "cols": {
            "idioma": "Idioma",
            "publico": "Público",
            "genero_aut": "genero_fix",
            "ia_gen": "Genero_Principal_IA",
            "ia_sub": "Subgeneros_Limpios_IA"
        }
    },
    "Euskera": {
        "titulo": "Nafarroako Irakurketa Klubak", 
        "subtitulo": "Clubes de Lectura de Navarra",
        "sidebar_tit": "🎯 Kontrol Panela",
        "exp_gral": "⚙️ Iragazki orokorrak", 
        "exp_cont": "📖 Edukiaren iragazkiak",
        "exp_disp": "📅 Erabilgarritasuna", # <--- NUEVA
        "f_actualizacion": "Azken eguneratzea: 2026/03/25", # <--- NUEVA
        "f_solo_disp": "Libre daudenak bakarrik", # <--- NUEVA
        "f_idioma": "🌍 Hizkuntza", 
        "f_publico": "👥 Publikoa",
        "f_genero_aut": "👤 Egilearen generoa", 
        "f_editorial": "📚 Argitaletxea", 
        "f_paginas": "📄 Orrialde kopurua",
        "f_local": "🏠 Bertako autoreak", 
        "f_ia_gen": "📂 Generoa", 
        "f_ia_sub": "🏷️ Azpigeneroa",
        "tab1": "📖 Izenburu / Idazle bilaketa", 
        "tab2": "✨ Bilaketa librea", 
        "tab3": "🔍 Lote antzekoak", 
        "tab4": "🎲 Zorizko bilaketa",
        "placeholder": "Adibidez: Nafarroako historiaren inguruko eleberriak", 
        "input_query": "Nahi duzuna idatzi dezakezu",
        "lote_input": "Sartu lote kodea. Bat baina gehiago erabili dezakezu, tarteko loteak bilatzeko, adibidez: 121N, 445N, etab.:", 
        "busq_titulo": "Izenburuaren arabera bilatu:", 
        "busq_autor": "Egilearen arabera bilatu:",
        "resumen_btn": "Ikusi laburpena", 
        "pags_label": "orr", 
        "thanks": "✅ Iritzia gordeta", 
        "ask": "Gogoko duzu?",
        "voto_pregunta": "Egokia da?",
        "boton_txt": "Harritu nazazu!", 
        "no_results": "Ez da emaitzarik aurkitu iragazki hauekin.",
        "cols": {
            "idioma": "Idioma_eus",
            "publico": "Público_eus",
            "genero_aut": "genero_fix_eus",
            "ia_gen": "Genero_Principal_IA_eus",
            "ia_sub": "Subgeneros_Limpios_IA_eus"
        }
    }
}

t = texts[st.session_state.idioma]
c = t["cols"]

# --- 2. CARGA DE RECURSOS (Unificado y Corregido) ---
@st.cache_resource
def load_resources():
    # 1. Rutas de archivos
    excel_path = f"{PATH_RECO}/metadatos_entidades_OA.xlsx"
    disp_path = f"{PATH_RECO}/disponibilidad_catalogo_completo.xlsx"
    ruta_pkl = f"{PATH_RECO}/clubes_lectura_small_v15.pkl"
    ruta_index = f"{PATH_RECO}/clubes_lectura_small_v15.index"

    # Verificar existencia del Excel principal
    if not os.path.exists(excel_path):
        st.error(f"Archivo crítico no encontrado: {excel_path}")
        st.stop()
    
    # 2. CARGA CATÁLOGO PRINCIPAL
    df = pd.read_excel(excel_path)
    df.columns = df.columns.str.strip()
    df['Lote'] = df['Lote'].astype(str).str.strip()
    
    # 3. VINCULAR DISPONIBILIDAD
    if os.path.exists(disp_path):
        df_disp = pd.read_excel(disp_path)
        df_disp.columns = df_disp.columns.str.strip()
        if 'Lote' in df_disp.columns:
            df_disp['Lote'] = df_disp['Lote'].astype(str).str.strip()
            df = df.drop(columns=[c for c in ['Fechas_Reservadas', 'URL_Ficha'] if c in df.columns], errors='ignore')
            df = pd.merge(df, df_disp[['Lote', 'Fechas_Reservadas', 'URL_Ficha']], on='Lote', how='left')

    # 4. LIMPIEZA Y FORMATEO
    df['Páginas'] = pd.to_numeric(df['Páginas'], errors='coerce').fillna(0).astype(int)
    cols_check = [
        'Idioma', 'Idioma_eus', 'Público', 'Público_eus', 
        'genero_fix', 'genero_fix_eus', 'Editorial', 'Geografia_Autor', 
        'Genero_Principal_IA', 'Genero_Principal_IA_eus', 
        'Subgeneros_Limpios_IA', 'Subgeneros_Limpios_IA_eus'
    ]
    for col in cols_check:
        if col in df.columns:
            df[col] = df[col].astype(str).replace(['nan', 'None', '<NA>', ''], "Desconocido")
        else:
            df[col] = "Desconocido"
            
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
    
    # 5. CARGA DE RECURSOS IA (FAISS y Modelo)
    # Nota: Usamos el df del Excel como base, pero cargamos el índice y modelo
    if not os.path.exists(ruta_index):
        st.error(f"Índice FAISS no encontrado: {ruta_index}")
        st.stop()
        
    index = faiss.read_index(ruta_index)
    model = SentenceTransformer('intfloat/multilingual-e5-small')
    
    import gc
    gc.collect()
    
    # Retornamos todo lo necesario
    return df, index, model

# --- EJECUCIÓN (Fuera de la función, pegado a la izquierda) ---
df, index, model = load_resources()

# --- 3. FUNCIONES AUXILIARES ---


def guardar_voto(lote, titulo, valor, query):
    usuario = st.session_state.get("usuario_actual", "Anónimo")
    # Creamos una clave única para este voto en esta sesión
    voto_id = f"voted_{usuario}_{lote}_{query}"
    
    # 1. Verificamos si ya votó en esta sesión
    if st.session_state.get(voto_id):
        st.warning("⚠️ Ya has registrado tu opinión sobre este libro.")
        return False

    sheet = conectar_sheets()
    if sheet:
        try:
            val_txt = "👍" if valor == 1 else "👎"
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                str(lote), 
                str(titulo), 
                val_txt, 
                str(query), 
                usuario
            ]
            
            sheet.append_row(row)
            
            # 2. Marcamos como votado en el estado de la sesión
            st.session_state[voto_id] = True
            
            # 3. Mensaje de confirmación potente
            st.success(f"¡Gracias {usuario}! Tu {val_txt} ha sido registrado.")
            st.toast(f"✅ Voto registrado: {titulo}", icon="🗳️")
            return True
            
        except Exception as e:
            st.error(f"❌ Error al guardar: {e}")
            return False


# 4. Mostrar tarjeta
@st.fragment
def mostrar_card(r, context):
    IMG_WIDTH = 160  
    lote_id = str(r.get('Lote', '')).strip()
    
    with st.container(border=True):
        # Tres columnas: Imagen | Contenido | Botones
        col_img, col_content, col_vote = st.columns([1, 3, 0.5])

        # --- COLUMNA 1: IMAGEN ---
        with col_img:
            foto_path = None
            if os.path.exists(RUTA_PORTADAS):
                for f in os.listdir(RUTA_PORTADAS):
                    if os.path.splitext(f)[0] == lote_id:
                        foto_path = f"{RUTA_PORTADAS}/{f}"
                        break

            # Imagen escalada, más pequeña
            if foto_path:
                st.image(foto_path, width=IMG_WIDTH)
            else:
                st.markdown("<p style='font-size:30px; text-align:center;'>📖</p>", unsafe_allow_html=True)

            st.caption(f"Lote {lote_id}")

        # --- COLUMNA 2: CONTENIDO ---
        
        with col_content:
            st.markdown(f"### {r.get('Título','Sin título')}")
            st.write(f"**{r.get('Autor','Autor desconocido')}**")

            # Info adicional
            pags_val = r.get('Páginas', r.get('Páginas_ex','--'))
            try:
                pags_display = str(int(float(pags_val))) if pd.notnull(pags_val) and str(pags_val).replace('.','',1).isdigit() else str(pags_val)
            except:
                pags_display = str(pags_val)
            
            # Caption con Editorial, Idioma, Páginas y Público
            st.caption(f"{r.get('Editorial','--')} | {r.get(c['idioma'],'--')} | {pags_display} {t['pags_label']} | {r.get(c['publico'],'--')}")

            # NUEVO: GESTIÓN DE DISPONIBILIDAD
            reservas = r.get('Fechas_Reservadas', "")
            # Comprobamos si hay texto en 'Fechas_Reservadas' (y que no sea 'nan')
            if pd.notnull(reservas) and str(reservas).strip() != "" and str(reservas).lower() != "nan":
                # Si está ocupado, mostramos un aviso llamativo
                msg_ocupado = f"⚠️ **Ocupado:** {reservas}" if st.session_state.idioma == "Castellano" else f"⚠️ **Erreserbatuta:** {reservas}"
                st.warning(msg_ocupado)
            else:
                # Si está libre, un mensaje sutil en verde
                msg_libre = "✅ Disponible" if st.session_state.idioma == "Castellano" else "✅ Librea"
                st.markdown(f"<span style='color: #28a745; font-size: 0.9rem;'>{msg_libre}</span>", unsafe_allow_html=True)

            # Subgéneros dinámicos
            genero_ia = r.get(c['ia_gen'])
            subgeneros_ia = r.get(c['ia_sub'])
            
            if pd.notnull(subgeneros_ia) and subgeneros_ia != "Desconocido":
                st.write(f"**{genero_ia}**: {subgeneros_ia}")

            # Resumen con expander
            with st.expander(t["resumen_btn"], expanded=False):
                st.write(r.get('Resumen_navarra','No hay resumen disponible.'))


        # --- COLUMNA 3: BOTONES DE VOTO ---
        with col_vote:
            # Mostramos la pregunta traducida según el idioma actual
            st.caption(f"**{t['voto_pregunta']}**")
            
            # Usamos llaves únicas para que Streamlit no se confunda entre libros
            if st.button("👍", key=f"up_{lote_id}_{context}"):
                guardar_voto(lote_id, r.get('Título'), 1, context)
                st.toast(t["thanks"]) # Opcional: un aviso rápido al votar
        
            if st.button("👎", key=f"down_{lote_id}_{context}"):
                guardar_voto(lote_id, r.get('Título'), 0, context)
                st.toast(t["thanks"])

                
# --- 5. PANEL DE CONTROL (DINÁMICO) ---
st.sidebar.title(t["sidebar_tit"])

# Botón de Cerrar Sesión
if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state.auth = False
    st.rerun()

st.sidebar.markdown("---")

# --- VERIFICACIÓN DE SEGURIDAD PARA RENDERIZAR FILTROS ---
if 'df' in locals() and df is not None:
    # 5.1 FILTROS GENERALES
    with st.sidebar.expander(t["exp_gral"], expanded=False):
        # Idioma
        f_idioma = st.multiselect(t["f_idioma"], sorted(df[c['idioma']].dropna().unique()))
        # Público
        f_publico = st.multiselect(t["f_publico"], sorted(df[c['publico']].dropna().unique()))
        # Género Autor
        f_gen_aut = st.multiselect(t["f_genero_aut"], sorted(df[c['genero_aut']].dropna().unique()))
        # Editorial
        opciones_ed = sorted([e for e in df['Editorial'].dropna().unique() if e != "Desconocido"])
        f_editorial = st.multiselect(t["f_editorial"], opciones_ed)
        
        f_local = st.checkbox(t["f_local"])
        f_paginas = st.slider(t["f_paginas"], 50, 1500, 1500)

    # 5.2 FILTROS DE CONTENIDO (IA)
    with st.sidebar.expander(t["exp_cont"], expanded=False):
        opciones_ia_gen = sorted([g for g in df[c['ia_gen']].dropna().unique() if g != "Desconocido"])
        f_ia_gen = st.multiselect(t["f_ia_gen"], opciones_ia_gen)
        
        f_ia_sub = []
        if f_ia_gen:
            subs = set()
            df[df[c['ia_gen']].isin(f_ia_gen)][c['ia_sub']].str.split(',').dropna().apply(
                lambda x: subs.update([s.strip() for s in x])
            )
            f_ia_sub = st.multiselect(t["f_ia_sub"], sorted([s for s in list(subs) if s != "Desconocido"]))

    # 5.3 FILTROS DE DISPONIBILIDAD (ACTUALIZADO Y TRADUCIDO)
    with st.sidebar.expander(t["exp_disp"], expanded=False):
        # Mensaje informativo con la fecha manual
        st.info(t["f_actualizacion"])
        
        # Selector de rango de fechas
        label_rango = "Rango de lectura" if st.session_state.idioma == "Castellano" else "Irakurketa tartea"
        f_rango = st.date_input(label_rango, value=[], help="Selecciona fecha de inicio y fin")
       
        # Checkbox con traducción desde el diccionario
        f_solo_disponibles = st.checkbox(t["f_solo_disp"])

    # --- FUNCIÓN FILTRAR ---
    def filtrar(dataframe):
        temp = dataframe.copy()
        
        # 1. Filtros básicos
        if f_idioma: temp = temp[temp[c['idioma']].isin(f_idioma)]
        if f_publico: temp = temp[temp[c['publico']].isin(f_publico)]
        if f_gen_aut: temp = temp[temp[c['genero_aut']].isin(f_gen_aut)]
        if f_local: temp = temp[temp['Geografia_Autor'] == "Local"]
        if f_paginas < 1500: temp = temp[temp['Páginas'] <= f_paginas]
        if f_editorial: temp = temp[temp['Editorial'].isin(f_editorial)]
        
        # 2. Filtro de Disponibilidad (Checkbox o Rango)
        if len(f_rango) == 2:
            # Usamos la función de apoyo que pusimos arriba
            mask = temp['Fechas_Reservadas'].apply(lambda x: comprobar_disponibilidad(x, f_rango))
            temp = temp[mask]
        elif f_solo_disponibles:
            temp = temp[
                (temp['Fechas_Reservadas'].isna()) |
                (temp['Fechas_Reservadas'].astype(str).str.strip() == "") |
                (temp['Fechas_Reservadas'].astype(str).str.lower() == "nan")
            ]
        
        # 3. Filtros de IA
        if f_ia_gen: temp = temp[temp[c['ia_gen']].isin(f_ia_gen)]
        if f_ia_sub: 
            temp = temp[temp[c['ia_sub']].apply(
                lambda x: any(s in str(x) for s in f_ia_sub) if pd.notnull(x) else False
            )]
            
        return temp

else:
    st.sidebar.warning("Esperando a la base de datos...")
    st.stop()
    
# --- 6. INTERFAZ ---
col_logo, col_tit = st.columns([1,6])
with col_logo:
    if os.path.exists(URL_LOGO): st.image(URL_LOGO, width=150)
with col_tit:
    st.title(t["titulo"])
    st.caption(t["subtitulo"])

tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])


# --- TAB1: Búsqueda por título/autor ---
with tab1:
    c1, c2 = st.columns(2)
    b_tit = c1.text_input(t["busq_titulo"], key="busq_t_input")
    b_aut = c2.text_input(t["busq_autor"], key="busq_a_input")
   
    if b_tit or b_aut:
        texto_buscado = f"Tit: {b_tit} | Aut: {b_aut}".strip(" | ")
        res = filtrar(df)
        if b_tit: res = res[res['titulo_norm'].str.contains(normalizar_texto(b_tit), na=False)]
        if b_aut: res = res[res['autor_norm'].str.contains(normalizar_texto(b_aut), na=False)]
        res = res.dropna(subset=['Título']).reset_index(drop=True)
       
        for _, r in res.head(10).iterrows():
            mostrar_card(r, texto_buscado)

# --- TAB2: Búsqueda libre con FAISS (Versión Silenciosa y Filtrada) ---
with tab2:
    q = st.text_input(t["input_query"], placeholder=t["placeholder"], key="txt_libre_80")
    
    if q:
        # 1. Encoding con prefijo query para e5-large (1024 dim)
        vec = model.encode([f"query: {q}"], normalize_embeddings=True).astype('float32')
        
        # 2. Buscamos 100 para asegurar que, tras filtrar, nos queden resultados
        D, I = index.search(vec, 100)
        
        # 3. Umbral de corte (ajustado a 0.70 para mayor cobertura)
        mask = D[0] >= 0.85
        indices_validos = I[0][mask]
        scores_validos = D[0][mask]

        if len(indices_validos) > 0:
            # Creamos el set de resultados de la IA con su puntuación
            res_ia = df.iloc[indices_validos].copy()
            res_ia['search_score'] = scores_validos

            # 4. Aplicar filtros de la Sidebar (Estado actual de los selectores)
            df_filtrado_sidebar = filtrar(df) 

            # 5. Cruce: Solo lo que la IA recomienda Y que pasa los filtros del usuario
            # Usamos 'Lote' como clave de unión
            lotes_permitidos = set(df_filtrado_sidebar['Lote'])
            res_final = res_ia[res_ia['Lote'].isin(lotes_permitidos)].copy()

            # 6. Ordenar por relevancia pura de la IA y limpiar duplicados de Lote
            res_final = res_final.sort_values('search_score', ascending=False)
            res_final = res_final.drop_duplicates(subset=['Lote'])

            # 7. Limpieza de nulos y límite visual de 10 cards
            res_final = res_final.dropna(subset=['Título']).head(12)

            # 8. Renderizado directo
            if not res_final.empty:
                for _, r in res_final.iterrows():
                    mostrar_card(r, q)
            else:
                # Solo avisamos si literalmente no hay NADA que mostrar tras filtrar
                st.warning(t["no_results"])
        else:
            st.warning(t["no_results"])

# --- TAB3: Lotes similares (Punto Medio / Multi-lote) ---
with tab3:
    lid_input = st.text_input(t["lote_input"], key="txt_sim_lote_multi")
   
    if lid_input:
        # 1. Limpieza de entrada
        lotes_solicitados = [l.strip().upper() for l in lid_input.replace(',', ' ').split() if l.strip()]
        
        vectores_para_promediar = []
        lotes_encontrados = []

        # 2. Extraemos los vectores (embeddings) del índice
        for lid_clean in lotes_solicitados:
            ref_ia = df[df['Lote'] == lid_clean]
            if not ref_ia.empty:
                try:
                    idx_ia = ref_ia.index[0]
                    v_lote = index.reconstruct(int(idx_ia))
                    vectores_para_promediar.append(v_lote)
                    lotes_encontrados.append(lid_clean)
                except Exception:
                    continue # Si falla la reconstrucción, saltamos silenciosamente

        if vectores_para_promediar:
            # 3. CÁLCULO DEL CENTROIDE (Punto medio semántico)
            v_ref = np.mean(vectores_para_promediar, axis=0).astype('float32').reshape(1, -1)
            # Normalizamos el centroide para mantener la consistencia con IndexFlatIP
            faiss.normalize_L2(v_ref)
            
            # 4. Buscamos en el índice FAISS (pedimos más para tener margen tras filtrar)
            D, I = index.search(v_ref, 50) 
            
            # 5. Umbral flexible para multi-búsqueda (0.70 es ideal aquí)
            umbral_sim = 0.80
            mask = D[0] >= umbral_sim
            indices_validos = I[0][mask]
            scores_validos = D[0][mask]

            if len(indices_validos) > 0:
                # Creamos DataFrame temporal con scores
                res_ia = df.iloc[indices_validos].copy()
                res_ia['search_score'] = scores_validos

                # 6. Filtrar por Sidebar y excluir los que el usuario ya escribió
                df_filtrado_sidebar = filtrar(df)
                lotes_permitidos = set(df_filtrado_sidebar['Lote'])
                
                # Solo libros que pasen el filtro Y no sean los buscados
                res_final = res_ia[
                    (res_ia['Lote'].isin(lotes_permitidos)) & 
                    (~res_ia['Lote'].isin(lotes_encontrados))
                ].copy()

                # 7. Ordenar por score y eliminar duplicados de lote
                res_final = res_final.sort_values('search_score', ascending=False)
                res_final = res_final.drop_duplicates(subset=['Lote'])

                # 8. Limite y renderizado
                res_final = res_final.dropna(subset=['Título']).head(10)

                if not res_final.empty:
                    st.info(f"Libros similares a la combinación de: {', '.join(lotes_encontrados)}")
                    for _, r in res_final.iterrows():
                        mostrar_card(r, f"Sim_{hash(lid_input) % 1000}")
                else:
                    st.warning(t["no_results"])
            else:
                st.warning(t["no_results"])

# --- TAB4: Búsqueda aleatoria ---
with tab4:
    col_s1, col_s2 = st.columns([1, 4])
    with col_s1:
        if os.path.exists(URL_SERENDIPIA):
            st.image(URL_SERENDIPIA, width=120)
    with col_s2:
        if st.button(t["boton_txt"], use_container_width=True):
            posibles = filtrar(df)
            if not posibles.empty: 
                st.session_state.azar = posibles.sample(1).iloc[0]
            else:
                st.session_state.azar = None

    if 'azar' in st.session_state and st.session_state.azar is not None:
        mostrar_card(st.session_state.azar, "Serendipia")
    elif 'azar' in st.session_state:
        st.info(t["no_results"])
