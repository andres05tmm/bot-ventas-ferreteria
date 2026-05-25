import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { Card } from '@/components/ui/card.jsx'

export default function Login() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const widgetRef = useRef(null)

  useEffect(() => {
    window.onTelegramAuth = async (user) => {
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

    return () => { delete window.onTelegramAuth }
  }, [navigate])

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col items-center justify-center p-5 text-foreground">
      <Card className="w-full max-w-sm px-10 py-12 flex flex-col items-center gap-7">
        {/* Branding */}
        <div className="flex flex-col items-center gap-2.5 w-full">
          <div className="w-8 h-[3px] bg-primary mb-1" />
          <p className="m-0 text-[9px] font-medium text-muted-foreground tracking-[.2em] uppercase">
            Ferretería
          </p>
          <h1 className="m-0 text-[22px] font-extrabold text-foreground tracking-tight leading-tight text-center">
            Punto Rojo
          </h1>
          <p className="m-0 mt-1 text-[11px] text-muted-foreground tracking-wider uppercase">
            Dashboard de ventas
          </p>
        </div>

        <div className="w-full h-px bg-border" />

        {/* Widget container — el script se inyecta aquí */}
        <div ref={widgetRef} className="flex justify-center min-h-[48px] w-full" />

        {loading && (
          <div className="inline-flex items-center gap-2 text-muted-foreground text-xs tracking-wide">
            <Loader2 className="size-3.5 animate-spin text-primary" />
            <span>Autenticando…</span>
          </div>
        )}

        {error && (
          <div className="w-full text-center bg-destructive/10 border border-destructive/40 rounded-md px-3.5 py-2.5 text-xs text-destructive font-medium">
            {error}
          </div>
        )}

        <p className="m-0 text-[11px] text-muted-foreground text-center leading-relaxed">
          Inicia sesión con tu cuenta de Telegram para acceder al dashboard
        </p>
      </Card>

      <p className="mt-8 text-[10px] text-muted-foreground tracking-widest uppercase">
        v5 · Bot Telegram
      </p>
    </div>
  )
}
