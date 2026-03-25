"""
Google Drive: subir, descargar y cola de reintentos.
Usa el servicio cacheado de config.py para no autenticar en cada llamada.
"""

import logging

import io
import json
import os
import threading
import time

import config
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

_COLA_FILE = "cola_drive.json"

# ─────────────────────────────────────────────
# DEBOUNCE: evitar subidas múltiples del mismo archivo en ráfagas cortas
# (ej: 10 ventas seguidas generan 10 llamadas a subir_a_drive en <2s)
# ─────────────────────────────────────────────
_DEBOUNCE_SEGUNDOS = 2.0
_debounce_lock  = threading.Lock()
_debounce_timers: dict[str, threading.Timer] = {}   # nombre_archivo → Timer activo
_debounce_pendiente: set[str] = set()               # archivos esperando ser subidos


def _crear_service_aislado():
    """
    Crea una instancia NUEVA del servicio Drive para uso en hilos de threading.
    httplib2 NO es thread-safe — compartir una instancia cacheada entre hilos
    causa segfault en Python 3.11 cuando dos subidas ocurren simultáneamente
    (ej: ventas.xlsx y memoria.json en la misma ráfaga de ventas).
    Cada hilo de subida necesita su propio objeto de conexión.
    """
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    import json as _json
    creds_dict = _json.loads(config.GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)


def _ejecutar_subida_real(nombre_archivo: str):
    """Función que realmente llama a la API de Drive. Se ejecuta tras el debounce."""
    with _debounce_lock:
        _debounce_pendiente.discard(nombre_archivo)
        _debounce_timers.pop(nombre_archivo, None)

    if not os.path.exists(nombre_archivo):
        return
    try:
        # Instancia aislada por hilo — evita segfault por httplib2 no thread-safe
        service = _crear_service_aislado()
        _subir_con_service(service, nombre_archivo)
        config._set_drive_disponible(True)
        _reintentar_pendientes()
    except Exception as e:
        logging.getLogger("ferrebot.drive").warning(f"⚠️ Error subiendo '{nombre_archivo}' a Drive: {e}. Guardando en cola local.")
        config._set_drive_disponible(False)
        config.reset_google_clients()
        _encolar_para_subir(nombre_archivo)


def _mime_para(nombre_archivo: str) -> str:
    if nombre_archivo.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if nombre_archivo.endswith(".json"):
        return "application/json"
    return "application/octet-stream"


def _buscar_archivo(service, nombre_archivo: str):
    """Retorna el file_id del archivo en Drive, o None si no existe."""
    query = (
        f"name='{nombre_archivo}' "
        f"and '{config.GOOGLE_FOLDER_ID}' in parents "
        f"and trashed=false"
    )
    resultado = service.files().list(q=query, fields="files(id, name)").execute()
    archivos = resultado.get("files", [])
    return archivos[0]["id"] if archivos else None


def _subir_con_service(service, nombre_archivo: str) -> bool:
    """
    Sube o actualiza un archivo usando un service ya autenticado.
    Extrae la logica duplicada que antes estaba en subir_a_drive y _reintentar_pendientes.
    """
    file_id = _buscar_archivo(service, nombre_archivo)
    mime_type = _mime_para(nombre_archivo)

    with open(nombre_archivo, "rb") as f:
        contenido = f.read()

    media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mime_type)

    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        metadata = {"name": nombre_archivo, "parents": [config.GOOGLE_FOLDER_ID]}
        service.files().create(body=metadata, media_body=media).execute()

    return True


def descargar_de_drive(nombre_archivo: str, ruta_destino: str = None) -> bool:
    """
    Descarga un archivo de Drive al servidor. Retorna False si falla.
    - nombre_archivo: nombre del archivo tal como está en Drive.
    - ruta_destino:   ruta local donde guardar el archivo.
                      Si es None, se guarda con el mismo nombre en el directorio actual.
    """
    ruta_local = ruta_destino or nombre_archivo
    try:
        service = config.get_drive_service()
        file_id = _buscar_archivo(service, nombre_archivo)
        if not file_id:
            return False

        buffer = io.BytesIO()
        request = service.files().get_media(fileId=file_id)
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        buffer.seek(0)
        with open(ruta_local, "wb") as f:
            f.write(buffer.read())

        config._set_drive_disponible(True)
        return True

    except Exception as e:
        logging.getLogger("ferrebot.drive").warning(f"⚠️ Error descargando '{nombre_archivo}' de Drive (modo offline): {e}")
        config._set_drive_disponible(False)
        config.reset_google_clients()
        return False


def subir_a_drive_urgente(nombre_archivo: str) -> None:
    """
    Sube inmediatamente sin debounce, en hilo aislado.
    Usar para cambios críticos (precios, configuración) donde el debounce
    puede causar pérdida de datos si el container se reinicia antes de 2s.
    Cancela el timer de debounce pendiente para ese archivo si existe.
    """
    with _debounce_lock:
        # Cancelar timer pendiente si existe — la subida urgente lo reemplaza
        timer_anterior = _debounce_timers.pop(nombre_archivo, None)
        if timer_anterior:
            timer_anterior.cancel()
        _debounce_pendiente.discard(nombre_archivo)

    # Ejecutar en hilo aislado inmediatamente (no bloquea el caller)
    t = threading.Thread(target=_ejecutar_subida_real, args=[nombre_archivo], daemon=True)
    t.start()


def subir_archivo_a_drive(ruta_local: str, nombre_drive: str) -> bool:
    """
    Sube un archivo desde ruta_local a Drive con el nombre nombre_drive.
    Útil cuando la ruta local difiere del nombre en Drive (ej: archivos temporales).
    """
    import shutil, tempfile
    # Copiar al directorio de trabajo con el nombre correcto y usar subir_a_drive normal
    ruta_estable = nombre_drive
    try:
        shutil.copy2(ruta_local, ruta_estable)
        return subir_a_drive(ruta_estable)
    except Exception as e:
        logging.getLogger("ferrebot.drive").warning(f"⚠️ subir_archivo_a_drive falló: {e}")
        return False


def subir_a_drive(nombre_archivo: str) -> bool:
    """
    Sube o actualiza un archivo en Drive con debounce:
    si se llama varias veces en menos de DEBOUNCE_SEGUNDOS para el mismo archivo,
    solo se ejecuta la última llamada. Evita ráfagas de uploads en ventas múltiples.
    """
    with _debounce_lock:
        # Cancelar timer anterior si existe
        timer_anterior = _debounce_timers.pop(nombre_archivo, None)
        if timer_anterior:
            timer_anterior.cancel()

        # Registrar que este archivo está pendiente
        _debounce_pendiente.add(nombre_archivo)

        # Crear nuevo timer
        timer = threading.Timer(_DEBOUNCE_SEGUNDOS, _ejecutar_subida_real, args=[nombre_archivo])
        timer.daemon = True
        _debounce_timers[nombre_archivo] = timer
        timer.start()

    return True  # La subida real ocurrirá tras el debounce


def _encolar_para_subir(nombre_archivo: str):
    cola = _leer_cola()
    if nombre_archivo not in cola:
        cola.append(nombre_archivo)
    _escribir_cola(cola)


def _reintentar_pendientes():
    cola = _leer_cola()
    if not cola:
        return

    subidos = []
    try:
        # Instancia aislada — se llama desde hilo de threading, no compartir el service cacheado
        service = _crear_service_aislado()
        for nombre in cola:
            if not os.path.exists(nombre):
                subidos.append(nombre)  # ya no existe, no tiene sentido reintentarlo
                continue
            try:
                _subir_con_service(service, nombre)
                subidos.append(nombre)
                logging.getLogger("ferrebot.drive").info(f"✅ Pendiente subido: {nombre}")
            except Exception as e:
                logging.getLogger("ferrebot.drive").warning(f"⚠️ No se pudo subir pendiente '{nombre}': {e}")
    except Exception as e:
        logging.getLogger("ferrebot.drive").error("Error reintentando pendientes Drive: %s", e)

    cola_restante = [n for n in cola if n not in subidos]
    _escribir_cola(cola_restante)


def _leer_cola() -> list:
    if not os.path.exists(_COLA_FILE):
        return []
    try:
        with open(_COLA_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _escribir_cola(cola: list):
    with open(_COLA_FILE, "w") as f:
        json.dump(cola, f)


def sincronizar_archivos():
    """Al iniciar el bot, descarga los archivos de Drive si existen."""
    logging.getLogger("ferrebot.drive").info("Sincronizando con Google Drive...")

    from memoria import invalidar_cache_memoria, bloquear_subida_drive

    # Bloquear subidas a Drive durante la sincronizacion
    bloquear_subida_drive(True)

    # Cancelar TODOS los timers de debounce pendientes para que no
    # sobreescriban los archivos que vamos a descargar de Drive
    with _debounce_lock:
        for nombre, timer in list(_debounce_timers.items()):
            timer.cancel()
            logging.getLogger("ferrebot.drive").info(f"Timer cancelado para '{nombre}'")
        _debounce_timers.clear()
        _debounce_pendiente.clear()

    try:
        # Limpiar cache RAM
        invalidar_cache_memoria()

        # Sacar memoria.json de la cola pendiente para proteger el Drive
        cola = _leer_cola()
        cola_limpia = [f for f in cola if f != config.MEMORIA_FILE]
        if len(cola_limpia) != len(cola):
            logging.getLogger("ferrebot.drive").info("Removido memoria.json de cola pendiente.")
            _escribir_cola(cola_limpia)

        ok_excel = descargar_de_drive(config.EXCEL_FILE)
        ok_mem   = descargar_de_drive(config.MEMORIA_FILE)

        # Forzar recarga del JSON recien descargado
        invalidar_cache_memoria()

        if ok_excel or ok_mem:
            logging.getLogger("ferrebot.drive").info("Sincronizacion completa.")
        else:
            logging.getLogger("ferrebot.drive").warning("No se pudo sincronizar con Drive. Modo local.")
    finally:
        # Desbloquear subidas — a partir de aqui todo funciona normal
        bloquear_subida_drive(False)
        logging.getLogger("ferrebot.drive").info("Subida a Drive desbloqueada.")


# ─────────────────────────────────────────────────────────────────────────────
# SUBCARPETAS Y FOTOS DE FACTURAS
# ─────────────────────────────────────────────────────────────────────────────

def _normalizar_nombre_carpeta(nombre: str) -> str:
    """Normaliza un nombre para usarlo como carpeta en Drive (sin caracteres raros)."""
    import re, unicodedata
    nombre = unicodedata.normalize("NFD", nombre)
    nombre = "".join(c for c in nombre if unicodedata.category(c) != "Mn")
    nombre = re.sub(r"[^\w\s\-]", "", nombre).strip()
    nombre = re.sub(r"\s+", "_", nombre)
    return nombre[:80]  # Drive permite hasta 255, usamos 80 para legibilidad


def _obtener_o_crear_carpeta(service, nombre: str, parent_id: str) -> str:
    """
    Busca una carpeta por nombre dentro de parent_id.
    Si no existe, la crea. Retorna el folder_id.
    """
    nombre_norm = _normalizar_nombre_carpeta(nombre)
    query = (
        f"name='{nombre_norm}' "
        f"and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    res = service.files().list(q=query, fields="files(id, name)").execute()
    carpetas = res.get("files", [])
    if carpetas:
        return carpetas[0]["id"]
    # Crear carpeta
    metadata = {
        "name": nombre_norm,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    carpeta = service.files().create(body=metadata, fields="id").execute()
    logging.getLogger("ferrebot.drive").info(f"[Drive] 📁 Carpeta creada: {nombre_norm}")
    return carpeta["id"]


def _obtener_carpeta_facturas_proveedor(service, proveedor: str) -> str:
    """
    Retorna (o crea) la ruta:
      GOOGLE_FOLDER_ID / Facturas_Proveedores / <Proveedor>
    y devuelve el folder_id de la carpeta del proveedor.
    """
    root_id = config.GOOGLE_FOLDER_ID
    facturas_id = _obtener_o_crear_carpeta(service, "Facturas_Proveedores", root_id)
    proveedor_id = _obtener_o_crear_carpeta(service, proveedor, facturas_id)
    return proveedor_id


def subir_foto_factura(ruta_local: str, nombre_archivo: str, proveedor: str) -> dict:
    """
    Sube una foto de factura a Drive/Facturas_Proveedores/<Proveedor>/<nombre_archivo>.
    Retorna {"ok": True, "file_id": "...", "url": "...", "nombre": "..."}
    o       {"ok": False, "error": "..."}
    """
    from googleapiclient.http import MediaFileUpload
    try:
        service = config.get_drive_service()
        carpeta_id = _obtener_carpeta_facturas_proveedor(service, proveedor)

        mime = "image/jpeg"
        if nombre_archivo.lower().endswith(".png"):
            mime = "image/png"
        elif nombre_archivo.lower().endswith(".pdf"):
            mime = "application/pdf"

        media = MediaFileUpload(ruta_local, mimetype=mime, resumable=False)
        metadata = {"name": nombre_archivo, "parents": [carpeta_id]}
        archivo = service.files().create(
            body=metadata, media_body=media, fields="id, name, webViewLink"
        ).execute()

        file_id = archivo.get("id", "")
        url     = archivo.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")
        logging.getLogger("ferrebot.drive").info(
            f"[Drive] 📎 Foto subida: {nombre_archivo} → {proveedor}"
        )
        return {"ok": True, "file_id": file_id, "url": url, "nombre": nombre_archivo}

    except Exception as e:
        logging.getLogger("ferrebot.drive").error(f"[Drive] ❌ Error subiendo foto: {e}")
        return {"ok": False, "error": str(e)}
