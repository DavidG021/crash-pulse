import requests
import time

url = "http://127.0.0.1:8000/api/round"

print("Enviando racha bajista forzada para probar la alerta...")

# Lista con valores menores a 2.0x para activar la alerta de inmediato
racha_baja = [1.45, 1.20, 1.15, 1.80, 1.33]

for val in racha_baja:
    payload = {"multiplier": val}
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        print(f"Ronda enviada: {val}x (¡Baja!)")
    else:
        print(f"Error: {response.text}")
        
    time.sleep(1.5) # Espera 1.5 segundos entre cada una

print("¡Prueba de racha finalizada!")