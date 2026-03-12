import { useState, useEffect, useCallback } from 'react'
import { useTheme, useFetch, Spinner, ErrorMsg, cop, API_BASE } from '../components/shared.jsx'

// ─── Persistencia de favoritos en localStorage ───────────────────────────────
const FAV_KEY = 'vr_favoritos_v1'
function cargarFavs() {
  try { return JSON.parse(localStorage.getItem(FAV_KEY) || '[]') } catch { return [] }
}
function guardarFavs(keys) {
  try { localStorage.setItem(FAV_KEY, JSON.stringify(keys)) } catch {}
}

// ─── Íconos por categoría ─────────────────────────────────────────────────────
function iconCat(cat = '') {
  const c = cat.toLowerCase()
  if (c.includes('pintura') || c.includes('disolvente')) return '🎨'
  if (c.includes('ferreteria') || c.includes('ferretería')) return '🔧'
  if (c.includes('tornillo') || c.includes('puntilla')) return '🔩'
  if (c.includes('lija')) return '📄'
  if (c.includes('thinner') || c.includes('varsol') || c.includes('solvente')) return '🧪'
  return '📦'
}

// ─── Tipo de producto ─────────────────────────────────────────────────────────
function tipoProducto(prod) {
  if (prod.nombre?.toLowerCase().includes('esmeril')) return 'cm'
  if (prod.precios_fraccion && Object.keys(prod.precios_fraccion).length > 0) return 'fraccion'
  return 'simple'
}

// ─── Formatear descripción de cantidad ───────────────────────────────────────
function fmtDesc(qty, frac) {
  const parts = []
  if (qty > 0) parts.push(`${qty} ${qty === 1 ? 'und' : 'und'}`)
  if (frac) parts.push(frac)
  return parts.join(' + ') || '—'
}

// ══════════════════════════════════════════════════════════════════════════════
// PRODUCT CARD
// ══════════════════════════════════════════════════════════════════════════════
function ProductCard({ prod, onClick, enCarrito, isFav, onToggleFav, modoFavoritos }) {
  const t = useTheme()
  const tipo = tipoProducto(prod)
  const hint = tipo === 'fraccion' ? '½' : tipo === 'cm' ? 'cm' : null

  return (
    <div
      onClick={() => onClick(prod)}
      style={{
        background:    enCarrito ? t.accentSub : t.card,
        border:        `1px solid ${enCarrito ? t.accent + '66' : t.border}`,
        borderRadius:  9,
        padding:       '11px 11px 9px',
        cursor:        'pointer',
        position:      'relative',
        transition:    'all .15s',
        userSelect:    'none',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = t.accent + '99'
        e.currentTarget.style.transform = 'translateY(-1px)'
        e.currentTarget.style.boxShadow = `0 4px 12px rgba(0,0,0,.3)`
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = enCarrito ? t.accent + '66' : t.border
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      {/* Botón favorito */}
      <div
        onClick={e => { e.stopPropagation(); onToggleFav(prod.key) }}
        title={isFav ? 'Quitar de favoritos' : 'Agregar a favoritos'}
        style={{
          position: 'absolute', top: 7, right: 7,
          fontSize: 12, color: isFav ? '#fbbf24' : t.textMuted,
          cursor: 'pointer', transition: 'color .15s', zIndex: 2,
          padding: '2px',
        }}
      >
        {isFav ? '★' : '☆'}
      </div>

      {/* Badge tipo */}
      {hint && (
        <div style={{
          position: 'absolute', top: 7, left: 8,
          fontSize: 9, color: t.textMuted,
          background: t.border, borderRadius: 4, padding: '1px 4px',
          fontFamily: 'monospace',
        }}>
          {hint}
        </div>
      )}

      <div style={{ fontSize: 18, marginBottom: 5, marginTop: hint ? 8 : 0 }}>
        {iconCat(prod.categoria)}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, color: t.text, lineHeight: 1.3, marginBottom: 3, paddingRight: 14 }}>
        {prod.nombre}
      </div>
      <div style={{ fontSize: 11, color: t.green, fontFamily: 'monospace' }}>
        {cop(prod.precio)}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// SECCIÓN DE PRODUCTOS
// ══════════════════════════════════════════════════════════════════════════════
function SeccionProductos({ titulo, productos, carrito, favKeys, onClickProd, onToggleFav, modoFavoritos }) {
  const t = useTheme()
  if (!productos.length) return null
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{
        fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
        letterSpacing: '.12em', marginBottom: 9,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {titulo}
        <div style={{ flex: 1, height: 1, background: t.border }} />
        <span style={{ color: t.textMuted }}>{productos.length}</span>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
        gap: 7,
      }}>
        {productos.map(p => (
          <ProductCard
            key={p.key}
            prod={p}
            onClick={onClickProd}
            enCarrito={carrito.some(c => c.key === p.key && c.tipo === 'simple')}
            isFav={favKeys.includes(p.key)}
            onToggleFav={onToggleFav}
            modoFavoritos={modoFavoritos}
          />
        ))}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL BASE
// ══════════════════════════════════════════════════════════════════════════════
function Modal({ show, onClose, title, subtitle, children, onConfirm, confirmLabel = 'Agregar al carrito', confirmDisabled }) {
  const t = useTheme()
  if (!show) return null
  return (
    <div
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
      style={{
        position: 'fixed', inset: 0, background: '#000000bb',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 300, padding: 16,
      }}
    >
      <div style={{
        background: t.card, border: `1px solid ${t.accent}44`,
        borderRadius: 14, width: '100%', maxWidth: 390,
        animation: 'modalIn .2s cubic-bezier(.34,1.4,.64,1)',
      }}>
        <style>{`@keyframes modalIn{from{opacity:0;transform:scale(.93) translateY(8px)}to{opacity:1;transform:scale(1) translateY(0)}}`}</style>
        <div style={{ padding: '16px 18px 12px', borderBottom: `1px solid ${t.border}` }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: t.text }}>{title}</div>
          {subtitle && <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>{subtitle}</div>}
        </div>
        <div style={{ padding: '14px 18px' }}>{children}</div>
        <div style={{ display: 'flex', gap: 8, padding: '0 18px 18px' }}>
          <button onClick={onClose} style={{
            flex: 1, padding: 10, background: t.border, border: 'none',
            borderRadius: 8, color: t.textMuted, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
          }}>Cancelar</button>
          <button onClick={onConfirm} disabled={confirmDisabled} style={{
            flex: 2, padding: 10, background: confirmDisabled ? t.border : t.accent,
            border: 'none', borderRadius: 8, color: confirmDisabled ? t.textMuted : '#fff',
            cursor: confirmDisabled ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
            fontSize: 12, fontWeight: 600, transition: 'background .15s',
          }}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// RESUMEN MODAL (fila total)
// ══════════════════════════════════════════════════════════════════════════════
function ModalResumen({ desc, total }) {
  const t = useTheme()
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      background: t.id === 'light' ? '#f8fafc' : '#0f0f0f',
      border: `1px solid ${t.border}`, borderRadius: 8,
      padding: '10px 13px', marginBottom: 14,
    }}>
      <span style={{ fontSize: 12, color: t.textMuted }}>{desc || '—'}</span>
      <span style={{ fontSize: 17, fontFamily: 'monospace', color: t.accent, fontWeight: 700 }}>{cop(total)}</span>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL FRACCIÓN
// ══════════════════════════════════════════════════════════════════════════════
function ModalFraccion({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [unidades, setUnidades] = useState(0)
  const [fracKey, setFracKey] = useState(null)

  const fracs = prod?.precios_fraccion || {}
  const totalFrac = fracKey && fracs[fracKey] ? fracs[fracKey].precio : 0
  const total = unidades * (prod?.precio || 0) + totalFrac
  const desc = fmtDesc(unidades, fracKey)
  const valid = unidades > 0 || fracKey

  return (
    <Modal
      show={!!prod} onClose={onClose}
      title={prod?.nombre}
      subtitle={`Precio unidad: ${cop(prod?.precio)}`}
      onConfirm={() => onConfirm({ unidades, fracKey, total, desc })}
      confirmDisabled={!valid}
    >
      {/* Unidades enteras */}
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Unidades completas
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        background: t.id === 'light' ? '#f8fafc' : '#111',
        border: `1px solid ${t.border}`, borderRadius: 8, padding: '9px 13px', marginBottom: 14,
      }}>
        <span style={{ flex: 1, fontSize: 12, color: t.textMuted }}>Galones / unidades</span>
        {[-1, 1].map(d => (
          <button key={d} onClick={() => setUnidades(u => Math.max(0, u + d))} style={{
            width: 26, height: 26, background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 5, color: t.text, cursor: 'pointer', fontSize: 15,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>{d < 0 ? '−' : '+'}</button>
        )).reduce((a, b, i) => [a, <span key="v" style={{ fontFamily: 'monospace', fontSize: 16, color: t.text, minWidth: 22, textAlign: 'center' }}>{unidades}</span>, b])}
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
        {/* Opción "ninguna" */}
        <div
          onClick={() => setFracKey(null)}
          style={{
            padding: '8px 5px', borderRadius: 7, cursor: 'pointer', textAlign: 'center',
            background: !fracKey ? t.accentSub : (t.id === 'light' ? '#f8fafc' : '#111'),
            border: `1px solid ${!fracKey ? t.accent : t.border}`, transition: 'all .15s',
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: !fracKey ? t.accent : t.textMuted }}>Ninguna</div>
          <div style={{ fontSize: 9, color: t.textMuted, marginTop: 1 }}>solo unidades</div>
        </div>
        {Object.entries(fracs).map(([k, v]) => (
          <div
            key={k}
            onClick={() => setFracKey(k)}
            style={{
              padding: '8px 5px', borderRadius: 7, cursor: 'pointer', textAlign: 'center',
              background: fracKey === k ? t.accentSub : (t.id === 'light' ? '#f8fafc' : '#111'),
              border: `1px solid ${fracKey === k ? t.accent : t.border}`, transition: 'all .15s',
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 700, color: fracKey === k ? t.accent : t.text }}>{k}</div>
            <div style={{ fontSize: 10, color: t.green, fontFamily: 'monospace', marginTop: 1 }}>{cop(v.precio)}</div>
          </div>
        ))}
      </div>

      <ModalResumen desc={desc} total={total} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL CM (lija esmeril)
// ══════════════════════════════════════════════════════════════════════════════
function ModalCm({ prod, onClose, onConfirm }) {
  const [cm, setCm] = useState('')
  const t = useTheme()
  const pxcm = prod ? Math.round((prod.precio || 0) / 100) : 0
  const cmNum = parseInt(cm) || 0
  const total = cmNum * pxcm

  return (
    <Modal
      show={!!prod} onClose={onClose}
      title={prod?.nombre}
      subtitle={`Pliego completo: ${cop(prod?.precio)} · ${cop(pxcm)}/cm`}
      onConfirm={() => onConfirm({ cm: cmNum, total, desc: `${cmNum} cm` })}
      confirmDisabled={cmNum <= 0}
    >
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad en centímetros
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: t.id === 'light' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8,
        padding: '10px 14px', marginBottom: 8,
      }}>
        <input
          autoFocus
          type="number" min="1" value={cm}
          onChange={e => setCm(e.target.value)}
          style={{
            flex: 1, background: 'transparent', border: 'none',
            color: t.text, fontSize: 22, fontFamily: 'monospace',
            outline: 'none', width: 80, textAlign: 'center',
          }}
          placeholder="0"
        />
        <span style={{ fontSize: 13, color: t.textMuted }}>cm</span>
      </div>
      <div style={{ fontSize: 11, color: t.textMuted, textAlign: 'center', marginBottom: 14 }}>
        Precio por cm: <span style={{ color: t.green, fontFamily: 'monospace' }}>{cop(pxcm)}</span>
      </div>
      <ModalResumen desc={`${cmNum} cm`} total={total} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL QTY SIMPLE (productos unitarios con edición de cantidad)
// ══════════════════════════════════════════════════════════════════════════════
function ModalQtySimple({ prod, onClose, onConfirm }) {
  const [qty, setQty] = useState(1)
  const t = useTheme()
  const total = qty * (prod?.precio || 0)

  return (
    <Modal
      show={!!prod} onClose={onClose}
      title={prod?.nombre}
      subtitle={`Precio unitario: ${cop(prod?.precio)}`}
      onConfirm={() => onConfirm({ qty, total, desc: `${qty} ${qty === 1 ? 'unidad' : 'unidades'}` })}
    >
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16,
        background: t.id === 'light' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8, padding: 14, marginBottom: 14,
      }}>
        <button onClick={() => setQty(q => Math.max(1, q - 1))} style={{
          width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`,
          borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 18,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>−</button>
        <span style={{ fontSize: 26, fontFamily: 'monospace', color: t.text, minWidth: 44, textAlign: 'center' }}>{qty}</span>
        <button onClick={() => setQty(q => q + 1)} style={{
          width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`,
          borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 18,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>+</button>
      </div>
      <ModalResumen desc={`${qty} ${qty === 1 ? 'unidad' : 'unidades'}`} total={total} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// CARRITO ITEM
// ══════════════════════════════════════════════════════════════════════════════
function CartItem({ item, idx, onRemove, onQtyChange }) {
  const t = useTheme()
  const esSimple = item.tipo === 'simple'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 7,
      padding: '9px 14px', borderBottom: `1px solid ${t.border}`,
      animation: 'cartIn .15s ease',
    }}>
      <style>{`@keyframes cartIn{from{opacity:0;transform:translateX(6px)}to{opacity:1;transform:translateX(0)}}`}</style>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, color: t.text, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {item.nombre}
        </div>
        <div style={{ fontSize: 10, color: t.textMuted, marginTop: 1 }}>{item.desc}</div>
      </div>
      {esSimple && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          {[-1, 1].map(d => (
            <button key={d} onClick={() => onQtyChange(idx, d)} style={{
              width: 20, height: 20, background: t.card, border: `1px solid ${t.border}`,
              borderRadius: 4, color: t.text, cursor: 'pointer', fontSize: 12,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>{d < 0 ? '−' : '+'}</button>
          )).reduce((a, b, i) => [a, <span key="v" style={{ fontFamily: 'monospace', fontSize: 11, color: t.text, width: 20, textAlign: 'center' }}>{item.qty}</span>, b])}
        </div>
      )}
      <div style={{ fontSize: 11, fontFamily: 'monospace', color: t.green, minWidth: 54, textAlign: 'right' }}>
        {cop(item.total)}
      </div>
      <span onClick={() => onRemove(idx)} style={{ color: t.textMuted, cursor: 'pointer', fontSize: 13, padding: '2px 3px' }}
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

  // Datos
  const { data: dataProd, loading: loadProd, error: errProd } = useFetch('/productos', [refreshKey])
  const { data: dataTop,  loading: loadTop  }                 = useFetch('/ventas/top?periodo=mes', [refreshKey])

  // Favoritos (persistidos en localStorage)
  const [favKeys, setFavKeys] = useState(cargarFavs)

  // Búsqueda
  const [busq, setBusq] = useState('')

  // Carrito
  const [carrito, setCarrito] = useState([])
  const [metodo, setMetodo]   = useState('efectivo')
  const [vendedor, setVendedor] = useState('Dashboard')

  // Modales
  const [modalFrac, setModalFrac]     = useState(null) // prod activo
  const [modalCm,   setModalCm]       = useState(null)
  const [modalQty,  setModalQty]      = useState(null)

  // Registro
  const [registrando, setRegistrando] = useState(false)
  const [toastMsg,    setToastMsg]    = useState(null)

  // ── Procesar catálogo ──────────────────────────────────────────────────────
  const productos = (dataProd?.productos || [])
    .filter(p => p.precio > 0)
    .map(p => ({
      ...p,
      tipo:             tipoProducto(p),
      precios_fraccion: p.precios_fraccion || null,
    }))

  const productosFiltrados = busq.trim()
    ? productos.filter(p => p.nombre.toLowerCase().includes(busq.toLowerCase()))
    : productos

  // Sección favoritos
  const favs = productos.filter(p => favKeys.includes(p.key))

  // Sección top (usando keys del top)
  const topKeys = (dataTop?.top || []).map(t => t.producto?.toLowerCase().trim())
  const topProds = productos.filter(p =>
    topKeys.some(tk => p.nombre.toLowerCase().includes(tk) || tk.includes(p.nombre.toLowerCase()))
  ).slice(0, 12)

  // Agrupar por categoría (excluyendo los números del prefijo)
  const categorias = {}
  productosFiltrados.forEach(p => {
    const cat = p.categoria?.replace(/^\d+\s*/, '') || 'Sin categoría'
    if (!categorias[cat]) categorias[cat] = []
    categorias[cat].push(p)
  })

  // ── Favoritos toggle ───────────────────────────────────────────────────────
  const toggleFav = useCallback((key) => {
    setFavKeys(prev => {
      const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
      guardarFavs(next)
      return next
    })
  }, [])

  // ── Click en producto ──────────────────────────────────────────────────────
  const handleClickProd = useCallback((prod) => {
    if (prod.tipo === 'fraccion') {
      setModalFrac(prod)
    } else if (prod.tipo === 'cm') {
      setModalCm(prod)
    } else {
      // Simple: si ya está en el carrito, editar cantidad
      const existente = carrito.find(c => c.key === prod.key && c.tipo === 'simple')
      if (existente) {
        setModalQty(prod)
      } else {
        // Primer click → agregar directo con qty 1
        setCarrito(prev => [...prev, {
          id:    Date.now(),
          key:   prod.key,
          nombre: prod.nombre,
          precio: prod.precio,
          qty:    1,
          total:  prod.precio,
          desc:   '1 unidad',
          tipo:   'simple',
        }])
      }
    }
  }, [carrito])

  // ── Confirmaciones modales ─────────────────────────────────────────────────
  const confirmarFraccion = ({ unidades, fracKey, total, desc }) => {
    setCarrito(prev => [...prev, {
      id:    Date.now(),
      key:   modalFrac.key,
      nombre: modalFrac.nombre,
      precio: total,
      qty:    1, total, desc, tipo: 'fraccion',
    }])
    setModalFrac(null)
  }

  const confirmarCm = ({ cm, total, desc }) => {
    setCarrito(prev => [...prev, {
      id:    Date.now(),
      key:   modalCm.key,
      nombre: modalCm.nombre,
      precio: total,
      qty:    1, total, desc, tipo: 'cm',
    }])
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
  const qtyChange = (idx, delta) => {
    setCarrito(prev => {
      const next = [...prev]
      const item = { ...next[idx] }
      item.qty = Math.max(1, item.qty + delta)
      item.total = item.precio * item.qty
      item.desc = `${item.qty} ${item.qty === 1 ? 'unidad' : 'unidades'}`
      next[idx] = item
      return next
    })
  }

  const removeItem = (idx) => setCarrito(prev => prev.filter((_, i) => i !== idx))

  const totalCarrito = carrito.reduce((s, c) => s + c.total, 0)

  // ── Registrar venta ────────────────────────────────────────────────────────
  const registrar = async () => {
    if (!carrito.length || registrando) return
    setRegistrando(true)
    try {
      const res = await fetch(`${API_BASE}/venta-rapida`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          productos: carrito.map(c => ({
            nombre:    c.nombre,
            cantidad:  c.tipo === 'cm' ? c.desc : (c.qty),
            total:     c.total,
          })),
          metodo,
          vendedor,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setCarrito([])
      setToastMsg('✅ Venta registrada correctamente')
    } catch (e) {
      setToastMsg(`⚠️ Error: ${e.message}`)
    } finally {
      setRegistrando(false)
      setTimeout(() => setToastMsg(null), 3000)
    }
  }

  if (loadProd) return <Spinner />
  if (errProd)  return <ErrorMsg msg={`Error cargando catálogo: ${errProd}`} />

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 310px', gap: 16, alignItems: 'start' }}>

      {/* ── Panel izquierdo ── */}
      <div>
        {/* Búsqueda */}
        <div style={{ position: 'relative', marginBottom: 14 }}>
          <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: t.textMuted, pointerEvents: 'none' }}>🔍</span>
          <input
            value={busq}
            onChange={e => setBusq(e.target.value)}
            placeholder="Buscar producto..."
            style={{
              width: '100%', background: t.card, border: `1px solid ${t.border}`,
              borderRadius: 8, padding: '8px 10px 8px 30px', color: t.text,
              fontFamily: 'inherit', fontSize: 12, outline: 'none',
            }}
            onFocus={e => e.currentTarget.style.borderColor = t.accent + '88'}
            onBlur={e  => e.currentTarget.style.borderColor = t.border}
          />
        </div>

        {busq.trim() ? (
          // Resultados de búsqueda
          <SeccionProductos
            titulo={`Resultados "${busq}"`}
            productos={productosFiltrados}
            carrito={carrito} favKeys={favKeys}
            onClickProd={handleClickProd} onToggleFav={toggleFav}
          />
        ) : (
          <>
            {/* Favoritos */}
            {favs.length > 0 ? (
              <SeccionProductos
                titulo="⭐ Favoritos"
                productos={favs}
                carrito={carrito} favKeys={favKeys}
                onClickProd={handleClickProd} onToggleFav={toggleFav}
              />
            ) : (
              <div style={{
                border: `1px dashed ${t.border}`, borderRadius: 9,
                padding: '14px 16px', marginBottom: 16,
                display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <span style={{ fontSize: 18, opacity: .4 }}>☆</span>
                <span style={{ fontSize: 11, color: t.textMuted }}>
                  Haz click en <strong style={{ color: t.yellow }}>★</strong> en cualquier producto para agregarlo a favoritos
                </span>
              </div>
            )}

            {/* Top productos */}
            {topProds.length > 0 && (
              <SeccionProductos
                titulo="🏆 Top productos"
                productos={topProds}
                carrito={carrito} favKeys={favKeys}
                onClickProd={handleClickProd} onToggleFav={toggleFav}
              />
            )}

            {/* Categorías */}
            {Object.entries(categorias).map(([cat, prods]) => (
              <SeccionProductos
                key={cat}
                titulo={`${iconCat(cat)} ${cat}`}
                productos={prods}
                carrito={carrito} favKeys={favKeys}
                onClickProd={handleClickProd} onToggleFav={toggleFav}
              />
            ))}
          </>
        )}
      </div>

      {/* ── Carrito ── */}
      <div style={{
        background: t.card, border: `1px solid ${t.border}`,
        borderRadius: 11, overflow: 'hidden', position: 'sticky', top: 70,
      }}>
        {/* Header carrito */}
        <div style={{
          padding: '12px 14px', borderBottom: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, letterSpacing: '.1em', textTransform: 'uppercase' }}>
            Carrito
          </span>
          <div style={{
            background: carrito.length > 0 ? t.accent : t.border,
            color: '#fff', fontSize: 9, fontWeight: 700,
            width: 18, height: 18, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'background .2s',
          }}>
            {carrito.reduce((s, c) => s + (c.qty || 1), 0)}
          </div>
        </div>

        {/* Items */}
        <div style={{ maxHeight: 260, overflowY: 'auto' }}>
          {carrito.length === 0 ? (
            <div style={{ padding: '28px 14px', textAlign: 'center', color: t.textMuted, fontSize: 11, lineHeight: 1.8 }}>
              <div style={{ fontSize: 24, opacity: .3, marginBottom: 6 }}>🛒</div>
              Haz click en un producto<br />para agregarlo
            </div>
          ) : (
            carrito.map((item, idx) => (
              <CartItem key={item.id} item={item} idx={idx} onRemove={removeItem} onQtyChange={qtyChange} />
            ))
          )}
        </div>

        {/* Resumen total */}
        {carrito.length > 0 && (
          <div style={{ padding: '12px 14px', borderTop: `1px solid ${t.border}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: 10, color: t.textMuted }}>{carrito.length} producto{carrito.length > 1 ? 's' : ''}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', paddingTop: 6, borderTop: `1px solid ${t.border}` }}>
              <span style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em' }}>Total</span>
              <span style={{ fontSize: 20, fontFamily: 'monospace', fontWeight: 700, color: t.text }}>{cop(totalCarrito)}</span>
            </div>
          </div>
        )}

        {/* Vendedor */}
        <div style={{ padding: '8px 14px', borderTop: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', minWidth: 52 }}>Vendedor</span>
          <input
            value={vendedor}
            onChange={e => setVendedor(e.target.value)}
            style={{
              flex: 1, background: t.id === 'light' ? '#f8fafc' : '#111',
              border: `1px solid ${t.border}`, borderRadius: 5, color: t.text,
              fontSize: 11, padding: '4px 7px', fontFamily: 'inherit', outline: 'none',
            }}
          />
        </div>

        {/* Método de pago */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 5, padding: '0 14px 12px' }}>
          {[
            { key: 'efectivo',      label: 'Efectivo',  icon: '💵' },
            { key: 'transferencia', label: 'Transfer.', icon: '📲' },
            { key: 'datafono',      label: 'Datáfono',  icon: '💳' },
          ].map(m => (
            <button
              key={m.key}
              onClick={() => setMetodo(m.key)}
              style={{
                padding: '7px 3px',
                background: metodo === m.key ? t.accentSub : (t.id === 'light' ? '#f8fafc' : '#0f0f0f'),
                border: `1px solid ${metodo === m.key ? t.accent : t.border}`,
                borderRadius: 7, color: metodo === m.key ? t.accent : t.textMuted,
                fontSize: 10, cursor: 'pointer', fontFamily: 'inherit',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
                transition: 'all .15s',
              }}
            >
              <span style={{ fontSize: 13 }}>{m.icon}</span>
              {m.label}
            </button>
          ))}
        </div>

        {/* Botón registrar */}
        <button
          onClick={registrar}
          disabled={carrito.length === 0 || registrando}
          style={{
            margin: '0 14px 14px', padding: 12,
            background: carrito.length === 0 ? t.border : t.accent,
            color: carrito.length === 0 ? t.textMuted : '#fff',
            border: 'none', borderRadius: 8, fontSize: 12, fontWeight: 600,
            cursor: carrito.length === 0 ? 'not-allowed' : 'pointer',
            fontFamily: 'inherit', letterSpacing: '.04em',
            width: 'calc(100% - 28px)', transition: 'all .15s',
          }}
        >
          {registrando ? 'Registrando...' : 'Registrar venta'}
        </button>
      </div>

      {/* Modales */}
      <ModalFraccion  prod={modalFrac} onClose={() => setModalFrac(null)} onConfirm={confirmarFraccion} />
      <ModalCm        prod={modalCm}   onClose={() => setModalCm(null)}   onConfirm={confirmarCm} />
      <ModalQtySimple prod={modalQty}  onClose={() => setModalQty(null)}  onConfirm={confirmarQty} />

      {/* Toast */}
      {toastMsg && (
        <div style={{
          position: 'fixed', bottom: 22, right: 22,
          background: t.card,
          border: `1px solid ${toastMsg.includes('Error') ? t.accent : t.green}`,
          color: toastMsg.includes('Error') ? t.accent : t.green,
          padding: '10px 16px', borderRadius: 9, fontSize: 12, fontWeight: 500,
          zIndex: 999, boxShadow: t.shadow,
          animation: 'toastIn .25s cubic-bezier(.34,1.56,.64,1)',
        }}>
          <style>{`@keyframes toastIn{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}`}</style>
          {toastMsg}
        </div>
      )}
    </div>
  )
}
