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
        const response = await fetch('/auth/telegram', {
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
      background: '#000000',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      fontFamily: "'Inter', Arial, Helvetica, sans-serif",
      color: '#FFFFFF',
    }}>
      {/* Card */}
      <div style={{
        background: '#FFFFFF',
        borderRadius: '2px',
        padding: '48px 40px',
        boxShadow: 'none',
        border: '1px solid #CCCCCC',
        maxWidth: '380px',
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '28px',
      }}>
        {/* Branding */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '10px',
          width: '100%',
        }}>
          {/* Red accent bar */}
          <div style={{ width: 32, height: 3, background: '#DA291C', marginBottom: 4 }}/>
          <p style={{
            margin: '0',
            fontSize: '9px',
            fontWeight: '500',
            color: '#8F8F8F',
            letterSpacing: '.2em',
            textTransform: 'uppercase',
          }}>
            Ferretería
          </p>
          <h1 style={{
            margin: '0',
            fontSize: '22px',
            fontWeight: '800',
            color: '#181818',
            letterSpacing: '-0.02em',
            lineHeight: 1.1,
            textAlign: 'center',
          }}>
            Punto Rojo
          </h1>
          <p style={{
            margin: '4px 0 0',
            fontSize: '11px',
            color: '#8F8F8F',
            fontWeight: '400',
            letterSpacing: '.08em',
            textTransform: 'uppercase',
          }}>
            Dashboard de ventas
          </p>
        </div>

        {/* Divider */}
        <div style={{ width: '100%', height: 1, background: '#EEEEEE' }}/>

        {/* Widget container — el script se inyecta aquí */}
        <div
          ref={widgetRef}
          style={{
            display: 'flex',
            justifyContent: 'center',
            minHeight: '48px',
            width: '100%',
          }}
        />

        {/* Loading */}
        {loading && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            color: '#666666',
            fontSize: '12px',
            letterSpacing: '.04em',
          }}>
            <div style={{
              width: '13px',
              height: '13px',
              borderRadius: '50%',
              border: '2px solid #EEEEEE',
              borderTopColor: '#DA291C',
              animation: 'spin 0.8s linear infinite',
            }} />
            <span>Autenticando...</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            background: 'rgba(218,41,28,0.06)',
            border: '1px solid #DA291C',
            borderRadius: '2px',
            padding: '10px 14px',
            fontSize: '12px',
            color: '#DA291C',
            fontWeight: '500',
            width: '100%',
            textAlign: 'center',
            letterSpacing: '.02em',
          }}>
            {error}
          </div>
        )}

        <p style={{
          margin: '0',
          fontSize: '11px',
          color: '#8F8F8F',
          textAlign: 'center',
          lineHeight: '1.6',
        }}>
          Inicia sesión con tu cuenta de Telegram para acceder al dashboard
        </p>
      </div>

      {/* Footer mark */}
      <p style={{
        marginTop: 32,
        fontSize: '10px',
        color: '#333333',
        letterSpacing: '.12em',
        textTransform: 'uppercase',
      }}>
        v5 · Bot Telegram
      </p>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0 }
      `}</style>
    </div>
  )
}
