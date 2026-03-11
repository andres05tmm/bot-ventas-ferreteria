import { useState, useMemo } from 'react'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, StyledInput, EmptyState, Th, cop, num,
} from '../components/shared.jsx'

// Colores de badge por método de pago
function metodoBadge(metodo, t) {
  const raw = (metodo || '').toLowerCase()
  if (raw.includes('efect'))  return { bg: '#052e16', color: '#4ade80', border: '#4ade8033' }
  if (raw.includes('nequi'))  return { bg: '#172554', color: '#93c5fd', border: '#93c5fd33' }
  if (raw.includes('billet')) return { bg: '#172554', color: '#818cf8', border: '#818cf833' }
  if (raw.includes('transf')) return { bg: '#1c1917', color: '#d4d4aa', border: '#d4d4aa33' }
  if (raw.includes('tarjet')) return { bg: '#1e1b4b', color: '#a5b4fc', border: '#a5b4fc33' }
  return { bg: t.card, color: t.textMuted, border: t.border }
}

// Exportar tabla como CSV
function exportCSV(ventas) {
  const headers = ['#', 'Fecha', 'Hora', 'Producto', 'Cliente', 'Cantidad', 'Precio Unit.', 'Total', 'Vendedor', 'Método']
  const rows = ventas.map(v => [
    v.num, v.fecha, v.hora, v.producto, v.cliente || 'Consumidor Final',
    v.cantidad, v.precio_unitario, v.total, v.vendedor, v.metodo || '',
  ])
  const csv = [headers, ...rows].map(r => r.map(c => `"${c}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url
  a.download = `ventas_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function TabHistorial({ refreshKey }) {
  const t = useTheme()
  const { data, loading, error } = useFetch('/ventas/hoy', [refreshKey])
  const [busqueda, setBusqueda]  = useState('')
  const [filtro,   setFiltro]    = useState('todos')

  const todasVentas = useMemo(() => (data?.ventas || []).map(v => ({
    ...v,
    estado: (v.metodo && v.metodo.trim() && v.metodo !== '—') ? 'pagado' : 'pendiente',
  })), [data])

  const ventas = useMemo(() => {
    let res = filtro === 'todos' ? todasVentas : todasVentas.filter(v => v.estado === filtro)
    if (busqueda) {
      const q = busqueda.toLowerCase()
      res = res.filter(v =>
        String(v.producto).toLowerCase().includes(q) ||
        String(v.cliente  ).toLowerCase().includes(q) ||
        String(v.vendedor ).toLowerCase().includes(q) ||
        String(v.num      ).includes(q)
      )
    }
    return res
  }, [todasVentas, filtro, busqueda])

  const total     = ventas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const totalTodo = todasVentas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const pagados   = todasVentas.filter(v => v.estado === 'pagado').length
  const pendientes = todasVentas.filter(v => v.estado === 'pendiente').length

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* KPIs rápidos */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {[
          { label: 'Total hoy',      value: cop(totalTodo),      color: t.accent },
          { label: 'Registros',      value: todasVentas.length,  color: t.text },
          { label: '✅ Pagados',     value: pagados,             color: t.green },
          { label: '⏳ Sin método',  value: pendientes,          color: t.yellow },
        ].map(item => (
          <div key={item.label} style={{
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 8, padding: '10px 16px', flex: 1, minWidth: 120,
          }}>
            <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 5 }}>{item.label}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: item.color }}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* Filtros + búsqueda + export */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {['todos', 'pagado', 'pendiente'].map(f => (
            <PeriodBtn key={f} active={filtro === f} onClick={() => setFiltro(f)}>
              {f === 'todos' ? 'Todos' : f === 'pagado' ? '✅ Pagados' : '⏳ Pendientes'}
            </PeriodBtn>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <StyledInput
            value={busqueda}
            onChange={e => setBusqueda(e.target.value)}
            placeholder="Buscar..."
            style={{ width: 200 }}
          />
          {todasVentas.length > 0 && (
            <button
              onClick={() => exportCSV(todasVentas)}
              style={{
                background: t.accentSub,
                border: `1px solid ${t.accent}55`,
                color: t.accent,
                borderRadius: 7,
                padding: '7px 13px',
                fontSize: 11,
                fontWeight: 600,
                fontFamily: 'inherit',
                transition: 'all .15s',
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = t.accent; e.currentTarget.style.color = '#fff' }}
              onMouseLeave={e => { e.currentTarget.style.background = t.accentSub; e.currentTarget.style.color = t.accent }}
            >
              ↓ Exportar CSV
            </button>
          )}
        </div>
      </div>

      {/* Tabla */}
      <Card style={{ padding: 0 }}>
        <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
          <SectionTitle>
            Ventas del Día — {new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </SectionTitle>
        </div>
        <div style={{ overflowX: 'auto' }}>
          {ventas.length === 0 ? (
            <EmptyState msg={busqueda ? 'Sin resultados para la búsqueda.' : 'No hay ventas registradas hoy.'} />
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: t.tableAlt }}>
                  <Th>#</Th>
                  <Th>Hora</Th>
                  <Th>Producto</Th>
                  <Th>Cliente</Th>
                  <Th center>Cant.</Th>
                  <Th right>V. Unit.</Th>
                  <Th right>Total</Th>
                  <Th>Vendedor</Th>
                  <Th center>Método</Th>
                  <Th center>Estado</Th>
                </tr>
              </thead>
              <tbody>
                {ventas.map((v, i) => {
                  const badge = metodoBadge(v.metodo, t)
                  return (
                    <tr key={i}
                      style={{ borderBottom: `1px solid ${t.border}` }}
                      onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '9px 14px', color: t.accent, fontWeight: 700 }}>{v.num}</td>
                      <td style={{ padding: '9px 14px', color: t.textMuted, fontStyle: 'italic', whiteSpace: 'nowrap' }}>{v.hora}</td>
                      <td style={{ padding: '9px 14px', color: t.text, maxWidth: 200 }}>{v.producto}</td>
                      <td style={{ padding: '9px 14px', color: t.textSub, fontSize: 11 }}>{v.cliente || 'Consumidor Final'}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'center', color: t.textSub }}>{v.cantidad}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textMuted }}>{cop(v.precio_unitario)}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: t.green, fontWeight: 600 }}>{cop(v.total)}</td>
                      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{v.vendedor || '—'}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-block',
                          padding: '2px 9px',
                          borderRadius: 99,
                          background: badge.bg,
                          color: badge.color,
                          border: `1px solid ${badge.border}`,
                          fontSize: 10,
                          fontWeight: 500,
                          whiteSpace: 'nowrap',
                        }}>
                          {v.metodo || '—'}
                        </span>
                      </td>
                      <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-block', padding: '2px 9px', borderRadius: 99, fontSize: 10, fontWeight: 600,
                          background: v.estado === 'pagado' ? '#14532d22' : '#78350f22',
                          color:      v.estado === 'pagado' ? '#4ade80'   : '#fbbf24',
                          border: `1px solid ${v.estado === 'pagado' ? '#4ade8033' : '#fbbf2433'}`,
                        }}>
                          {v.estado}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr style={{ borderTop: `1px solid ${t.border}`, background: t.tableFoot }}>
                  <td colSpan={6} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>
                    SUBTOTAL ({ventas.length} registros)
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: t.accent, fontWeight: 700, fontSize: 14 }}>{cop(total)}</td>
                  <td colSpan={3} />
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      </Card>
    </div>
  )
}
