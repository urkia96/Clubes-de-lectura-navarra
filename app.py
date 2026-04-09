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
import hashlib
import re



# --- 0. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Clubes de Lectura de Navarra", layout="wide")

# --- 1. INICIALIZAR ESTADO TEMPRANO ---
if "idioma" not in st.session_state:
    st.session_state.idioma = "Castellano"
if "auth" not in st.session_state:
    st.session_state.auth = False

def conectar_sheets():
    try:
        # Priorizamos st.secrets (Estándar en Streamlit Cloud / Local .toml)
        if "gcp_service_account" in st.secrets:
            creds_info = dict(st.secrets["gcp_service_account"])
            sheet_url = st.secrets.get("GSHEET_URL") or st.secrets.get("gsheet_url")
        
        # Backup para Variables de Entorno (como en HF o entornos CI/CD)
        elif "GCP_SERVICE_ACCOUNT" in os.environ:
            creds_info = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
            sheet_url = os.environ.get("GSHEET_URL")
        
        else:
            st.error("❌ No se configuraron las credenciales (secrets.toml o env vars)")
            return None

        # Configuración de las credenciales
        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )

        gc_client = gspread.authorize(creds)
        
        if not sheet_url:
            st.error("❌ Falta la URL de la hoja de cálculo (GSHEET_URL)")
            return None
            
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
    
    #st.stop() # <--- ESTO ES LO QUE BLOQUEA EL RESTO DEL CÓDIGO. Se puede quitar para no obligar a autenticarse.

# --- 1. CONFIGURACIÓN E IDIOMAS ---

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

def estrellas_puntuacion(puntuacion):
    if pd.isna(puntuacion): return "Sin votos"
    enteras = int(puntuacion)
    media = 1 if (puntuacion - enteras) >= 0.5 else 0
    vacias = 5 - enteras - media
    return "⭐" * enteras + "✨" * media + "🔘" * vacias # Puedes usar "★" y "☆" si prefieres





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
        "nav_tit": "🚀 Navegación",
        "btn_ranking": "🏆 Libros mejor puntuados",
        "btn_nueva_busqueda": "🔄 Nueva búsqueda",
        "btn_cerrar_sesion": "🚪 Cerrar Sesión",
        "btn_volver": "⬅️ Volver",
        "rank_cap": "Filtrando el ranking según tus preferencias",
        "exp_gral": "⚙️ Filtros generales",
        "exp_cont": "📖 Filtros de contenido",
        "exp_disp": "📅 Disponibilidad",
        "mis_favs_tit": "Libros Guardados",
        "f_actualizacion": "Última actualización: 08/04/2026",
        "f_solo_disp": "Solo disponibles ahora",
        "f_idioma": "🌍 Idioma",
        "f_publico": "👥 Público",
        "f_genero_aut": "👤 Género Autor/a",
        "f_editorial": "📚 Editorial",
        "f_paginas": "📄 Número de páginas",
        "f_local": "🏠 Autores locales",
        "f_lf": "👓 Lectura Fácil",
        "f_ia_gen": "📂 Género",
        "f_ia_sub": "🏷️ Subgénero",
        "f_keywords": "🔍 Conceptos clave",
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
        "help_add": "Añadir a favoritos",
        "help_remove": "Quitar de favoritos",
        "mis_favs_tit": "Libros Guardados",
        "thanks": "✅ Voto registrado",
        
        "ask_relevante": "¿Es relevante?",
        "ask_recomendarias": "¿Lo recomendarías?",
        "boton_txt": "¡Sorpréndeme!",
        "no_results": "Sin resultados con esos filtros.",
        "excluir_subs": ["Teatro", "Poesía", "Infantil", "Juvenil"],
        "cols": {
            "idioma": "Idioma",
            "publico": "Público",
            "genero_aut": "genero_fix",
            "ia_gen": "Genero_Principal_IA",
            "ia_sub": "Subgenero_ES",
            "keywords": "Keywords_ES"
        }
    },
    "Euskera": {
        "titulo": "Nafarroako Irakurketa Klubak",
        "subtitulo": "Clubes de Lectura de Navarra",
        "sidebar_tit": "🎯 Kontrol Panela",
        "nav_tit": "🚀 Nabigazioa",
        "btn_ranking": "🏆 Hobeto puntuatuak",
        "btn_nueva_busqueda": "🔄 Bilaketa berria",
        "btn_cerrar_sesion": "🚪 Saioa itxi",
        "btn_volver": "⬅️ Itzuli",
        "rank_cap": "Rankinga zure hobespenen arabera iragazten",
        "exp_gral": "⚙️ Iragazki orokorrak",
        "exp_cont": "📖 Edukiaren iragazkiak",
        "exp_disp": "📅 Erabilgarritasuna",
        "mis_favs_tit": "📚 Gordetako Liburuak",
        "f_actualizacion": "Azken eguneratzea: 2026/04/08",
        "f_solo_disp": "Libre daudenak bakarrik",
        "f_idioma": "🌍 Hizkuntza",
        "f_publico": "👥 Publikoa",
        "f_genero_aut": "👤 Egilearen generoa",
        "f_editorial": "📚 Argitaletxea",
        "f_paginas": "📄 Orrialde kopurua",
        "f_local": "🏠 Bertako autoreak",
        "f_lf": "👓 Irakurketa Erraza",
        "f_ia_gen": "📂 Generoa",
        "f_ia_sub": "🏷️ Azpigeneroa",
        "f_keywords": "🔍 Kontzeptu nagusiak",
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
        "help_add": "Gogokoetara gehitu",
        "help_remove": "Gogokoetatik kendu",
        "mis_favs_tit": "📚 Gordetako Liburuak",
        "thanks": "✅ Iritzia gordeta",
        "ask_relevante": "Esanguratsua da?",
        "ask_recomendarias": "Gomendatuko zenuke?",
        "boton_txt": "Harritu nazazu!",
        "no_results": "Ez da emaitzarik aurkitu iragazki hauekin.",
        "excluir_subs": ["Antzerkia", "Olerkiak", "Haur literatura", "Gazte literatura"],
        "cols": {
            "idioma": "Idioma_eus",
            "publico": "Público_eus",
            "genero_aut": "genero_fix_eus",
            "ia_gen": "Genero_Principal_IA_eus",
            "ia_sub": "Azpigeneroa_EUS",
            "keywords": "Keywords_EUS"
        }
    }
}

t = texts[st.session_state.idioma]
c = t["cols"]


@st.cache_resource
def load_resources():
    excel_path = os.path.join(PATH_RECO, "Etiquetas_Normalizadas_Final (1).xlsx")
    disp_path = os.path.join(PATH_RECO, "disponibilidad_catalogo_completo.xlsx")

    if not os.path.exists(excel_path):
        st.error(f"Archivo crítico no encontrado: {excel_path}")
        st.stop()
  
    # 1. CARGA CATÁLOGO PRINCIPAL (Sin tocar nombres originales)
    df = pd.read_excel(excel_path)
    df.columns = df.columns.str.strip()
   
    # Aseguramos que la columna de unión se llame 'Lote' (por si acaso)
    if 'Lote' not in df.columns:
        df.rename(columns={df.columns[0]: 'Lote'}, inplace=True)
   
    df['Lote'] = df['Lote'].astype(str).str.strip()
  
    # 2. CARGA DISPONIBILIDAD (Como tabla independiente para el cruce)
    if os.path.exists(disp_path):
        try:
            df_disp = pd.read_excel(disp_path)
            df_disp.columns = df_disp.columns.str.strip()
           
            # Forzamos nombres por POSICIÓN solo en esta tabla temporal
            # Col 0 -> Lote, Col 1 -> Fechas_Reservadas
            temp_disp = pd.DataFrame()
            temp_disp['Lote'] = df_disp.iloc[:, 0].astype(str).str.strip()
           
            if df_disp.shape[1] > 1:
                temp_disp['Fechas_Reservadas'] = df_disp.iloc[:, 1].fillna("").astype(str)
            else:
                temp_disp['Fechas_Reservadas'] = ""

            # Eliminamos basura previa en el DF principal para evitar el error .x .y
            df = df.drop(columns=['Fechas_Reservadas'], errors='ignore')
           
            # UNIÓN: Pegamos la disponibilidad al catálogo
            df = pd.merge(df, temp_disp[['Lote', 'Fechas_Reservadas']], on='Lote', how='left')
           
        except Exception as e:
            st.warning(f"⚠️ No se pudo procesar la disponibilidad: {e}")

    # --- GARANTÍA DE COLUMNAS ---
    if 'Fechas_Reservadas' not in df.columns:
        df['Fechas_Reservadas'] = ""
    df['Fechas_Reservadas'] = df['Fechas_Reservadas'].fillna("")
    # ----------------------------

    # 3. PROCESAMIENTO DE METADATOS (Aquí es donde se crea titulo_norm)
    # Importante: No mover este bloque de aquí
    df['Páginas'] = pd.to_numeric(df['Páginas'], errors='coerce').fillna(0).astype(int)
  
    cols_check = [
        'Idioma', 'Idioma_eus', 'Público', 'Público_eus',
        'genero_fix', 'genero_fix_eus', 'Editorial', 'Geografia_Autor',
        'Genero_Principal_IA', 'Genero_Principal_IA_eus',
        'Subgenero_ES', 'Azpigeneroa_EUS',
        'Keywords_ES', 'Keywords_EUS'
    ]
  
    for col in cols_check:
        if col in df.columns:
            df[col] = df[col].astype(str).replace(['nan', 'None', '<NA>', ''], "Desconocido")
        else:
            df[col] = "Desconocido"
   
    # ESTAS LÍNEAS SON LAS QUE TE DABAN EL ERROR:
    df['titulo_norm'] = df['Título'].apply(normalizar_texto)
    df['autor_norm'] = df['Autor'].apply(normalizar_texto)
  
    # 4. CARGA IA
    with open(os.path.join(PATH_RECO, "clubes_lectura_small_modelo1_keywords.pkl"), "rb") as f:
        df_ia_meta = pickle.load(f)
   
    # Aseguramos el nombre 'Lote' en el PKL también
    if 'Lote' not in df_ia_meta.columns:
        df_ia_meta.rename(columns={df_ia_meta.columns[0]: 'Lote'}, inplace=True)
    df_ia_meta['Lote'] = df_ia_meta['Lote'].astype(str).str.strip()
  
    index = faiss.read_index(os.path.join(PATH_RECO, "clubes_lectura_small_modelo1_keywords.index"))
    model = SentenceTransformer('intfloat/multilingual-e5-small')
  
    gc.collect()
    return df, df_ia_meta, index, model
# Ejecución
df, df_ia_meta, index, model = load_resources()


# --- 3. FUNCIONES AUXILIARES ---

def guardar_voto(lote, titulo, valor, tipo_busqueda, terminos, filtros, posicion):
    usuario = st.session_state.get("usuario_actual", "Anónimo")
    sheet = conectar_sheets()
    if not sheet: return False

    try:
        spreadsheet = sheet.spreadsheet
        try:
            ws_votos = spreadsheet.worksheet("votos")
        except:
            # Si la pestaña no existe, la creamos con los 9 encabezados
            ws_votos = spreadsheet.add_worksheet(title="votos", rows="1000", cols="9")
            ws_votos.append_row(["Fecha", "Usuario", "Lote", "Titulo", "Tipo_Busqueda", "Terminos", "Filtros", "Puntuacion", "Posicion"])
            datos = []
        else:
            datos = ws_votos.get_all_records()

        # VALIDACIÓN DE DUPLICADOS
        if datos:
            df_votos = pd.DataFrame(datos)
            # Limpiamos nombres de columnas (quitar espacios, tildes y poner minúsculas)
            df_votos.columns = [normalizar_texto(str(c)) for c in df_votos.columns]
            
            # Solo comprobamos si existen las columnas necesarias
            if 'usuario' in df_votos.columns and 'lote' in df_votos.columns:
                ya_voto = df_votos[
                    (df_votos['usuario'].astype(str) == str(usuario)) & 
                    (df_votos['lote'].astype(str) == str(lote))
                ]
                if not ya_voto.empty:
                    st.warning(f"⚠️ {usuario}, ya has valorado este club.")
                    return False

        # REGISTRO DEL VOTO (Ahora sí incluimos al usuario)
        # Importante: el orden debe coincidir con los encabezados de arriba
        nueva_fila = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(usuario),
            str(lote),
            str(titulo),
            str(tipo_busqueda),
            str(terminos),
            str(filtros),
            int(valor), # Aquí va la puntuación (estrellas)
            int(posicion)
        ]
        
        ws_votos.append_row(nueva_fila)
        return True

    except Exception as e:
        st.error(f"❌ Error en el sistema de votos: {e}")
        return False


def votar_lote(lote, puntuacion):
    """Guarda la recomendación (estrellas) usando la conexión general"""
    sheet_control = conectar_sheets() # Usamos tu función de siempre
    if not sheet_control: return False
    try:
        spreadsheet = sheet_control.spreadsheet
        try:
            ws_votos = spreadsheet.worksheet("votos")
        except:
            # Si no existe la pestaña, la crea con sus cabeceras
            ws_votos = spreadsheet.add_worksheet(title="votos", rows="1000", cols="3")
            ws_votos.append_row(["Lote", "Puntuacion", "Fecha"])

        # Añadimos la fila
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws_votos.append_row([str(lote), int(puntuacion), fecha])
        return True
    except Exception as e:
        st.error(f"Error al guardar recomendación: {e}")
        return False

def obtener_ranking():
    sheet_control = conectar_sheets()
    if not sheet_control: return pd.DataFrame()
    
    try:
        spreadsheet = sheet_control.spreadsheet
        try:
            ws_votos = spreadsheet.worksheet("votos")
        except:
            return pd.DataFrame() # Si no existe la pestaña, devolvemos vacío sin error
            
        datos = ws_votos.get_all_records()
        if not datos:
            return pd.DataFrame()
            
        df_votos = pd.DataFrame(datos)
        
        # --- NORMALIZAR COLUMNAS PARA EVITAR EL ERROR ---
        # Pasamos todo a minúsculas y quitamos tildes para encontrar las columnas
        mapeo = {col: normalizar_texto(str(col)) for col in df_votos.columns}
        df_votos = df_votos.rename(columns=mapeo)
        
        # Ahora buscamos las columnas normalizadas
        col_lote = "lote"
        col_puntos = "puntuacion"
        
        if col_puntos not in df_votos.columns:
            # Si aún así no la encuentra, imprimimos las que ve para ayudarte
            # st.warning(f"Columnas detectadas: {df_votos.columns.tolist()}")
            return pd.DataFrame()

        # Convertimos a números y limpiamos
        df_votos[col_puntos] = pd.to_numeric(df_votos[col_puntos], errors='coerce')
        df_votos[col_lote] = df_votos[col_lote].astype(str).str.strip()
        
        # Agrupamos
        ranking = df_votos.groupby(col_lote)[col_puntos].agg(['mean', 'count']).reset_index()
        ranking.columns = ['Lote', 'Media', 'Total_Votos']
        
        return ranking.sort_values(by='Media', ascending=False)
    except Exception as e:
        # Esto evitará que la app se bloquee si hay un error, solo mostrará el aviso
        st.sidebar.error(f"Aviso: No se pudo cargar el ranking")
        return pd.DataFrame()


def guardar_favorito(lote_id, titulo):
    usuario = st.session_state.get("usuario_actual", "Anónimo")
    sheet = conectar_sheets()
    if not sheet: return False
   
    try:
        spreadsheet = sheet.spreadsheet
        try:
            ws_favs = spreadsheet.worksheet("favoritos")
        except:
            ws_favs = spreadsheet.add_worksheet(title="favoritos", rows="1000", cols="3")
            ws_favs.append_row(["usuario", "lote", "titulo"])

        # Verificar si ya existe para no duplicar en el Sheets
        existentes = ws_favs.get_all_records()
        ya_guardado = any(str(f['usuario']) == str(usuario) and str(f['lote']) == str(lote_id) for f in existentes)
       
        if not ya_guardado:
            ws_favs.append_row([str(usuario), str(lote_id), str(titulo)])
            st.toast(f"⭐ {titulo} guardado", icon="📚")
            return True
        else:
            st.info("Este libro ya está en tu lista.")
            return False
    except Exception as e:
        st.error(f"Error al guardar favorito: {e}")
        return False

@st.cache_data(ttl=60) # Cache de 1 minuto para no saturar la API de Google
def obtener_mis_libros(usuario):
    sheet = conectar_sheets()
    if not sheet: return []
    try:
        ws_favs = sheet.spreadsheet.worksheet("favoritos")
        datos = ws_favs.get_all_records()
        mis_lotes = [str(f['lote']) for f in datos if str(f['usuario']) == str(usuario)]
        return mis_lotes
    except:
        return []

def eliminar_favorito(lote_id):
    usuario = st.session_state.get("usuario_actual", "Anónimo")
    sheet = conectar_sheets()
    if not sheet: return False
   
    try:
        ws_favs = sheet.spreadsheet.worksheet("favoritos")
        datos = ws_favs.get_all_records()
       
        # Encontrar el número de fila (Sheets empieza en 1, +1 por la cabecera)
        fila_a_borrar = None
        for i, fila in enumerate(datos, start=2):
            if str(fila['usuario']) == str(usuario) and str(fila['lote']) == str(lote_id):
                fila_a_borrar = i
                break
       
        if fila_a_borrar:
            ws_favs.delete_rows(fila_a_borrar)
            st.toast(f"🗑️ Eliminado de favoritos", icon="✅")
            return True
        return False
    except Exception as e:
        st.error(f"Error al eliminar: {e}")
        return False



def aplicar_busqueda_hibrida(df_input, query, campos_busqueda):
    if not query:
        return df_input, query

    # Detectar operadores: "frase exacta" o -exclusion
    tiene_exacta = bool(re.findall(r'"([^"]*)"', query))
    tiene_exclusion = bool(re.findall(r'-(\S+)', query))

    df_resultado = df_input.copy()

    if tiene_exacta or tiene_exclusion:
        # --- LÓGICA BOOLEANA ---
        # 1. Frases exactas: "historia de navarra"
        frases = re.findall(r'"([^"]*)"', query)
        for f in frases:
            f_norm = normalizar_texto(f)
            # Buscamos en los campos combinados (Título, Autor, Resumen, Keywords)
            mask = df_resultado.apply(lambda r: any(f_norm in normalizar_texto(str(r[col])) for col in campos_busqueda), axis=1)
            df_resultado = df_resultado[mask]

        # 2. Exclusiones: -reyes
        exclusiones = re.findall(r'-(\S+)', query)
        for e in exclusiones:
            e_norm = normalizar_texto(e)
            mask = df_resultado.apply(lambda r: any(e_norm in normalizar_texto(str(r[col])) for col in campos_busqueda), axis=1)
            df_resultado = df_resultado[~mask] # Invertimos la máscara para excluir

        # Limpiamos la query para el Transformer (quitamos los operadores)
        query_para_ia = re.sub(r'"[^"]*"|-\S+', '', query).strip()
        return df_resultado, query_para_ia
   
    return df_resultado, query

    #Función para recuperar los filtros utilizados
def obtener_filtros_activos():
    filtros = []
    # Recogemos los valores de los widgets del sidebar
    if f_idioma: filtros.extend(f_idioma)
    if f_publico: filtros.extend(f_publico)
    if f_local: filtros.append("Autor Local")
    if f_lf: filtros.append("Lectura Fácil")
    if f_ia_gen: filtros.extend(f_ia_gen)
    if f_ia_sub: filtros.extend(f_ia_sub)
   
    # Si no hay nada seleccionado
    return filtros if filtros else ["Sin filtros"]

# 4. Mostrar tarjeta
@st.fragment
def mostrar_card(r, context, lotes_en_mis_favs, idx=0, posicion=0):
    IMG_WIDTH = 160 
    lote_id = str(r.get('Lote', '')).strip()
    titulo_actual = r.get('Título', 'Sin título')
   
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

            # ---SECCIÓN DE KEYWORDS ---
            keywords_val = r.get(c['keywords'])
            if pd.notnull(keywords_val) and keywords_val != "Desconocido":
                st.write(f"**Keywords:** {keywords_val}")

            # Resumen con expander
            with st.expander(t["resumen_btn"], expanded=False):
                st.write(r.get('Resumen_navarra','No hay resumen disponible.'))


         # --- COLUMNA 3: BOTONES (Relevancia, Recomendación y Favoritos) ---
        with col_vote:
            usuario_act = st.session_state.get("usuario_actual", "Anónimo")
            
            # --- SECCIÓN 1: RELEVANCIA ---
            st.markdown(f"<p style='font-size:0.8rem; font-weight:bold; margin-bottom:0;'>1. {t['ask_relevante']}</p>", unsafe_allow_html=True)
            
            # Feedback de pulgares (thumbs)
            # El valor será 0 (dislike) o 1 (like)
            voto_rel = st.feedback("thumbs", key=f"rel_{lote_id}_{idx}")
            
            # Si quieres que se guarde algo en el log cuando pulsen el pulgar:
            if voto_rel is not None:
                # Aquí podrías llamar a una función técnica de log si quisieras, 
                # o simplemente dejar que Streamlit lo gestione en el estado.
                pass
            
            st.markdown("---")
            
            # --- SECCIÓN 2: RECOMENDACIÓN (ESTRELLAS) ---
            usuario_act = st.session_state.get("usuario_actual", "Anónimo")
            lote_id_str = str(lote_id)
            
            # 1. Verificar si ya votó (usamos un pequeño truco de caché para no leer el Excel mil veces)
            # Si no quieres complicarte con caché ahora, usa una variable de estado:
            voto_realizado = st.session_state.get(f"voted_{usuario_act}_{lote_id_str}", False)

            # 1. Título de la pregunta (Usamos t["ask_recomendarias"])
            st.markdown(f"<p style='font-size:0.8rem; font-weight:bold; margin-bottom:0;'>2. {t['ask_recomendarias']}</p>", unsafe_allow_html=True)
            
            if voto_realizado:
                # 2. Mensaje de confirmación (Usamos t["thanks"])
                st.info(t["thanks"])
            else:
                # 3. El componente de feedback (El buscador de estrellas ya es intuitivo)
                voto_estrellas = st.feedback("stars", key=f"rating_{lote_id_str}_{context}_{idx}")
                
                if voto_estrellas is not None:
                    puntuacion_final = voto_estrellas + 1
                    
                    tipo_busqueda = st.session_state.get("tab_actual", "Búsqueda")
                    filtros_lista = [st.session_state.get(f) for f in ['f_idioma_w', 'f_publico_w', 'f_gen_aut_w'] if st.session_state.get(f)]
                    filtros_str = ", ".join(map(str, filtros_lista)) if filtros_lista else "Sin filtros"
            
                    # Ejecutamos el guardado
                    exito = guardar_voto(lote_id, titulo_actual, puntuacion_final, tipo_busqueda, str(context), filtros_str, posicion)
    
                    if exito:
                        st.session_state[f"voted_{usuario_act}_{lote_id_str}"] = True
                        st.toast(f"¡Gracias por tu recomendación!", icon="🌟")
                        st.rerun()
          
            st.markdown("---")
            
            # --- SECCIÓN 3: FAVORITOS ---
            st.markdown(f"<p style='font-size:0.8rem; font-weight:bold; margin-bottom:0;'>3. {t['mis_favs_tit']}</p>", unsafe_allow_html=True)
            es_favorito = lote_id in lotes_en_mis_favs
            
            if es_favorito:
                # Botón Corazón Lleno
                if st.button("❤️", key=f"fav_full_{lote_id}_{idx}", help=t["help_remove"], use_container_width=True):
                    if eliminar_favorito(lote_id):
                        st.cache_data.clear()
                        st.rerun()
            else:
                # Botón Corazón Vacío
                if st.button("🤍", key=f"fav_empty_{lote_id}_{idx}", help=t["help_add"], use_container_width=True):
                    if guardar_favorito(lote_id, titulo_actual):
                        st.cache_data.clear()
                        st.rerun()



# --- 4. LÓGICA DE FILTRADO ---
def filtrar(dataframe):
    temp = dataframe.copy()
   
    # 1. Filtros Generales
    f_id = st.session_state.get("f_idioma_w")
    if f_id: 
        temp = temp[temp[c['idioma']].isin(f_id)] # Usamos f_id, no st.session_state.f_idioma_w
   
    f_pub = st.session_state.get("f_publico_w")
    if f_pub: 
        temp = temp[temp[c['publico']].isin(f_pub)] # Usamos f_pub
   
    f_gen = st.session_state.get("f_gen_aut_w")
    if f_gen: 
        temp = temp[temp[c['genero_aut']].isin(f_gen)] # Usamos f_gen
   
    if st.session_state.get("f_local_w"):
        temp = temp[temp['Geografia_Autor'] == "Local"]
       
    if st.session_state.get("f_lf_w"):
        if 'Materias' in temp.columns:
            temp = temp[temp['Materias'].str.contains("Lectura Fácil", case=False, na=False)]
           
    f_pag = st.session_state.get("f_paginas_w", 1500)
    if f_pag < 1500: 
        temp = temp[temp['Páginas'] <= f_pag]
   
    f_ed = st.session_state.get("f_editorial_w")
    if f_ed: 
        temp = temp[temp['Editorial'].isin(f_ed)] # Usamos f_ed
   
    # 2. Filtros Contenido (IA)
    f_iagen = st.session_state.get("f_ia_gen_w")
    if f_iagen: 
        temp = temp[temp[c['ia_gen']].isin(f_iagen)] # Usamos f_iagen
   
    f_iasub = st.session_state.get("f_ia_sub_w")
    if f_iasub:
        temp = temp[temp[c['ia_sub']].apply(lambda x: any(s in str(x) for s in f_iasub) if pd.notnull(x) else False)]
   
    # 3. Filtros Disponibilidad
    f_ran = st.session_state.get("f_rango_w")
    if f_ran and len(f_ran) == 2:
        temp = temp[temp['Fechas_Reservadas'].apply(lambda x: comprobar_disponibilidad(x, f_ran))]
    elif st.session_state.get("f_solo_disp_w"):
        temp = temp[(temp['Fechas_Reservadas'].isna()) | (temp['Fechas_Reservadas'].astype(str).str.strip() == "")]

    # 4. Filtro por Keywords (Conceptos Clave)
    kw_sel = st.session_state.get("f_kw_seleccionadas")
    if kw_sel:
        temp = temp[temp[c['keywords']].apply(lambda x: any(kw in str(x) for kw in kw_sel) if pd.notnull(x) else False)]
        
    return temp


# --- 5. PANEL DE CONTROL (SIDEBAR ÚNICA AGRUPADA) ---
st.sidebar.title(t["sidebar_tit"])

# --- 1. BOTÓN DE SALIDA ---
if st.sidebar.button(t["btn_cerrar_sesion"], use_container_width=True):
    st.session_state.auth = False
    st.rerun()

st.sidebar.markdown("---")

# --- 2. GRUPO DE ACCIONES PRINCIPALES (Agrupados en el mismo nivel) ---
# Usamos un contenedor para visualmente mantener la unidad
with st.sidebar.container():
    st.subheader(t["nav_tit"])
    
    # ELEMENTO 1: RANKING
    if st.sidebar.button(t["btn_ranking"], use_container_width=True):
        st.session_state.ver_ranking = True
        st.session_state.ver_favoritos = False
        st.rerun()

    # ELEMENTO 2: MIS LIBROS
    if st.sidebar.button(f"📚 {t['mis_favs_tit']}", use_container_width=True):
        st.cache_data.clear() # Limpieza de caché para asegurar recuperación de Sheets
        st.session_state.ver_favoritos = True
        st.session_state.ver_ranking = False
        st.rerun()

    # ELEMENTO 3: NUEVA BÚSQUEDA
    if st.sidebar.button(t["btn_nueva_busqueda"], use_container_width=True):
        keys_to_reset = [
            "f_idioma_w", "f_publico_w", "f_gen_aut_w", "f_editorial_w",
            "f_local_w", "f_lf_w", "f_paginas_w", "f_ia_gen_w", "f_ia_sub_w",
            "f_kw_seleccionadas", "f_rango_w", "f_solo_disp_w",
            "df_final_actual", "azar", "txt_sim_lote_multi", "input_ia",
            "busq_t_input", "busq_a_input"
        ]
        for k in keys_to_reset:
            if k in st.session_state:
                del st.session_state[k]
        st.session_state.ver_favoritos = False
        st.session_state.ver_ranking = False
        st.rerun()

st.sidebar.markdown("---")


# --- 3. BLOQUE: FILTROS GENERALES ---
with st.sidebar.expander(t["exp_gral"], expanded=False):
    st.multiselect(t["f_idioma"], sorted(df[c['idioma']].dropna().unique()), key="f_idioma_w")
    st.multiselect(t["f_publico"], sorted(df[c['publico']].dropna().unique()), key="f_publico_w")
    st.multiselect(t["f_genero_aut"], sorted(df[c['genero_aut']].dropna().unique()), key="f_gen_aut_w")
    opciones_ed = sorted([e for e in df['Editorial'].dropna().unique() if e != "Desconocido"])
    st.multiselect(t["f_editorial"], opciones_ed, key="f_editorial_w")
    st.checkbox(t["f_local"], key="f_local_w")
    st.checkbox(t["f_lf"], key="f_lf_w")
    st.slider(t["f_paginas"], 50, 1500, 1500, key="f_paginas_w")

# --- 4. BLOQUE: CONTENIDO IA ---
with st.sidebar.expander(t["exp_cont"], expanded=True):
    # 1. Géneros IA
    opciones_ia_gen = sorted([str(g) for g in df[c['ia_gen']].dropna().unique() if str(g) != "Desconocido"])
    st.multiselect(t["f_ia_gen"], opciones_ia_gen, key="f_ia_gen_w")
   
    # 2. Subgéneros dinámicos
    f_ia_gen_val = st.session_state.get("f_ia_gen_w", [])
    if f_ia_gen_val:
        df_temp_sub = df[df[c['ia_gen']].isin(f_ia_gen_val)]
        raw_subs = df_temp_sub[c['ia_sub']].astype(str).str.split(',').explode().str.strip().unique()
        opciones_sub = sorted([str(s) for s in raw_subs if str(s) not in ["Desconocido", "nan", "None", ""]])
       
        if opciones_sub:
            st.multiselect(t["f_ia_sub"], opciones_sub, key="f_ia_sub_w")

    # --- 3. Conceptos Clave (LISTA DINÁMICA CON DICCIONARIO COMPLETO) ---
    st.markdown(f"<b>{t['f_keywords']}</b>", unsafe_allow_html=True)

    # 1. Función para cargar el "Diccionario Maestro" (Todas las keywords del Excel)
    @st.cache_data
    def obtener_diccionario_maestro(_df, col_name):
        if col_name not in _df.columns:
            return []
        # Convertimos a string, separamos por comas, aplanamos y limpiamos espacios
        todas = _df[col_name].fillna("").astype(str).str.split(',').explode().str.strip()
        # Filtramos valores basura y convertimos a lista de strings únicos
        valores_limpios = [str(x) for x in todas.unique() if x not in ["nan", "None", "", "Desconocido"]]
        return sorted(valores_limpios)

    nombre_col_kw = c.get('keywords', 'Keywords_IA')
    diccionario_completo = obtener_diccionario_maestro(df, nombre_col_kw)

    # 2. Decidimos qué sugerir (las 150 más frecuentes de la vista actual)
    if "df_final_actual" in st.session_state and not st.session_state.df_final_actual.empty:
        fuente_palabras = st.session_state.df_final_actual
    else:
        # Si no hay resultados actuales, filtramos el df original para ver qué hay disponible
        fuente_palabras = filtrar(df)

    lista_sugerida = []
    if fuente_palabras is not None and not fuente_palabras.empty:
        try:
            series_actual = fuente_palabras[nombre_col_kw].astype(str).str.split(',').explode().str.strip()
            counts = series_actual.value_counts().drop(["Desconocido", "nan", "None", ""], errors='ignore')
            # Tomamos las 150 más frecuentes para que aparezcan primero al abrir el menú
            lista_sugerida = [str(x) for x in counts.head(150).index.tolist()]
        except:
            lista_sugerida = []

    # 3. LÓGICA HÍBRIDA:
    # Obtenemos lo seleccionado actualmente asegurando que sean strings
    seleccionadas = [str(s) for s in st.session_state.get("f_kw_seleccionadas", [])]

    # Unimos todo: sugeridas + ya seleccionadas + diccionario maestro (para que busque cualquier palabra)
    # Al usar set() evitamos duplicados y sorted() nos da orden alfabético
    opciones_multiselect = sorted(list(set(lista_sugerida + seleccionadas + diccionario_completo)))

    # 4. El Componente Multiselect
    st.multiselect(
        "Filtrar por concepto:",
        options=opciones_multiselect,
        key="f_kw_seleccionadas",
        label_visibility="collapsed",
        placeholder="Escribe cualquier concepto..."
    )
            

# --- 5. BLOQUE: DISPONIBILIDAD ---
with st.sidebar.expander(t["exp_disp"], expanded=False):
    st.date_input("Rango de fechas", value=[], key="f_rango_w")
    st.checkbox(t["f_solo_disp"], key="f_solo_disp_w")


   
# --- 6. INTERFAZ ---

t = texts[st.session_state.idioma]

col_logo, col_tit = st.columns([1,6])
with col_logo:
    if os.path.exists(URL_LOGO):
        st.image(URL_LOGO, width=150)
with col_tit:
    st.title(t["titulo"])
    st.caption(t["subtitulo"])

# --- LÓGICA DE VISUALIZACIÓN PRINCIPAL ---
usuario_act = st.session_state.get("usuario_actual", "Anónimo")

# IMPORTANTE: Inicializamos la variable como un DataFrame vacío al principio
# Así, si por lo que sea no entra en el bloque del ranking, la app no explota.
df_rank_data = pd.DataFrame() 

# 1. VISTA DE RANKING
if st.session_state.get("ver_ranking"):
    col_t, col_b = st.columns([4, 1])
    st.title(t["btn_ranking"])
    st.caption(t["rank_cap"])
    with col_b:
        if st.button(t["btn_volver"], key="btn_volver_rank"):
            st.session_state.ver_ranking = False
            st.rerun()
            
    # Obtenemos los votos desde Sheets
    df_rank_data = obtener_ranking()
    
    if not df_rank_data.empty:
        # --- EL CAMBIO MÁGICO ---
        # Aplicamos los filtros de la sidebar antes de mostrar el ranking
        df_filtrado_para_rank = filtrar(df)
        
        # Aseguramos tipos de datos para que el merge no falle
        df_rank_data['Lote'] = df_rank_data['Lote'].astype(str).str.strip()
        df_filtrado_para_rank['Lote'] = df_filtrado_para_rank['Lote'].astype(str).str.strip()

        # Al hacer el merge con 'inner', solo quedan los libros que:
        # 1. Tienen votos
        # 2. Cumplen los filtros de la sidebar
        df_rank_display = pd.merge(df_rank_data, df_filtrado_para_rank, on='Lote', how='inner')
        
        # Ordenamos por media (de mayor a menor)
        df_rank_display = df_rank_display.sort_values(by='Media', ascending=False).drop_duplicates('Lote')
        
        lotes_favs = obtener_mis_libros(usuario_act)
        
        if not df_rank_display.empty:
            # Usamos enumerate para que el puesto (1º, 2º...) sea correcto tras filtrar
            for i, (original_idx, row) in enumerate(df_rank_display.iterrows(), start=1):
                media = row['Media']
                total_votos = int(row['Total_Votos'])
                estrellas = estrellas_puntuacion(media)
                
                st.markdown(f"#### {i}º Lugar | {estrellas} `{media:.1f}` ({total_votos} votos)")
                # Pasamos un idx único combinando el lote y la posición para evitar errores de botones
                mostrar_card(row, "Ranking", lotes_favs, idx=f"R_{row['Lote']}_{i}")
                st.divider()
        else:
            st.warning("No hay libros puntuados que coincidan con los filtros seleccionados.")
    else:
        st.info("Todavía no hay votos registrados.")


# 2. ¿O estamos viendo los FAVORITOS?
elif st.session_state.get("ver_favoritos"):
    col_t, col_b = st.columns([4, 1])
    with col_t:
        st.title(t["mis_favs_tit"])
    with col_b:
        if st.button("⬅️ Volver", key="btn_volver_favs"):
            st.session_state.ver_favoritos = False
            st.rerun()

    lotes_favs = obtener_mis_libros(usuario_act)
    if lotes_favs:
        df_favs = df[df['Lote'].isin(lotes_favs)]
        for idx, row in df_favs.iterrows():
            mostrar_card(row, "Favoritos", lotes_favs, idx=idx)
    else:
        st.info("Tu lista de favoritos está vacía.")

# 3. SI NO ES NINGUNA DE LAS ANTERIORES, MOSTRAR EL BUSCADOR NORMAL
else:
    st.title(t["titulo"])
    st.subheader(t["subtitulo"])
    
    # Aquí es donde van tus TABS originales
    tab1, tab2, tab3, tab4 = st.tabs([t["tab1"], t["tab2"], t["tab3"], t["tab4"]])


# --- TAB1: Búsqueda por título/autor ---
    with tab1:
        c1, c2 = st.columns(2)
        b_tit = c1.text_input(t["busq_titulo"], key="busq_t_input")
        b_aut = c2.text_input(t["busq_autor"], key="busq_a_input")
        
       
        if b_tit or b_aut:
            # 1. Aplicar filtros base de la barra lateral (idioma, público, etc.)
            res = filtrar(df)
           
            # 2. Filtrado por texto normalizado
            if b_tit:
                res = res[res['titulo_norm'].str.contains(normalizar_texto(b_tit), na=False)]
            if b_aut:
                res = res[res['autor_norm'].str.contains(normalizar_texto(b_aut), na=False)]
           
            # 3. LIMPIEZA CRÍTICA: Eliminar nulos y duplicados por lote
            res = res.dropna(subset=['Título', 'Lote'])
            res = res.drop_duplicates(subset=['Lote'])
            res = res.reset_index(drop=True)
           
            # --- NUEVO: PREPARAR DATOS PARA LAS TARJETAS ---
            # Obtenemos la lista de favoritos del usuario actual una sola vez para este tab
            usuario_act = st.session_state.get("usuario_actual", "Anónimo")
            lotes_en_mis_favs = obtener_mis_libros(usuario_act)
            # -----------------------------------------------
    
            # 4. Mostrar resultados (Limitado a los 10 mejores para rendimiento)
            if not res.empty:
                texto_buscado = f"Busq: {b_tit} {b_aut}".strip()
                # Generar un hash simple para evitar conflictos de IDs de botones
                contexto_id = f"TAB1_{hash(texto_buscado) % 1000}"
               
                for i, (_, r) in enumerate(res.head(10).iterrows()):
                    mostrar_card(r, contexto_id, lotes_en_mis_favs, idx=i)
            else:
                st.warning(t["no_results"])
    
    # --- TAB2: Búsqueda libre HÍBRIDA ---
    with tab2:
        q_original = st.text_input(t["input_query"], key="input_ia")
        if q_original:
            # 1. Filtros base de la barra lateral
            df_base = filtrar(df)
           
            # 2. Aplicar lógica de Booleanos (Comillas y Menos)
            columnas_texto = ['Título', 'Autor', 'Resumen_navarra', c['keywords']]
            df_filtrado_bool, q_limpia = aplicar_busqueda_hibrida(df_base, q_original, columnas_texto)
    
            # 3. Búsqueda Semántica (IA)
            if q_limpia:
                vec = model.encode([f"query: {q_limpia}"], normalize_embeddings=True).astype('float32')
                D, I = index.search(vec, 50)
                indices_validos = I[0][D[0] >= 0.80]
               
                lotes_ia = df_ia_meta.iloc[indices_validos]['Lote'].astype(str).str.strip().tolist()
                res_final = df_filtrado_bool[df_filtrado_bool['Lote'].isin(lotes_ia)].copy()
               
                # Reordenar por relevancia de la IA
                lotes_que_existen = [l for l in lotes_ia if l in res_final['Lote'].values]
                res_final['Lote'] = pd.Categorical(res_final['Lote'], categories=lotes_que_existen, ordered=True)
                res_final = res_final.sort_values('Lote')
            else:
                res_final = df_filtrado_bool
    
            # 4. Renderizar resultados
            res_final = res_final.drop_duplicates(subset=['Lote']).head(15)
           
            # --- NUEVO: PREPARAR DATOS PARA LAS TARJETAS ---
            usuario_act = st.session_state.get("usuario_actual", "Anónimo")
            lotes_en_mis_favs = obtener_mis_libros(usuario_act)
            # -----------------------------------------------
           
            if not res_final.empty:
                st.session_state.df_final_actual = res_final
            
            # Renderizar tarjetas
            for i, (_, r) in enumerate(res_final.iterrows()):
                    mostrar_card(r, q_original, lotes_en_mis_favs, idx=f"T2_{i}")
        else:
            st.warning(t["no_results"])
               
    # --- TAB3: Lotes similares (Punto Medio / Multi-lote) ---
    with tab3:
        lid_input = st.text_input(t["lote_input"], key="txt_sim_lote_multi")
     
        if lid_input:
            lotes_solicitados = [l.strip().upper() for l in lid_input.replace(',', ' ').split() if l.strip()]
           
            vectores_para_promediar = []
            lotes_encontrados = []
    
            for lid_clean in lotes_solicitados:
                ref_ia = df_ia_meta[df_ia_meta['Lote'] == lid_clean]
                if not ref_ia.empty:
                    idx_ia = ref_ia.index[0]
                    v_lote = index.reconstruct(int(idx_ia))
                    vectores_para_promediar.append(v_lote)
                    lotes_encontrados.append(lid_clean)
                else:
                    st.warning(f"El lote {lid_clean} no se encuentra en el sistema.")
    
            if vectores_para_promediar:
                # 3. CÁLCULO DEL PUNTO MEDIO
                v_ref = np.mean(vectores_para_promediar, axis=0).astype('float32').reshape(1, -1)
               
                # 4. Buscamos en el índice FAISS
                D, I = index.search(v_ref, 30)
                indices_validos = I[0][D[0] >= 0.80]
                lotes_sim = df_ia_meta.iloc[indices_validos]['Lote'].unique().tolist()
             
                # 5. Aplicamos los filtros de la Sidebar (¡Ojo! filtra el DF original)
                df_base = filtrar(df)
               
                # 6. Quitamos los lotes que el usuario ya ha introducido
                lotes_ordenados = [l for l in lotes_sim if l not in lotes_encontrados]
               
                # 7. Evitar duplicados y ordenar por relevancia
                res_sim = df_base[df_base['Lote'].isin(lotes_ordenados)].copy()
                res_sim = res_sim.drop_duplicates(subset=['Lote'])
               
                res_sim['Lote'] = pd.Categorical(res_sim['Lote'], categories=lotes_ordenados, ordered=True)
                res_sim = res_sim.sort_values('Lote').dropna(subset=['Título']).head(10)
             
                # 💡 PASO CLAVE 1: Actualizamos el estado para que la Sidebar reaccione
                if not res_sim.empty:
                    # Si los resultados actuales son distintos a los guardados, actualizamos
                    if "df_final_actual" not in st.session_state or not st.session_state.df_final_actual.equals(res_sim):
                        st.session_state.df_final_actual = res_sim
                        # Forzamos un rerun para que la Sidebar se actualice inmediatamente con las nuevas Keywords
                        st.rerun()
    
                # 8. ID único para los botones
                contexto_voto = f"Sim_{hash(lid_input) % 10000}"
             
                # --- OBTENER FAVORITOS ANTES DE RENDERIZAR ---
                usuario_act = st.session_state.get("usuario_actual", "Anónimo")
                lotes_en_mis_favs = obtener_mis_libros(usuario_act)
    
                if not res_sim.empty:
                    st.info(f"Mostrando libros similares a: {', '.join(lotes_encontrados)}")
                    
                    # 💡 PASO CLAVE 2: Renderizar las tarjetas
                    for i, (_, r) in enumerate(res_sim.iterrows(), start=1):
                        mostrar_card(
                            r,
                            contexto_voto,
                            lotes_en_mis_favs,
                            idx=f"SIM_{i}", 
                            posicion=i
                        )
                else:
                    st.warning("No hay otros lotes con suficiente similitud para esta combinación.")
    
    # --- TAB4: Búsqueda aleatoria ---
    with tab4:
        col_s1, col_s2 = st.columns([1, 4])
        with col_s1:
            if os.path.exists(URL_SERENDIPIA):
                st.image(URL_SERENDIPIA, width=120)
       
        with col_s2:
            if st.button(t["boton_txt"], use_container_width=True):
                # 1. Filtramos según los criterios actuales de la Sidebar
                posibles = filtrar(df)
                
                if not posibles.empty:
                    # 2. Seleccionamos uno al azar
                    seleccionado = posibles.sample(1)
                    st.session_state.azar = seleccionado.iloc[0]
                    
                    # 💡 PASO CLAVE: Actualizamos el 'cerebro' de la Sidebar
                    # Convertimos la fila en un DataFrame para que la Sidebar pueda leer sus keywords
                    st.session_state.df_final_actual = seleccionado
                    
                    # Forzamos reinicio para que la Sidebar vea el cambio al instante
                    st.rerun()
                else:
                    st.session_state.azar = None
                    st.session_state.df_final_actual = pd.DataFrame() # Vacío si no hay nada

    # --- PREPARAR DATOS PARA LA TARJETA ---
    usuario_act = st.session_state.get("usuario_actual", "Anónimo")
    lotes_en_mis_favs = obtener_mis_libros(usuario_act)

    if 'azar' in st.session_state and st.session_state.azar is not None:
        # Mostramos la tarjeta del libro seleccionado
        mostrar_card(
            st.session_state.azar, 
            "Serendipia", 
            lotes_en_mis_favs, 
            idx="AZAR_1", 
            posicion=1
        )
    elif 'azar' in st.session_state:
        st.info(t["no_results"])
