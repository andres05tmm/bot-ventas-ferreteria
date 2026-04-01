/**
 * useAuth - Custom hook for authentication utilities
 * Provides token, user, and auth state management
 */

export const useAuth = () => {
  const getToken = () => localStorage.getItem('ferrebot_token')

  const getUser = () => {
    const user = localStorage.getItem('ferrebot_user')
    return user ? JSON.parse(user) : null
  }

  const logout = () => {
    localStorage.removeItem('ferrebot_token')
    localStorage.removeItem('ferrebot_user')
    window.location.href = '/login'
  }

  const isAdmin = () => getUser()?.rol === 'admin'

  const authHeader = () => {
    const token = getToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  return { getToken, getUser, logout, isAdmin, authHeader }
}
