import { useState, useMemo } from 'react'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  Badge, StyledInput, EmptyState, Th, cop,
} from '../components/shared.jsx'

function catIcon(cat) {
  const c = (cat || '').toLowerCase()
  if (c.includes('pint') || c.includes('vinilo') || c.includes('color'))              return '🎨'
  if (c.includes('thinner') || c.includes('varsol') || c.includes('solvente'))       return '🧪'
  if (c.includes('lija') || c.includes('esmeril') || c.includes('abras'))            return '🪚'
  if (c.includes('tornill') || c.includes('clav') || c.includes('perno'))            return '🔩'
  if (c.includes('adhesiv') || c.includes('pega') || c.includes('silicon'))          return '🧲'
  if (c.includes('ferret') || c.includes('herram') || c.includes('brocha') || c.includes('rodillo')) return '🔧'
  if (c.includes('granel'))                                                           return '⚖️'
  return '📦'
}

export default function TabInventario({ refreshKey }) {
  const t = useTheme()
  const { data, loading, error } = useFetch('/productos',      [refreshKey])
  const { data: alertasData }    = useFetch('/inventario/bajo', [refreshKey])

  const [busqueda,   setBusqueda]   = useState('')
  const [soloBajos,  setSoloBajos]  = useState(false)
  const [abierta,    setAbierta]    = useState(null)

  const alertaMap = useMemo(() => {
    const m = {}
    ;(alertasData?.alertas || []).forEach(a => { m[a.key] = a })
    return m
  }, [alertasData])

  const categorias = useMemo(() => {
    const grupos = {}
    ;(data?.productos || []).forEach(p => {
      const cat = p.categoria || 'Sin categoría'
      if (!grupos[cat]) grupos[cat] = []
      grupos[cat].push(p)
    })
    return Object.entries(grupos).sort(([a], [b]) => (parseInt(a) || 999) - (parseInt(b) || 999))
  }, [data])

  const filtrar = prods => {
    let res = prods
    if (busqueda) {
      const q = busqueda.toLowerCase()
      res = res.filter(p => p.nombre.toLowerCase().includes(q) || (p.codigo || '').toLowerCase().includes(q))
    }
    if (soloBajos) res = res.filter(p => alertaMap[p.key])
    return res
  }

  const totalAlertas = alertasData?.total || 0

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  const totalProductos = data?.total || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Stats + buscador */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, padding: '8px 14px', fontSize: 11, color: t.textSub }}>
            📦 <strong style={{ color: t.text }}>{totalProductos}</strong> productos
          </div>
          {totalAlertas > 0 && (
            <button
              onClick={() => setSoloBajos(s => !s)}
              style={{
                background: soloBajos ? t.accent : t.accentSub,
                border: `1px solid ${t.accent}55`,
                color: soloBajos ? '#fff' : t.accent,
                borderRadius: 8,
                padding: '8px 14px',
                fontSize: 11,
                fontWeight: 600,
                transition: 'all .15s',
                fontFamily: 'inherit',
              }}
            >
              ⚠️ {totalAlertas} alertas {soloBajos ? '— Ver todos' : '— Ver solo alertas'}
            </button>
          )}
        </div>
        <StyledInput
          value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          placeholder="Buscar producto o código..."
          style={{ width: 240 }}
        />
      </div>

      {/* Categorías */}
      {categorias.map(([cat, prods]) => {
        const label    = cat.replace(/^\d+\s*/, '')
        const filtrados = filtrar(prods)
        if ((busqueda || soloBajos) && filtrados.length === 0) return null
        const alertasCat = prods.filter(p => alertaMap[p.key]).length
        const expandida  = busqueda || soloBajos ? true : abierta === cat

        return (
          <div key={cat} style={{
            background: t.card,
            border: `1px solid ${expandida ? t.accent + '44' : t.border}`,
            borderRadius: 10,
            overflow: 'hidden',
            transition: 'border-color .2s',
          }}>
            {/* Header */}
            <div
              onClick={() => !(busqueda || soloBajos) && setAbierta(p => p === cat ? null : cat)}
              style={{
                padding: '12px 16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: (busqueda || soloBajos) ? 'default' : 'pointer',
                userSelect: 'none',
              }}
              onMouseEnter={e => { if (!(busqueda || soloBajos)) e.currentTarget.style.background = t.cardHover }}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 17 }}>{catIcon(label)}</span>
                <span style={{ fontWeight: 600, fontSize: 13, color: t.text }}>{label}</span>
                <span style={{ fontSize: 10, color: t.textMuted }}>{prods.length} productos</span>
                {alertasCat > 0 && (
                  <span style={{ fontSize: 10, color: t.accent }}>⚠️ {alertasCat}</span>
                )}
              </div>
              {!(busqueda || soloBajos) && (
                <span style={{
                  color: t.textMuted, fontSize: 11,
                  transition: 'transform .2s',
                  transform: expandida ? 'rotate(90deg)' : 'rotate(0deg)',
                  display: 'inline-block',
                }}>▶</span>
              )}
            </div>

            {/* Tabla */}
            {expandida && (
              <div style={{ borderTop: `1px solid ${t.border}`, overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: t.tableAlt }}>
                      <Th>Producto</Th>
                      <Th>Código</Th>
                      <Th center>Precio</Th>
                      <Th center>Estado</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtrados.map(p => {
                      const alerta = alertaMap[p.key]
                      const esAlerta = !!alerta
                      return (
                        <tr key={p.key}
                          style={{
                            borderTop: `1px solid ${t.border}`,
                            background: esAlerta ? (t.id === 'light' ? '#fef2f2' : '#1a0808') : 'transparent',
                          }}
                          onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                          onMouseLeave={e => e.currentTarget.style.background = esAlerta ? (t.id === 'light' ? '#fef2f2' : '#1a0808') : 'transparent'}
                        >
                          <td style={{ padding: '9px 14px', color: t.text }}>
                            {esAlerta && (
                              <span style={{ width: 6, height: 6, background: t.accent, borderRadius: '50%', display: 'inline-block', marginRight: 7, animation: 'pulse 1.5s infinite' }} />
                            )}
                            {p.nombre}
                          </td>
                          <td style={{ padding: '9px 14px', color: t.textMuted, fontFamily: 'monospace', fontSize: 11 }}>
                            {p.codigo || '—'}
                          </td>
                          <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                            {p.precio ? (
                              <span style={{ color: t.green, fontWeight: 600 }}>{cop(p.precio)}</span>
                            ) : (
                              <Badge color={t.yellow}>Sin precio</Badge>
                            )}
                          </td>
                          <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                            {esAlerta ? (
                              <Badge color={t.accent}>
                                {alerta.motivo === 'sin_precio' ? 'Sin precio' : 'Stock 0'}
                              </Badge>
                            ) : (
                              <Badge color={t.green}>OK</Badge>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}

      {categorias.length === 0 && <EmptyState msg="No hay productos cargados." />}
    </div>
  )
}
