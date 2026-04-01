import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTheme, THEMES } from '../components/shared.jsx'

export default function Login() {
  const t = useTheme()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    // Inyecta el script de Telegram Login Widget
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-web-app.js'
    script.async = true
    document.body.appendChild(script)

    // Define el callback de autenticación
    window.onTelegramAuth = async (user) => {
      setLoading(true)
      setError('')

      try {
        // Envía los datos del usuario a /api/auth/telegram
        const response = await fetch('/api/auth/telegram', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(user),
        })

        if (response.ok) {
          const data = await response.json()
          // Guarda el token y la información del usuario en localStorage
          localStorage.setItem('ferrebot_token', data.token)
          localStorage.setItem('ferrebot_user', JSON.stringify({
            usuario_id: data.usuario_id || user.id,
            nombre: data.nombre,
            rol: data.rol,
          }))
          // Redirige al dashboard
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

    return () => {
      if (document.body.contains(script)) {
        document.body.removeChild(script)
      }
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
        {/* Logo/Branding */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '16px',
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
            color: t.text,
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

        {/* Telegram Widget Container */}
        <div style={{
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '16px',
        }}>
          <div
            className="telegram-login"
            data-telegram-login="elmicha_bot"
            data-size="large"
            data-onauth="onTelegramAuth"
            data-request-access="write"
            style={{
              display: 'flex',
              justifyContent: 'center',
            }}
          />
        </div>

        {/* Loading Spinner */}
        {loading && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
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

        {/* Error Message */}
        {error && (
          <div style={{
            background: 'rgba(200, 32, 14, 0.08)',
            border: `1px solid ${t.accent}`,
            borderRadius: '10px',
            padding: '12px 16px',
            fontSize: '13px',
            color: t.accent,
            fontWeight: '500',
            width: '100%',
            textAlign: 'center',
          }}>
            {error}
          </div>
        )}

        {/* Help Text */}
        <p style={{
          margin: '0',
          fontSize: '12px',
          color: t.textMuted,
          textAlign: 'center',
          lineHeight: '1.5',
        }}>
          Haz clic en el botón de Telegram para ingresar al dashboard
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
