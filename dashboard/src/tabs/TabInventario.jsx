import { useState, useRef, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import {
  useTheme, useFetch, Spinner, ErrorMsg,
  StyledInput, Badge, EmptyState, cop, API_BASE,
} from '../components/shared.jsx'

// ── Utilidades ────────────────────────────────────────────────────────────────
const nl = s => (s || '').toLowerCase()

function catIcon(cat) {
  const c = nl(cat)
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

// ── Subcategorías ─────────────────────────────────────────────────────────────
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
    { key: 'imp_imp',     icono: '💧', label: 'Impermeabilizantes', fn: p => nl(p.nombre).includes('imperme') },
    { key: 'imp_cemento', icono: '🏗️', label: 'Cemento / Mortero', fn: p => nl(p.nombre).includes('cemento') || nl(p.nombre).includes('mortero') || nl(p.nombre).includes('pega') },
    { key: 'imp_otros',   icono: '📦', label: 'Otros',              fn: () => true },
  ],
  '5 materiales electricos': [
    { key: 'elec_cable',    icono: '🔌', label: 'Cables',        fn: p => nl(p.nombre).includes('cable') || nl(p.nombre).includes('alambre') },
    { key: 'elec_interrup', icono: '💡', label: 'Interruptores', fn: p => nl(p.nombre).includes('interruptor') || nl(p.nombre).includes('toma') },
    { key: 'elec_otros',    icono: '⚡', label: 'Otros',         fn: () => true },
  ],
}

function getSubcats(catKey) { return SUBCATS[catKey.toLowerCase()] || [] }

function filtrarPorSubcat(prods, subcats, subcatKey) {
  const idx = subcats.findIndex(s => s.key === subcatKey)
  if (idx === -1) return prods
  const sc = subcats[idx]
  const esComodin = sc.label === 'Otros' || sc.label === 'Varios'
  if (esComodin) {
    const prevFns = subcats.slice(0, idx).map(s => s.fn)
    return prods.filter(p => !prevFns.some(fn => fn(p)))
  }
  return prods.filter(sc.fn)
}

// ── Fracciones ────────────────────────────────────────────────────────────────
function parseFraccion(str) {
  if (!str) return null
  str = String(str).trim().replace(',', '.')
  const mixto  = str.match(/^(\d+(?:\.\d+)?)\s+(\d+)\/(\d+)$/)
  if (mixto)  return parseFloat(mixto[1]) + parseFloat(mixto[2]) / parseFloat(mixto[3])
  const simple = str.match(/^(\d+)\/(\d+)$/)
  if (simple) return parseFloat(simple[1]) / parseFloat(simple[2])
  const n = parseFloat(str)
  return isNaN(n) ? null : n
}

const FRACS_CONOCIDAS = [
  [1/16,'1/16'],[1/8,'1/8'],[1/4,'1/4'],[1/3,'1/3'],[3/8,'3/8'],
  [1/2,'1/2'],[5/8,'5/8'],[2/3,'2/3'],[3/4,'3/4'],[7/8,'7/8'],[1/10,'1/10'],
]

function decimalAFrac(val) {
  if (val === null || val === undefined) return null
  val = parseFloat(val)
  if (isNaN(val)) return null
  if (Number.isInteger(val)) return String(val)
  const entero = Math.floor(val)
  const frac   = val - entero
  for (const [dec, label] of FRACS_CONOCIDAS) {
    if (Math.abs(frac - dec) < 0.005) return entero > 0 ? `${entero} ${label}` : label
  }
  return val.toFixed(2).replace(/\.?0+$/, '')
}

// ── Editor de precio inline ───────────────────────────────────────────────────
function PrecioInline({ value, prodKey, onSaved }) {
  const t = useTheme()
  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState(value || 0)
  const [estado,   setEstado]   = useState('idle') // idle | saving | ok | err
  const ref = useRef()

  const abrir = (e) => { e.stopPropagation(); setVal(value || 0); setEstado('idle'); setEditando(true); setTimeout(() => ref.current?.select(), 20) }
  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = async () => {
    if (Number(val) === Number(value)) { cerrar(); return }
    setEstado('saving')
    try {
      const r = await fetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/precio`, {
        method:'PATCH', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ precio: Number(val) }),
      })
      if (!r.ok) throw new Error()
      setEstado('ok'); onSaved(Number(val))
      setTimeout(cerrar, 1200)
    } catch { setEstado('err'); setTimeout(cerrar, 1500) }
  }

  if (editando) return (
    <div style={{ display:'flex', alignItems:'center', gap:5 }} onClick={e => e.stopPropagation()}>
      <span style={{ color:t.textMuted, fontSize:11 }}>$</span>
      <input
        ref={ref} type="number" min="0" value={val}
        onChange={e => setVal(parseInt(e.target.value)||0)}
        onKeyDown={e => { if(e.key==='Enter') guardar(); if(e.key==='Escape') cerrar() }}
        style={{
          width:90, background:t.id==='caramelo'?'#f8fafc':'#111',
          border:`1px solid ${t.accent}88`, borderRadius:6,
          color:t.accent, fontSize:12, fontFamily:'monospace', fontWeight:700,
          padding:'3px 7px', outline:'none', MozAppearance:'textfield', appearance:'textfield',
        }}
      />
      <button onClick={guardar} style={{ background:t.accent, border:'none', borderRadius:5, color:'#fff', width:22, height:22, cursor:'pointer', fontSize:12, display:'flex', alignItems:'center', justifyContent:'center' }}>
        {estado==='saving'?'…':'✓'}
      </button>
      <button onClick={cerrar} style={{ background:'transparent', border:`1px solid ${t.border}`, borderRadius:5, color:t.textMuted, width:22, height:22, cursor:'pointer', fontSize:11, display:'flex', alignItems:'center', justifyContent:'center' }}>✕</button>
    </div>
  )

  return (
    <div style={{ display:'flex', alignItems:'center', gap:6, cursor:'pointer' }} onClick={abrir} title="Clic para editar precio">
      {value
        ? <span style={{ color: estado==='ok'?t.green : estado==='err'?'#f87171' : t.green, fontWeight:600, transition:'color .3s' }}>
            {cop(value)}
            {estado==='ok'  && <span style={{ fontSize:9, marginLeft:5, color:t.green }}>✓</span>}
            {estado==='err' && <span style={{ fontSize:9, marginLeft:5, color:'#f87171' }}>✗</span>}
          </span>
        : <Badge color={t.yellow}>Sin precio</Badge>
      }
      <span style={{ fontSize:10, color:t.textMuted, opacity:.45 }}>✏</span>
    </div>
  )
}

// ── Editor de stock inline (con fracciones para fraccionables) ────────────────
function StockInline({ value, prodKey, fracciones, onSaved }) {
  const t       = useTheme()
  const esFracc = !!(fracciones && Object.keys(fracciones).filter(k=>k!=='unidad_suelta').length > 0)
  const fracBtns = useMemo(() => {
    if (!esFracc) return []
    return Object.keys(fracciones).filter(k=>k!=='unidad_suelta')
      .sort((a,b) => (parseFraccion(b)||0) - (parseFraccion(a)||0))
  }, [fracciones, esFracc])

  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState('')
  const [estado,   setEstado]   = useState('idle')
  const ref = useRef()

  const display = esFracc ? decimalAFrac(value) : (value!==null&&value!==undefined ? String(value) : null)

  const abrir = (e) => { e.stopPropagation(); setVal(display||''); setEstado('idle'); setEditando(true); setTimeout(()=>{ref.current?.focus();ref.current?.select()},20) }
  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = useCallback(async (strVal) => {
    const src = strVal !== undefined ? strVal : val
    const num = esFracc ? parseFraccion(String(src)) : parseFloat(String(src).replace(',','.'))
    if (num===null||isNaN(num)||num<0) { cerrar(); return }
    setEstado('saving')
    try {
      const r = await fetch(`${API_BASE}/inventario/${encodeURIComponent(prodKey)}/stock`, {
        method:'PATCH', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ stock: num }),
      })
      if (!r.ok) throw new Error()
      setEstado('ok'); onSaved(num)
      setTimeout(cerrar, 700)
    } catch { setEstado('err'); setTimeout(cerrar, 900) }
  }, [val, prodKey, esFracc, onSaved])

  const onKey = e => { if(e.key==='Enter') guardar(); if(e.key==='Escape') cerrar() }
  const sumar  = frac => { const b=parseFraccion(val)||0; setVal(decimalAFrac(b+(parseFraccion(frac)||0))||'') }
  const restar = frac => { const b=parseFraccion(val)||0; setVal(decimalAFrac(Math.max(0,b-(parseFraccion(frac)||0)))||'0') }

  if (editando) return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:5 }} onClick={e=>e.stopPropagation()}>
      <div style={{ display:'flex', alignItems:'center', gap:4 }}>
        <input
          ref={ref} value={val} onChange={e=>setVal(e.target.value)} onKeyDown={onKey} onBlur={guardar}
          placeholder={esFracc?'ej: 2 3/4':'0'} inputMode="decimal"
          style={{
            width:esFracc?88:68, background:t.id==='caramelo'?'#f8fafc':'#111',
            border:`1.5px solid ${estado==='err'?t.accent:t.green}`,
            borderRadius:6, padding:'3px 8px', fontSize:12, color:t.text,
            fontFamily:'monospace', outline:'none', textAlign:'center',
          }}
        />
        <button onClick={()=>guardar()} style={{ background:t.green+'22', border:`1px solid ${t.green}44`, color:t.green, borderRadius:5, padding:'3px 7px', fontSize:11, cursor:'pointer' }}>✓</button>
        <button onClick={cerrar} style={{ background:'none', border:`1px solid ${t.border}`, color:t.textMuted, borderRadius:5, padding:'3px 7px', fontSize:11, cursor:'pointer' }}>✕</button>
      </div>
      {esFracc && fracBtns.length > 0 && (
        <div style={{ display:'flex', flexWrap:'wrap', gap:3, justifyContent:'center' }}>
          {fracBtns.map(frac => (
            <div key={frac} style={{ display:'flex', gap:1 }}>
              <button onClick={()=>restar(frac)} style={{ background:t.accentSub, border:`1px solid ${t.accent}33`, color:t.accent, borderRadius:'4px 0 0 4px', padding:'2px 5px', fontSize:10, cursor:'pointer', fontWeight:700 }}>−</button>
              <span style={{ background:t.card, border:`1px solid ${t.border}`, borderLeft:'none', borderRight:'none', padding:'2px 6px', fontSize:10, color:t.text, display:'flex', alignItems:'center' }}>{frac}</span>
              <button onClick={()=>sumar(frac)} style={{ background:t.green+'22', border:`1px solid ${t.green}33`, color:t.green, borderRadius:'0 4px 4px 0', padding:'2px 5px', fontSize:10, cursor:'pointer', fontWeight:700 }}>+</button>
            </div>
          ))}
        </div>
      )}
      {estado==='saving'&&<span style={{fontSize:9,color:t.textMuted}}>Guardando…</span>}
      {estado==='ok'    &&<span style={{fontSize:10,color:t.green}}>✓</span>}
      {estado==='err'   &&<span style={{fontSize:10,color:t.accent}}>✗</span>}
    </div>
  )

  const hay     = value!==null&&value!==undefined
  const esFracV = esFracc && hay && !Number.isInteger(parseFloat(value))
  return (
    <div style={{ display:'flex', alignItems:'center', gap:5, cursor:'pointer', justifyContent:'center' }} onClick={abrir} title="Clic para editar stock">
      {hay
        ? <span style={{ color:esFracV?t.yellow:t.blue, fontWeight:esFracV?600:400, fontFamily:'monospace', fontSize:12 }}>
            {display}{esFracc&&<span style={{fontSize:9,opacity:.5,marginLeft:2}}>gal</span>}
          </span>
        : <span style={{ color:t.textMuted, fontSize:11, opacity:.6 }}>—</span>
      }
      <span style={{ fontSize:9, color:t.textMuted, opacity:.35 }}>✏</span>
    </div>
  )
}

// ── Editor de fracciones inline ───────────────────────────────────────────────
const FRACS_ORDEN = ['3/4','1/2','1/4','1/8','1/10','1/16']

function FraccionesEditor({ fracciones, prodKey, onSaved }) {
  const t = useTheme()
  const [editando, setEditando] = useState(false)
  const [vals,     setVals]     = useState({})
  const [estado,   setEstado]   = useState('idle')

  const abrir = (e) => {
    e.stopPropagation()
    const init = {}
    FRACS_ORDEN.forEach(f => { const v=fracciones?.[f]; init[f]=v?(typeof v==='object'?v.precio:v):'' })
    setVals(init); setEditando(true)
  }

  const guardar = async (e) => {
    e.stopPropagation()
    setEstado('saving')
    const fracs = {}
    FRACS_ORDEN.forEach(f => { if (vals[f]>0) fracs[f]=parseInt(vals[f]) })
    try {
      const r = await fetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/fracciones`, {
        method:'PATCH', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ fracciones: fracs }),
      })
      if (!r.ok) throw new Error()
      setEstado('ok'); onSaved(fracs)
      setTimeout(()=>{ setEstado('idle'); setEditando(false) }, 1000)
    } catch { setEstado('err'); setTimeout(()=>setEstado('idle'), 2000) }
  }

  const hasFracs = fracciones && Object.keys(fracciones).length > 0

  if (!editando) return (
    <div>
      {hasFracs && (
        <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:7 }}>
          {FRACS_ORDEN.filter(f=>fracciones[f]).map(f => {
            const precio = typeof fracciones[f]==='object' ? fracciones[f].precio : fracciones[f]
            return (
              <div key={f} style={{ background:t.card, border:`1px solid ${t.border}`, borderRadius:7, padding:'4px 9px' }}>
                <div style={{ fontSize:9, color:t.textMuted, marginBottom:1 }}>{f}</div>
                <div style={{ color:t.accent, fontWeight:600, fontSize:11 }}>{cop(precio)}</div>
              </div>
            )
          })}
        </div>
      )}
      <button onClick={abrir} style={{
        fontSize:10, color:t.accent, background:t.accentSub,
        border:`1px solid ${t.accent}44`, borderRadius:6, padding:'4px 10px',
        cursor:'pointer', fontFamily:'inherit',
      }}>
        ✏ {hasFracs ? 'Editar fracciones' : 'Agregar fracciones'}
      </button>
    </div>
  )

  return (
    <div onClick={e=>e.stopPropagation()}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:6, marginBottom:10 }}>
        {FRACS_ORDEN.map(f => (
          <div key={f}>
            <div style={{ fontSize:9, color:t.textMuted, marginBottom:3 }}>{f}</div>
            <div style={{ display:'flex', alignItems:'center', gap:3 }}>
              <span style={{ fontSize:10, color:t.textMuted }}>$</span>
              <input type="number" min="0" value={vals[f]||''} placeholder="—"
                onChange={e=>setVals(v=>({...v,[f]:parseInt(e.target.value)||0}))}
                style={{
                  width:'100%', background:t.id==='caramelo'?'#f8fafc':'#111',
                  border:`1px solid ${vals[f]>0?t.accent+'88':t.border}`, borderRadius:6,
                  color:t.text, fontSize:11, fontFamily:'monospace', padding:'4px 6px',
                  outline:'none', MozAppearance:'textfield', appearance:'textfield',
                }}
              />
            </div>
          </div>
        ))}
      </div>
      <div style={{ display:'flex', gap:6, alignItems:'center' }}>
        <button onClick={guardar} style={{
          background: estado==='ok'?t.green:t.accent, border:'none', borderRadius:6,
          color:'#fff', padding:'5px 14px', cursor:'pointer', fontFamily:'inherit', fontSize:11, fontWeight:600,
        }}>
          {estado==='saving'?'Guardando…':estado==='ok'?'✓ Guardado':'Guardar fracciones'}
        </button>
        <button onClick={e=>{e.stopPropagation();setEditando(false)}} style={{
          background:'transparent', border:`1px solid ${t.border}`, borderRadius:6,
          color:t.textMuted, padding:'5px 12px', cursor:'pointer', fontFamily:'inherit', fontSize:11,
        }}>Cancelar</button>
        {estado==='err'&&<span style={{fontSize:10,color:'#f87171'}}>✗ Error</span>}
      </div>
    </div>
  )
}

// ── Fila de producto ──────────────────────────────────────────────────────────
function ProductoRow({ p: pInit, expanded, onToggle }) {
  const t = useTheme()
  const [p, setP] = useState(pInit)
  const hasFracs   = p.fracciones && Object.keys(p.fracciones).length > 0
  const expandible = hasFracs || p.mayorista

  // Badge de unidad de medida — solo si no es "Unidad" genérica
  const unidad = p.unidad_medida || 'Unidad'
  const esUnidadEspecial = unidad && unidad.toLowerCase() !== 'unidad'
  const UNIDAD_COLORES = {
    'galón': { bg: '#fef9c3', color: '#a16207', border: '#fde047' },
    'galon': { bg: '#fef9c3', color: '#a16207', border: '#fde047' },
    'kg':    { bg: '#dcfce7', color: '#166534', border: '#86efac' },
    'mts':   { bg: '#dbeafe', color: '#1d4ed8', border: '#93c5fd' },
    'cms':   { bg: '#ede9fe', color: '#6d28d9', border: '#c4b5fd' },
    'lts':   { bg: '#e0f2fe', color: '#0369a1', border: '#7dd3fc' },
    'lt':    { bg: '#e0f2fe', color: '#0369a1', border: '#7dd3fc' },
  }
  const unidadKey = unidad.toLowerCase().replace('ó','o')
  const unidadColor = UNIDAD_COLORES[unidadKey] || { bg: '#f3f4f6', color: '#6b7280', border: '#d1d5db' }

  return (
    <>
      <tr
        style={{ borderBottom:`1px solid ${t.border}`, cursor: expandible?'pointer':'default' }}
        onClick={() => expandible && onToggle()}
        onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <td style={{ padding:'9px 14px', color:t.textMuted, fontFamily:'monospace', fontSize:10 }}>{p.codigo||'—'}</td>
        <td style={{ padding:'9px 14px', color:t.text }}>
          {p.nombre}
          <div style={{ display:'flex', gap:4, flexWrap:'wrap', marginTop:3 }}>
            {hasFracs && (
              <span style={{ background:t.accentSub, color:t.accent, border:`1px solid ${t.accent}33`, padding:'1px 7px', borderRadius:99, fontSize:9 }}>fracciones</span>
            )}
            {p.mayorista && (
              <span style={{ background:t.id==='caramelo'?'#eff6ff':'#172554', color:t.blue, border:`1px solid ${t.blue}33`, padding:'1px 7px', borderRadius:99, fontSize:9 }}>mayorista ×{p.mayorista.umbral}</span>
            )}
          </div>
        </td>
        <td style={{ padding:'9px 14px' }} onClick={e=>e.stopPropagation()}>
          <PrecioInline value={p.precio} prodKey={p.key} onSaved={v=>setP(prev=>({...prev,precio:v}))}/>
        </td>
        <td style={{ padding:'9px 10px', textAlign:'center' }} onClick={e=>e.stopPropagation()}>
          <StockInline
            value={p.stock!==null&&p.stock!==undefined ? p.stock : null}
            prodKey={p.key}
            fracciones={p.fracciones||null}
            onSaved={v=>setP(prev=>({...prev,stock:v}))}
          />
        </td>
        <td style={{ padding:'9px 10px', textAlign:'center' }}>
          {esUnidadEspecial
            ? <span style={{
                background: t.id==='caramelo' ? unidadColor.bg : unidadColor.bg+'33',
                color: t.id==='caramelo' ? unidadColor.color : unidadColor.border,
                border: `1px solid ${unidadColor.border}55`,
                padding:'2px 8px', borderRadius:99, fontSize:9, fontWeight:600,
              }}>{unidad}</span>
            : <span style={{ color:t.textMuted, fontSize:10, opacity:.4 }}>und</span>
          }
        </td>
        <td style={{ padding:'9px 14px', textAlign:'center', color:t.textMuted, fontSize:11 }}>
          {expandible ? (expanded?'▲':'▼') : ''}
        </td>
      </tr>
      {expanded && (
        <tr style={{ background:t.tableAlt }}>
          <td colSpan={6} style={{ padding:'10px 24px 14px' }}>
            <FraccionesEditor
              fracciones={p.fracciones} prodKey={p.key}
              onSaved={v=>setP(prev=>({...prev,fracciones:v}))}
            />
            {p.mayorista && (
              <div style={{ marginTop: hasFracs?12:0 }}>
                <div style={{ fontSize:10, color:t.textMuted, textTransform:'uppercase', letterSpacing:'.08em', marginBottom:6 }}>Precio mayorista</div>
                <div style={{ background:t.card, border:`1px solid ${t.blue}33`, borderRadius:7, padding:'6px 12px', display:'inline-block' }}>
                  <span style={{ color:t.textMuted, fontSize:10 }}>Desde {p.mayorista.umbral} uds: </span>
                  <span style={{ color:t.blue, fontWeight:600, fontSize:12 }}>{cop(p.mayorista.precio)} c/u</span>
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ── Tabla ─────────────────────────────────────────────────────────────────────
function TablaCat({ prods }) {
  const t = useTheme()
  const [expanded, setExpanded] = useState({})
  const toggle = useCallback(k => setExpanded(p=>({...p,[k]:!p[k]})), [])

  return (
    <div style={{ borderTop:`1px solid ${t.border}`, overflowX:'auto' }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
        <thead>
          <tr style={{ background:t.tableAlt }}>
            {['Código','Nombre','Precio','Stock','Unidad',''].map((h,i)=>(
              <th key={i} style={{
                padding:'8px 14px', textAlign: (i===2||i===3||i===4)?'center':'left',
                fontSize:9, color:t.textMuted, textTransform:'uppercase',
                letterSpacing:'.08em', fontWeight:500, borderBottom:`1px solid ${t.border}`,
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {prods.map(p => (
            <ProductoRow key={p.key} p={p} expanded={!!expanded[p.key]} onToggle={()=>toggle(p.key)}/>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Modal Crear Producto ──────────────────────────────────────────────────────
const CATEGORIAS_DISPONIBLES = [
  '1 Artículos de Ferreteria',
  '2 Pinturas y Disolventes',
  '3 Tornilleria',
  '4 Impermeabilizantes y Materiales de Construcción',
  '5 Materiales Electricos',
]

const UNIDADES_DISPONIBLES = [
  'Unidad','Galón','Kg','Mts','Cms','Lt','Lts','25 kg',
]

function ModalCrearProducto({ onClose, onCreado }) {
  const t = useTheme()
  const [form, setForm] = useState({
    nombre:        '',
    categoria:     CATEGORIAS_DISPONIBLES[0],
    precio_unidad: '',
    unidad_medida: 'Unidad',
    codigo:        '',
    stock_inicial: '',
  })
  const [estado, setEstado] = useState('idle')
  const [errMsg, setErrMsg] = useState('')

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const guardar = async () => {
    if (!form.nombre.trim())                              { setErrMsg('El nombre es obligatorio'); return }
    if (!form.precio_unidad || isNaN(Number(form.precio_unidad))) { setErrMsg('El precio debe ser un número'); return }
    setErrMsg(''); setEstado('saving')
    try {
      const body = {
        nombre:        form.nombre.trim(),
        categoria:     form.categoria,
        precio_unidad: Number(form.precio_unidad),
        unidad_medida: form.unidad_medida,
        codigo:        form.codigo.trim(),
      }
      if (form.stock_inicial !== '' && !isNaN(Number(form.stock_inicial)))
        body.stock_inicial = Number(form.stock_inicial)

      const r = await fetch(`${API_BASE}/catalogo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Error desconocido')
      setEstado('ok')
      setTimeout(() => { onCreado(data); onClose() }, 800)
    } catch(e) {
      setErrMsg(e.message || 'Error al crear el producto')
      setEstado('err')
    }
  }

  const inp = {
    width: '100%', boxSizing: 'border-box',
    background: t.id === 'caramelo' ? '#f8fafc' : '#111',
    border: `1px solid ${t.border}`, borderRadius: 7,
    color: t.text, fontSize: 12, padding: '8px 11px',
    outline: 'none', fontFamily: 'inherit',
  }
  const lbl = {
    fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
    letterSpacing: '.07em', marginBottom: 4, display: 'block',
  }

  // Renderizar via Portal directo al body — inmune a scroll/overflow del tab
  return createPortal(
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
      onMouseDown={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: t.bg, border: `1px solid ${t.border}`,
        borderRadius: 14, width: '100%', maxWidth: 460,
        maxHeight: '90vh', overflowY: 'auto',
        boxShadow: '0 24px 64px rgba(0,0,0,.45)',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
          padding: '20px 22px 0', marginBottom: 18,
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: t.text }}>➕ Crear producto</div>
            <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
              Se guardará en catálogo y en el Excel de productos
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'transparent', border: `1px solid ${t.border}`,
            borderRadius: 7, color: t.textMuted,
            width: 28, height: 28, cursor: 'pointer', fontSize: 14, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginLeft: 12,
          }}>✕</button>
        </div>

        {/* Cuerpo */}
        <div style={{ padding: '0 22px 22px', display: 'flex', flexDirection: 'column', gap: 13 }}>

          {/* Nombre */}
          <div>
            <label style={lbl}>Nombre del producto *</label>
            <input style={inp} value={form.nombre} autoFocus
              onChange={e => set('nombre', e.target.value)}
              onKeyDown={e => e.key === 'Enter' && guardar()}
              placeholder='Ej: Brocha de 2"' />
          </div>

          {/* Categoría */}
          <div>
            <label style={lbl}>Categoría *</label>
            <select style={inp} value={form.categoria} onChange={e => set('categoria', e.target.value)}>
              {CATEGORIAS_DISPONIBLES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Precio + Unidad */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={lbl}>Precio unitario (COP) *</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: t.textMuted, fontSize: 11 }}>$</span>
                <input style={{ ...inp, paddingLeft: 22 }} type="number" min="0"
                  value={form.precio_unidad}
                  onChange={e => set('precio_unidad', e.target.value)}
                  placeholder="0" />
              </div>
            </div>
            <div>
              <label style={lbl}>Unidad de medida (DIAN)</label>
              <select style={inp} value={form.unidad_medida} onChange={e => set('unidad_medida', e.target.value)}>
                {UNIDADES_DISPONIBLES.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>

          {/* Código + Stock */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={lbl}>Código (opcional)</label>
              <input style={inp} value={form.codigo}
                onChange={e => set('codigo', e.target.value)}
                placeholder="Ej: 1brocha2" />
            </div>
            <div>
              <label style={lbl}>Stock inicial (opcional)</label>
              <input style={inp} type="number" min="0" step="0.01"
                value={form.stock_inicial}
                onChange={e => set('stock_inicial', e.target.value)}
                placeholder="0" />
            </div>
          </div>

          {/* Nota */}
          <div style={{
            padding: '8px 11px',
            background: t.accentSub, border: `1px solid ${t.accent}22`, borderRadius: 7,
          }}>
            <span style={{ fontSize: 10, color: t.accent }}>
              💡 Galón → pinturas · Kg → productos por peso · Mts/Cms → cables y telas · Unidad → resto
            </span>
          </div>

          {/* Error */}
          {errMsg && (
            <div style={{
              padding: '7px 11px', background: '#fef2f2',
              border: '1px solid #fca5a5', borderRadius: 7,
              fontSize: 11, color: '#dc2626',
            }}>⚠ {errMsg}</div>
          )}

          {/* Botones */}
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 2 }}>
            <button onClick={onClose} style={{
              background: 'transparent', border: `1px solid ${t.border}`,
              borderRadius: 8, color: t.textMuted, padding: '8px 18px',
              cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
            }}>Cancelar</button>
            <button onClick={guardar} disabled={estado === 'saving'} style={{
              background: estado === 'ok' ? t.green : estado === 'err' ? '#dc2626' : t.accent,
              border: 'none', borderRadius: 8, color: '#fff',
              padding: '8px 22px', cursor: estado === 'saving' ? 'wait' : 'pointer',
              fontFamily: 'inherit', fontSize: 12, fontWeight: 700,
              display: 'flex', alignItems: 'center', gap: 7,
              opacity: estado === 'saving' ? .75 : 1, transition: 'background .2s',
            }}>
              {estado === 'saving' && (
                <span style={{
                  width: 12, height: 12, border: '2px solid #ffffff55',
                  borderTop: '2px solid #fff', borderRadius: '50%',
                  display: 'inline-block', animation: 'spin .7s linear infinite',
                }} />
              )}
              {estado === 'ok' ? '✓ Creado' : estado === 'err' ? '✗ Error' : 'Crear producto'}
            </button>
          </div>
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>,
    document.body   // ← Portal: se monta directamente en <body>, fuera del scroll del tab
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────
export default function TabInventario({ refreshKey }) {
  const t = useTheme()
  const [busqueda,     setBusqueda]     = useState('')
  const [abierta,      setAbierta]      = useState(null)
  const [subcatActiva, setSubcatActiva] = useState({})
  const [queryActivo,  setQueryActivo]  = useState('')
  const [modalCrear,   setModalCrear]   = useState(false)
  const [localRefresh, setLocalRefresh] = useState(0)

  const url = queryActivo ? `/catalogo/nav?q=${encodeURIComponent(queryActivo)}` : '/catalogo/nav'
  const { data, loading, error } = useFetch(url, [queryActivo, refreshKey, localRefresh])

  const categorias  = data?.categorias || {}
  const total       = data?.total || 0
  const catEntries  = Object.entries(categorias)

  const handleBuscar = val => {
    setBusqueda(val)
    clearTimeout(window._invTimer)
    window._invTimer = setTimeout(() => setQueryActivo(val), 300)
  }

  const handleCreado = () => {
    setLocalRefresh(r => r + 1)
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>

      {modalCrear && (
        <ModalCrearProducto
          onClose={() => setModalCrear(false)}
          onCreado={handleCreado}
        />
      )}

      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10 }}>
        <div style={{ display:'flex', alignItems:'center', gap:12, flexWrap:'wrap' }}>
          <div style={{ fontSize:11, color:t.textMuted }}>
            📦 <strong style={{color:t.text}}>{total}</strong> productos ·{' '}
            <strong style={{color:t.text}}>{catEntries.length}</strong> categorías
            <span style={{ marginLeft:10, opacity:.6 }}>· Clic en precio o stock para editar ✏</span>
          </div>
          <button
            onClick={() => setModalCrear(true)}
            style={{
              background: t.accent, border: 'none', borderRadius: 8,
              color: '#fff', padding: '6px 14px', cursor: 'pointer',
              fontFamily: 'inherit', fontSize: 11, fontWeight: 700,
              display: 'flex', alignItems: 'center', gap: 5,
              boxShadow: `0 2px 8px ${t.accent}44`,
            }}
          >
            ➕ Nuevo producto
          </button>
        </div>
        <StyledInput
          value={busqueda} onChange={e=>handleBuscar(e.target.value)}
          placeholder="🔍  Buscar producto o código..." style={{ width:280 }}
        />
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {!loading && !error && (
        <>
          {catEntries.length === 0
            ? <EmptyState msg={busqueda?'Sin resultados.':'Sin productos.'} />
            : catEntries.map(([cat, prods]) => {
              const catKey     = cat.toLowerCase()
              const label      = cat.replace(/^\d+\s*/,'')
              const expandida  = busqueda ? true : abierta === cat
              const subcats    = getSubcats(catKey)
              const subcatSel  = subcatActiva[cat] || null
              const conFracs   = prods.filter(p=>p.fracciones&&Object.keys(p.fracciones).length>0).length
              const sinPrecio  = prods.filter(p=>!p.precio).length
              const sinStock   = prods.filter(p=>p.stock===null||p.stock===undefined).length
              const prodsVisibles = subcatSel ? filtrarPorSubcat(prods, subcats, subcatSel) : prods

              return (
                <div key={cat} style={{
                  background:t.card,
                  border:`1px solid ${expandida?t.accent+'44':t.border}`,
                  borderRadius:10, overflow:'hidden', transition:'border-color .2s',
                }}>
                  {/* Header categoría */}
                  <div
                    onClick={() => !busqueda && setAbierta(p=>p===cat?null:cat)}
                    style={{ padding:'13px 16px', display:'flex', alignItems:'center', justifyContent:'space-between', cursor:busqueda?'default':'pointer', userSelect:'none' }}
                    onMouseEnter={e=>{ if(!busqueda) e.currentTarget.style.background=t.cardHover }}
                    onMouseLeave={e=>e.currentTarget.style.background='transparent'}
                  >
                    <div style={{ display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
                      <span style={{fontSize:18}}>{catIcon(label)}</span>
                      <span style={{fontWeight:700, fontSize:13, color:t.text}}>{label}</span>
                      <span style={{fontSize:10, color:t.textMuted}}>{prods.length} productos</span>
                      {conFracs>0  && <span style={{fontSize:10,color:t.accent,background:t.accentSub,padding:'1px 7px',borderRadius:99}}>{conFracs} fraccionables</span>}
                      {sinPrecio>0 && <span style={{fontSize:10,color:t.yellow}}>⚠️ {sinPrecio} sin precio</span>}
                      {sinStock>0  && <span style={{fontSize:10,color:t.textMuted}}>📦 {sinStock} sin stock</span>}
                    </div>
                    {!busqueda && (
                      <span style={{ color:t.textMuted, fontSize:11, transition:'transform .2s', transform:expandida?'rotate(90deg)':'rotate(0deg)', display:'inline-block' }}>▶</span>
                    )}
                  </div>

                  {/* Subcategorías */}
                  {expandida && subcats.length>0 && (
                    <div style={{ padding:'8px 16px', borderTop:`1px solid ${t.border}`, display:'flex', gap:6, flexWrap:'wrap', background:t.tableAlt }}>
                      <button
                        onClick={()=>setSubcatActiva(prev=>({...prev,[cat]:null}))}
                        style={{
                          background:!subcatSel?t.accent:'transparent',
                          border:`1px solid ${!subcatSel?t.accent:t.border}`,
                          color:!subcatSel?'#fff':t.textMuted,
                          fontSize:11, padding:'4px 12px', borderRadius:20,
                          cursor:'pointer', fontFamily:'inherit', fontWeight:!subcatSel?600:400, transition:'all .15s',
                        }}
                      >Todos ({prods.length})</button>

                      {subcats.map(sc => {
                        const cnt    = filtrarPorSubcat(prods,subcats,sc.key).length
                        const active = subcatSel===sc.key
                        if (cnt===0) return null
                        return (
                          <button key={sc.key}
                            onClick={()=>setSubcatActiva(prev=>({...prev,[cat]:sc.key}))}
                            style={{
                              background:active?t.accent:'transparent',
                              border:`1px solid ${active?t.accent:t.border}`,
                              color:active?'#fff':t.textMuted,
                              fontSize:11, padding:'4px 12px', borderRadius:20,
                              cursor:'pointer', fontFamily:'inherit', fontWeight:active?600:400,
                              display:'flex', alignItems:'center', gap:5, transition:'all .15s',
                            }}
                          >
                            <span>{sc.icono}</span><span>{sc.label}</span>
                            <span style={{fontSize:10,opacity:.7}}>({cnt})</span>
                          </button>
                        )
                      })}
                    </div>
                  )}

                  {/* Tabla */}
                  {expandida && (
                    prodsVisibles.length===0
                      ? <div style={{padding:'20px',textAlign:'center',color:t.textMuted,fontSize:12}}>Sin productos en esta subcategoría.</div>
                      : <TablaCat prods={prodsVisibles}/>
                  )}
                </div>
              )
            })
          }
        </>
      )}
    </div>
  )
}
