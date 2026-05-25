"""
generate_bancolombia_token.py
Genera un refresh_token de Gmail para Bancolombia usando las credenciales
exactas de Railway. Usa un servidor local en puerto 8080 para capturar
el callback OAuth2 automáticamente.

Requisito previo en Google Cloud Console:
  Credentials → tu OAuth Client → Authorized redirect URIs → agregar:
  http://localhost:8080

Uso:
    python generate_bancolombia_token.py
"""

import http.server
import json
import threading
import urllib.parse
import urllib.request
import webbrowser

PORT         = 8080
REDIRECT_URI = f"http://localhost:{PORT}"
SCOPE        = "https://www.googleapis.com/auth/gmail.readonly"

# ─────────────────────────────────────────────────────────────────────────────
print("=" * 60)
print("Generador de refresh_token Gmail — Bancolombia")
print("=" * 60)
print("\nPega los valores exactos de Railway:\n")

CLIENT_ID     = input("BANCOLOMBIA_GMAIL_CLIENT_ID     → ").strip()
CLIENT_SECRET = input("BANCOLOMBIA_GMAIL_CLIENT_SECRET → ").strip()

if not CLIENT_ID or not CLIENT_SECRET:
    print("\n❌ Error: debes ingresar ambos valores.")
    exit(1)

# ─── Servidor local para capturar el código OAuth ────────────────────────────
received_code = [None]
server_error  = [None]

class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            received_code[0] = params["code"][0]
            body = b"<h2>Autorizado. Puedes cerrar esta ventana.</h2>"
        elif "error" in params:
            server_error[0] = params["error"][0]
            body = f"<h2>Error: {params['error'][0]}</h2>".encode()
        else:
            body = b"<h2>Esperando...</h2>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # silenciar logs del servidor HTTP

server = http.server.HTTPServer(("localhost", PORT), _Handler)
thread = threading.Thread(target=server.handle_request)
thread.daemon = True
thread.start()

# ─── Abrir navegador para autorizar ──────────────────────────────────────────
auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    + urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPE,
        "response_type": "code",
        "access_type":   "offline",
        "prompt":        "consent",
    })
)

print(f"\nAbriendo navegador...")
print(f"→ Autoriza con la cuenta Gmail de Bancolombia\n")
webbrowser.open(auth_url)
print("Esperando respuesta de Google...")

thread.join(timeout=120)  # esperar máximo 2 minutos

if server_error[0]:
    print(f"\n❌ Google devolvió error: {server_error[0]}")
    exit(1)

if not received_code[0]:
    print("\n❌ No se recibió el código en 2 minutos.")
    print(f"Intenta abrir esta URL manualmente:\n{auth_url}")
    exit(1)

print("✅ Código recibido — intercambiando por tokens...\n")

# ─── Intercambiar código por tokens ──────────────────────────────────────────
payload = urllib.parse.urlencode({
    "code":          received_code[0],
    "client_id":     CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri":  REDIRECT_URI,
    "grant_type":    "authorization_code",
}).encode("utf-8")

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=payload,
    method="POST",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)

try:
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"❌ Error {e.code} al intercambiar el código:")
    print(body)
    exit(1)

# ─── Verificar el token localmente antes de enviarlo a Railway ───────────────
refresh_token = result.get("refresh_token", "")

if refresh_token:
    print("Verificando el token localmente con tus credenciales...")
    verify_payload = urllib.parse.urlencode({
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    }).encode("utf-8")
    verify_req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=verify_payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(verify_req) as vresp:
            vresult = json.loads(vresp.read().decode())
        print(f"✅ Verificación LOCAL exitosa — el token funciona con las credenciales ingresadas.")
        print(f"   access_token (primeros 30 chars): {vresult.get('access_token','')[:30]}...\n")
    except urllib.error.HTTPError as ve:
        vbody = ve.read().decode()
        print(f"❌ Verificación LOCAL FALLIDA — error {ve.code}:")
        print(vbody)
        print("\n⚠️  El token NO funciona con las credenciales que ingresaste.")
        print("   Verifica que CLIENT_ID y CLIENT_SECRET sean exactamente los de Railway.")
        exit(1)

# ─── Mostrar resultado ────────────────────────────────────────────────────────
print("=" * 60)
if refresh_token:
    print("✅ ÉXITO — refresh_token generado y verificado correctamente\n")
    print(f"refresh_token:\n{refresh_token}\n")
    print("-" * 60)
    print("Comando para actualizar en Railway (cópialo completo):")
    print("-" * 60)
    t = refresh_token.replace('"', '\\"')
    print(
        f'curl -X POST "https://bot-ventas-ferreteria-production.up.railway.app'
        f'/bancolombia/gmail/token?auth=5c244aadbccdd566731233d25ff93971f231cf42"'
        f' -H "Content-Type: application/json"'
        f' -d "{{\\"token\\": \\"{t}\\"}}"'
    )
else:
    print("⚠️  Google no devolvió refresh_token.")
    print("Respuesta:", json.dumps(result, indent=2))

print("=" * 60)
