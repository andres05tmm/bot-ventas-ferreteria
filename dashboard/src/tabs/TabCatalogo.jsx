import { useState, useRef, useCallback } from 'react'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  StyledInput, Badge, EmptyState, cop, API_BASE,
} from '../components/shared.jsx'

// ── Icono por categoría ───────────────────────────────────────────────────────
function catIcon(cat) {
  const c = (cat || '').toLowerCase()
  if (c.includes('pint') || c.includes('disol'))                               return '🎨'
  if (c.includes('thinner') || c.includes('varsol'))                          return '🧪'
  if (c.includes('lija') || c.includes('esmeril'))                            return '🪚'
  if (c.includes('tornill') || c.includes('clav') || c.includes('puntilla'))  return '🔩'
  if (c.includes('adhesiv') || c.includes('pega') || c.includes('silicon'))   return '🧲'
  if (c.includes('ferret') || c.includes('herram') || c.includes('artículo')) return '🔧'
  if (c.includes('construc') || c.includes('imperme'))                        return '🏗️'
  if (c.includes('electric'))                                                  return '⚡'
  return '📦'
}

// ── Subcategorías (igual que TabVentasRapidas) ────────────────────────────────
const nl = s => (s || '').toLowerCase()

const SUBCATS = {
  '1 artículos de ferreteria': [
    { key: 'ferr_brochas',    icono: '🖌️', label: 'Brochas / Rodillos', fn: p => nl(p.nombre).includes('brocha') || nl(p.nombre).includes('rodillo') },
    { key: 'ferr_lijas',      icono: '📏', label: 'Lijas',               fn: p => nl(p.nombre).includes('lija') || nl(p.nombre).includes('esmeril') },
    { key: 'ferr_cintas',     icono: '🔗', label: 'Cintas',              fn: p => nl(p.nombre).includes('cinta') || nl(p.nombre).includes('pele') || nl(p.nombre).includes('enmascarar') },
    { key: 'ferr_cerraduras', icono: '🔒', label: 'Cerraduras',          fn: p => ['cerradura','candado','cerrojo','falleba'].some(k => nl(p.nombre).includes(k)) },
    { key: 'ferr_brocas',     icono: '🪚', label: 'Brocas / Discos',     fn: p => nl(p.nombre).includes('broca') || nl(p.nombre).includes('disco') },
    { key: 'ferr_herr',       icono: '🔧', label: 'Herramientas',        fn: p => ['martillo','metro','destornillador','exacto','espatula','tijera','formon','grapadora','machete','taladro','llave','pulidora'].some(k => nl(p.nombre).includes(k)) },
    { key: 'ferr_varios',     icono: '📦', label: 'Varios',              fn: () => true },
  ],
  '2 pinturas y disolventes': [
    { key: 'pint_vinilo',   icono: '🖌️', label: 'Vinilo / Cuñetes',    fn: p => nl(p.nombre).includes('vinilo') || /cu[ñn]ete/i.test(p.nombre) },
    { key: 'pint_esmalte',  icono: '🎨', label: 'Esmalte / Anticorr.', fn: p => nl(p.nombre).includes('esmalte') || nl(p.nombre).includes('anticorrosivo') },
    { key: 'pint_laca',     icono: '🪄', label: 'Laca',                fn: p => nl(p.nombre).includes('laca') },
    { key: 'pint_thinner',  icono: '🧪', label: 'Thinner / Varsol',    fn: p => nl(p.nombre).includes('thinner') || nl(p.nombre).includes('varsol') || nl(p.nombre).includes('tiner') },
    { key: 'pint_poli',     icono: '💧', label: 'Poliuretano',         fn: p => nl(p.nombre).includes('poliuretano') || nl(p.nombre).includes('poliamida') },
    { key: 'pint_aerosol',  icono: '🎭', label: 'Aerosol',             fn: p => nl(p.nombre).includes('aerosol') },
    { key: 'pint_sellador', icono: '🧴', label: 'Sellador / Masilla',  fn: p => nl(p.nombre).includes('sellador') || nl(p.nombre).includes('masilla') },
    { key: 'pint_otros',    icono: '🎨', label: 'Otros',               fn: () => true },
  ],
  '3 tornilleria': [
    { key: 'torn_dry6',      icono: '⚙️', label: 'Drywall ×6',          fn: p => nl(p.nombre).includes('drywall') && /6x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_dry8',      icono: '⚙️', label: 'Drywall ×8',          fn: p => nl(p.nombre).includes('drywall') && /8x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_dry10',     icono: '⚙️', label: 'Drywall ×10',         fn: p => nl(p.nombre).includes('drywall') && /10x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_hex',       icono: '🔩', label: 'Hex Galvanizado',      fn: p => nl(p.nombre).includes('hex') },
    { key: 'torn_puntillas', icono: '📌', label: 'Puntillas',            fn: p => nl(p.nombre).includes('puntilla') },
    { key: 'torn_tirafondo', icono: '🔩', label: 'Tira Fondo',           fn: p => nl(p.nombre).includes('tira fondo') },
    { key: 'torn_arandelas', icono: '⚙️', label: 'Arandelas / Chazos',  fn: p => nl(p.nombre).includes('arandela') || nl(p.nombre).includes('chazo') },
    { key: 'torn_otros',     icono: '📦', label: 'Otros',                fn: () => true },
  ],
  '4 impermeabilizantes y materiales de construcción': [
    { key: 'imp_imp',    icono: '💧', label: 'Impermeabilizantes', fn: p => nl(p.nombre).includes('imperme') || nl(p.nombre).includes('impermeable') },
    { key: 'imp_cemento',icono: '🏗️', label: 'Cemento / Mortero', fn: p => nl(p.nombre).includes('cemento') || nl(p.nombre).includes('mortero') || nl(p.nombre).includes('pega') },
    { key: 'imp_otros',  icono: '📦', label: 'Otros',              fn: () => true },
  ],
  '5 materiales electricos': [
    { key: 'elec_cable',    icono: '🔌', label: 'Cables',         fn: p => nl(p.nombre).includes('cable') || nl(p.nombre).includes('alambre') },
    { key: 'elec_interrup', icono: '💡', label: 'Interruptores',  fn: p => nl(p.nombre).includes('interruptor') || nl(p.nombre).includes('toma') || nl(p.nombre).includes('toma corriente') },
    { key: 'elec_otros',    icono: '⚡', label: 'Otros',          fn: () => true },
  ],
}

function getSubcats(catKey) {
  return SUBCATS[catKey.toLowerCase()] || []
}

// Filtra productos por subcategoría, excluyendo los que ya cayeron en anteriores
function filtrarPorSubcat(prods, subcats, subcatKey) {
  const idx = subcats.findIndex(s => s.key === subcatKey)
  if (idx === -1) return prods
  const sc = subcats[idx]
  // "Otros/Varios" = los que no matchean ninguna subcat anterior
  const esComodin = sc.label === 'Otros' || sc.label === 'Varios'
  if (esComodin) {
    const prevFns = subcats.slice(0, idx).map(s => s.fn)
    return prods.filter(p => !prevFns.some(fn => fn(p)))
  }
  return prods.filter(sc.fn)
}

// ── Input inline de precio ────────────────────────────────────────────────────
function PrecioInline({ value, prodKey, onSaved, t }) {
  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState(value || 0)
  const [saving,   setSaving]   = useState(false)
  const [flash,    setFlash]    = useState(null) // 'ok' | 'err'
  const ref = useRef()

  const abrir = (e) => {
    e.stopPropagation()
    setVal(value || 0)
    setEditando(true)
    setTimeout(() => ref.current?.select(), 30)
  }

  const guardar = async () => {
    if (Number(val) === Number(value)) { setEditando(false); return }
    setSaving(true)
    try {
      const r = await fetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/precio`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ precio: Number(val) }),
      })
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      setFlash('ok')
      onSaved(Number(val))
      setTimeout(() => setFlash(null), 2000)
    } catch {
      setFlash('err')
      setTimeout(() => setFlash(null), 2500)
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
      <button onClick={guardar} disabled={saving} style={{ background: t.accent, border: 'none', borderRadius: 5, color: '#fff', width: 22, height: 22, cursor: 'pointer', fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {saving ? '…' : '✓'}
      </button>
      <button onClick={cancelar} style={{ background: 'transparent', border: `1px solid ${t.border}`, borderRadius: 5, color: t.textMuted, width: 22, height: 22, cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
    </div>
  )

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }} onClick={abrir} title="Click para editar precio">
      {value ? (
        <span style={{
          color: flash === 'ok' ? t.green : flash === 'err' ? '#f87171' : t.green,
          fontWeight: 600, transition: 'color .3s',
        }}>
          {cop(value)}
          {flash === 'ok' && <span style={{ fontSize: 9, marginLeft: 5, color: t.green }}>✓ guardado</span>}
          {flash === 'err' && <span style={{ fontSize: 9, marginLeft: 5, color: '#f87171' }}>✗ error</span>}
        </span>
      ) : (
        <Badge color={t.yellow}>Sin precio</Badge>
      )}
      <span style={{ fontSize: 10, color: t.textMuted, opacity: 0.5 }}>✏️</span>
    </div>
  )
}

// ── Editor de fracciones inline ───────────────────────────────────────────────
const FRACS_ORDEN = ['3/4', '1/2', '1/4', '1/8', '1/10', '1/16']

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
      setTimeout(() => { setFlash(null); setEditando(false) }, 1000)
    } catch {
      setFlash('err')
      setTimeout(() => setFlash(null), 2500)
    }
    setSaving(false)
  }

  const fracsList = fracciones ? Object.entries(fracciones) : []
  const hasFracs  = fracsList.length > 0

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
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <button onClick={guardar} disabled={saving} style={{
          background: flash === 'ok' ? t.green : t.accent, border: 'none', borderRadius: 6,
          color: '#fff', padding: '5px 14px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11, fontWeight: 600,
        }}>
          {saving ? 'Guardando…' : flash === 'ok' ? '✓ Guardado en JSON + Excel' : 'Guardar fracciones'}
        </button>
        <button onClick={e => { e.stopPropagation(); setEditando(false) }} style={{
          background: 'transparent', border: `1px solid ${t.border}`, borderRadius: 6,
          color: t.textMuted, padding: '5px 12px', cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
        }}>Cancelar</button>
        {flash === 'err' && <span style={{ fontSize: 10, color: '#f87171' }}>✗ Error al guardar</span>}
      </div>
    </div>
  )
}

// ── Fila de producto ──────────────────────────────────────────────────────────
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

// ── Tabla de productos de una categoría ──────────────────────────────────────
function TablaCat({ prods, t }) {
  const [expandedP, setExpandedP] = useState({})
  const toggleProd = useCallback((key) => {
    setExpandedP(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  return (
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
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────
export default function TabCatalogo({ refreshKey }) {
  const t = useTheme()
  const [busqueda,    setBusqueda]    = useState('')
  const [abierta,     setAbierta]     = useState(null)   // categoría expandida
  const [subcatActiva, setSubcatActiva] = useState({})   // { catKey: subcatKey }
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div style={{ fontSize: 11, color: t.textMuted }}>
          📦 <strong style={{ color: t.text }}>{total}</strong> productos ·{' '}
          <strong style={{ color: t.text }}>{catEntries.length}</strong> categorías
          <span style={{ marginLeft: 10, opacity: .7 }}>· Click en precio para editar ✏️ · Guarda en JSON y Excel</span>
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
              const catKey    = cat.toLowerCase()
              const label     = cat.replace(/^\d+\s*/, '')
              const expandida = busqueda ? true : abierta === cat
              const subcats   = getSubcats(catKey)
              const subcatSel = subcatActiva[cat] || null

              const conFracs  = prods.filter(p => p.fracciones && Object.keys(p.fracciones).length > 0).length
              const sinPrecio = prods.filter(p => !p.precio).length

              // Filtrar por subcategoría si hay una activa
              const prodsVisibles = subcatSel
                ? filtrarPorSubcat(prods, subcats, subcatSel)
                : prods

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
                      {conFracs > 0  && <span style={{ fontSize: 10, color: t.accent, background: t.accentSub, padding: '1px 7px', borderRadius: 99 }}>{conFracs} con fracciones</span>}
                      {sinPrecio > 0 && <span style={{ fontSize: 10, color: t.yellow }}>⚠️ {sinPrecio} sin precio</span>}
                    </div>
                    {!busqueda && (
                      <span style={{
                        color: t.textMuted, fontSize: 11, transition: 'transform .2s',
                        transform: expandida ? 'rotate(90deg)' : 'rotate(0deg)', display: 'inline-block',
                      }}>▶</span>
                    )}
                  </div>

                  {/* Subcategorías */}
                  {expandida && subcats.length > 0 && (
                    <div style={{
                      padding: '8px 16px', borderTop: `1px solid ${t.border}`,
                      display: 'flex', gap: 6, flexWrap: 'wrap', background: t.tableAlt,
                    }}>
                      {/* Botón "Todos" */}
                      <button
                        onClick={() => setSubcatActiva(prev => ({ ...prev, [cat]: null }))}
                        style={{
                          background: !subcatSel ? t.accent : 'transparent',
                          border: `1px solid ${!subcatSel ? t.accent : t.border}`,
                          color: !subcatSel ? '#fff' : t.textMuted,
                          fontSize: 11, padding: '4px 12px', borderRadius: 20,
                          cursor: 'pointer', fontFamily: 'inherit', fontWeight: !subcatSel ? 600 : 400,
                          transition: 'all .15s',
                        }}
                      >
                        Todos ({prods.length})
                      </button>

                      {/* Botones subcategorías */}
                      {subcats.map(sc => {
                        const cnt    = filtrarPorSubcat(prods, subcats, sc.key).length
                        const active = subcatSel === sc.key
                        if (cnt === 0) return null
                        return (
                          <button
                            key={sc.key}
                            onClick={() => setSubcatActiva(prev => ({ ...prev, [cat]: sc.key }))}
                            style={{
                              background: active ? t.accent : 'transparent',
                              border: `1px solid ${active ? t.accent : t.border}`,
                              color: active ? '#fff' : t.textMuted,
                              fontSize: 11, padding: '4px 12px', borderRadius: 20,
                              cursor: 'pointer', fontFamily: 'inherit', fontWeight: active ? 600 : 400,
                              display: 'flex', alignItems: 'center', gap: 5,
                              transition: 'all .15s',
                            }}
                          >
                            <span>{sc.icono}</span>
                            <span>{sc.label}</span>
                            <span style={{ fontSize: 10, opacity: .7 }}>({cnt})</span>
                          </button>
                        )
                      })}
                    </div>
                  )}

                  {/* Tabla */}
                  {expandida && (
                    prodsVisibles.length === 0
                      ? <div style={{ padding: '20px', textAlign: 'center', color: t.textMuted, fontSize: 12 }}>Sin productos en esta subcategoría.</div>
                      : <TablaCat prods={prodsVisibles} t={t} />
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
