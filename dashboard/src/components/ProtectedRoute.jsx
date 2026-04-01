import { Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'

export const ProtectedRoute = ({ children }) => {
  const { getToken } = useAuth()
  const [loading, setLoading] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    const token = getToken()
    if (!token) {
      setAuthenticated(false)
      setLoading(false)
      return
    }

    // Verifica el token con GET /auth/me
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
  }, [getToken])

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
