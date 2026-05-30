"""
dev/repro_match.py — Reproduce el matching de catálogo contra la BD real.
No llama a Claude: solo muestra el bloque MATCH/precálculos que vería el bot.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TELEGRAM_TOKEN", "dummy")
os.environ.setdefault("OPENAI_API_KEY", "dummy")

sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

import db as _db
_db.init_db()

from memoria import cargar_memoria, buscar_multiples_con_alias
from ai.prompt_products import construir_seccion_match

mem = cargar_memoria()
cat = mem.get("catalogo", {})
print(f"== Catálogo cargado: {len(cat)} productos ==")
esmeril = [v["nombre"] for v in cat.values() if "esmeril" in v.get("nombre_lower", "")]
print("Esmeril en memoria:", esmeril)
print()

mensajes = [
    "Que precio tiene 30 centímetros de Lija esmeril 60",
    "30 centimetros lija esmeril 80",
    "2 wayper blanco",
    "2 kg de wayper blanco",
    "30 cm lija esmeril 36",
]

for msg in mensajes:
    print("=" * 70)
    print("MSG:", msg)
    print("-" * 70)
    # candidatos crudos
    cands = buscar_multiples_con_alias(msg, limite=10)
    print("buscar_multiples_con_alias →", [c["nombre"] for c in cands])
    print("-" * 70)
    seccion = construir_seccion_match(msg, "Owner", mem)
    print(seccion)
    print()
