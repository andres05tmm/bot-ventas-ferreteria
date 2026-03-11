import { useState, useMemo } from 'react'
import { Card, SectionTitle, Spinner, ErrorMsg, useFetch, cop, Badge } from '../components/shared.jsx'

export default function TabInventario() {
  const { data, loading, error } = useFetch('/productos')
  const { data: alertasData } = useFetch('/inventario/bajo')

  const [busqueda, setBusqueda] = useState('')
  const [soloBajos, setSoloBajos] = useState(false)

  const alertaKeys = useMemo(() => {
    const set = new Set()
    ;(alertasData?.alertas || []).forEach(a => set.add(a.key))
    return set
  }, [alertasData])

  const productos = useMemo(() => {
    const lista = data?.productos || []
    return lista.filter(p => {
      const matchBusqueda = !busqueda ||
        p.nombre.toLowerCase().includes(busqueda.toLowerCase()) ||
        p.codigo.toLowerCase().includes(busqueda.toLowerCase())
      const matchBajo = !soloBajos || alertaKeys.has(p.key)
      return matchBusqueda && matchBajo
    })
  }, [data, busqueda, soloBajos, alertaKeys])

  // Agrupar por categoría
  const porCategoria = useMemo(() => {
    const grupos = {}
    productos.forEach(p => {
      const cat = p.categoria || 'Sin categoría'
      if (!grupos[cat]) grupos[cat] = []
      grupos[cat].push(p)
    })
    return grupos
  }, [productos])

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  const totalAlertas = alertasData?.total || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Alertas resumen */}
      {totalAlertas > 0 && (
        <div style={{
          background: '#1a0a0a',
          border: '1px solid #7f1d1d',
          borderRadius: 8,
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}>
          <span style={{ fontSize: 18 }}>⚠️</span>
          <span style={{ color: '#fca5a5', fontSize: 13 }}>
            <strong>{totalAlertas}</strong> {totalAlertas === 1 ? 'producto requiere' : 'productos requieren'} atención
            (stock en cero o sin precio)
          </span>
          <button
            onClick={() => setSoloBajos(s => !s)}
            style={{
              marginLeft: 'auto',
              padding: '4px 12px',
              borderRadius: 5,
              border: '1px solid #7f1d1d',
              background: soloBajos ? '#dc2626' : 'transparent',
              color: soloBajos ? '#fff' : '#fca5a5',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            {soloBajos ? 'Mostrar todos' : 'Ver solo alertas'}
          </button>
        </div>
      )}

      {/* Buscador */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="Buscar producto o código..."
          value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          style={{
            flex: 1,
            minWidth: 200,
            padding: '8px 14px',
            borderRadius: 7,
            border: '1px solid #2a2a2a',
            background: '#141414',
            color: '#f5f5f5',
            fontSize: 13,
            outline: 'none',
          }}
        />
        <span style={{ color: '#888', fontSize: 12 }}>
          {productos.length} producto{productos.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Tabla por categoría */}
      {Object.entries(porCategoria).map(([cat, prods]) => (
        <Card key={cat}>
          <SectionTitle>
            {cat.replace(/^\d+\s*/, '')}
            <span style={{ color: '#666', fontWeight: 400, marginLeft: 8, fontSize: 12 }}>
              ({prods.length})
            </span>
          </SectionTitle>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  {['Código', 'Nombre', 'Precio', 'Estado'].map(h => (
                    <th key={h} style={{
                      textAlign: h === 'Precio' || h === 'Estado' ? 'center' : 'left',
                      padding: '8px 12px',
                      color: '#888',
                      fontWeight: 600,
                      borderBottom: '1px solid #2a2a2a',
                      whiteSpace: 'nowrap',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {prods.map(p => {
                  const esAlerta = alertaKeys.has(p.key)
                  return (
                    <tr
                      key={p.key}
                      style={{
                        borderBottom: '1px solid #1a1a1a',
                        background: esAlerta ? '#1a0808' : 'transparent',
                      }}
                    >
                      <td style={{ padding: '9px 12px', color: '#666', fontFamily: 'monospace', fontSize: 12 }}>
                        {p.codigo || '—'}
                      </td>
                      <td style={{ padding: '9px 12px', color: '#f5f5f5' }}>
                        {p.nombre}
                        {esAlerta && (
                          <span style={{ marginLeft: 6, fontSize: 10, color: '#f87171' }}>●</span>
                        )}
                      </td>
                      <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                        {p.precio ? (
                          <span style={{ color: '#22c55e', fontWeight: 600 }}>{cop(p.precio)}</span>
                        ) : (
                          <Badge color="#f59e0b">Sin precio</Badge>
                        )}
                      </td>
                      <td style={{ padding: '9px 12px', textAlign: 'center' }}>
                        {esAlerta ? (
                          <Badge color="#dc2626">
                            {!p.precio ? 'Sin precio' : 'Stock 0'}
                          </Badge>
                        ) : (
                          <Badge color="#22c55e">OK</Badge>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      ))}

      {productos.length === 0 && (
        <Card>
          <p style={{ color: '#666', fontSize: 13 }}>No se encontraron productos.</p>
        </Card>
      )}
    </div>
  )
}
