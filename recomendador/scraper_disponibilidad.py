import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import itertools
import os
from datetime import datetime, timedelta

# --- FUNCIONES DE APOYO ---

def agrupar_ocupados(fechas_ocupadas):
    """Agrupa fechas sueltas en rangos legibles: '01/05 al 15/05'"""
    if not fechas_ocupadas: return ""
    try:
        fechas = sorted([datetime.strptime(f, "%Y-%m-%d") for f in fechas_ocupadas])
        rangos = []
        for k, g in itertools.groupby(enumerate(fechas), lambda x: x[1] - timedelta(days=x[0])):
            grupo = list(map(lambda x: x[1], g))
            inicio, fin = grupo[0].strftime("%d/%m/%Y"), grupo[-1].strftime("%d/%m/%Y")
            rangos.append(f"{inicio} al {fin}" if inicio != fin else inicio)
        return " | ".join(rangos)
    except:
        return ""

def extraer_solo_lote(soup_d):
    """Busca el número de lote (ej: 1156N) en el texto de la ficha"""
    texto_pagina = soup_d.get_text()
    match_lote = re.search(r'Nº lote:\s*([0-9]+[A-Z]?)', texto_pagina)
    return match_lote.group(1) if match_lote else "S/N"

# --- SCRIPT PRINCIPAL ---

def ejecutar_scraping_final():
    resultados = []
    visitadas = set()
   
     # Cabeceras mejoradas para evitar ser detectados como bot
    headers_base = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    }
   
    BASE_URL = "https://www.culturanavarra.es"
    url_actual = "https://www.culturanavarra.es/es/clubes-de-lectura-1"
    url_ajax = f"{BASE_URL}/ajaxDisponibilidadCatalogoClubesLectura.php"
   
    hoy = datetime.now()
    meses_consulta = [{'m': (hoy.replace(day=1) + timedelta(days=i*31)).strftime("%m"),
                       'a': (hoy.replace(day=1) + timedelta(days=i*31)).strftime("%Y")} for i in range(6)]

    print(f"🚀 Iniciando extracción automática (Modo Robusto)...")

    pagina_n = 1
    while url_actual and url_actual not in visitadas:
        print(f"📂 Procesando Página {pagina_n}: {url_actual}")
        visitadas.add(url_actual)
       
        try:
            res = requests.get(url_actual, headers=headers_base, timeout=30)
            if res.status_code != 200:
                print(f"⚠️ Error de respuesta: {res.status_code}")
                break

            soup = BeautifulSoup(res.text, 'html.parser')
           
            # Buscamos enlaces de forma más flexible: 
            # Cualquier enlace que contenga la ruta de clubes y no sea el de solicitar
            enlaces_raw = soup.find_all('a', href=True)
            enlaces = []
            for a in enlaces_raw:
                h = a['href']
                if 'es/clubes-de-lectura-1/' in h and 'solicitar' not in h:
                    enlaces.append(h)
            
            # Limpiar duplicados manteniendo orden
            enlaces = list(dict.fromkeys(enlaces))
            print(f"🔗 Encontrados {len(enlaces)} libros en esta página.")

            if not enlaces:
                print("❌ No se detectaron libros. Finalizando por precaución.")
                break
                        resultados.append({
                            'Lote': lote,
                            'Fechas_Reservadas': agrupar_ocupados(fechas_ocupadas),
                            'URL_Ficha': full_url
                        })
                        print(f" ✅ Lote {lote} procesado.")
                   
                    time.sleep(1.2)
                except Exception as e:
                    print(f" ⚠️ Error en libro {href}: {e}")
                    continue

            # Paginación
            sig_boton = soup.find('a', {'aria-label': 'Siguiente'})
            if sig_boton and sig_boton.has_attr('href'):
                href_sig = sig_boton['href']
                proxima_url = BASE_URL + (href_sig if href_sig.startswith('/') else '/' + href_sig)
                url_actual = proxima_url if proxima_url != url_actual else None
                pagina_n += 1
            else:
                url_actual = None

        except Exception as e:
            print(f"🔥 Error en listado: {e}")
            break

    # --- GUARDADO ---
    if resultados:
        df = pd.DataFrame(resultados)
        nombre_file = "disponibilidad_catalogo_completo.xlsx"
        df.to_excel(nombre_file, index=False)
        print(f"\n✨ ¡TODO LISTO! {len(df)} registros guardados.")
    else:
        print("❌ No se obtuvieron datos finales.")

if __name__ == "__main__":
    ejecutar_scraping_final()
