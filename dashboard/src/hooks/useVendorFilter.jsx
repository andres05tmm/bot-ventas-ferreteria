import { createContext, useContext, useState, useEffect } from 'react'
import { useAuth } from './useAuth'

const VendorContext = createContext(null)

export function VendorProvider({ children }) {
  const { authFetch } = useAuth()
  const [vendedores, setVendedores] = useState([])
  const [selectedVendor, setSelectedVendor] = useState(null) // null = todos
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const resp = await authFetch('/usuarios/vendedores')
        const data = resp.ok ? await resp.json() : []
        setVendedores(data || [])
      } catch (e) {
        setVendedores([])
      } finally {
        setLoading(false)
      }
    })()
  }, []) // [] — solo al montar. authFetch no está memoizada con useCallback,
         // incluirla causaría un loop infinito (nueva referencia en cada render).

  return (
    <VendorContext.Provider value={{ vendedores, selectedVendor, setSelectedVendor, loading }}>
      {children}
    </VendorContext.Provider>
  )
}

export function useVendorFilter() {
  const ctx = useContext(VendorContext)
  if (!ctx) {
    return { vendedores: [], selectedVendor: null, setSelectedVendor: () => {}, loading: false }
  }
  return ctx
}
