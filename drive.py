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


def _ejecutar_subida_real(nombre_archivo: str):
    """Función que realmente llama a la API de Drive. Se ejecuta tras el debounce."""
    with _debounce_lock:
        _debounce_pendiente.discard(nombre_archivo)
        _debounce_timers.pop(nombre_archivo, None)

    if not os.path.exists(nombre_archivo):
        return
    try:
        service = config.get_drive_service()
        _subir_con_service(service, nombre_archivo)
        config.DRIVE_DISPONIBLE = True
        _reintentar_pendientes()
    except Exception as e:
        logging.getLogger("ferrebot.drive").warning(f"⚠️ Error subiendo '{nombre_archivo}' a Drive: {e}. Guardando en cola local.")
        config.DRIVE_DISPONIBLE = False
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


def descargar_de_drive(nombre_archivo: str) -> bool:
    """Descarga un archivo de Drive al servidor. Retorna False si falla."""
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
        with open(nombre_archivo, "wb") as f:
            f.write(buffer.read())

        config.DRIVE_DISPONIBLE = True
        return True

    except Exception as e:
        logging.getLogger("ferrebot.drive").warning(f"⚠️ Error descargando '{nombre_archivo}' de Drive (modo offline): {e}")
        config.DRIVE_DISPONIBLE = False
        config.reset_google_clients()
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
        service = config.get_drive_service()
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
