import { useState, useRef, useCallback } from 'react'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  StyledInput, Badge, EmptyState, cop, API_BASE,
} from '../components/shared.jsx'

function catIcon(cat) {
  const c = (cat || '').toLowerCase()
  if (c.includes('pint') || c.includes('disol'))                              return '🎨'
  if (c.includes('thinner') || c.includes('varsol'))                         return '🧪'
  if (c.includes('lija') || c.includes('esmeril'))                           return '🪚'
  if (c.includes('tornill') || c.includes('clav') || c.includes('puntilla')) return '🔩'
  if (c.includes('adhesiv') || c.includes('pega') || c.includes('silicon'))  return '🧲'
  if (c.includes('ferret') || c.includes('herram') || c.includes('artículo'))return '🔧'
  if (c.includes('construc') || c.includes('imperme'))                       return '🏗️'
  if (c.includes('electric'))                                                 return '⚡'
  return '📦'
}

// ── Input inline de precio ─────────────────────────────────────────────────
function PrecioInline({ value, prodKey, onSaved, t }) {
  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState(value || 0)
  const [saving,   setSaving]   = useState(false)
  const [flash,    setFlash]    = useState(null) // 'ok' | 'err'
  const ref = useRef()

  const abrir = (e) => { e.stopPropagation(); setVal(value || 0); setEditando(true); setTimeout(() => ref.current?.select(), 30) }

  const guardar = async () => {
    if (val === value) { setEditando(false); return }
    setSaving(true)
    try {
      const r = await fetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/precio`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ precio: val }),
      })
      if (!r.ok) throw new Error(await r.text())
      setFlash('ok')
      onSaved(val)
      setTimeout(() => setFlash(null), 1500)
    } catch {
      setFlash('err')
      setTimeout(() => setFlash(null), 2000)
    }
    setSaving(false)
    setEditando(false)
  }

  const cancelar = () => { setEditando(false); setVal(value || 0) }

  if (editando) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }} onClick={e => e.stopPropagation()}>
      <span style={{ color: t.textMuted, fontSize: 11 }}>$</span>
      <input
        ref={ref} type="number" min="0" value={val}
        onChange={e => setVal(parseInt(e.target.value) || 0)}
        onKeyDown={e => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape') cancelar() }}
        style={{
          width: 90, background: t.id === 'light' ? '#f8fafc' : '#111',
          border: `1px solid ${t.accent}88`, borderRadius: 6,
          color: t.accent, fontSize: 12, fontFamily: 'monospace', fontWeight: 700,
          padding: '3px 7px', outline: 'none', MozAppearance: 'textfield', appearance: 'textfield',
        }}
      />
      <button onClick={guardar} disabled={saving} style={{ background: t.accent, border: 'none', borderRadius: 5, color: '#fff', width: 22, height: 22, cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{saving ? '…' : '✓'}</button>
      <button onClick={cancelar} style={{ background: 'transparent', border: `1px solid ${t.border}`, borderRadius: 5, color: t.textMuted, width: 22, height: 22, cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
    </div>
  )

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }} onClick={abrir} title="Click para editar precio">
      {value ? (
        <span style={{ color: flash === 'ok' ? t.green : flash === 'err' ? t.accent : t.green, fontWeight: 600, transition: 'color .3s' }}>{cop(value)}</span>
      ) : (
        <Badge color={t.yellow}>Sin precio</Badge>
      )}
      <span style={{ fontSize: 10, color: t.textMuted, opacity: 0.5 }}>✏️</span>
    </div>
  )
}

// ── Editor de fracciones inline ───────────────────────────────────────────────
const FRACS_ORDEN = ['3/4','1/2','1/4','1/8','1/10','1/16']

function FraccionesEditor({ fracciones, prodKey, precioUnidad, onSaved, t }) {
  const [editando, setEditando] = useState(false)
  const [vals,     setVals]     = useState({})
  const [saving,   setSaving]   = useState(false)
  const [flash,    setFlash]    = useState(null)

  const abrirEditor = (e) => {
    e.stopPropagation()
    const init = {}
    FRACS_ORDEN.forEach(f => {
      const v = fracciones?.[f]
      init[f] = v ? (typeof v === 'object' ? v.precio : v) : ''
    })
    setVals(init)
    setEditando(true)
  }

  const guardar = async (e) => {
    e.stopPropagation()
    setSaving(true)
    const fracs = {}
    FRACS_ORDEN.forEach(f => { if (vals[f] > 0) fracs[f] = parseInt(vals[f]) })
    try {
      const r = await fetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/fracciones`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fracciones: fracs }),
      })
      if (!r.ok) throw new Error(await r.text())
      setFlash('ok')
      onSaved(fracs)
      setTimeout(() => { setFlash(null); setEditando(false) }, 800)
    } catch {
      setFlash('err')
      setTimeout(() => setFlash(null), 2000)
    }
    setSaving(false)
  }

  const fracsList = fracciones ? Object.entries(fracciones) : []
  const hasFracs = fracsList.length > 0

  if (!editando) return (
    <div>
      {hasFracs && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
          {FRACS_ORDEN.filter(f => fracciones[f]).map(f => {
            const precio = typeof fracciones[f] === 'object' ? fracciones[f].precio : fracciones[f]
            return (
              <div key={f} style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, padding: '5px 10px' }}>
                <div style={{ fontSize: 9, color: t.textMuted, marginBottom: 1 }}>{f}</div>
                <div style={{ color: t.accent, fontWeight: 600, fontSize: 11 }}>{cop(precio)}</div>
              </div>
            )
          })}
        </div>
      )}
      <button onClick={abrirEditor} style={{
        fontSize: 10, color: t.accent, background: t.accentSub, border: `1px solid ${t.accent}44`,
        borderRadius: 6, padding: '4px 10px', cursor: 'pointer', fontFamily: 'inherit',
      }}>
        ✏️ {hasFracs ? 'Editar fracciones' : 'Agregar fracciones'}
      </button>
    </div>
  )

  return (
    <div onClick={e => e.stopPropagation()}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 10 }}>
        {FRACS_ORDEN.map(f => (
          <div key={f}>
            <div style={{ fontSize: 9, color: t.textMuted, marginBottom: 3 }}>{f}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <span style={{ fontSize: 10, color: t.textMuted }}>$</span>
              <input
                type="number" min="0" value={vals[f] || ''}
                onChange={e => setVals(v => ({ ...v, [f]: parseInt(e.target.value) || 0 }))}
                placeholder="—"
                style={{
                  width: '100%', background: t.id === 'light' ? '#f8fafc' : '#111',
                  border: `1px solid ${vals[f] > 0 ? t.accent + '88' : t.border}`, borderRadius: 6,
                  color: t.text, fontSize: 11, fontFamily: 'monospace',
                  padding: '4px 6px', outline: 'none',
                  MozAppearance: 'textfield', appearance: 'textfield',
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        <button onClick={guardar} disabled={saving} style={{
          background: flash === 'ok' ? t.green : t.accent, border: 'none', borderRadius: 6,
          color: '#fff', padding: '5px 14px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11, fontWeight: 600,
        }}>
          {saving ? 'Guardando…' : flash === 'ok' ? '✓ Guardado' : 'Guardar fracciones'}
        </button>
        <button onClick={e => { e.stopPropagation(); setEditando(false) }} style={{
          background: 'transparent', border: `1px solid ${t.border}`, borderRadius: 6,
          color: t.textMuted, padding: '5px 12px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
        }}>Cancelar</button>
      </div>
      {flash === 'err' && <div style={{ fontSize: 10, color: t.accent, marginTop: 5 }}>Error al guardar</div>}
    </div>
  )
}

// ── Fila de producto ───────────────────────────────────────────────────────────
function ProductoRow({ p: pInit, expanded, onToggle, t }) {
  const [p, setP] = useState(pInit)
  const hasFracs   = p.fracciones && Object.keys(p.fracciones).length > 0
  const expandible = hasFracs || p.mayorista

  const onPrecioSaved = (nuevoPrecio) => setP(prev => ({ ...prev, precio: nuevoPrecio }))
  const onFracsSaved  = (nuevasFracs) => setP(prev => ({ ...prev, fracciones: nuevasFracs }))

  return (
    <>
      <tr
        style={{ borderBottom: `1px solid ${t.border}`, cursor: expandible ? 'pointer' : 'default' }}
        onClick={() => expandible && onToggle()}
        onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <td style={{ padding: '9px 14px', color: t.textMuted, fontFamily: 'monospace', fontSize: 10 }}>
          {p.codigo || '—'}
        </td>
        <td style={{ padding: '9px 14px', color: t.text }}>
          {p.nombre}
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 3 }}>
            {hasFracs && (
              <span style={{ background: t.accentSub, color: t.accent, border: `1px solid ${t.accent}33`, padding: '1px 7px', borderRadius: 99, fontSize: 9 }}>fracciones</span>
            )}
            {p.mayorista && (
              <span style={{ background: t.id==='light'?'#eff6ff':'#172554', color: t.blue, border: `1px solid ${t.blue}33`, padding: '1px 7px', borderRadius: 99, fontSize: 9 }}>mayorista ×{p.mayorista.umbral}</span>
            )}
          </div>
        </td>
        <td style={{ padding: '9px 14px' }} onClick={e => e.stopPropagation()}>
          <PrecioInline value={p.precio} prodKey={p.key} onSaved={onPrecioSaved} t={t} />
        </td>
        <td style={{ padding: '9px 14px', textAlign: 'center' }}>
          {p.stock !== null && p.stock !== undefined
            ? <span style={{ color: Number(p.stock) > 0 ? t.green : '#f87171', fontWeight: 600 }}>{p.stock}</span>
            : <span style={{ color: t.textMuted, fontSize: 10 }}>—</span>}
        </td>
        <td style={{ padding: '9px 14px', textAlign: 'center', color: t.textMuted, fontSize: 11 }}>
          {expandible ? (expanded ? '▲' : '▼') : ''}
        </td>
      </tr>
      {expanded && (
        <tr style={{ background: t.tableAlt }}>
          <td colSpan={5} style={{ padding: '10px 24px 14px' }}>
            <FraccionesEditor
              fracciones={p.fracciones} prodKey={p.key}
              precioUnidad={p.precio} onSaved={onFracsSaved} t={t}
            />
            {p.mayorista && (
              <div style={{ marginTop: hasFracs ? 12 : 0 }}>
                <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 6 }}>Precio mayorista</div>
                <div style={{ background: t.card, border: `1px solid ${t.blue}33`, borderRadius: 7, padding: '6px 12px', display: 'inline-block' }}>
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

// ── Tab principal ──────────────────────────────────────────────────────────────
export default function TabCatalogo({ refreshKey }) {
  const t = useTheme()
  const [busqueda,    setBusqueda]    = useState('')
  const [abierta,     setAbierta]     = useState(null)
  const [expandedP,   setExpandedP]   = useState({})
  const [queryActivo, setQueryActivo] = useState('')

  const url = queryActivo
    ? `/catalogo/nav?q=${encodeURIComponent(queryActivo)}`
    : '/catalogo/nav'

  const { data, loading, error } = useFetch(url, [queryActivo, refreshKey])

  const categorias  = data?.categorias || {}
  const total       = data?.total || 0
  const catEntries  = Object.entries(categorias)

  const handleBuscar = (val) => {
    setBusqueda(val)
    clearTimeout(window._catTimer)
    window._catTimer = setTimeout(() => setQueryActivo(val), 300)
  }

  const toggleProd = useCallback((key) => {
    setExpandedP(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ fontSize: 11, color: t.textMuted }}>
          📦 <strong style={{ color: t.text }}>{total}</strong> productos ·{' '}
          <strong style={{ color: t.text }}>{catEntries.length}</strong> categorías
          <span style={{ marginLeft: 10, color: t.textMuted, opacity: .7 }}>· Click en el precio para editarlo ✏️</span>
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
              const conFracs  = prods.filter(p => p.fracciones && Object.keys(p.fracciones).length > 0).length
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
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 18 }}>{catIcon(label)}</span>
                      <span style={{ fontWeight: 700, fontSize: 13, color: t.text }}>{label}</span>
                      <span style={{ fontSize: 10, color: t.textMuted }}>{prods.length} productos</span>
                      {conFracs > 0 && <span style={{ fontSize: 10, color: t.accent, background: t.accentSub, padding: '1px 7px', borderRadius: 99 }}>{conFracs} con fracciones</span>}
                      {sinPrecio > 0 && <span style={{ fontSize: 10, color: t.yellow }}>⚠️ {sinPrecio} sin precio</span>}
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
                                textAlign: i >= 2 && i <= 3 ? 'center' : 'left',
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
