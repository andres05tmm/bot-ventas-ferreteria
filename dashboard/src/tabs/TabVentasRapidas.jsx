import { useState, useCallback } from 'react'
import { useTheme, useFetch, Spinner, ErrorMsg, cop, API_BASE } from '../components/shared.jsx'

// ── Favoritos persistidos ─────────────────────────────────────────────────────
const FAV_KEY = 'vr_favs_v2'
const loadFavs  = () => { try { return JSON.parse(localStorage.getItem(FAV_KEY) || '[]') } catch { return [] } }
const saveFavs  = (keys) => { try { localStorage.setItem(FAV_KEY, JSON.stringify(keys)) } catch {} }

// ── Icono por categoría ───────────────────────────────────────────────────────
const CAT_ICON = {
  '1 artículos de ferreteria':                    '🔧',
  '2 pinturas y disolventes':                     '🎨',
  '3 tornilleria':                                '🔩',
  '4 impermeabilizantes y materiales de construcción': '🧱',
  '5 materiales electricos':                      '⚡',
}
function iconCat(cat = '') {
  return CAT_ICON[cat.toLowerCase()] || '📦'
}

// ── Nombre limpio de categoría (sin número prefijo) ───────────────────────────
function catLabel(cat = '') {
  return cat.replace(/^\d+\s*/, '')
}

// ── Tipo de producto ──────────────────────────────────────────────────────────
function tipoProd(prod) {
  if (prod.nombre?.toLowerCase().includes('esmeril')) return 'cm'
  if (prod.precios_fraccion && Object.keys(prod.precios_fraccion).length > 0) return 'fraccion'
  return 'simple'
}

// ══════════════════════════════════════════════════════════════════════════════
// PRODUCT CARD
// ══════════════════════════════════════════════════════════════════════════════
function ProdCard({ prod, onClick, isFav, onFav, cantCarrito }) {
  const t    = useTheme()
  const tipo = tipoProd(prod)

  return (
    <div
      onClick={() => onClick(prod)}
      style={{
        background:   cantCarrito > 0 ? t.accentSub : t.card,
        border:       `1px solid ${cantCarrito > 0 ? t.accent + '55' : t.border}`,
        borderRadius: 9,
        padding:      '10px 10px 8px',
        cursor:       'pointer',
        position:     'relative',
        transition:   'all .15s',
        userSelect:   'none',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = t.accent + '88'
        e.currentTarget.style.transform   = 'translateY(-1px)'
        e.currentTarget.style.boxShadow   = `0 4px 14px rgba(0,0,0,.35)`
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = cantCarrito > 0 ? t.accent + '55' : t.border
        e.currentTarget.style.transform   = 'translateY(0)'
        e.currentTarget.style.boxShadow   = 'none'
      }}
    >
      {/* Estrella favorito */}
      <span
        onClick={e => { e.stopPropagation(); onFav(prod.key) }}
        title={isFav ? 'Quitar de favoritos' : 'Agregar a favoritos'}
        style={{
          position: 'absolute', top: 6, right: 7,
          fontSize: 13, color: isFav ? '#fbbf24' : t.muted,
          cursor: 'pointer', transition: 'color .15s', lineHeight: 1,
          opacity: isFav ? 1 : .4,
        }}
        onMouseEnter={e => e.currentTarget.style.opacity = 1}
        onMouseLeave={e => e.currentTarget.style.opacity = isFav ? 1 : .4}
      >
        {isFav ? '★' : '☆'}
      </span>

      {/* Badge cantidad en carrito */}
      {cantCarrito > 0 && (
        <div style={{
          position: 'absolute', top: 6, left: 7,
          background: t.accent, color: '#fff',
          fontSize: 9, fontWeight: 700, lineHeight: 1,
          padding: '2px 5px', borderRadius: 99,
          fontFamily: 'monospace',
        }}>{cantCarrito}</div>
      )}

      {/* Badge tipo fracción/cm */}
      {tipo !== 'simple' && (
        <div style={{
          position: 'absolute', bottom: 6, right: 7,
          fontSize: 9, color: t.textMuted,
          background: t.border, borderRadius: 3, padding: '1px 4px',
          fontFamily: 'monospace',
        }}>
          {tipo === 'cm' ? 'cm' : '½'}
        </div>
      )}

      <div style={{ fontSize: 17, marginBottom: 5, marginTop: cantCarrito > 0 ? 8 : 0 }}>
        {iconCat(prod.categoria)}
      </div>
      <div style={{
        fontSize: 11, fontWeight: 600, color: t.text,
        lineHeight: 1.3, marginBottom: 3, paddingRight: 12,
      }}>
        {prod.nombre}
      </div>
      <div style={{ fontSize: 11, color: t.green, fontFamily: 'monospace' }}>
        {cop(prod.precio)}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// SECCIÓN
// ══════════════════════════════════════════════════════════════════════════════
function Seccion({ icono, titulo, cantidad, productos, carrito, favKeys, onClickProd, onFav }) {
  const t = useTheme()
  if (!productos.length) return null
  return (
    <div style={{ marginBottom: 24 }}>
      {/* Header sección */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10,
      }}>
        <span style={{ fontSize: 14 }}>{icono}</span>
        <span style={{
          fontSize: 11, fontWeight: 600, color: t.textSub,
          textTransform: 'uppercase', letterSpacing: '.1em',
        }}>
          {titulo}
        </span>
        <div style={{ flex: 1, height: 1, background: t.border }} />
        <span style={{
          fontSize: 10, color: t.textMuted,
          fontFamily: 'monospace',
        }}>{cantidad}</span>
      </div>

      {/* Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(128px, 1fr))',
        gap: 7,
      }}>
        {productos.map(p => (
          <ProdCard
            key={p.key}
            prod={p}
            onClick={onClickProd}
            isFav={favKeys.includes(p.key)}
            onFav={onFav}
            cantCarrito={carrito.filter(c => c.key === p.key).reduce((s, c) => s + (c.qty || 1), 0)}
          />
        ))}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL BASE
// ══════════════════════════════════════════════════════════════════════════════
function Modal({ show, onClose, title, subtitle, children, onConfirm, okLabel = 'Agregar al carrito', okDisabled }) {
  const t = useTheme()
  if (!show) return null
  return (
    <div
      onClick={e => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, background: '#000000cc',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 400, padding: 16,
      }}
    >
      <div style={{
        background: t.card, border: `1px solid ${t.accent}44`,
        borderRadius: 14, width: '100%', maxWidth: 390,
        animation: 'mIn .2s cubic-bezier(.34,1.4,.64,1)',
      }}>
        <style>{`@keyframes mIn{from{opacity:0;transform:scale(.92) translateY(10px)}to{opacity:1;transform:scale(1) translateY(0)}}`}</style>
        <div style={{ padding: '16px 18px 12px', borderBottom: `1px solid ${t.border}` }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: t.text }}>{title}</div>
          {subtitle && <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>{subtitle}</div>}
        </div>
        <div style={{ padding: '14px 18px' }}>{children}</div>
        <div style={{ display: 'flex', gap: 8, padding: '0 18px 18px' }}>
          <button onClick={onClose} style={{
            flex: 1, padding: 10, background: t.border, border: 'none',
            borderRadius: 8, color: t.textMuted, cursor: 'pointer',
            fontFamily: 'inherit', fontSize: 12,
          }}>Cancelar</button>
          <button onClick={onConfirm} disabled={okDisabled} style={{
            flex: 2, padding: 10,
            background: okDisabled ? t.border : t.accent,
            border: 'none', borderRadius: 8,
            color: okDisabled ? t.textMuted : '#fff',
            cursor: okDisabled ? 'not-allowed' : 'pointer',
            fontFamily: 'inherit', fontSize: 12, fontWeight: 600,
          }}>{okLabel}</button>
        </div>
      </div>
    </div>
  )
}

function ResumenModal({ desc, total }) {
  const t = useTheme()
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      background: t.id === 'light' ? '#f8fafc' : '#0f0f0f',
      border: `1px solid ${t.border}`, borderRadius: 8,
      padding: '10px 13px', marginBottom: 0,
    }}>
      <span style={{ fontSize: 12, color: t.textMuted }}>{desc || '—'}</span>
      <span style={{ fontSize: 18, fontFamily: 'monospace', color: t.accent, fontWeight: 700 }}>{cop(total)}</span>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL FRACCIÓN
// ══════════════════════════════════════════════════════════════════════════════
function ModalFraccion({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [unidades, setUnidades] = useState(0)
  const [fracKey,  setFracKey]  = useState(null)
  if (!prod) return null

  const fracs    = prod.precios_fraccion || {}
  const fracPrecio = fracKey && fracs[fracKey] ? fracs[fracKey].precio : 0
  const total    = unidades * prod.precio + fracPrecio
  const parts    = []
  if (unidades > 0) parts.push(`${unidades} ${unidades === 1 ? 'unidad' : 'unidades'}`)
  if (fracKey)      parts.push(fracKey)
  const desc     = parts.join(' + ') || '—'
  const valid    = unidades > 0 || fracKey

  return (
    <Modal show title={prod.nombre} subtitle={`Precio unidad: ${cop(prod.precio)}`}
      onClose={onClose} onConfirm={() => onConfirm({ unidades, fracKey, total, desc })} okDisabled={!valid}>

      {/* Unidades */}
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Unidades completas
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        background: t.id === 'light' ? '#f8fafc' : '#111',
        border: `1px solid ${t.border}`, borderRadius: 8,
        padding: '9px 13px', marginBottom: 14,
      }}>
        <span style={{ flex: 1, fontSize: 12, color: t.textMuted }}>Galones / unidades</span>
        <button onClick={() => setUnidades(u => Math.max(0, u - 1))} style={{ width: 26, height: 26, background: t.card, border: `1px solid ${t.border}`, borderRadius: 5, color: t.text, cursor: 'pointer', fontSize: 16 }}>−</button>
        <span style={{ fontFamily: 'monospace', fontSize: 17, color: t.text, minWidth: 22, textAlign: 'center' }}>{unidades}</span>
        <button onClick={() => setUnidades(u => u + 1)} style={{ width: 26, height: 26, background: t.card, border: `1px solid ${t.border}`, borderRadius: 5, color: t.text, cursor: 'pointer', fontSize: 16 }}>+</button>
      </div>

      {/* Fracciones */}
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Fracción adicional
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(Object.keys(fracs).length + 1, 3)}, 1fr)`,
        gap: 6, marginBottom: 14,
      }}>
        <div onClick={() => setFracKey(null)} style={{
          padding: '8px 4px', borderRadius: 7, cursor: 'pointer', textAlign: 'center',
          background: !fracKey ? t.accentSub : (t.id === 'light' ? '#f8fafc' : '#111'),
          border: `1px solid ${!fracKey ? t.accent : t.border}`, transition: 'all .15s',
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: !fracKey ? t.accent : t.textMuted }}>Ninguna</div>
          <div style={{ fontSize: 9, color: t.textMuted, marginTop: 1 }}>sólo unidades</div>
        </div>
        {Object.entries(fracs).map(([k, v]) => (
          <div key={k} onClick={() => setFracKey(k)} style={{
            padding: '8px 4px', borderRadius: 7, cursor: 'pointer', textAlign: 'center',
            background: fracKey === k ? t.accentSub : (t.id === 'light' ? '#f8fafc' : '#111'),
            border: `1px solid ${fracKey === k ? t.accent : t.border}`, transition: 'all .15s',
          }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: fracKey === k ? t.accent : t.text }}>{k}</div>
            <div style={{ fontSize: 10, color: t.green, fontFamily: 'monospace', marginTop: 1 }}>{cop(v.precio)}</div>
          </div>
        ))}
      </div>
      <ResumenModal desc={desc} total={total} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL CM
// ══════════════════════════════════════════════════════════════════════════════
function ModalCm({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [cm, setCm] = useState('')
  if (!prod) return null
  const pxcm  = Math.round((prod.precio || 0) / 100)
  const cmNum = parseInt(cm) || 0
  const total = cmNum * pxcm
  return (
    <Modal show title={prod.nombre} subtitle={`Pliego: ${cop(prod.precio)} · ${cop(pxcm)}/cm`}
      onClose={onClose} onConfirm={() => onConfirm({ cm: cmNum, total, desc: `${cmNum} cm` })} okDisabled={cmNum <= 0}>
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad en centímetros
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: t.id === 'light' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8,
        padding: '10px 14px', marginBottom: 8,
      }}>
        <input autoFocus type="number" min="1" value={cm}
          onChange={e => setCm(e.target.value)}
          style={{ flex: 1, background: 'transparent', border: 'none', color: t.text, fontSize: 24, fontFamily: 'monospace', outline: 'none', textAlign: 'center' }}
          placeholder="0"
        />
        <span style={{ fontSize: 13, color: t.textMuted }}>cm</span>
      </div>
      <div style={{ fontSize: 11, color: t.textMuted, textAlign: 'center', marginBottom: 14 }}>
        Precio por cm: <span style={{ color: t.green, fontFamily: 'monospace' }}>{cop(pxcm)}</span>
      </div>
      <ResumenModal desc={`${cmNum} cm`} total={total} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL QTY SIMPLE
// ══════════════════════════════════════════════════════════════════════════════
function ModalQty({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [qty, setQty] = useState(1)
  if (!prod) return null
  const total = qty * prod.precio
  return (
    <Modal show title={prod.nombre} subtitle={`Precio unitario: ${cop(prod.precio)}`}
      onClose={onClose} onConfirm={() => onConfirm({ qty, total, desc: `${qty} ${qty === 1 ? 'unidad' : 'unidades'}` })}>
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 18,
        background: t.id === 'light' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8,
        padding: 14, marginBottom: 14,
      }}>
        <button onClick={() => setQty(q => Math.max(1, q - 1))} style={{ width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 20 }}>−</button>
        <span style={{ fontSize: 28, fontFamily: 'monospace', color: t.text, minWidth: 44, textAlign: 'center' }}>{qty}</span>
        <button onClick={() => setQty(q => q + 1)} style={{ width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 20 }}>+</button>
      </div>
      <ResumenModal desc={`${qty} ${qty === 1 ? 'unidad' : 'unidades'}`} total={total} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// CARRITO ITEM
// ══════════════════════════════════════════════════════════════════════════════
function CartItem({ item, idx, onRemove, onQtyChange }) {
  const t = useTheme()
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 7,
      padding: '8px 14px', borderBottom: `1px solid ${t.border}`,
      animation: 'cIn .15s ease',
    }}>
      <style>{`@keyframes cIn{from{opacity:0;transform:translateX(6px)}to{opacity:1;transform:translateX(0)}}`}</style>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: t.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.nombre}</div>
        <div style={{ fontSize: 10, color: t.textMuted, marginTop: 1 }}>{item.desc}</div>
      </div>
      {item.tipo === 'simple' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <button onClick={() => onQtyChange(idx, -1)} style={{ width: 20, height: 20, background: t.card, border: `1px solid ${t.border}`, borderRadius: 4, color: t.text, cursor: 'pointer', fontSize: 12 }}>−</button>
          <span style={{ fontFamily: 'monospace', fontSize: 11, width: 20, textAlign: 'center' }}>{item.qty}</span>
          <button onClick={() => onQtyChange(idx, +1)} style={{ width: 20, height: 20, background: t.card, border: `1px solid ${t.border}`, borderRadius: 4, color: t.text, cursor: 'pointer', fontSize: 12 }}>+</button>
        </div>
      )}
      <div style={{ fontSize: 11, fontFamily: 'monospace', color: t.green, minWidth: 54, textAlign: 'right' }}>{cop(item.total)}</div>
      <span onClick={() => onRemove(idx)}
        style={{ color: t.textMuted, cursor: 'pointer', fontSize: 13, padding: '2px 4px', transition: 'color .1s' }}
        onMouseEnter={e => e.currentTarget.style.color = t.accent}
        onMouseLeave={e => e.currentTarget.style.color = t.textMuted}
      >✕</span>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB PRINCIPAL
// ══════════════════════════════════════════════════════════════════════════════
export default function TabVentasRapidas({ refreshKey }) {
  const t = useTheme()

  const { data: dataProd, loading, error } = useFetch('/productos',        [refreshKey])
  const { data: dataTop }                  = useFetch('/ventas/top?periodo=mes', [refreshKey])

  const [favKeys,   setFavKeys]   = useState(loadFavs)
  const [busq,      setBusq]      = useState('')
  const [carrito,   setCarrito]   = useState([])
  const [metodo,    setMetodo]    = useState('efectivo')
  const [vendedor,  setVendedor]  = useState('Dashboard')
  const [modalFrac, setModalFrac] = useState(null)
  const [modalCm,   setModalCm]   = useState(null)
  const [modalQty,  setModalQty]  = useState(null)
  const [toast,     setToast]     = useState(null)
  const [enviando,  setEnviando]  = useState(false)

  // ── Procesar productos ─────────────────────────────────────────────────────
  const productos = (dataProd?.productos || [])
    .filter(p => p.precio > 0)
    .map(p => ({ ...p, tipo: tipoProd(p) }))

  // Búsqueda
  const prodsFiltrados = busq.trim()
    ? productos.filter(p => p.nombre.toLowerCase().includes(busq.toLowerCase()))
    : productos

  // Favoritos
  const favs = productos.filter(p => favKeys.includes(p.key))

  // Top productos — match por nombre del top con key del catálogo
  const topNombres = (dataTop?.top || []).map(x => x.producto?.toLowerCase().trim() || '')
  const tops = productos.filter(p => {
    const nl = p.nombre.toLowerCase()
    return topNombres.some(tn => tn && (nl.includes(tn) || tn.includes(nl)))
  }).slice(0, 12)

  // Categorías ordenadas
  const catMap = {}
  prodsFiltrados.forEach(p => {
    const cat = p.categoria || 'Sin categoría'
    if (!catMap[cat]) catMap[cat] = []
    catMap[cat].push(p)
  })
  const catsOrdenadas = Object.keys(catMap).sort()

  // ── Favoritos toggle ───────────────────────────────────────────────────────
  const toggleFav = useCallback((key) => {
    setFavKeys(prev => {
      const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
      saveFavs(next)
      return next
    })
  }, [])

  // ── Click producto ─────────────────────────────────────────────────────────
  const clickProd = useCallback((prod) => {
    if (prod.tipo === 'fraccion') { setModalFrac(prod); return }
    if (prod.tipo === 'cm')       { setModalCm(prod);   return }
    // Simple: primer click = directo, segundo click = editar qty
    const ya = carrito.find(c => c.key === prod.key && c.tipo === 'simple')
    if (ya) { setModalQty(prod) }
    else {
      setCarrito(prev => [...prev, {
        id: Date.now(), key: prod.key, nombre: prod.nombre,
        precio: prod.precio, qty: 1, total: prod.precio,
        desc: '1 unidad', tipo: 'simple',
      }])
    }
  }, [carrito])

  // ── Confirmaciones ─────────────────────────────────────────────────────────
  const confirmarFrac = ({ unidades, fracKey, total, desc }) => {
    setCarrito(p => [...p, { id: Date.now(), key: modalFrac.key, nombre: modalFrac.nombre, precio: total, qty: 1, total, desc, tipo: 'fraccion' }])
    setModalFrac(null)
  }
  const confirmarCm = ({ cm, total, desc }) => {
    setCarrito(p => [...p, { id: Date.now(), key: modalCm.key, nombre: modalCm.nombre, precio: total, qty: 1, total, desc, tipo: 'cm' }])
    setModalCm(null)
  }
  const confirmarQty = ({ qty, total, desc }) => {
    setCarrito(prev => {
      const idx = prev.findIndex(c => c.key === modalQty.key && c.tipo === 'simple')
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], qty, total, desc }
        return next
      }
      return [...prev, { id: Date.now(), key: modalQty.key, nombre: modalQty.nombre, precio: modalQty.precio, qty, total, desc, tipo: 'simple' }]
    })
    setModalQty(null)
  }

  // ── Carrito ops ────────────────────────────────────────────────────────────
  const qtyChange = (idx, d) => setCarrito(prev => {
    const next = [...prev], it = { ...next[idx] }
    it.qty = Math.max(1, it.qty + d)
    it.total = it.precio * it.qty
    it.desc  = `${it.qty} ${it.qty === 1 ? 'unidad' : 'unidades'}`
    next[idx] = it; return next
  })
  const removeItem  = idx => setCarrito(p => p.filter((_, i) => i !== idx))
  const totalCarrito = carrito.reduce((s, c) => s + c.total, 0)

  // ── Registrar ──────────────────────────────────────────────────────────────
  const registrar = async () => {
    if (!carrito.length || enviando) return
    setEnviando(true)
    try {
      const res = await fetch(`${API_BASE}/venta-rapida`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          productos: carrito.map(c => ({ nombre: c.nombre, cantidad: c.qty, total: c.total })),
          metodo, vendedor,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCarrito([])
      setToast('✅ Venta registrada')
    } catch (e) {
      setToast(`⚠️ Error: ${e.message}`)
    } finally {
      setEnviando(false)
      setTimeout(() => setToast(null), 3000)
    }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error cargando productos: ${error}`} />

  // ── Render ─────────────────────────────────────────────────────────────────
  const seccionProps = { carrito, favKeys, onClickProd: clickProd, onFav: toggleFav }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 310px', gap: 16, alignItems: 'start' }}>

      {/* ══ PANEL IZQUIERDO ══ */}
      <div>
        {/* Búsqueda */}
        <div style={{ position: 'relative', marginBottom: 18 }}>
          <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: t.textMuted, pointerEvents: 'none' }}>🔍</span>
          <input
            value={busq} onChange={e => setBusq(e.target.value)}
            placeholder="Buscar producto..."
            style={{
              width: '100%', background: t.card, border: `1px solid ${t.border}`,
              borderRadius: 8, padding: '8px 10px 8px 30px',
              color: t.text, fontFamily: 'inherit', fontSize: 12, outline: 'none',
            }}
            onFocus={e => e.currentTarget.style.borderColor = t.accent + '88'}
            onBlur={e  => e.currentTarget.style.borderColor = t.border}
          />
        </div>

        {busq.trim() ? (
          /* Resultados de búsqueda */
          <Seccion icono="🔍" titulo={`"${busq}"`} cantidad={prodsFiltrados.length} productos={prodsFiltrados} {...seccionProps} />
        ) : (
          <>
            {/* ── Favoritos ── */}
            {favs.length > 0 ? (
              <Seccion icono="⭐" titulo="Favoritos" cantidad={favs.length} productos={favs} {...seccionProps} />
            ) : (
              <div style={{
                border: `1px dashed ${t.border}`, borderRadius: 9,
                padding: '12px 16px', marginBottom: 22,
                display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <span style={{ fontSize: 16, opacity: .4 }}>⭐</span>
                <span style={{ fontSize: 11, color: t.textMuted }}>
                  Marca la <strong style={{ color: '#fbbf24' }}>★</strong> en cualquier producto para agregarlo a favoritos
                </span>
              </div>
            )}

            {/* ── Top productos ── */}
            {tops.length > 0 && (
              <Seccion icono="🏆" titulo="Top productos del mes" cantidad={tops.length} productos={tops} {...seccionProps} />
            )}

            {/* ── Categorías ── */}
            {catsOrdenadas.map(cat => (
              <Seccion
                key={cat}
                icono={iconCat(cat)}
                titulo={catLabel(cat)}
                cantidad={catMap[cat].length}
                productos={catMap[cat]}
                {...seccionProps}
              />
            ))}
          </>
        )}
      </div>

      {/* ══ CARRITO ══ */}
      <div style={{
        background: t.card, border: `1px solid ${t.border}`,
        borderRadius: 11, overflow: 'hidden', position: 'sticky', top: 70,
      }}>
        {/* Header */}
        <div style={{
          padding: '12px 14px', borderBottom: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, letterSpacing: '.1em', textTransform: 'uppercase' }}>Carrito</span>
          <div style={{
            background: carrito.length ? t.accent : t.border,
            color: '#fff', fontSize: 9, fontWeight: 700,
            width: 18, height: 18, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background .2s',
          }}>
            {carrito.reduce((s, c) => s + (c.qty || 1), 0)}
          </div>
        </div>

        {/* Items */}
        <div style={{ maxHeight: 280, overflowY: 'auto' }}>
          {carrito.length === 0 ? (
            <div style={{ padding: '28px 14px', textAlign: 'center', color: t.textMuted, fontSize: 11, lineHeight: 1.9 }}>
              <div style={{ fontSize: 26, opacity: .25, marginBottom: 6 }}>🛒</div>
              Haz click en un producto<br />para agregarlo
            </div>
          ) : (
            carrito.map((item, idx) => (
              <CartItem key={item.id} item={item} idx={idx} onRemove={removeItem} onQtyChange={qtyChange} />
            ))
          )}
        </div>

        {/* Total */}
        {carrito.length > 0 && (
          <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.border}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em' }}>Total</span>
              <span style={{ fontSize: 20, fontFamily: 'monospace', fontWeight: 700, color: t.text }}>{cop(totalCarrito)}</span>
            </div>
          </div>
        )}

        {/* Vendedor */}
        <div style={{ padding: '8px 14px', borderTop: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', minWidth: 54 }}>Vendedor</span>
          <input
            value={vendedor} onChange={e => setVendedor(e.target.value)}
            style={{
              flex: 1, background: t.id === 'light' ? '#f8fafc' : '#111',
              border: `1px solid ${t.border}`, borderRadius: 5, color: t.text,
              fontSize: 11, padding: '4px 7px', fontFamily: 'inherit', outline: 'none',
            }}
          />
        </div>

        {/* Método de pago */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 5, padding: '8px 14px 12px' }}>
          {[
            { key: 'efectivo',      label: 'Efectivo',  icon: '💵' },
            { key: 'transferencia', label: 'Transfer.', icon: '📲' },
            { key: 'datafono',      label: 'Datáfono',  icon: '💳' },
          ].map(m => (
            <button key={m.key} onClick={() => setMetodo(m.key)} style={{
              padding: '7px 3px',
              background: metodo === m.key ? t.accentSub : (t.id === 'light' ? '#f8fafc' : '#0f0f0f'),
              border: `1px solid ${metodo === m.key ? t.accent : t.border}`,
              borderRadius: 7, color: metodo === m.key ? t.accent : t.textMuted,
              fontSize: 10, cursor: 'pointer', fontFamily: 'inherit',
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              transition: 'all .15s',
            }}>
              <span style={{ fontSize: 13 }}>{m.icon}</span>{m.label}
            </button>
          ))}
        </div>

        {/* Botón registrar */}
        <button
          onClick={registrar}
          disabled={!carrito.length || enviando}
          style={{
            margin: '0 14px 14px', padding: 12,
            background: carrito.length ? t.accent : t.border,
            color: carrito.length ? '#fff' : t.textMuted,
            border: 'none', borderRadius: 8, fontSize: 12, fontWeight: 600,
            cursor: carrito.length ? 'pointer' : 'not-allowed',
            fontFamily: 'inherit', letterSpacing: '.04em',
            width: 'calc(100% - 28px)', transition: 'all .15s',
          }}
        >
          {enviando ? 'Registrando...' : 'Registrar venta'}
        </button>
      </div>

      {/* Modales */}
      <ModalFraccion prod={modalFrac} onClose={() => setModalFrac(null)} onConfirm={confirmarFrac} />
      <ModalCm       prod={modalCm}   onClose={() => setModalCm(null)}   onConfirm={confirmarCm}  />
      <ModalQty      prod={modalQty}  onClose={() => setModalQty(null)}  onConfirm={confirmarQty} />

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 22, right: 22,
          background: t.card,
          border: `1px solid ${toast.includes('Error') ? t.accent : t.green}`,
          color: toast.includes('Error') ? t.accent : t.green,
          padding: '10px 16px', borderRadius: 9, fontSize: 12, fontWeight: 500,
          zIndex: 999, boxShadow: t.shadow,
          animation: 'tIn .25s cubic-bezier(.34,1.56,.64,1)',
        }}>
          <style>{`@keyframes tIn{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}`}</style>
          {toast}
        </div>
      )}
    </div>
  )
}
