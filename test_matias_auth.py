#!/usr/bin/env python3
"""
test_matias_auth.py
Prueba la URL de autenticación de MATIAS API y muestra exactamente qué responde.

Ejecutar:
    railway run python test_matias_auth.py

Requiere: MATIAS_EMAIL, MATIAS_PASSWORD en las variables de Railway.
"""
import os, sys, json

# Cargar .env local si existe (para pruebas sin railway run)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Si no está instalado python-dotenv, leer .env manualmente
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

import httpx

EMAIL    = os.getenv("MATIAS_EMAIL")
PASSWORD = os.getenv("MATIAS_PASSWORD")
API_URL  = os.getenv("MATIAS_API_URL", "https://api-v2.matias-api.com/api/ubl2.1")

# Las dos URLs candidatas a probar
CANDIDATAS = [
    f"{API_URL}/auth/login",                        # lo que hace el código actual
    "https://auth-v2.matias-api.com/auth/login",    # lo que dice el docstring
    "https://auth-v2.matias-api.com/api/auth/login",# variante con /api/
]

if not EMAIL or not PASSWORD:
    print("❌  Faltan MATIAS_EMAIL o MATIAS_PASSWORD en las variables de entorno.")
    sys.exit(1)

payload = {"email": EMAIL, "password": PASSWORD, "remember_me": 0}
headers = {"Accept": "application/json", "Content-Type": "application/json"}

print(f"\n🔍  Probando login con: {EMAIL}\n{'─'*60}")

for url in CANDIDATAS:
    print(f"\n➡  POST {url}")
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=10, follow_redirects=True)
        print(f"   HTTP {r.status_code}")
        print(f"   Content-Type: {r.headers.get('content-type', '—')}")

        if not r.text.strip():
            print("   Body: (vacío)")
            continue

        try:
            data = r.json()
            # Mostrar sin exponer el token completo
            preview = {}
            for k, v in data.items():
                if k in ("token", "access_token"):
                    preview[k] = str(v)[:20] + "…" if v else None
                elif isinstance(v, dict):
                    preview[k] = {kk: (str(vv)[:20] + "…" if kk in ("token","access_token") else vv)
                                  for kk, vv in v.items()}
                else:
                    preview[k] = v
            print(f"   JSON: {json.dumps(preview, ensure_ascii=False, indent=4)}")

            # Veredicto
            token = (data.get("token") or data.get("access_token")
                     or (data.get("data") or {}).get("token")
                     or (data.get("data") or {}).get("access_token"))
            if token:
                print(f"\n   ✅  TOKEN ENCONTRADO — esta URL funciona")
            else:
                print(f"\n   ⚠️   Respuesta JSON pero sin token. Claves: {list(data.keys())}")

        except Exception:
            print(f"   Body (no JSON): {r.text[:400]}")

    except httpx.ConnectError:
        print("   ❌  No se pudo conectar (host inaccesible o rechazó la conexión)")
    except Exception as e:
        print(f"   ❌  Error: {e}")

print(f"\n{'─'*60}")
print("Listo. La URL que muestre ✅ TOKEN ENCONTRADO es la correcta.")
print("Si ninguna funciona, verifica MATIAS_EMAIL y MATIAS_PASSWORD en Railway.\n")
