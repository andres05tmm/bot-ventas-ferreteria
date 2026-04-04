/**
 * useRealtime.js — Hook SSE para recibir notificaciones en tiempo real del backend.
 *
 * El servidor emite eventos via GET /events (Server-Sent Events) cada vez que
 * ocurre un cambio relevante: venta registrada, stock actualizado, caja cerrada, etc.
 * Este hook escucha ese stream y llama a onEvent(type, data) por cada mensaje.
 *
 * Características:
 *  - Reconexión automática con backoff exponencial (2s → 4s → 8s … máx 30s)
 *  - Heartbeat ignorado automáticamente (el servidor emite ": heartbeat" cada 25s)
 *  - Compatible con el mismo origen (sin VITE_API_URL) y con API separada
 *  - El callback onEvent siempre llama a la versión más reciente via ref,
 *    así no se necesita incluirlo en las dependencias del useEffect
 *
 * Uso:
 *   import { useRealtime } from './hooks/useRealtime'
 *
 *   useRealtime((type, data) => {
 *     if (type === 'venta_registrada') doRefresh()
 *     if (type === 'inventario_actualizado') recargarCatalogo()
 *   })
 *
 * Eventos que emite el backend:
 *   venta_registrada      → nueva venta o venta varia registrada
 *   venta_editada         → venta modificada o línea eliminada
 *   venta_eliminada       → consecutivo eliminado
 *   caja_abierta          → caja del día abierta
 *   caja_cerrada          → caja del día cerrada
 *   gasto_registrado      → nuevo gasto registrado
 *   compra_registrada     → nueva compra de mercancía o fiscal
 *   compra_actualizada    → compra editada
 *   inventario_actualizado → producto creado, editado, precio o stock cambiado
 */

import { useEffect, useRef } from 'react'

const API_URL = import.meta.env.VITE_API_URL || ''

export function useRealtime(onEvent) {
  // Guardar el callback en un ref para que el useEffect no necesite re-ejecutarse
  // cuando el padre re-renderiza con una función nueva en cada render.
  const onEventRef = useRef(onEvent)
  useEffect(() => {
    onEventRef.current = onEvent
  })

  useEffect(() => {
    let es = null
    let retryTimer = null
    let retries = 0
    let destroyed = false

    function connect() {
      if (destroyed) return

      // EventSource no soporta headers custom, pero withCredentials=true
      // envía las cookies de sesión (necesario si el backend usa autenticación por cookie)
      es = new EventSource(`${API_URL}/events`, { withCredentials: true })

      es.onopen = () => {
        retries = 0 // resetear contador de reintentos al conectar exitosamente
      }

      es.onmessage = (e) => {
        // Los comentarios SSE (": heartbeat", ": connected") no disparan onmessage,
        // solo los mensajes "data: ..." lo hacen — no se necesita filtrarlos aquí.
        try {
          const { type, data } = JSON.parse(e.data)
          onEventRef.current?.(type, data)
        } catch {
          // JSON malformado — ignorar silenciosamente
        }
      }

      es.onerror = () => {
        es.close()
        es = null
        if (destroyed) return

        // Backoff exponencial: 2s, 4s, 8s, 16s, 30s (tope)
        const delay = Math.min(2000 * Math.pow(2, retries), 30_000)
        retries++
        retryTimer = setTimeout(connect, delay)
      }
    }

    connect()

    // Cleanup: cerrar la conexión al desmontar el componente
    return () => {
      destroyed = true
      clearTimeout(retryTimer)
      es?.close()
    }
  }, []) // sin deps — el ref mantiene el callback siempre actualizado
}
