/**
 * useRealtime.js — Hook SSE para recibir notificaciones en tiempo real del backend.
 *
 * El servidor emite eventos via GET /events (Server-Sent Events) cada vez que
 * ocurre un cambio relevante: venta registrada, stock actualizado, caja cerrada, etc.
 * Este hook escucha ese stream y llama a onEvent(type, data) por cada mensaje.
 *
 * Autenticación
 * ─────────────
 * EventSource (API nativa del browser) no soporta headers custom, por lo tanto
 * no puede enviar "Authorization: Bearer <token>". La solución es pasar el JWT
 * como query param: GET /events?token=<jwt>
 * El backend lo valida igual que cualquier otro endpoint protegido.
 *
 * El token se lee de localStorage con la clave "token" — ajustar si tu auth
 * guarda el JWT bajo una clave distinta.
 *
 * Características:
 *  - Reconexión automática con backoff exponencial (2s → 4s → 8s … máx 30s)
 *  - Heartbeat ignorado automáticamente (el servidor emite ": heartbeat" cada 25s)
 *  - Compatible con el mismo origen (sin VITE_API_URL) y con API separada
 *  - El callback onEvent siempre llama a la versión más reciente via ref,
 *    así no se necesita incluirlo en las dependencias del useEffect
 *  - Si no hay token en localStorage, no intenta conectar (evita 401 en loop)
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
 *
 * Evento sintético (solo del hook, no del backend):
 *   reconnected           → se perdió la conexión y se restableció; hacer re-fetch
 *                           de todos los datos críticos para cubrir el gap.
 */

import { useEffect, useRef } from 'react'

const API_URL = import.meta.env.VITE_API_URL || ''

/**
 * Verifica si un JWT está expirado decodificando el campo `exp` del payload.
 * Devuelve true si expiró o si no se puede decodificar (token corrupto).
 */
function isTokenExpired(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp && payload.exp < Date.now() / 1000
  } catch {
    return true
  }
}

function redirectToLogin() {
  localStorage.removeItem('ferrebot_token')
  localStorage.removeItem('ferrebot_user')
  window.location.href = '/login'
}

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
    let isFirstConnect = true

    function connect() {
      if (destroyed) return

      // EventSource no soporta headers custom, por lo que el JWT se pasa
      // como query param. El backend lo valida en GET /events?token=...
      const token = localStorage.getItem('ferrebot_token')
      if (!token) {
        // Sin token no hay sesión — no conectar para evitar 401 en bucle.
        return
      }

      // Si el token ya expiró, redirigir al login en lugar de conectar y
      // generar un loop de 401s que spamea los logs del servidor.
      if (isTokenExpired(token)) {
        redirectToLogin()
        return
      }

      const url = `${API_URL}/events?token=${encodeURIComponent(token)}`

      // withCredentials=true envía cookies de sesión si existieran,
      // aunque con JWT en query param no es estrictamente necesario.
      es = new EventSource(url, { withCredentials: true })

      es.onopen = () => {
        // Si es una reconexión (no la primera vez), notificar al consumer para
        // que haga un re-fetch completo y cubra los eventos perdidos durante la
        // desconexión. La primera conexión no emite este evento.
        if (!isFirstConnect) {
          onEventRef.current?.('reconnected', {})
        }
        isFirstConnect = false
        retries = 0
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

        // Si el token expiró mientras estaba conectado, no reintentar —
        // redirigir al login para que el vendedor obtenga un token nuevo.
        const currentToken = localStorage.getItem('ferrebot_token')
        if (!currentToken || isTokenExpired(currentToken)) {
          redirectToLogin()
          return
        }

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
