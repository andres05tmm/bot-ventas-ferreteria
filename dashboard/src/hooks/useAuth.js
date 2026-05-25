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

  /**
   * getAuthHeaders - Returns headers object with JWT Authorization header
   * @returns {Object} Headers with Authorization: Bearer <token>
   */
  const getAuthHeaders = () => {
    const token = getToken()
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }

  /**
   * authFetch - Wrapper around fetch that automatically adds JWT token.
   * Si el servidor responde 401 (token expirado o inválido), hace logout
   * automático y redirige al login en lugar de dejar la UI en estado vacío.
   * @param {string} url - The URL to fetch
   * @param {Object} options - fetch options (will be merged with auth headers)
   * @returns {Promise} fetch response promise
   */
  const authFetch = async (url, options = {}) => {
    const headers = {
      ...getAuthHeaders(),
      ...(options.headers || {})
    }

    const response = await fetch(url, { ...options, headers })

    if (response.status === 401) {
      // Token expirado o inválido — limpiar sesión y redirigir al login
      localStorage.removeItem('ferrebot_token')
      localStorage.removeItem('ferrebot_user')
      window.location.href = '/login'
    }

    return response
  }

  return { getToken, getUser, logout, isAdmin, authHeader, getAuthHeaders, authFetch }
}
