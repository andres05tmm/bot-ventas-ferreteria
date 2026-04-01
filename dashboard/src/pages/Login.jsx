import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTheme } from '../components/shared.jsx'

export default function Login() {
  const t = useTheme()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const widgetRef = useRef(null)

  useEffect(() => {
    // Definir el callback ANTES de que el script cargue
    window.onTelegramAuth = async (user) => {
      console.log('[TelegramAuth] datos recibidos del widget:', user)
      setLoading(true)
      setError('')

      try {
        const response = await fetch('https://cooperative-embrace-production-630e.up.railway.app/auth/telegram', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(user),
        })

        if (response.ok) {
          const data = await response.json()
          localStorage.setItem('ferrebot_token', data.token)
          localStorage.setItem('ferrebot_user', JSON.stringify({
            usuario_id: data.usuario_id || user.id,
            nombre: data.nombre,
            rol: data.rol,
          }))
          navigate('/')
        } else if (response.status === 403) {
          setError('No tienes acceso. Pídele a Andrés que te registre.')
        } else if (response.status === 401) {
          setError('Error de verificación. Intenta de nuevo.')
        } else {
          setError('Error al autenticar. Intenta de nuevo.')
        }
      } catch (err) {
        console.error('Auth error:', err)
        setError('Error de conexión. Intenta de nuevo.')
      } finally {
        setLoading(false)
      }
    }

    // Inyectar el script del widget con todos sus data-attributes
    // dangerouslySetInnerHTML no ejecuta <script>, hay que crearlo via DOM
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.setAttribute('data-telegram-login', 'elmicha_bot')
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-onauth', 'onTelegramAuth(user)')
    script.setAttribute('data-request-access', 'write')
    script.setAttribute('data-userpic', 'false')
    script.async = true

    if (widgetRef.current) {
      widgetRef.current.innerHTML = ''
      widgetRef.current.appendChild(script)
    }

    return () => {
      delete window.onTelegramAuth
    }
  }, [navigate])

  return (
    <div style={{
      minHeight: '100dvh',
      background: t.bgPattern,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      fontFamily: "'Sora', system-ui, sans-serif",
      color: t.text,
    }}>
      <div style={{
        background: t.card,
        borderRadius: '20px',
        padding: '48px',
        boxShadow: t.shadow,
        border: `1px solid ${t.border}`,
        maxWidth: '420px',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '24px',
      }}>
        {/* Branding */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '8px',
        }}>
          <div style={{
            width: '56px',
            height: '56px',
            borderRadius: '12px',
            background: t.accentSub,
            border: `2px solid ${t.accent}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '32px',
          }}>
            🏪
          </div>
          <h1 style={{
            margin: '0',
            fontSize: '24px',
            fontWeight: '800',
            color: '#C8200E',
            letterSpacing: '-0.02em',
          }}>
            Ferretería Punto Rojo
          </h1>
          <p style={{
            margin: '0',
            fontSize: '13px',
            color: t.textMuted,
            fontWeight: '500',
          }}>
            Dashboard de ventas
          </p>
        </div>

        {/* Widget container — el script se inyecta aquí */}
        <div
          ref={widgetRef}
          style={{
            display: 'flex',
            justifyContent: 'center',
            minHeight: '48px',
          }}
        />

        {/* Loading */}
        {loading && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            color: t.textMuted,
            fontSize: '13px',
          }}>
            <div style={{
              width: '14px',
              height: '14px',
              borderRadius: '50%',
              border: `2px solid ${t.accentSub}`,
              borderTopColor: t.accent,
              animation: 'spin 0.8s linear infinite',
            }} />
            <span>Autenticando...</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            background: 'rgba(200, 32, 14, 0.08)',
            border: '1px solid #C8200E',
            borderRadius: '10px',
            padding: '12px 16px',
            fontSize: '13px',
            color: '#C8200E',
            fontWeight: '500',
            width: '100%',
            textAlign: 'center',
          }}>
            {error}
          </div>
        )}

        <p style={{
          margin: '0',
          fontSize: '12px',
          color: t.textMuted,
          textAlign: 'center',
          lineHeight: '1.5',
        }}>
          Inicia sesión con tu cuenta de Telegram para acceder al dashboard
        </p>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
