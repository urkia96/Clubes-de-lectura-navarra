from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import re
from datetime import datetime

def configurar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    # Añadimos un agente de usuario real para que la web no nos bloquee
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    return webdriver.Chrome(options=chrome_options)

def ejecutar_scraper_selenium():
    driver = configurar_driver()
    resultados = []
    url_actual = "https://www.culturanavarra.es/es/clubes-de-lectura-1"
    
    try:
        while url_actual:
            print(f"🌐 Navegando a: {url_actual}")
            driver.get(url_actual)
            
            # Espera larga de 30 segundos a que cargue el cuerpo de la página
            wait = WebDriverWait(driver, 30)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Pausa de seguridad de 5 segundos para que el JavaScript termine de trabajar
            time.sleep(5) 
            
            # Buscamos los enlaces a los libros de forma más abierta
            elementos = driver.find_elements(By.CSS_SELECTOR, "a[href*='/es/clubes-de-lectura-1/']")
            links = list(dict.fromkeys([el.get_attribute("href") for el in elementos if "solicitar" not in el.get_attribute("href")]))
            
            print(f"📊 Libros detectados en esta página: {len(links)}")
            
            if len(links) == 0:
                print("⚠️ No se encontraron libros. Guardando captura de pantalla para debug...")
                driver.save_screenshot("error_page.png")
                break

            for link in links:
                # Por ahora guardamos el link para confirmar que el crawler navega
                resultados.append({
                    'Lote': "Extrayendo...",
                    'URL': link,
                    'Fecha_Scraping': datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                print(f" 🔗 Detectado: {link}")

            # Intentar localizar el botón de 'Siguiente'
            try:
                sig = driver.find_element(By.CSS_SELECTOR, "a[aria-label='Siguiente']")
                url_actual = sig.get_attribute("href")
                print("➡️ Pasando a la siguiente página...")
            except:
                print("🏁 No se encontró botón de 'Siguiente'. Fin del catálogo.")
                url_actual = None
                
    except Exception as e:
        print(f"❌ Error crítico: {e}")
    finally:
        driver.quit()
        if resultados:
            df = pd.DataFrame(resultados)
            df.to_excel("disponibilidad_catalogo_completo.xlsx", index=False)
            print(f"✨ ¡Éxito! Se han pre-listado {len(df)} libros.")
        else:
            print("❌ El proceso terminó sin recoger ningún dato.")

if __name__ == "__main__":
    ejecutar_scraper_selenium()
