"""
Google Drive: subir, descargar y cola de reintentos.
Usa el servicio cacheado de config.py para no autenticar en cada llamada.
"""

import io
import json
import os

import config
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

_COLA_FILE = "cola_drive.json"


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
        print(f"⚠️ Error descargando '{nombre_archivo}' de Drive (modo offline): {e}")
        config.DRIVE_DISPONIBLE = False
        config.reset_google_clients()
        return False


def subir_a_drive(nombre_archivo: str) -> bool:
    """
    Sube o actualiza un archivo en Drive.
    Si falla, encola el archivo para reintentar cuando Drive vuelva.
    """
    try:
        service = config.get_drive_service()
        _subir_con_service(service, nombre_archivo)
        config.DRIVE_DISPONIBLE = True
        _reintentar_pendientes()
        return True

    except Exception as e:
        print(f"⚠️ Error subiendo '{nombre_archivo}' a Drive: {e}. Guardando en cola local.")
        config.DRIVE_DISPONIBLE = False
        config.reset_google_clients()
        _encolar_para_subir(nombre_archivo)
        return False


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
                print(f"✅ Archivo pendiente subido a Drive: {nombre}")
            except Exception as e:
                print(f"⚠️ No se pudo subir archivo pendiente '{nombre}': {e}")
    except Exception as e:
        print(f"Error accediendo a Drive para reintentar pendientes: {e}")

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
    print("🔄 Sincronizando con Google Drive...")

    from memoria import invalidar_cache_memoria, bloquear_subida_drive

    # Bloquear subidas a Drive durante la sincronizacion
    # para que nada sobreescriba el JSON correcto mientras descargamos
    bloquear_subida_drive(True)

    try:
        # Limpiar cache RAM
        invalidar_cache_memoria()

        # Sacar memoria.json de la cola pendiente para proteger el Drive
        cola = _leer_cola()
        cola_limpia = [f for f in cola if f != config.MEMORIA_FILE]
        if len(cola_limpia) != len(cola):
            print("🧹 Removido memoria.json de cola pendiente para proteger el Drive.")
            _escribir_cola(cola_limpia)

        ok_excel = descargar_de_drive(config.EXCEL_FILE)
        ok_mem   = descargar_de_drive(config.MEMORIA_FILE)

        # Forzar recarga del JSON recien descargado
        invalidar_cache_memoria()

        if ok_excel or ok_mem:
            print("✅ Sincronizacion completa.")
        else:
            print("⚠️ No se pudo sincronizar con Drive. Trabajando en modo local.")
    finally:
        # Desbloquear subidas — a partir de aqui todo funciona normal
        bloquear_subida_drive(False)
        print("🔓 Subida a Drive desbloqueada.")
