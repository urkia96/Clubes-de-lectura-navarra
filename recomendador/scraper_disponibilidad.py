from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import re
from datetime import datetime, timedelta

def configurar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") # Sin ventana
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=chrome_options)

def ejecutar_scraper_selenium():
    driver = configurar_driver()
    resultados = []
    base_url = "https://www.culturanavarra.es"
    url_actual = "https://www.culturanavarra.es/es/clubes-de-lectura-1"
    
    try:
        while url_actual:
            print(f"🌐 Navegando a: {url_actual}")
            driver.get(url_actual)
            
            # Esperar a que los botones de los libros aparezcan (máximo 15 seg)
            wait = WebDriverWait(driver, 15)
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "btn-default")))
            
            # Extraer enlaces de los libros
            elementos = driver.find_elements(By.CSS_SELECTOR, "a[href*='/es/clubes-de-lectura-1/']")
            links = list(dict.fromkeys([el.get_attribute("href") for el in elementos if "solicitar" not in el.get_attribute("href")]))
            
            print(f"📊 Libros encontrados: {len(links)}")
            
            for link in links:
                driver.execute_script("window.open('');") # Abrir pestaña
                driver.switch_to.window(driver.window_handles[1])
                driver.get(link)
                
                try:
                    # Esperar al calendario
                    wait.until(EC.presence_of_element_located((By.ID, "disponibilidad_mes_actual")))
                    
                    texto = driver.page_source
                    lote = re.search(r'Nº lote:\s*([0-9]+[A-Z]?)', texto)
                    lote_txt = lote.group(1) if lote else "S/N"
                    
                    # Aquí el scraper ya tiene el ID del libro y podría hacer el AJAX 
                    # Pero para asegurar, guardamos que la ficha cargó bien
                    resultados.append({
                        'Lote': lote_txt,
                        'URL': link,
                        'Ultima_Actualizacion': datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    print(f" ✅ {lote_txt} capturado.")
                except:
                    print(f" ⚠️ Error en ficha: {link}")
                
                driver.close() # Cerrar pestaña
                driver.switch_to.window(driver.window_handles[0])
                time.sleep(1)

            # Lógica de Siguiente
            try:
                sig = driver.find_element(By.CSS_SELECTOR, "a[aria-label='Siguiente']")
                url_actual = sig.get_attribute("href")
            except:
                url_actual = None
                
    finally:
        driver.quit()
        if resultados:
            pd.DataFrame(resultados).to_excel("disponibilidad_catalogo_completo.xlsx", index=False)
            print("✨ Proceso terminado con éxito.")

if __name__ == "__main__":
    ejecutar_scraper_selenium()

