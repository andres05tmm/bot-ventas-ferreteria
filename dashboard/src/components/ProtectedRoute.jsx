import { Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'

export const ProtectedRoute = ({ children }) => {
  const [loading, setLoading]           = useState(true)
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    // Leer el token directamente de localStorage (estable, no causa re-ejecuciones)
    const token = localStorage.getItem('ferrebot_token')
    if (!token) {
      setAuthenticated(false)
      setLoading(false)
      return
    }

    fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (res.ok) {
          setAuthenticated(true)
        } else {
          localStorage.removeItem('ferrebot_token')
          localStorage.removeItem('ferrebot_user')
          setAuthenticated(false)
        }
      })
      .catch(() => {
        setAuthenticated(false)
      })
      .finally(() => {
        setLoading(false)
      })
  }, []) // ← [] en vez de [getToken]: getToken no es estable (nueva referencia
         //   en cada render) y causaba que el efecto corriera 2 veces por sesión.

  if (loading) {
    return (
      <div style={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '14px',
        color: '#666',
        fontFamily: "system-ui, sans-serif",
      }}>
        Cargando...
      </div>
    )
  }

  return authenticated ? children : <Navigate to="/login" />
}
