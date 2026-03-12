import { useState, useMemo } from 'react'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  StyledInput, Badge, EmptyState, cop,
} from '../components/shared.jsx'

function catIcon(cat) {
  const c = (cat || '').toLowerCase()
  if (c.includes('pint') || c.includes('disol'))                                     return '🎨'
  if (c.includes('thinner') || c.includes('varsol'))                                 return '🧪'
  if (c.includes('lija') || c.includes('esmeril'))                                   return '🪚'
  if (c.includes('tornill') || c.includes('clav') || c.includes('puntilla'))        return '🔩'
  if (c.includes('adhesiv') || c.includes('pega') || c.includes('silicon'))         return '🧲'
  if (c.includes('ferret') || c.includes('herram') || c.includes('artículo'))       return '🔧'
  if (c.includes('construc') || c.includes('imperme'))                              return '🏗️'
  if (c.includes('electric'))                                                        return '⚡'
  return '📦'
}

function PrecioBadge({ fracs, mayorista, t }) {
  if (!fracs && !mayorista) return null
  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
      {fracs && Object.keys(fracs).length > 0 && (
        <span style={{ background: t.accentSub, color: t.accent, border: `1px solid ${t.accent}33`, padding: '1px 7px', borderRadius: 99, fontSize: 9 }}>
          fracciones
        </span>
      )}
      {mayorista && (
        <span style={{ background: t.id === 'light' ? '#eff6ff' : '#172554', color: t.blue, border: `1px solid ${t.blue}33`, padding: '1px 7px', borderRadius: 99, fontSize: 9 }}>
          mayorista ×{mayorista.umbral}
        </span>
      )}
    </div>
  )
}

function ProductoRow({ p, expanded, onToggle, t }) {
  const hasFracs = p.fracciones && Object.keys(p.fracciones).length > 0
  return (
    <>
      <tr
        style={{ borderBottom: `1px solid ${t.border}`, cursor: hasFracs || p.mayorista ? 'pointer' : 'default' }}
        onClick={() => (hasFracs || p.mayorista) && onToggle()}
        onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <td style={{ padding: '9px 14px', color: t.textMuted, fontFamily: 'monospace', fontSize: 10 }}>
          {p.codigo || '—'}
        </td>
        <td style={{ padding: '9px 14px', color: t.text }}>
          {p.nombre}
          <PrecioBadge fracs={p.fracciones} mayorista={p.mayorista} t={t} />
        </td>
        <td style={{ padding: '9px 14px', textAlign: 'right' }}>
          {p.precio ? (
            <span style={{ color: t.green, fontWeight: 600 }}>{cop(p.precio)}</span>
          ) : (
            <Badge color={t.yellow}>Sin precio</Badge>
          )}
        </td>
        <td style={{ padding: '9px 14px', textAlign: 'center' }}>
          {p.stock !== null && p.stock !== undefined
            ? <span style={{ color: Number(p.stock) > 0 ? t.green : '#f87171', fontWeight: 600 }}>{p.stock}</span>
            : <span style={{ color: t.textMuted, fontSize: 10 }}>—</span>
          }
        </td>
        <td style={{ padding: '9px 14px', textAlign: 'center', color: t.textMuted, fontSize: 11 }}>
          {(hasFracs || p.mayorista) ? (expanded ? '▲' : '▼') : ''}
        </td>
      </tr>
      {expanded && (
        <tr style={{ background: t.tableAlt }}>
          <td colSpan={5} style={{ padding: '8px 24px 12px' }}>
            {hasFracs && (
              <div style={{ marginBottom: p.mayorista ? 8 : 0 }}>
                <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 6 }}>Precios por fracción</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {Object.entries(p.fracciones).map(([frac, precio]) => (
                    <div key={frac} style={{
                      background: t.card, border: `1px solid ${t.border}`,
                      borderRadius: 7, padding: '6px 12px',
                    }}>
                      <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 2 }}>{frac}</div>
                      <div style={{ color: t.accent, fontWeight: 600, fontSize: 12 }}>{cop(precio)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {p.mayorista && (
              <div>
                <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 6 }}>Precio mayorista</div>
                <div style={{
                  background: t.card, border: `1px solid ${t.blue}33`,
                  borderRadius: 7, padding: '6px 12px', display: 'inline-block',
                }}>
                  <span style={{ color: t.textMuted, fontSize: 10 }}>Desde {p.mayorista.umbral} uds: </span>
                  <span style={{ color: t.blue, fontWeight: 600, fontSize: 12 }}>{cop(p.mayorista.precio)} c/u</span>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function TabCatalogo({ refreshKey }) {
  const t = useTheme()
  const [busqueda,   setBusqueda]   = useState('')
  const [abierta,    setAbierta]    = useState(null)
  const [expandedP,  setExpandedP]  = useState({})

  // Búsqueda con debounce simple
  const [queryActivo, setQueryActivo] = useState('')
  const url = queryActivo
    ? `/catalogo/nav?q=${encodeURIComponent(queryActivo)}`
    : '/catalogo/nav'

  const { data, loading, error } = useFetch(url, [queryActivo, refreshKey])

  const categorias = data?.categorias || {}
  const total      = data?.total || 0
  const catEntries = Object.entries(categorias)

  const handleBuscar = (val) => {
    setBusqueda(val)
    clearTimeout(window._catTimer)
    window._catTimer = setTimeout(() => setQueryActivo(val), 300)
  }

  const toggleProd = (key) => {
    setExpandedP(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Buscador + stats */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ fontSize: 11, color: t.textMuted }}>
          📦 <strong style={{ color: t.text }}>{total}</strong> productos ·{' '}
          <strong style={{ color: t.text }}>{catEntries.length}</strong> categorías
        </div>
        <StyledInput
          value={busqueda}
          onChange={e => handleBuscar(e.target.value)}
          placeholder="🔍  Buscar producto o código..."
          style={{ width: 280 }}
        />
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {!loading && !error && (
        <>
          {catEntries.length === 0 ? (
            <Card><EmptyState msg={busqueda ? 'Sin resultados para la búsqueda.' : 'Sin productos.'} /></Card>
          ) : (
            catEntries.map(([cat, prods]) => {
              const label    = cat.replace(/^\d+\s*/, '')
              const expandida = busqueda ? true : abierta === cat
              const conFracs = prods.filter(p => p.fracciones && Object.keys(p.fracciones).length > 0).length
              const sinPrecio = prods.filter(p => !p.precio).length

              return (
                <div key={cat} style={{
                  background: t.card,
                  border: `1px solid ${expandida ? t.accent + '44' : t.border}`,
                  borderRadius: 10, overflow: 'hidden', transition: 'border-color .2s',
                }}>
                  {/* Header categoría */}
                  <div
                    onClick={() => !busqueda && setAbierta(p => p === cat ? null : cat)}
                    style={{
                      padding: '13px 16px', display: 'flex', alignItems: 'center',
                      justifyContent: 'space-between', cursor: busqueda ? 'default' : 'pointer', userSelect: 'none',
                    }}
                    onMouseEnter={e => { if (!busqueda) e.currentTarget.style.background = t.cardHover }}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ fontSize: 18 }}>{catIcon(label)}</span>
                      <span style={{ fontWeight: 700, fontSize: 13, color: t.text }}>{label}</span>
                      <span style={{ fontSize: 10, color: t.textMuted }}>{prods.length} productos</span>
                      {conFracs > 0 && (
                        <span style={{ fontSize: 10, color: t.accent, background: t.accentSub, padding: '1px 7px', borderRadius: 99 }}>
                          {conFracs} con fracciones
                        </span>
                      )}
                      {sinPrecio > 0 && (
                        <span style={{ fontSize: 10, color: t.yellow }}>⚠️ {sinPrecio} sin precio</span>
                      )}
                    </div>
                    {!busqueda && (
                      <span style={{ color: t.textMuted, fontSize: 11, transition: 'transform .2s', transform: expandida ? 'rotate(90deg)' : 'rotate(0deg)', display: 'inline-block' }}>▶</span>
                    )}
                  </div>

                  {/* Tabla */}
                  {expandida && (
                    <div style={{ borderTop: `1px solid ${t.border}`, overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ background: t.tableAlt }}>
                            {['Código', 'Nombre', 'Precio', 'Stock', ''].map((h, i) => (
                              <th key={i} style={{
                                padding: '8px 14px',
                                textAlign: i === 2 || i === 3 ? 'center' : 'left',
                                fontSize: 9, color: t.textMuted, textTransform: 'uppercase',
                                letterSpacing: '.08em', fontWeight: 500,
                                borderBottom: `1px solid ${t.border}`,
                              }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {prods.map(p => (
                            <ProductoRow
                              key={p.key} p={p} t={t}
                              expanded={!!expandedP[p.key]}
                              onToggle={() => toggleProd(p.key)}
                            />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </>
      )}
    </div>
  )
}
