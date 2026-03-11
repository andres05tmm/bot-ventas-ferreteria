import { useState, useMemo } from 'react'
import { Card, SectionTitle, Spinner, ErrorMsg, useFetch, cop, num } from '../components/shared.jsx'

export default function TabHistorial() {
  const { data, loading, error } = useFetch('/ventas/hoy')
  const [busqueda, setBusqueda] = useState('')

  const ventas = useMemo(() => {
    const lista = data?.ventas || []
    if (!busqueda) return lista
    const q = busqueda.toLowerCase()
    return lista.filter(v =>
      String(v.producto).toLowerCase().includes(q) ||
      String(v.cliente).toLowerCase().includes(q) ||
      String(v.vendedor).toLowerCase().includes(q) ||
      String(v.num).includes(q)
    )
  }, [data, busqueda])

  const totales = useMemo(() => {
    const total = ventas.reduce((s, v) => s + (parseFloat(v.total) || 0), 0)
    return { total, count: ventas.length }
  }, [ventas])

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Barra de búsqueda + stats */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="Buscar por producto, cliente, vendedor o #..."
          value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          style={{
            flex: 1,
            minWidth: 220,
            padding: '8px 14px',
            borderRadius: 7,
            border: '1px solid #2a2a2a',
            background: '#141414',
            color: '#f5f5f5',
            fontSize: 13,
            outline: 'none',
          }}
        />
        <button
          onClick={() => setBusqueda('')}
          style={{
            padding: '8px 14px',
            borderRadius: 7,
            border: '1px solid #2a2a2a',
            background: 'transparent',
            color: '#888',
            fontSize: 13,
          }}
        >
          Limpiar
        </button>
      </div>

      {/* Resumen rápido */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {[
          { label: 'Registros', value: num(totales.count) },
          { label: 'Total mostrado', value: cop(totales.total), color: '#dc2626' },
        ].map(item => (
          <div key={item.label} style={{
            background: '#141414',
            border: '1px solid #2a2a2a',
            borderRadius: 8,
            padding: '10px 18px',
            display: 'flex',
            gap: 10,
            alignItems: 'center',
          }}>
            <span style={{ color: '#888', fontSize: 12 }}>{item.label}:</span>
            <span style={{ fontWeight: 700, color: item.color || '#f5f5f5' }}>{item.value}</span>
          </div>
        ))}
      </div>

      {/* Tabla */}
      <Card style={{ padding: 0 }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #2a2a2a' }}>
          <SectionTitle>Ventas del Día — {new Date().toLocaleDateString('es-CO', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</SectionTitle>
        </div>
        <div style={{ overflowX: 'auto' }}>
          {ventas.length === 0 ? (
            <div style={{ padding: '32px 24px', color: '#666', fontSize: 13, textAlign: 'center' }}>
              {busqueda ? 'Sin resultados para la búsqueda.' : 'No hay ventas registradas hoy.'}
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#111' }}>
                  {['#', 'Hora', 'Producto', 'Cliente', 'Cant.', 'V. Unit.', 'Total', 'Vendedor', 'Pago'].map(h => (
                    <th key={h} style={{
                      padding: '10px 14px',
                      color: '#888',
                      fontWeight: 600,
                      textAlign: ['Cant.', 'V. Unit.', 'Total'].includes(h) ? 'right' : 'left',
                      whiteSpace: 'nowrap',
                      borderBottom: '1px solid #2a2a2a',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ventas.map((v, i) => (
                  <tr
                    key={i}
                    style={{ borderBottom: '1px solid #1a1a1a', background: i % 2 === 0 ? 'transparent' : '#0d0d0d' }}
                  >
                    <td style={{ padding: '9px 14px', color: '#dc2626', fontWeight: 700 }}>{v.num}</td>
                    <td style={{ padding: '9px 14px', color: '#888', whiteSpace: 'nowrap' }}>{v.hora}</td>
                    <td style={{ padding: '9px 14px', color: '#f5f5f5', maxWidth: 200 }}>{v.producto}</td>
                    <td style={{ padding: '9px 14px', color: '#ccc', maxWidth: 140 }}>{v.cliente || 'Consumidor Final'}</td>
                    <td style={{ padding: '9px 14px', textAlign: 'right', color: '#f5f5f5' }}>{v.cantidad}</td>
                    <td style={{ padding: '9px 14px', textAlign: 'right', color: '#888' }}>{cop(v.precio_unitario)}</td>
                    <td style={{ padding: '9px 14px', textAlign: 'right', color: '#22c55e', fontWeight: 600 }}>{cop(v.total)}</td>
                    <td style={{ padding: '9px 14px', color: '#888' }}>{v.vendedor}</td>
                    <td style={{ padding: '9px 14px' }}>
                      <span style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: v.metodo?.toLowerCase().includes('efect') ? '#052e16' :
                                    v.metodo?.toLowerCase().includes('nequi') || v.metodo?.toLowerCase().includes('billet') ? '#172554' :
                                    v.metodo?.toLowerCase().includes('transf') ? '#1c1917' : '#1e1e1e',
                        color: v.metodo?.toLowerCase().includes('efect') ? '#4ade80' :
                               v.metodo?.toLowerCase().includes('nequi') || v.metodo?.toLowerCase().includes('billet') ? '#93c5fd' :
                               v.metodo?.toLowerCase().includes('transf') ? '#d4d4aa' : '#888',
                        fontSize: 11,
                        fontWeight: 500,
                        whiteSpace: 'nowrap',
                      }}>
                        {v.metodo || '—'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
              {/* Pie con totales */}
              <tfoot>
                <tr style={{ borderTop: '1px solid #2a2a2a', background: '#111' }}>
                  <td colSpan={6} style={{ padding: '10px 14px', color: '#888', fontWeight: 600, fontSize: 12 }}>
                    TOTAL ({totales.count} registros)
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#dc2626', fontWeight: 700, fontSize: 15 }}>
                    {cop(totales.total)}
                  </td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      </Card>
    </div>
  )
}
