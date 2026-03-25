import requests
from bs4 import BeautifulSoup
import os

def diagnostico_github():
    url = "https://www.culturanavarra.es/es/clubes-de-lectura-1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }

    print(f"🔍 Probando conexión a: {url}")
    
    try:
        res = requests.get(url, headers=headers, timeout=30)
        
        print(f"📡 STATUS CODE: {res.status_code}")
        print(f"📏 TAMAÑO DEL HTML: {len(res.text)} caracteres")
        
        # Guardamos un trozo del HTML para ver qué hay dentro
        print("📝 PRIMEROS 500 CARACTERES DEL HTML:")
        print(res.text[:500])
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Buscamos los botones que buscas siempre
        botones = soup.find_all('a', class_='btn-default')
        print(f"🔘 BOTONES 'btn-default' ENCONTRADOS: {len(botones)}")
        
        # Buscamos cualquier enlace
        enlaces = soup.find_all('a')
        print(f"🔗 ENLACES TOTALES EN LA PÁGINA: {len(enlaces)}")

        if len(botones) == 0 and len(enlaces) > 10:
            print("⚠️ OJO: Hay enlaces pero NO tienen la clase 'btn-default'. La web ha cambiado el diseño.")
        elif len(enlaces) <= 5:
            print("🚫 BLOQUEO PROBABLE: La página está casi vacía. GitHub tiene la IP vetada.")

    except Exception as e:
        print(f"🔥 ERROR DE CONEXIÓN: {e}")

if __name__ == "__main__":
    diagnostico_github()
