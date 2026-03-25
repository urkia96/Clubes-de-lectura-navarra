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
   
    headers_base = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9'
    }
   
    BASE_URL = "https://www.culturanavarra.es"
    url_actual = "https://www.culturanavarra.es/es/clubes-de-lectura-1"
    url_ajax = f"{BASE_URL}/ajaxDisponibilidadCatalogoClubesLectura.php"
   
    hoy = datetime.now()
    meses_consulta = [{'m': (hoy.replace(day=1) + timedelta(days=i*31)).strftime("%m"),
                       'a': (hoy.replace(day=1) + timedelta(days=i*31)).strftime("%Y")} for i in range(6)]

    print(f"🚀 Iniciando extracción automática...")

    pagina_n = 1
    while url_actual and url_actual not in visitadas:
        print(f"📂 Procesando Página {pagina_n}: {url_actual}")
        visitadas.add(url_actual)
       
        try:
            res = requests.get(url_actual, headers=headers_base, timeout=30)
            if res.status_code != 200: break
                
            soup = BeautifulSoup(res.text, 'html.parser')
            enlaces_raw = soup.find_all('a', href=True)
            enlaces = list(dict.fromkeys([a['href'] for a in enlaces_raw 
                                         if 'es/clubes-de-lectura-1/' in a['href'] and 'solicitar' not in a['href']]))
            
            print(f"🔗 Encontrados {len(enlaces)} libros.")

            for href in enlaces:
                full_url = BASE_URL + (href if href.startswith('/') else '/' + href)
                try:
                    res_d = requests.get(full_url, headers=headers_base, timeout=20)
                    soup_d = BeautifulSoup(res_d.text, 'html.parser')
                    div_cal = soup_d.find('div', id='disponibilidad_mes_actual')
                   
                    if div_cal and div_cal.has_attr('data-libro'):
                        id_libro = div_cal['data-libro']
                        lote = extraer_solo_lote(soup_d)
                        fechas_ocupadas = []
                       
                        # Consultar los 6 meses
                        for m in meses_consulta:
                            payload = {'idLibro': id_libro, 'mes': m['m'], 'anio': m['a']}
                            headers_ajax = headers_base.copy()
                            headers_ajax.update({'Referer': full_url, 'X-Requested-With': 'XMLHttpRequest'})
                            
                            res_a = requests.post(url_ajax, data=payload, headers=headers_ajax, timeout=15)
                            if res_a.status_code == 200:
                                soup_a = BeautifulSoup(res_a.text, 'html.parser')
                                for dia_bloque in soup_a.find_all('div', class_='dia_evento'):
                                    d = dia_bloque.get('data-dia')
                                    if d: fechas_ocupadas.append(f"{m['a']}-{m['m']}-{d.zfill(2)}")
                            time.sleep(0.1)

                        # GUARDADO DEL LIBRO (Bien alineado)
                        resultados.append({
                            'Lote': lote,
                            'Fechas_Reservadas': agrupar_ocupados(fechas_ocupadas),
                            'URL_Ficha': full_url
                        })
                        print(f" ✅ Lote {lote} OK.")
                   
                    time.sleep(1.2)
                except Exception:
                    continue

            # Paginación
            sig_boton = soup.find('a', {'aria-label': 'Siguiente'})
            if sig_boton and sig_boton.has_attr('href'):
                href_sig = sig_boton['href']
                url_actual = BASE_URL + (href_sig if href_sig.startswith('/') else '/' + href_sig)
                pagina_n += 1
            else:
                url_actual = None

        except Exception as e:
            print(f"🔥 Error: {e}")
            break

    if resultados:
        df = pd.DataFrame(resultados)
        df.to_excel("disponibilidad_catalogo_completo.xlsx", index=False)
        print(f"\n✨ Éxito: {len(df)} libros guardados.")
    else:
        print("❌ Sin datos.")

if __name__ == "__main__":
    ejecutar_scraping_final()

