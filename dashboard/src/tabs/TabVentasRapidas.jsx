import { useState, useCallback, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useTheme, useFetch, Spinner, ErrorMsg, cop, API_BASE } from '../components/shared.jsx'


// ── Hook detección móvil ──────────────────────────────────────────────────────
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setIsMobile(window.innerWidth < 768)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return isMobile
}

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


// ══════════════════════════════════════════════════════════════════════════════
// SUBCATEGORÍAS — misma lógica que /productos en el bot
// ══════════════════════════════════════════════════════════════════════════════
const nl = s => (s || '').toLowerCase()

const SUBCATS = {
  '1 artículos de ferreteria': [
    { key: 'ferr_brochas',     icono: '🖌️', label: 'Brochas / Rodillos', fn: p => nl(p.nombre).includes('brocha') || nl(p.nombre).includes('rodillo') },
    { key: 'ferr_lijas',       icono: '📏', label: 'Lijas',               fn: p => nl(p.nombre).includes('lija')    || nl(p.nombre).includes('esmeril') },
    { key: 'ferr_cintas',      icono: '🔗', label: 'Cintas',              fn: p => nl(p.nombre).includes('cinta')   || nl(p.nombre).includes('pele')  || nl(p.nombre).includes('enmascarar') },
    { key: 'ferr_cerraduras',  icono: '🔒', label: 'Cerraduras',          fn: p => ['cerradura','candado','cerrojo','falleba'].some(k => nl(p.nombre).includes(k)) },
    { key: 'ferr_brocas',      icono: '🪚', label: 'Brocas / Discos',     fn: p => nl(p.nombre).includes('broca')   || nl(p.nombre).includes('disco') },
    { key: 'ferr_herr',        icono: '🔧', label: 'Herramientas',        fn: p => ['martillo','metro','destornillador','exacto','espatula','espátula','tijera','formon','grapadora','machete','taladro','llave','pulidora'].some(k => nl(p.nombre).includes(k)) },
    { key: 'ferr_varios',      icono: '📦', label: 'Varios',              fn: p => !['brocha','rodillo','lija','esmeril','cinta','pele','enmascarar','cerradura','candado','cerrojo','falleba','broca','disco','martillo','metro','destornillador','exacto','espatula','tijera','formon','grapadora','machete','taladro','llave','pulidora'].some(k => nl(p.nombre).includes(k)) },
  ],
  '2 pinturas y disolventes': [
    { key: 'pint_vinilo',    icono: '🖌️', label: 'Vinilo / Cuñetes',     fn: p => nl(p.nombre).includes('vinilo') || /cu[ñn]ete/i.test(p.nombre) },
    { key: 'pint_esmalte',   icono: '🎨', label: 'Esmalte / Anticorr.',  fn: p => nl(p.nombre).includes('esmalte') || nl(p.nombre).includes('anticorrosivo') },
    { key: 'pint_laca',      icono: '🪄', label: 'Laca',                 fn: p => nl(p.nombre).includes('laca') },
    { key: 'pint_thinner',   icono: '🧪', label: 'Thinner / Varsol',     fn: p => nl(p.nombre).includes('thinner') || nl(p.nombre).includes('varsol') || nl(p.nombre).includes('tiner') },
    { key: 'pint_poli',      icono: '💧', label: 'Poliuretano',          fn: p => nl(p.nombre).includes('poliuretano') || nl(p.nombre).includes('poliamida') },
    { key: 'pint_aerosol',   icono: '🎭', label: 'Aerosol',              fn: p => nl(p.nombre).includes('aerosol') || nl(p.nombre).includes('aersosol') },
    { key: 'pint_sellador',  icono: '🧴', label: 'Sellador / Masilla',   fn: p => nl(p.nombre).includes('sellador') || nl(p.nombre).includes('masilla') },
    { key: 'pint_otros',     icono: '🎨', label: 'Otros',                fn: p => !['vinilo','esmalte','anticorrosivo','laca','thinner','varsol','tiner','poliuretano','poliamida','aerosol','aersosol','sellador','masilla'].some(k => nl(p.nombre).includes(k)) },
  ],
  '3 tornilleria': [
    { key: 'torn_dry6',      icono: '⚙️', label: 'Drywall ×6',           fn: p => nl(p.nombre).includes('drywall') && /6x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_dry8',      icono: '⚙️', label: 'Drywall ×8',           fn: p => nl(p.nombre).includes('drywall') && /8x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_dry10',     icono: '⚙️', label: 'Drywall ×10',          fn: p => nl(p.nombre).includes('drywall') && /10x/.test(nl(p.nombre).replace(/ /g,'')) },
    { key: 'torn_hex',       icono: '🔩', label: 'Hex Galvanizado',       fn: p => nl(p.nombre).includes('hex') && (nl(p.nombre).includes('tornillo') || nl(p.nombre).includes('tuerca') || (nl(p.nombre).includes('arandela') && nl(p.nombre).includes('galv'))) },
    { key: 'torn_estufa',    icono: '🔩', label: 'Estufa',                fn: p => nl(p.nombre).includes('estufa') },
    { key: 'torn_puntillas', icono: '📌', label: 'Puntillas',             fn: p => nl(p.nombre).includes('puntilla') },
    { key: 'torn_tirafondo', icono: '🔩', label: 'Tira Fondo',            fn: p => nl(p.nombre).includes('tira fondo') },
    { key: 'torn_arandelas', icono: '⚙️', label: 'Arandelas / Chazos',   fn: p => (nl(p.nombre).includes('arandela') || nl(p.nombre).includes('chazo')) && !nl(p.nombre).includes('galv') },
  ],
  '4 impermeabilizantes y materiales de construcción': [],
  '5 materiales electricos': [],
}

// Ordenar tornillería: Drywall primero (6×→8×→10×), luego el resto por precio
function ordenarTornilleria(prods) {
  const isDry = p => nl(p.nombre).includes('drywall') && nl(p.nombre).includes('tornillo')
  const drySize = p => {
    const m = nl(p.nombre).replace(/ /g,'').match(/(\d+)x/)
    return m ? parseInt(m[1]) : 99
  }
  const dryLen = p => {
    const m = nl(p.nombre).replace(/ /g,'').match(/x(\d+(?:\.\d+)?)/)
    return m ? parseFloat(m[1]) : 999
  }
  const dry   = prods.filter(isDry).sort((a,b) => drySize(a)-drySize(b) || dryLen(a)-dryLen(b))
  const resto = prods.filter(p => !isDry(p)).sort((a,b) => a.precio - b.precio)
  return [...dry, ...resto]
}

// ── Tipo de producto ──────────────────────────────────────────────────────────
function tipoProd(prod) {
  if (prod.nombre?.toLowerCase().includes('esmeril')) return 'cm'
  if ((prod.unidad_medida || '').toUpperCase() === 'MLT') return 'mlt'
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
          {tipo === 'cm' ? 'cm' : tipo === 'mlt' ? 'ml' : '½'}
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
function Seccion({ icono, titulo, cantidad, productos, carrito, favKeys, onClickProd, onFav, columnas = 6 }) {
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
        gridTemplateColumns: `repeat(${columnas}, 1fr)`,
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
  return createPortal(
    <div
      onMouseDown={e => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, background: '#000000cc',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9998, padding: 16,
      }}
    >
      <div style={{
        background: t.card, border: `1px solid ${t.accent}44`,
        borderRadius: 14, width: '100%', maxWidth: 390,
        maxHeight: '90vh', overflowY: 'auto',
        animation: 'mIn .2s cubic-bezier(.34,1.4,.64,1)',
      }}>
        <style>{`@keyframes mIn{from{opacity:0;transform:scale(.92) translateY(10px)}to{opacity:1;transform:scale(1) translateY(0)}} input[type=number]::-webkit-inner-spin-button,input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}`}</style>
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
    </div>,
    document.body
  )
}

function PrecioEditor({ precioCalc, precioFinal, onChange, desc }) {
  const t = useTheme()
  const mod = precioFinal !== precioCalc
  return (
    <div style={{
      background: t.id === 'caramelo' ? '#f8fafc' : '#0f0f0f',
      border: `1px solid ${mod ? t.yellow + '88' : t.border}`,
      borderRadius: 8, padding: '10px 13px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 2 }}>{desc || '—'}</div>
          {mod && <div style={{ fontSize: 9, color: t.yellow }}>✏️ Precio especial · base {cop(precioCalc)}</div>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: 13, color: t.textMuted }}>$</span>
          <input
            type="number" min="0"
            value={precioFinal === 0 ? '' : precioFinal}
            onChange={e => onChange(parseInt(e.target.value) || 0)}
            style={{
              width: 100, background: 'transparent', border: 'none',
              borderBottom: `1px solid ${mod ? t.yellow : t.accent + '66'}`,
              color: mod ? t.yellow : t.accent,
              fontSize: 18, fontFamily: 'monospace', fontWeight: 700,
              outline: 'none', textAlign: 'right', padding: '2px 0',
              MozAppearance: 'textfield', appearance: 'textfield',
            }}
          />
        </div>
      </div>
      {mod && (
        <button onClick={() => onChange(precioCalc)} style={{
          marginTop: 5, fontSize: 9, color: t.textMuted, background: 'none',
          border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit',
        }}>↩ Volver al precio original</button>
      )}
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
  const [precioCustom, setPrecioCustom] = useState(null)
  if (!prod) return null

  const fracs    = prod.precios_fraccion || {}

  // Orden canónico: mayor fracción primero
  const DECIMAL_MAP = { '3/4':0.75,'1/2':0.5,'1/4':0.25,'1/10':0.1,'1/8':0.125,'1/16':0.0625,'1/3':0.333,'2/3':0.667 }
  const fracsOrdenadas = Object.entries(fracs)
    .sort(([a],[b]) => (DECIMAL_MAP[b] || 0) - (DECIMAL_MAP[a] || 0))
  const fracPrecio = fracKey && fracs[fracKey] ? fracs[fracKey].precio : 0
  const totalCalc  = unidades * prod.precio + fracPrecio
  const precioFinal = precioCustom !== null ? precioCustom : totalCalc
  const parts    = []
  if (unidades > 0) parts.push(`${unidades} ${unidades === 1 ? 'unidad' : 'unidades'}`)
  if (fracKey)      parts.push(fracKey)
  const desc     = parts.join(' + ') || '—'
  const valid    = unidades > 0 || fracKey

  // Reset precio custom cuando cambia selección
  const setFrac = (k) => { setFracKey(k); setPrecioCustom(null) }
  const setUnid = (fn) => { setUnidades(fn); setPrecioCustom(null) }

  return (
    <Modal show title={prod.nombre} subtitle={`Precio unidad: ${cop(prod.precio)}`}
      onClose={onClose} onConfirm={() => onConfirm({ unidades, fracKey, total: precioFinal, desc })} okDisabled={!valid}>

      {/* Unidades */}
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Unidades completas
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        background: t.id === 'caramelo' ? '#f8fafc' : '#111',
        border: `1px solid ${t.border}`, borderRadius: 8,
        padding: '9px 13px', marginBottom: 14,
      }}>
        <span style={{ flex: 1, fontSize: 12, color: t.textMuted }}>Galones / unidades</span>
        <button onClick={() => setUnid(u => Math.max(0, u - 1))} style={{ width: 26, height: 26, background: t.card, border: `1px solid ${t.border}`, borderRadius: 5, color: t.text, cursor: 'pointer', fontSize: 16 }}>−</button>
        <span style={{ fontFamily: 'monospace', fontSize: 17, color: t.text, minWidth: 22, textAlign: 'center' }}>{unidades}</span>
        <button onClick={() => setUnid(u => u + 1)} style={{ width: 26, height: 26, background: t.card, border: `1px solid ${t.border}`, borderRadius: 5, color: t.text, cursor: 'pointer', fontSize: 16 }}>+</button>
      </div>

      {/* Fracciones */}
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Fracción adicional
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(fracsOrdenadas.length + 1, 3)}, 1fr)`,
        gap: 6, marginBottom: 14,
      }}>
        <div onClick={() => setFrac(null)} style={{
          padding: '8px 4px', borderRadius: 7, cursor: 'pointer', textAlign: 'center',
          background: !fracKey ? t.accentSub : (t.id === 'caramelo' ? '#f8fafc' : '#111'),
          border: `1px solid ${!fracKey ? t.accent : t.border}`, transition: 'all .15s',
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: !fracKey ? t.accent : t.textMuted }}>Ninguna</div>
          <div style={{ fontSize: 9, color: t.textMuted, marginTop: 1 }}>sólo unidades</div>
        </div>
        {fracsOrdenadas.map(([k, v]) => (
          <div key={k} onClick={() => setFrac(k)} style={{
            padding: '8px 4px', borderRadius: 7, cursor: 'pointer', textAlign: 'center',
            background: fracKey === k ? t.accentSub : (t.id === 'caramelo' ? '#f8fafc' : '#111'),
            border: `1px solid ${fracKey === k ? t.accent : t.border}`, transition: 'all .15s',
          }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: fracKey === k ? t.accent : t.text }}>{k}</div>
            <div style={{ fontSize: 10, color: t.green, fontFamily: 'monospace', marginTop: 1 }}>{cop(v.precio)}</div>
          </div>
        ))}
      </div>
      <PrecioEditor precioCalc={totalCalc} precioFinal={precioFinal} onChange={setPrecioCustom} desc={desc} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL CM
// ══════════════════════════════════════════════════════════════════════════════
function ModalCm({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [cm, setCm] = useState('')
  const [precioCustom, setPrecioCustom] = useState(null)
  if (!prod) return null
  const pxcm     = Math.round((prod.precio || 0) / 100)
  const cmNum    = parseInt(cm) || 0
  const totalCalc = cmNum * pxcm
  const precioFinal = precioCustom !== null ? precioCustom : totalCalc
  return (
    <Modal show title={prod.nombre} subtitle={`Pliego: ${cop(prod.precio)} · ${cop(pxcm)}/cm`}
      onClose={onClose} onConfirm={() => onConfirm({ cm: cmNum, total: precioFinal, desc: `${cmNum} cm` })} okDisabled={cmNum <= 0}>
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad en centímetros
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: t.id === 'caramelo' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8,
        padding: '10px 14px', marginBottom: 8,
      }}>
        <input autoFocus type="number" min="1" value={cm}
          onChange={e => setCm(e.target.value)}
          style={{ flex: 1, background: 'transparent', border: 'none', color: t.text, fontSize: 24, fontFamily: 'monospace', outline: 'none', textAlign: 'center', MozAppearance: 'textfield', appearance: 'textfield' }}
          placeholder="0"
        />
        <span style={{ fontSize: 13, color: t.textMuted }}>cm</span>
      </div>
      <div style={{ fontSize: 11, color: t.textMuted, textAlign: 'center', marginBottom: 14 }}>
        Precio por cm: <span style={{ color: t.green, fontFamily: 'monospace' }}>{cop(pxcm)}</span>
      </div>
      <PrecioEditor precioCalc={totalCalc} precioFinal={precioFinal} onChange={(v) => { setPrecioCustom(v) }} desc={`${cmNum} cm`} />
    </Modal>
  )
}


// ══════════════════════════════════════════════════════════════════════════════
// MODAL MLT — Tintes y productos por mililitro
// ══════════════════════════════════════════════════════════════════════════════
function ModalMlt({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [modo,    setModo]    = useState('pesos')  // 'pesos' | 'ml'
  const [valor,   setValor]   = useState('')
  if (!prod) return null

  const precioTarro = prod.precio          // precio_unidad = precio del tarro completo (1000 ml)
  const precioMl    = precioTarro / 1000   // precio real por ml: ej 26000/1000 = 26
  const valorNum    = parseFloat(valor) || 0

  // Calcular según modo
  // Modo pesos: cliente dice cuánto plata → ml = pesos / precio_por_ml
  // Modo ml:    cliente dice cuántos ml   → total = ml * precio_por_ml
  const mlCalc    = modo === 'pesos' ? (valorNum > 0 ? Math.round((valorNum / precioMl) * 10) / 10 : 0) : valorNum
  const totalCalc = modo === 'pesos' ? valorNum : Math.round(valorNum * precioMl)

  const valido = valorNum > 0 && mlCalc > 0 && totalCalc > 0

  const ACCESOS_RAPIDOS = [
    { label: 'Tarro completo', ml: 1000, icon: '🪣' },
    { label: '½ Tarro',        ml: 500,  icon: '½'  },
    { label: '¼ Tarro',        ml: 250,  icon: '¼'  },
  ]

  const aplicarAcceso = (ml) => {
    setModo('ml')
    setValor(String(ml))
  }

  const confirmar = () => {
    if (!valido) return
    onConfirm({
      ml:    mlCalc,
      total: totalCalc,
      desc:  mlCalc >= 1000
        ? `${mlCalc / 1000} L`
        : `${mlCalc} ml`,
    })
  }

  return (
    <Modal show title={prod.nombre} subtitle={`$${precioMl.toFixed(0)}/ml · ${cop(precioTarro)} por tarro`}
      onClose={onClose} onConfirm={confirmar} okDisabled={!valido}
      okLabel="Agregar al carrito">

      {/* Accesos rápidos */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        {ACCESOS_RAPIDOS.map(a => (
          <button key={a.ml} onClick={() => aplicarAcceso(a.ml)} style={{
            flex: 1, padding: '8px 4px', borderRadius: 8, cursor: 'pointer', textAlign: 'center',
            background: (modo === 'ml' && parseFloat(valor) === a.ml) ? t.accentSub : (t.id === 'caramelo' ? '#f1f5f9' : '#111'),
            border: `1px solid ${(modo === 'ml' && parseFloat(valor) === a.ml) ? t.accent : t.border}`,
            color: (modo === 'ml' && parseFloat(valor) === a.ml) ? t.accent : t.text,
            fontSize: 11, fontFamily: 'inherit', transition: 'all .15s',
          }}>
            <div style={{ fontSize: 16, marginBottom: 3 }}>{a.icon}</div>
            <div style={{ fontWeight: 600 }}>{a.label}</div>
            <div style={{ fontSize: 10, color: t.textMuted, marginTop: 1 }}>{cop(Math.round(a.ml * precioMl))}</div>
          </button>
        ))}
      </div>

      {/* Toggle modo */}
      <div style={{
        display: 'flex', background: t.id === 'caramelo' ? '#f1f5f9' : '#111',
        border: `1px solid ${t.border}`, borderRadius: 8, padding: 3, marginBottom: 12, gap: 3,
      }}>
        {[
          { key: 'pesos', label: '$ Pesos',       hint: 'El cliente dice cuánto plata' },
          { key: 'ml',    label: 'ml Mililitros',  hint: 'Sabes exactamente cuántos ml' },
        ].map(m => (
          <button key={m.key} onClick={() => { setModo(m.key); setValor('') }} style={{
            flex: 1, padding: '7px 6px', borderRadius: 6, cursor: 'pointer',
            background: modo === m.key ? t.card : 'transparent',
            border: `1px solid ${modo === m.key ? t.accent + '55' : 'transparent'}`,
            color: modo === m.key ? t.accent : t.textMuted,
            fontSize: 11, fontFamily: 'inherit', fontWeight: modo === m.key ? 600 : 400,
            transition: 'all .15s',
          }}>
            {m.label}
          </button>
        ))}
      </div>

      {/* Input */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: t.id === 'caramelo' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8,
        padding: '10px 14px', marginBottom: 10,
      }}>
        <span style={{ fontSize: 16, color: t.textMuted, minWidth: 20 }}>
          {modo === 'pesos' ? '$' : 'ml'}
        </span>
        <input
          autoFocus type="number" min="1" value={valor}
          onChange={e => setValor(e.target.value)}
          placeholder={modo === 'pesos' ? 'ej: 2000' : 'ej: 500'}
          style={{
            flex: 1, background: 'transparent', border: 'none',
            color: t.text, fontSize: 26, fontFamily: 'monospace',
            outline: 'none', textAlign: 'center',
            MozAppearance: 'textfield', appearance: 'textfield',
          }}
        />
      </div>

      {/* Resultado calculado */}
      {valido && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: t.accentSub, border: `1px solid ${t.accent}33`,
          borderRadius: 8, padding: '10px 14px', marginBottom: 4,
        }}>
          <div>
            <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 2 }}>
              {modo === 'pesos' ? 'Cantidad en ml' : 'Total a cobrar'}
            </div>
            <div style={{ fontSize: 18, fontFamily: 'monospace', fontWeight: 700, color: t.accent }}>
              {modo === 'pesos' ? `${mlCalc} ml` : cop(totalCalc)}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 2 }}>
              {modo === 'pesos' ? 'Total' : 'Mililitros'}
            </div>
            <div style={{ fontSize: 13, color: t.text, fontFamily: 'monospace' }}>
              {modo === 'pesos' ? cop(totalCalc) : `${mlCalc} ml`}
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL QTY SIMPLE
// ══════════════════════════════════════════════════════════════════════════════
function ModalQty({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [qty, setQty] = useState(1)
  const [precioCustom, setPrecioCustom] = useState(null)
  if (!prod) return null
  const totalCalc   = qty * prod.precio
  const precioFinal = precioCustom !== null ? precioCustom : totalCalc
  const desc        = `${qty} ${qty === 1 ? 'unidad' : 'unidades'}`

  const cambiarQty = (fn) => { setQty(fn); setPrecioCustom(null) }

  return (
    <Modal show title={prod.nombre} subtitle={`Precio unitario: ${cop(prod.precio)}`}
      onClose={onClose} onConfirm={() => onConfirm({ qty, total: precioFinal, desc })}>
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14,
        background: t.id === 'caramelo' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8,
        padding: 14, marginBottom: 14,
      }}>
        <button onClick={() => cambiarQty(q => Math.max(1, q - 1))} style={{ width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 20 }}>−</button>
        <input
          type="number" min="1" value={qty}
          onChange={e => { const v = parseInt(e.target.value) || 1; cambiarQty(() => v) }}
          style={{
            width: 60, background: 'transparent', border: 'none',
            borderBottom: `1px solid ${t.accent}66`,
            color: t.text, fontSize: 26, fontFamily: 'monospace',
            outline: 'none', textAlign: 'center', padding: '2px 0',
            MozAppearance: 'textfield', appearance: 'textfield',
          }}
        />
        <button onClick={() => cambiarQty(q => q + 1)} style={{ width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 20 }}>+</button>
      </div>
      <PrecioEditor precioCalc={totalCalc} precioFinal={precioFinal} onChange={setPrecioCustom} desc={desc} />
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
// MODAL COLOR PREPARADO
// ══════════════════════════════════════════════════════════════════════════════
// Fracciones disponibles para color preparado
const FRACS_CP = [
  { k: null,    label: 'Galón',  mult: 1     },
  { k: '3/4',   label: '3/4',    mult: 0.75  },
  { k: '1/2',   label: '1/2',    mult: 0.5   },
  { k: '1/4',   label: '1/4',    mult: 0.25  },
  { k: '1/8',   label: '1/8',    mult: 0.125 },
  { k: '1/10',  label: '1/10',   mult: 0.10  },
  { k: '1/16',  label: '1/16',   mult: 0.0625},
]

function ModalColorPreparado({ show, precioBase, onClose, onConfirm }) {
  const t = useTheme()
  const [desc,    setDesc]    = useState('')
  const [precio,  setPrecio]  = useState(precioBase || 0)
  const [qty,     setQty]     = useState(1)
  const [frac,    setFrac]    = useState(null)   // key de fracción adicional
  const [modoPrecio, setModoPrecio] = useState(false)  // edición manual del precio

  useEffect(() => {
    if (show) { setPrecio(precioBase || 0); setDesc(''); setQty(1); setFrac(null); setModoPrecio(false) }
  }, [precioBase, show])

  if (!show) return null

  // Precio calculado automáticamente
  const precioCalc = precioBase ? Math.round(precioBase * qty + (frac ? precioBase * FRACS_CP.find(f=>f.k===frac)?.mult : 0)) : 0
  const precioFinal = modoPrecio ? precio : precioCalc
  const descCompleta = [
    qty > 0 ? `${qty} galón${qty>1?'es':''}` : null,
    frac || null,
  ].filter(Boolean).join(' + ')
  const valid = desc.trim().length > 0 && precioFinal > 0

  return createPortal(
    <div onMouseDown={e => e.target === e.currentTarget && onClose()} style={{
      position: 'fixed', inset: 0, background: '#00000088',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 9998, padding: 16,
    }}>
      <div style={{
        background: t.card, border: `1px solid ${t.border}`, borderRadius: 14,
        padding: '22px 20px', width: '100%', maxWidth: 400,
        maxHeight: '90vh', overflowY: 'auto',
        animation: 'mIn .2s cubic-bezier(.34,1.4,.64,1)',
      }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: t.text, marginBottom: 4 }}>🎨 Color Preparado</div>
        <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 18 }}>
          El cliente trae la muestra y se prepara en tienda
        </div>

        {/* Descripción */}
        <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 6 }}>Descripción del color</div>
        <input
          autoFocus value={desc} onChange={e => setDesc(e.target.value)}
          placeholder="ej: Vinilo T1 mostaza cliente"
          style={{
            width: '100%', background: t.id === 'caramelo' ? '#f8fafc' : '#111',
            border: `1px solid ${t.accent}66`, borderRadius: 8,
            color: t.text, fontSize: 13, padding: '10px 12px',
            fontFamily: 'inherit', outline: 'none', marginBottom: 16,
          }}
        />

        {/* Cantidad en galones */}
        <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>Galones completos</div>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14,
          background: t.id === 'caramelo' ? '#f8fafc' : '#111',
          border: `1px solid ${t.border}`, borderRadius: 8, padding: '10px 14px', marginBottom: 16,
        }}>
          <button onClick={() => { setQty(q => Math.max(0, q-1)); setModoPrecio(false) }}
            style={{ width: 32, height: 32, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 18 }}>−</button>
          <input type="number" min="0" value={qty}
            onChange={e => { setQty(parseInt(e.target.value)||0); setModoPrecio(false) }}
            style={{ width: 52, background: 'transparent', border: 'none', borderBottom: `1px solid ${t.border}`, color: t.text, fontSize: 22, fontFamily: 'monospace', outline: 'none', textAlign: 'center', MozAppearance: 'textfield', appearance: 'textfield' }}
          />
          <button onClick={() => { setQty(q => q+1); setModoPrecio(false) }}
            style={{ width: 32, height: 32, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 18 }}>+</button>
        </div>

        {/* Fracción adicional */}
        <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>Fracción adicional</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
          {FRACS_CP.map(f => (
            <button key={f.k||'gal'} onClick={() => { if (f.k === null) return; setFrac(frac === f.k ? null : f.k); setModoPrecio(false) }}
              style={{
                padding: '5px 12px', borderRadius: 99, cursor: f.k ? 'pointer' : 'default',
                background: frac === f.k ? t.accentSub : (t.id==='caramelo'?'#f1f5f9':'#1a1a1a'),
                border: `1px solid ${frac === f.k ? t.accent : t.border}`,
                color: frac === f.k ? t.accent : (f.k ? t.text : t.textMuted),
                fontSize: 11, fontFamily: 'inherit', fontWeight: frac===f.k ? 600 : 400,
              }}
            >{f.label}</button>
          ))}
        </div>

        {/* Precio total */}
        <div style={{
          background: t.id==='caramelo'?'#f8fafc':'#0f0f0f',
          border: `1px solid ${modoPrecio ? t.yellow+'88' : t.border}`,
          borderRadius: 8, padding: '10px 13px', marginBottom: 20,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 11, color: t.textMuted }}>{descCompleta || '—'}</div>
              {modoPrecio && <div style={{ fontSize: 9, color: t.yellow }}>✏️ Precio manual</div>}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ fontSize: 13, color: t.textMuted }}>$</span>
              <input type="number" min="0"
                value={precioFinal === 0 ? '' : precioFinal}
                onChange={e => { setPrecio(parseInt(e.target.value)||0); setModoPrecio(true) }}
                style={{
                  width: 100, background: 'transparent', border: 'none',
                  borderBottom: `1px solid ${modoPrecio ? t.yellow : t.accent+'66'}`,
                  color: modoPrecio ? t.yellow : t.accent,
                  fontSize: 18, fontFamily: 'monospace', fontWeight: 700,
                  outline: 'none', textAlign: 'right', padding: '2px 0',
                  MozAppearance: 'textfield', appearance: 'textfield',
                }}
              />
            </div>
          </div>
          {modoPrecio && (
            <button onClick={() => setModoPrecio(false)} style={{ marginTop: 5, fontSize: 9, color: t.textMuted, background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
              ↩ Volver al precio calculado ({cop(precioCalc)})
            </button>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <button onClick={onClose} style={{
            padding: 11, background: 'transparent', border: `1px solid ${t.border}`,
            borderRadius: 8, color: t.textMuted, cursor: 'pointer', fontFamily: 'inherit', fontSize: 13,
          }}>Cancelar</button>
          <button onClick={() => valid && onConfirm({ desc: desc.trim(), descCompleta, precio: precioFinal })}
            disabled={!valid} style={{
              padding: 11, background: valid ? t.accent : t.border, border: 'none', borderRadius: 8,
              color: valid ? '#fff' : t.textMuted,
              cursor: valid ? 'pointer' : 'not-allowed', fontFamily: 'inherit', fontSize: 13, fontWeight: 600,
          }}>Agregar al carrito</button>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// CONFIG DE GRUPOS DE COLOR
// ══════════════════════════════════════════════════════════════════════════════
const GRUPOS_CONFIG = {
  pint_vinilo: [
    { key:'T1',      icono:'🖌️', titulo:'Galón Vinilo T1',     match: p => /vinilo davinci t1/i.test(p.nombre),     getColor: p => p.nombre.replace(/Vinilo Davinci T1 /i,'').trim() },
    { key:'T2',      icono:'🖌️', titulo:'Galón Vinilo T2',     match: p => /vinilo davinci t2/i.test(p.nombre),     getColor: p => p.nombre.replace(/Vinilo Davinci T2 /i,'').trim() },
    { key:'T3',      icono:'🖌️', titulo:'Galón Vinilo T3',     sinColorPrep: true, match: p => /vinilo davinci t3/i.test(p.nombre),     getColor: p => p.nombre.replace(/Vinilo Davinci T3 /i,'').trim() },
    { key:'ico',     icono:'🖌️', titulo:'Vinilo ICO',          sinColorPrep: true, match: p => /vinilo ico/i.test(p.nombre) && !/cuñete|cunete/i.test(p.nombre), getColor: p => p.nombre.replace(/Vinilo ICO /i,'').trim() },
    { key:'cunete',  icono:'🪣', titulo:'Cuñete (5 gal)',      sinPrecio: true, match: p => /cu[ñn]ete/i.test(p.nombre) && !/1\/2|medio|masilla|placco/i.test(p.nombre), getColor: p => p.nombre },
    { key:'medio',   icono:'🪣', titulo:'½ Cuñete (2.5 gal)', sinPrecio: true, match: p => /(1\/2\s*cu[ñn]ete|medio\s*cu[ñn]ete)/i.test(p.nombre), getColor: p => p.nombre },
  ],
  pint_esmalte: [
    { key:'std',   icono:'🎨', titulo:'Esmalte estándar',  match: p => /^esmalte /i.test(p.nombre)  && !/3.en|aluminio|dorado/i.test(p.nombre), getColor: p => p.nombre.replace(/^esmalte /i,'').trim() },
    { key:'anti',  icono:'🔴', titulo:'Anticorrosivo',      match: p => /^anticorrosivo /i.test(p.nombre), getColor: p => p.nombre.replace(/^anticorrosivo /i,'').trim() },
    { key:'3en1',  icono:'🎨', titulo:'Esmalte 3 en 1',    match: p => /3.en.?1/i.test(p.nombre) && !/aluminio/i.test(p.nombre), getColor: p => p.nombre.replace(/esmalte 3 en.?1\s*/i,'').replace(/\s*(davinci|tonner|pintuco)\s*/i,' ').trim() },
  ],
  pint_laca: [
    { key:'cat',     icono:'🪄', titulo:'Laca Catalizada', match: p => /catalizada/i.test(p.nombre) && !/masilla/i.test(p.nombre), getColor: p => p.nombre.replace(/laca /i,'').replace(/ catalizada/i,'').trim() },
    { key:'corr',    icono:'🪄', titulo:'Laca Corriente',  match: p => /laca corriente/i.test(p.nombre), getColor: p => p.nombre.replace(/laca corriente\s*/i,'').trim() },
    { key:'masilla', icono:'🧴', titulo:'Masilla Laca',    match: p => /masilla laca/i.test(p.nombre), getColor: p => p.nombre.replace(/masilla laca\s*/i,'').trim() },
  ],
  pint_aerosol: [
    { key:'std',  icono:'🎭', titulo:'Aerosol estándar', match: p => /aerosol/i.test(p.nombre) && !/alta\s*temp|fluorec|silicona/i.test(p.nombre), getColor: p => p.nombre.replace(/^aerosol\s*/i,'').trim() },
  ],
}

const SUBCATS_COLORES = Object.keys(GRUPOS_CONFIG)

// ─── buildGrupos: agrupa productos por config ─────────────────────────────────
function buildGrupos(prods, subcatKey) {
  const config = GRUPOS_CONFIG[subcatKey]
  if (!config) return { grupos: [], sueltos: prods }
  const asignados = new Set()
  const grupos = config.map(gc => {
    const items = prods.filter(p => { if (asignados.has(p.key)) return false; const ok = gc.match(p); if (ok) asignados.add(p.key); return ok })
    return { ...gc, items }
  }).filter(g => g.items.length > 0)
  const sueltos = prods.filter(p => !asignados.has(p.key))
  return { grupos, sueltos }
}

// ══════════════════════════════════════════════════════════════════════════════
// GRUPO COLORES — tarjeta grande con pills de colores
// ══════════════════════════════════════════════════════════════════════════════
const MOSTRAR_INICIAL = 8

function GrupoColores({ grupo, carrito, onAgregar, onColorPrep }) {
  const t = useTheme()
  const [expandido, setExpandido] = useState(false)
  if (!grupo.items.length) return null

  const precioBase = grupo.items[0].precio
  const hay_mas = grupo.items.length > MOSTRAR_INICIAL

  // Ordenar: Blanco primero, Negro segundo, resto alfabético
  const ordenados = [...grupo.items].sort((a, b) => {
    const ca = grupo.getColor(a).toLowerCase()
    const cb = grupo.getColor(b).toLowerCase()
    const pri = c => c.startsWith('blanco') ? 0 : c.startsWith('negro') ? 1 : 2
    return pri(ca) - pri(cb) || ca.localeCompare(cb)
  })
  const visibles = expandido ? ordenados : ordenados.slice(0, MOSTRAR_INICIAL)
  const etiquetaCount = grupo.items.length === 1 ? '1 opción' : `${grupo.items.length} colores`

  return (
    <div style={{
      background: t.card, border: `1px solid ${t.border}`, borderRadius: 11,
      padding: '14px 16px', marginBottom: 12,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{ fontSize: 16 }}>{grupo.icono}</span>
          <span style={{ fontSize: 13, fontWeight: 700, color: t.text }}>{grupo.titulo}</span>
          <span style={{ fontSize: 10, color: t.textMuted }}>({etiquetaCount})</span>
        </div>
        {!grupo.sinPrecio && (
          <span style={{ fontSize: 15, fontFamily: 'monospace', fontWeight: 700, color: t.accent }}>{cop(precioBase)}</span>
        )}
      </div>

      {/* Pills de colores */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
        {visibles.map(prod => {
          const color = grupo.getColor(prod)
          const enCarrito = carrito.some(c => c.key === prod.key)
          return (
            <button
              key={prod.key}
              onClick={() => onAgregar(prod)}
              style={{
                padding: '5px 11px', borderRadius: 99, cursor: 'pointer',
                background: enCarrito ? t.accentSub : (t.id === 'caramelo' ? '#f1f5f9' : '#1a1a1a'),
                border: `1px solid ${enCarrito ? t.accent : t.border}`,
                color: enCarrito ? t.accent : t.text,
                fontSize: 11, fontFamily: 'inherit', fontWeight: enCarrito ? 600 : 400,
                transition: 'all .12s', whiteSpace: 'nowrap',
              }}
            >
              {enCarrito && <span style={{ marginRight: 4, fontSize: 9 }}>✓</span>}
              {color}
            </button>
          )
        })}

        {/* Ver más / menos */}
        {hay_mas && (
          <button
            onClick={() => setExpandido(v => !v)}
            style={{
              padding: '5px 11px', borderRadius: 99, cursor: 'pointer',
              background: 'transparent',
              border: `1px dashed ${t.border}`,
              color: t.textMuted, fontSize: 11, fontFamily: 'inherit',
            }}
          >
            {expandido ? '▲ ver menos' : `+${grupo.items.length - MOSTRAR_INICIAL} más`}
          </button>
        )}

        {/* Botón color preparado */}
        {onColorPrep && !grupo.sinColorPrep && !grupo.sinPrecio && (
          <button
            onClick={() => onColorPrep(precioBase)}
            style={{
              padding: '5px 12px', borderRadius: 99, cursor: 'pointer',
              background: 'transparent',
              border: `1px solid ${t.accent}55`,
              color: t.accent, fontSize: 11, fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: 4,
            }}
          >
            🎨 Color preparado
          </button>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// VISTA GRUPOS — contenedor que usa GrupoColores + cards sueltas
// ══════════════════════════════════════════════════════════════════════════════
function VistaGrupos({ prods, subcatKey, carrito, onClickProd, favKeys, onFav, columnas, onColorPrep }) {
  const t = useTheme()
  const { grupos, sueltos } = buildGrupos(prods, subcatKey)

  // Para agregar directo desde pill (producto simple)
  const agregarDirecto = (prod) => onClickProd(prod)

  return (
    <div>
      {grupos.map(g => (
        <GrupoColores key={g.key} grupo={g} carrito={carrito} onAgregar={agregarDirecto} onColorPrep={onColorPrep} />
      ))}
      {sueltos.length > 0 && (
        <div>
          {sueltos.length > 0 && (
            <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 8, marginTop: 4 }}>
              Otros
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${columnas}, 1fr)`, gap: 8 }}>
            {sueltos.map(prod => (
              <ProdCard
                key={prod.key} prod={prod}
                onClick={onClickProd}
                isFav={favKeys.includes(prod.key)}
                onFav={onFav}
                cantCarrito={carrito.filter(c => c.key === prod.key).reduce((s,c) => s+(c.qty||1), 0)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// SELECTOR DE CLIENTE
// ══════════════════════════════════════════════════════════════════════════════
function SelectorCliente({ t, clienteSeleccionado, onSeleccionar }) {
  const [busq,       setBusq]       = useState('')
  const [resultados, setResultados] = useState([])
  const [buscando,   setBuscando]   = useState(false)
  const [abierto,    setAbierto]    = useState(false)
  const [modalNuevo, setModalNuevo] = useState(false)
  const timer = useRef(null)

  const buscar = (q) => {
    setBusq(q)
    clearTimeout(timer.current)
    if (!q.trim() || q.trim().length < 2) { setResultados([]); setAbierto(false); return }
    setBuscando(true)
    setAbierto(true)
    timer.current = setTimeout(async () => {
      try {
        const r = await fetch(`${API_BASE}/clientes/buscar?q=${encodeURIComponent(q)}`)
        const d = await r.json()
        setResultados(d.clientes || [])
      } catch { setResultados([]) }
      finally { setBuscando(false) }
    }, 350)
  }

  const seleccionar = (c) => {
    const nombre = c['Nombre tercero'] || ''
    const id     = c['Identificacion'] ? String(c['Identificacion']) : ''
    onSeleccionar({ nombre, id, datos: c })
    setBusq(''); setResultados([]); setAbierto(false)
  }

  const limpiar = () => { onSeleccionar(null); setBusq('') }

  const inp = {
    flex:1, background: t.id==='caramelo'?'#f8fafc':'#111',
    border:`1px solid ${t.border}`, borderRadius:5,
    color:t.text, fontSize:11, padding:'5px 8px',
    fontFamily:'inherit', outline:'none', minWidth:0,
  }

  if (clienteSeleccionado) return (
    <div style={{padding:'8px 14px',borderTop:`1px solid ${t.border}`}}>
      <div style={{fontSize:9,color:t.textMuted,textTransform:'uppercase',letterSpacing:'.08em',marginBottom:4}}>Cliente</div>
      <div style={{display:'flex',alignItems:'center',gap:8,background:t.accentSub,border:`1px solid ${t.accent}33`,borderRadius:7,padding:'6px 10px'}}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontSize:12,fontWeight:600,color:t.accent,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
            👤 {clienteSeleccionado.nombre}
          </div>
          {clienteSeleccionado.id && <div style={{fontSize:10,color:t.textMuted}}>ID: {clienteSeleccionado.id}</div>}
        </div>
        <button onClick={limpiar} title="Quitar cliente" style={{
          background:'transparent',border:'none',color:t.textMuted,
          cursor:'pointer',fontSize:14,padding:'0 2px',flexShrink:0,
        }}>✕</button>
      </div>
    </div>
  )

  return (
    <div style={{padding:'8px 14px',borderTop:`1px solid ${t.border}`,position:'relative'}}>
      <div style={{fontSize:9,color:t.textMuted,textTransform:'uppercase',letterSpacing:'.08em',marginBottom:4}}>Cliente (opcional)</div>
      <div style={{display:'flex',gap:5}}>
        <input
          style={inp} value={busq}
          onChange={e=>buscar(e.target.value)}
          onFocus={()=>busq&&setAbierto(true)}
          placeholder="Buscar por nombre o cédula/NIT..."
        />
        <button onClick={()=>setModalNuevo(true)} title="Registrar cliente nuevo" style={{
          background:t.accentSub,border:`1px solid ${t.accent}44`,color:t.accent,
          borderRadius:5,padding:'5px 8px',cursor:'pointer',fontSize:12,flexShrink:0,
        }}>+</button>
      </div>
      {/* Dropdown resultados */}
      {abierto && (resultados.length > 0 || buscando) && (
        <div style={{
          position:'absolute',left:14,right:14,top:'100%',zIndex:200,
          background:t.card,border:`1px solid ${t.border}`,borderRadius:8,
          boxShadow:'0 8px 24px rgba(0,0,0,.25)',overflow:'hidden',
        }}>
          {buscando && <div style={{padding:'10px 12px',fontSize:11,color:t.textMuted}}>Buscando…</div>}
          {!buscando && resultados.length===0 && (
            <div style={{padding:'10px 12px',fontSize:11,color:t.textMuted}}>
              Sin resultados —{' '}
              <span style={{color:t.accent,cursor:'pointer'}} onClick={()=>{setModalNuevo(true);setAbierto(false)}}>
                registrar cliente nuevo
              </span>
            </div>
          )}
          {resultados.map((c,i)=>(
            <div key={i} onClick={()=>seleccionar(c)} style={{
              padding:'9px 12px',cursor:'pointer',borderBottom:`1px solid ${t.border}`,
              transition:'background .1s',
            }}
              onMouseEnter={e=>e.currentTarget.style.background=t.cardHover}
              onMouseLeave={e=>e.currentTarget.style.background='transparent'}
            >
              <div style={{fontSize:12,fontWeight:500,color:t.text}}>{c['Nombre tercero']}</div>
              <div style={{fontSize:10,color:t.textMuted}}>
                {c['Tipo de identificacion']} {c['Identificacion']}
                {c['Telefono']&&c['Telefono']!=='000-0000000-' ? ` · ${c['Telefono']}` : ''}
              </div>
            </div>
          ))}
          <div onClick={()=>{setModalNuevo(true);setAbierto(false)}} style={{
            padding:'8px 12px',fontSize:11,color:t.accent,cursor:'pointer',
            background:t.accentSub,textAlign:'center',fontWeight:500,
          }}>
            + Registrar cliente nuevo
          </div>
        </div>
      )}
      {/* Modal nuevo cliente */}
      {modalNuevo && (
        <ModalNuevoCliente
          t={t} nombreInicial={busq}
          onClose={()=>setModalNuevo(false)}
          onCreado={(c)=>{ seleccionar(c); setModalNuevo(false) }}
        />
      )}
    </div>
  )
}

// ── Modal Nuevo Cliente ───────────────────────────────────────────────────────
function ModalNuevoCliente({ t, nombreInicial, onClose, onCreado }) {
  const TIPOS_ID = ['CC','NIT','CE','PAS']
  const [form, setForm] = useState({
    nombre:         nombreInicial||'',
    tipo_id:        'CC',
    identificacion: '',
    tipo_persona:   'Natural',
    correo:         '',
    telefono:       '',
    direccion:      '',
  })
  const [estado, setEstado] = useState('idle')
  const [err,    setErr]    = useState('')
  const set = (k,v)=>setForm(f=>({...f,[k]:v}))

  const guardar = async () => {
    if (!form.nombre.trim()) { setErr('El nombre es obligatorio'); return }
    setEstado('saving'); setErr('')
    try {
      const r = await fetch(`${API_BASE}/clientes`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(form),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail||'Error')
      setEstado('ok')
      // Devolver formato compatible con la hoja Clientes
      const clienteParaSelector = {
        'Nombre tercero':          form.nombre.toUpperCase(),
        'Identificacion':          form.identificacion,
        'Tipo de identificacion':  form.tipo_id,
        'Telefono':                form.telefono,
      }
      setTimeout(()=>{ onCreado(clienteParaSelector); onClose() }, 600)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  const inp = {
    width:'100%', boxSizing:'border-box',
    background:t.id==='caramelo'?'#f8fafc':'#111',
    border:`1px solid ${t.border}`, borderRadius:7,
    color:t.text, fontSize:12, padding:'7px 10px',
    outline:'none', fontFamily:'inherit',
  }
  const lbl = { fontSize:10, color:t.textMuted, textTransform:'uppercase', letterSpacing:'.07em', marginBottom:3, display:'block' }

  return createPortal(
    <div onMouseDown={e=>e.target===e.currentTarget&&onClose()} style={{
      position:'fixed',inset:0,zIndex:10000,background:'rgba(0,0,0,.65)',
      display:'flex',alignItems:'center',justifyContent:'center',padding:16,
    }}>
      <div style={{
        background:t.bg, border:`1px solid ${t.border}`, borderRadius:14,
        width:'100%', maxWidth:420, maxHeight:'90vh', overflowY:'auto',
        boxShadow:'0 24px 64px rgba(0,0,0,.45)',
      }}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'18px 20px 0'}}>
          <div>
            <div style={{fontWeight:700,fontSize:14,color:t.text}}>👤 Registrar cliente</div>
            <div style={{fontSize:11,color:t.textMuted,marginTop:2}}>Se guardará en la hoja Clientes del Excel</div>
          </div>
          <button onClick={onClose} style={{background:'transparent',border:`1px solid ${t.border}`,borderRadius:7,color:t.textMuted,width:28,height:28,cursor:'pointer',fontSize:14,display:'flex',alignItems:'center',justifyContent:'center'}}>✕</button>
        </div>
        <div style={{padding:'16px 20px 20px',display:'flex',flexDirection:'column',gap:11}}>

          <div><label style={lbl}>Nombre completo *</label>
            <input style={inp} value={form.nombre} onChange={e=>set('nombre',e.target.value)} autoFocus/></div>

          <div style={{display:'grid',gridTemplateColumns:'1fr 2fr',gap:10}}>
            <div><label style={lbl}>Tipo ID</label>
              <select style={inp} value={form.tipo_id} onChange={e=>set('tipo_id',e.target.value)}>
                {TIPOS_ID.map(t=><option key={t} value={t}>{t}</option>)}
              </select></div>
            <div><label style={lbl}>Número</label>
              <input style={inp} value={form.identificacion} onChange={e=>set('identificacion',e.target.value)} placeholder="Cédula o NIT"/></div>
          </div>

          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
            <div><label style={lbl}>Tipo persona</label>
              <select style={inp} value={form.tipo_persona} onChange={e=>set('tipo_persona',e.target.value)}>
                <option value="Natural">Natural</option>
                <option value="Juridica">Jurídica</option>
              </select></div>
            <div><label style={lbl}>Teléfono (opcional)</label>
              <input style={inp} value={form.telefono} onChange={e=>set('telefono',e.target.value)} placeholder="300..."/></div>
          </div>

          <div><label style={lbl}>Correo electrónico (opcional)</label>
            <input style={inp} type="email" value={form.correo} onChange={e=>set('correo',e.target.value)} placeholder="correo@..."/></div>

          <div style={{padding:'7px 10px',background:t.accentSub,border:`1px solid ${t.accent}22`,borderRadius:7,fontSize:10,color:t.accent}}>
            💡 Con estos datos queda listo para factura electrónica DIAN. El teléfono y correo son opcionales.
          </div>

          {err && <div style={{padding:'7px 10px',background:'#fef2f2',border:'1px solid #fca5a5',borderRadius:7,fontSize:11,color:'#dc2626'}}>⚠ {err}</div>}

          <div style={{display:'flex',gap:8,justifyContent:'flex-end',marginTop:2}}>
            <button onClick={onClose} style={{background:'transparent',border:`1px solid ${t.border}`,borderRadius:8,color:t.textMuted,padding:'8px 16px',cursor:'pointer',fontFamily:'inherit',fontSize:12}}>Cancelar</button>
            <button onClick={guardar} disabled={estado==='saving'} style={{
              background:estado==='ok'?t.green:estado==='err'?'#dc2626':t.accent,
              border:'none',borderRadius:8,color:'#fff',padding:'8px 20px',
              cursor:'pointer',fontFamily:'inherit',fontSize:12,fontWeight:700,
              opacity:estado==='saving'?.7:1,transition:'background .2s',
            }}>
              {estado==='saving'?'Guardando…':estado==='ok'?'✓ Guardado':estado==='err'?'✗ Error':'Registrar cliente'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL CARRITO (compartido desktop + drawer móvil)
// ══════════════════════════════════════════════════════════════════════════════
function PanelCarrito({ t, carrito, totalCarrito, vendedor, setVendedor, metodo, setMetodo,
                        clienteSeleccionado, setClienteSeleccionado,
                        removeItem, qtyChange, registrar, enviando, sticky, mobile }) {
  return (
    <div style={{
      background: t.card, border: mobile ? 'none' : `1px solid ${t.border}`,
      borderRadius: mobile ? 0 : 11, overflow: 'hidden',
      position: sticky ? 'sticky' : 'relative', top: sticky ? 70 : 'auto',
    }}>
      {/* Header (solo desktop) */}
      {!mobile && (
        <div style={{
          padding: '12px 14px', borderBottom: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, letterSpacing: '.1em', textTransform: 'uppercase' }}>Carrito</span>
          <div style={{
            background: carrito.length ? t.accent : t.border, color: '#fff',
            fontSize: 9, fontWeight: 700, width: 18, height: 18, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'background .2s',
          }}>
            {carrito.reduce((s, c) => s + (c.qty || 1), 0)}
          </div>
        </div>
      )}

      {/* Items */}
      <div style={{ maxHeight: mobile ? 'none' : 280, overflowY: mobile ? 'visible' : 'auto' }}>
        {carrito.length === 0 ? (
          <div style={{ padding: '28px 14px', textAlign: 'center', color: t.textMuted, fontSize: 12, lineHeight: 1.9 }}>
            <div style={{ fontSize: 28, opacity: .25, marginBottom: 6 }}>🛒</div>
            Toca un producto para agregarlo
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
            <span style={{ fontSize: mobile ? 24 : 20, fontFamily: 'monospace', fontWeight: 700, color: t.text }}>{cop(totalCarrito)}</span>
          </div>
        </div>
      )}

      {/* Cliente */}
      <SelectorCliente
        t={t}
        clienteSeleccionado={clienteSeleccionado}
        onSeleccionar={setClienteSeleccionado}
      />

      {/* Vendedor */}
      <div style={{ padding: '8px 14px', borderTop: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', minWidth: 54 }}>Vendedor</span>
        <input
          value={vendedor} onChange={e => setVendedor(e.target.value)}
          style={{
            flex: 1, background: t.id === 'caramelo' ? '#f8fafc' : '#111',
            border: `1px solid ${t.border}`, borderRadius: 5, color: t.text,
            fontSize: mobile ? 14 : 11, padding: mobile ? '7px 10px' : '4px 7px',
            fontFamily: 'inherit', outline: 'none',
          }}
        />
      </div>

      {/* Método de pago */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6, padding: '8px 14px 12px' }}>
        {[
          { key: 'efectivo',      label: 'Efectivo',  icon: '💵' },
          { key: 'transferencia', label: 'Transfer.', icon: '📲' },
          { key: 'datafono',      label: 'Datáfono',  icon: '💳' },
        ].map(m => (
          <button key={m.key} onClick={() => setMetodo(m.key)} style={{
            padding: mobile ? '10px 3px' : '7px 3px',
            background: metodo === m.key ? t.accentSub : (t.id === 'caramelo' ? '#f8fafc' : '#0f0f0f'),
            border: `1px solid ${metodo === m.key ? t.accent : t.border}`,
            borderRadius: 7, color: metodo === m.key ? t.accent : t.textMuted,
            fontSize: mobile ? 12 : 10, cursor: 'pointer', fontFamily: 'inherit',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
            transition: 'all .15s',
          }}>
            <span style={{ fontSize: mobile ? 18 : 13 }}>{m.icon}</span>{m.label}
          </button>
        ))}
      </div>

      {/* Botón registrar */}
      <button
        onClick={registrar}
        disabled={!carrito.length || enviando}
        style={{
          margin: '0 14px 14px', padding: mobile ? 16 : 12,
          background: carrito.length ? t.accent : t.border,
          color: carrito.length ? '#fff' : t.textMuted,
          border: 'none', borderRadius: 8,
          fontSize: mobile ? 15 : 12, fontWeight: 600,
          cursor: carrito.length ? 'pointer' : 'not-allowed',
          fontFamily: 'inherit', letterSpacing: '.04em',
          width: 'calc(100% - 28px)', transition: 'all .15s',
        }}
      >
        {enviando ? 'Registrando...' : `Registrar venta${carrito.length > 0 ? ' · ' + cop(totalCarrito) : ''}`}
      </button>
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
  const [filtro,    setFiltro]    = useState('todos')
  const [columnas,  setColumnas]  = useState(() => window.innerWidth < 768 ? 2 : 6)
  const [carrito,   setCarrito]   = useState([])
  const [metodo,    setMetodo]    = useState('efectivo')
  const [vendedor,  setVendedor]  = useState('Dashboard')
  const [clienteSeleccionado, setClienteSeleccionado] = useState(null) // {nombre, id} | null
  const [modalFrac, setModalFrac] = useState(null)
  const [modalCm,   setModalCm]   = useState(null)
  const [modalQty,  setModalQty]  = useState(null)
  const [modalMlt,  setModalMlt]  = useState(null)
  const [toast,     setToast]     = useState(null)
  const [enviando,  setEnviando]  = useState(false)
  const [subcatFiltro,      setSubcatFiltro]      = useState(null)
  const [modalColorPrep,    setModalColorPrep]    = useState(false)
  const [precioBaseColor,   setPrecioBaseColor]   = useState(0)
  const [carritoAbierto, setCarritoAbierto] = useState(false)
  const isMobile = useIsMobile()

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
  // Ordenar tornillería: Drywall primero
  const catKey3 = Object.keys(catMap).find(k => k.toLowerCase().includes('tornill'))
  if (catKey3) catMap[catKey3] = ordenarTornilleria(catMap[catKey3])

  const catsOrdenadas = Object.keys(catMap).sort()

  // Subcats disponibles para la categoría seleccionada
  const catActivaKey = filtro !== 'todos' && filtro !== 'favs' && filtro !== 'top' ? filtro : null
  const subcatsDisp = catActivaKey ? (SUBCATS[catActivaKey.toLowerCase()] || []) : []

  // Filtrar por subcat si hay una activa
  const aplicarSubcat = (prods) => {
    let res = prods
    if (subcatFiltro && catActivaKey) {
      const sub = subcatsDisp.find(s => s.key === subcatFiltro)
      res = sub ? res.filter(sub.fn) : res
    }
    // Siempre ordenar tornillería con drywall primero
    if (catActivaKey && catActivaKey.toLowerCase().includes('tornill')) {
      res = ordenarTornilleria(res)
    }
    return res
  }

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
    if (prod.tipo === 'mlt')      { setModalMlt(prod);  return }
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
  const confirmarMlt = ({ ml, total, desc }) => {
    setCarrito(p => [...p, {
      id: Date.now(), key: modalMlt.key, nombre: modalMlt.nombre,
      precio: total, qty: ml, total, desc, tipo: 'mlt',
    }])
    setModalMlt(null)
  }
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

  // ── Color preparado ───────────────────────────────────────────────────────
  const abrirColorPrep = useCallback((precioBase) => {
    setPrecioBaseColor(precioBase)
    setModalColorPrep(true)
  }, [])
  const confirmarColorPrep = useCallback(({ desc, descCompleta, precio }) => {
    setCarrito(prev => [...prev, {
      id: Date.now(), key: `color_prep_${Date.now()}`,
      nombre: `🎨 Color Preparado: ${desc}`,
      precio, qty: 1, total: precio,
      desc: descCompleta || '1 galón', tipo: 'simple',
    }])
    setModalColorPrep(false)
  }, [])

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
          productos: carrito.map(c => ({ nombre: c.nombre, cantidad: c.tipo === 'mlt' ? c.qty : c.qty, total: c.total })),
          metodo, vendedor,
          cliente_nombre: clienteSeleccionado?.nombre || '',
          cliente_id:     clienteSeleccionado?.id     || '',
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setCarrito([])
      setClienteSeleccionado(null)
      setToast(`✅ Venta #${data.consecutivo} registrada · ${data.productos} producto${data.productos > 1 ? 's' : ''}`)
    } catch (e) {
      setToast(`⚠️ Error: ${e.message}`)
    } finally {
      setEnviando(false)
      setTimeout(() => setToast(null), 3000)
    }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error cargando productos: ${error}`} />

  // Botones de filtro dinámicos
  const filtros = [
    { key: 'todos',  label: 'Todos',           icono: '📦' },
    { key: 'favs',   label: 'Favoritos',        icono: '⭐' },
    { key: 'top',    label: 'Top productos',    icono: '🏆' },
    ...catsOrdenadas.map(cat => ({ key: cat, label: catLabel(cat), icono: iconCat(cat) })),
  ]

  // ── Render ─────────────────────────────────────────────────────────────────
  const seccionProps = { carrito, favKeys, onClickProd: clickProd, onFav: toggleFav, columnas }

  // Qué mostrar según filtro activo
  const mostrarSeccion = (key) => !busq.trim() && (filtro === 'todos' || filtro === key)

  const totalItems = carrito.reduce((s, c) => s + (c.qty || 1), 0)

  return (
    <div style={{ position: 'relative' }}>
      <style>{`
        .vr-filtros::-webkit-scrollbar { display: none }
        .vr-filtros { -ms-overflow-style: none; scrollbar-width: none }
      `}</style>

      {/* ══ LAYOUT DESKTOP: grid | MÓVIL: columna ══ */}
      <div style={{
        display: isMobile ? 'block' : 'grid',
        gridTemplateColumns: '1fr 310px',
        gap: 16, alignItems: 'start',
        paddingBottom: isMobile ? 150 : 0,
      }}>

      {/* ══ PANEL IZQUIERDO ══ */}
      <div>

        {/* ── Botones de filtro + selector columnas ── */}
        <div style={{ marginBottom: 12 }}>
        <div className="vr-filtros" style={{
          display: 'flex', alignItems: 'center', gap: 6,
          overflowX: 'auto', paddingBottom: 4,
          flexWrap: isMobile ? 'nowrap' : 'wrap',
        }}>
          {filtros.map(f => {
            const activo = filtro === f.key
            return (
              <button
                key={f.key}
                onClick={() => { setFiltro(f.key); setBusq(''); setSubcatFiltro(null) }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '5px 12px', borderRadius: 99,
                  background: activo ? t.accentSub : 'transparent',
                  border: `1px solid ${activo ? t.accent : t.border}`,
                  color: activo ? t.accent : t.textMuted,
                  fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                  transition: 'all .15s', whiteSpace: 'nowrap',
                }}
                onMouseEnter={e => { if (!activo) { e.currentTarget.style.borderColor = t.accent + '66'; e.currentTarget.style.color = t.text } }}
                onMouseLeave={e => { if (!activo) { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.textMuted } }}
              >
                <span>{f.icono}</span>
                {f.label}
              </button>
            )
          })}

          {/* Espaciador */}
          <div style={{ flex: 1 }} />

          {/* Selector de columnas */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 10, color: t.textMuted, marginRight: 2 }}>Columnas:</span>
            {[4, 5, 6].map(n => (
              <button
                key={n}
                onClick={() => setColumnas(n)}
                style={{
                  width: 26, height: 26, borderRadius: 6,
                  background: columnas === n ? t.accentSub : 'transparent',
                  border: `1px solid ${columnas === n ? t.accent : t.border}`,
                  color: columnas === n ? t.accent : t.textMuted,
                  fontSize: 11, fontWeight: 600, cursor: 'pointer',
                  fontFamily: 'inherit', transition: 'all .15s',
                }}
              >{n}</button>
            ))}
          </div>
        </div>
        </div>

        {/* ── Búsqueda ── */}
        <div style={{ position: 'relative', marginBottom: 18 }}>
          <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: t.textMuted, pointerEvents: 'none' }}>🔍</span>
          <input
            value={busq} onChange={e => { setBusq(e.target.value); if (e.target.value) setFiltro('todos') }}
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

        {/* ── Subcategorías ── */}
        {subcatsDisp.length > 0 && !busq.trim() && (
          <div style={{
            display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 4, marginBottom: 12,
            scrollbarWidth: 'none',
          }}>
            <style>{`.sc-bar::-webkit-scrollbar{display:none}`}</style>
            <button
              onClick={() => setSubcatFiltro(null)}
              style={{
                padding: '5px 13px', borderRadius: 99, whiteSpace: 'nowrap', cursor: 'pointer',
                background: !subcatFiltro ? t.accentSub : 'transparent',
                border: `1px solid ${!subcatFiltro ? t.accent : t.border}`,
                color: !subcatFiltro ? t.accent : t.textMuted,
                fontSize: 11, fontFamily: 'inherit', flexShrink: 0,
              }}
            >Todos</button>
            {subcatsDisp.map(sub => {
              const active = subcatFiltro === sub.key
              return (
                <button key={sub.key} onClick={() => setSubcatFiltro(active ? null : sub.key)} style={{
                  padding: '5px 13px', borderRadius: 99, whiteSpace: 'nowrap', cursor: 'pointer',
                  background: active ? t.accentSub : 'transparent',
                  border: `1px solid ${active ? t.accent : t.border}`,
                  color: active ? t.accent : t.textMuted,
                  fontSize: 11, fontFamily: 'inherit', flexShrink: 0,
                  display: 'flex', alignItems: 'center', gap: 5,
                }}>
                  <span>{sub.icono}</span>{sub.label}
                </button>
              )
            })}
          </div>
        )}

        {busq.trim() ? (
          <Seccion icono="🔍" titulo={`"${busq}"`} cantidad={prodsFiltrados.length} productos={prodsFiltrados} {...seccionProps} />
        ) : (
          <>
            {/* ── Favoritos ── */}
            {mostrarSeccion('favs') && (
              favs.length > 0 ? (
                <Seccion icono="⭐" titulo="Favoritos" cantidad={favs.length} productos={favs} {...seccionProps} />
              ) : filtro === 'favs' ? (
                <div style={{
                  border: `1px dashed ${t.border}`, borderRadius: 9,
                  padding: '24px 16px', marginBottom: 22, textAlign: 'center',
                }}>
                  <div style={{ fontSize: 28, opacity: .3, marginBottom: 8 }}>⭐</div>
                  <span style={{ fontSize: 12, color: t.textMuted }}>
                    Aún no tienes favoritos.<br />Marca la <strong style={{ color: '#fbbf24' }}>★</strong> en cualquier producto para agregarlo.
                  </span>
                </div>
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
              )
            )}

            {/* ── Top productos ── */}
            {mostrarSeccion('top') && tops.length > 0 && (
              <Seccion icono="🏆" titulo="Top productos del mes" cantidad={tops.length} productos={tops} {...seccionProps} />
            )}

            {/* ── Categorías ── */}
            {catsOrdenadas.map(cat => {
              if (!mostrarSeccion(cat)) return null
              const prodsCat = aplicarSubcat(catMap[cat])
              if (prodsCat.length === 0) return null
              const subActiva = subcatsDisp.find(s => s.key === subcatFiltro)
              const titulo = subActiva && cat === catActivaKey
                ? `${catLabel(cat)} › ${subActiva.icono} ${subActiva.label}`
                : catLabel(cat)

              // Vista grupos de color (vinilos, esmaltes, lacas, aerosoles)
              const usarGrupos = subcatFiltro && SUBCATS_COLORES.includes(subcatFiltro)
              if (usarGrupos) {
                return (
                  <div key={cat}>
                    <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 10 }}>
                      {iconCat(cat)} {titulo}
                    </div>
                    <VistaGrupos
                      prods={prodsCat}
                      subcatKey={subcatFiltro}
                      carrito={carrito}
                      onClickProd={clickProd}
                      favKeys={favKeys}
                      onFav={toggleFav}
                      columnas={columnas}
                      onColorPrep={abrirColorPrep}
                    />
                  </div>
                )
              }

              return (
                <Seccion
                  key={cat}
                  icono={iconCat(cat)}
                  titulo={titulo}
                  cantidad={prodsCat.length}
                  productos={prodsCat}
                  {...seccionProps}
                />
              )
            })}
          </>
        )}
      </div>

      {/* ══ CARRITO — solo visible en desktop ══ */}
      {!isMobile && (
        <PanelCarrito
          t={t} carrito={carrito} totalCarrito={totalCarrito}
          vendedor={vendedor} setVendedor={setVendedor}
          metodo={metodo} setMetodo={setMetodo}
          clienteSeleccionado={clienteSeleccionado}
          setClienteSeleccionado={setClienteSeleccionado}
          removeItem={removeItem} qtyChange={qtyChange}
          registrar={registrar} enviando={enviando}
          sticky
        />
      )}

      </div>{/* fin grid */}

      {/* ══ MÓVIL: barra inferior fija del carrito ══ */}
      {isMobile && (
        <div style={{
          position: 'fixed', bottom: 62, left: 0, right: 0,
          zIndex: 200, padding: '10px 16px 10px',
          background: t.header,
          borderTop: `1px solid ${t.border}`,
          boxShadow: '0 -4px 20px rgba(0,0,0,.15)',
        }}>
          <button
            onClick={() => setCarritoAbierto(true)}
            style={{
              width: '100%', padding: '13px 18px',
              background: carrito.length ? t.accent : t.card,
              border: `1px solid ${carrito.length ? t.accent : t.border}`,
              borderRadius: 12, color: carrito.length ? '#fff' : t.textMuted,
              fontSize: 14, fontWeight: 600, fontFamily: 'inherit',
              cursor: 'pointer', display: 'flex',
              alignItems: 'center', justifyContent: 'space-between',
              transition: 'all .2s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 18 }}>🛒</span>
              {totalItems > 0 ? (
                <span>{totalItems} {totalItems === 1 ? 'producto' : 'productos'}</span>
              ) : (
                <span>Ver carrito</span>
              )}
            </div>
            {totalItems > 0 ? (
              <span style={{ fontSize: 16, fontVariantNumeric: 'tabular-nums' }}>{cop(totalCarrito)}</span>
            ) : (
              <span style={{ fontSize: 12, opacity: .5 }}>vacío</span>
            )}
          </button>
        </div>
      )}

      {/* ══ MÓVIL: bottom drawer del carrito ══ */}
      {isMobile && carritoAbierto && (
        <div
          onClick={e => e.target === e.currentTarget && setCarritoAbierto(false)}
          style={{
            position: 'fixed', inset: 0, background: '#00000077',
            zIndex: 300, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
          }}
        >
          <div style={{
            background: t.card, borderRadius: '18px 18px 0 0',
            maxHeight: '88vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
            animation: 'drawerUp .25s cubic-bezier(.34,1.2,.64,1)',
          }}>
            <style>{`@keyframes drawerUp{from{transform:translateY(100%)}to{transform:translateY(0)}}`}</style>
            {/* Handle */}
            <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 4px' }}>
              <div style={{ width: 36, height: 4, borderRadius: 99, background: t.border }} />
            </div>
            {/* Header drawer */}
            <div style={{
              padding: '8px 18px 12px', display: 'flex',
              alignItems: 'center', justifyContent: 'space-between',
              borderBottom: `1px solid ${t.border}`,
            }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>🛒 Carrito</span>
              <button onClick={() => setCarritoAbierto(false)} style={{
                background: 'none', border: 'none', color: t.textMuted,
                fontSize: 20, cursor: 'pointer', padding: '4px 8px',
              }}>✕</button>
            </div>
            {/* Contenido carrito */}
            <div style={{ overflowY: 'auto', flex: 1 }}>
              <PanelCarrito
                t={t} carrito={carrito} totalCarrito={totalCarrito}
                vendedor={vendedor} setVendedor={setVendedor}
                metodo={metodo} setMetodo={setMetodo}
                clienteSeleccionado={clienteSeleccionado}
                setClienteSeleccionado={setClienteSeleccionado}
                removeItem={removeItem} qtyChange={qtyChange}
                registrar={() => { registrar(); setCarritoAbierto(false) }}
                enviando={enviando}
                mobile
              />
            </div>
          </div>
        </div>
      )}

      {/* Modal color preparado */}
      <ModalColorPreparado
        show={modalColorPrep}
        precioBase={precioBaseColor}
        onClose={() => setModalColorPrep(false)}
        onConfirm={confirmarColorPrep}
      />

      {/* Modales */}
      <ModalFraccion prod={modalFrac} onClose={() => setModalFrac(null)} onConfirm={confirmarFrac} />
      <ModalCm       prod={modalCm}   onClose={() => setModalCm(null)}   onConfirm={confirmarCm}  />
      <ModalQty      prod={modalQty}  onClose={() => setModalQty(null)}  onConfirm={confirmarQty} />
      <ModalMlt      prod={modalMlt}  onClose={() => setModalMlt(null)}  onConfirm={confirmarMlt} />

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: isMobile ? 90 : 22, right: 22,
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
