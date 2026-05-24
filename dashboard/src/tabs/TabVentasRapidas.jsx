import { useState, useCallback, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Star, Trash2, ShoppingCart, User, X, Plus, Loader2 } from 'lucide-react'
import { useTheme, useFetch, Spinner, ErrorMsg, cop, API_BASE } from '../components/shared.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog.jsx'
import { Button } from '@/components/ui/button.jsx'
import { cn } from '@/lib/utils'
import { ModalCliente } from './TabClientes.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'
import {
  FAV_KEY, loadFavs, saveFavs,
  CART_KEY, loadCart, saveCart,
  CAT_ICON, iconCat, catLabel,
  nl, SUBCATS, ordenarTornilleria, tipoProd,
  GRUPOS_CONFIG, SUBCATS_COLORES, buildGrupos,
} from './ventasRapidas.helpers.js'


// ── Hook detección móvil ──────────────────────────────────────────────────────
function useIsMobile() {
  const getIsMobile = () => {
    if (typeof window === 'undefined') return false
    // Usar window.innerWidth, no screen — screen no se actualiza bien en todos los browsers al rotar
    return window.innerWidth < 768
  }
  const [v, setV] = useState(getIsMobile)
  useEffect(() => {
    const handler = () => {
      // Esperar 150ms después de rotate para que el DOM se estabilice
      setTimeout(() => setV(getIsMobile()), 150)
    }
    window.addEventListener('resize', handler)
    window.addEventListener('orientationchange', handler)
    return () => {
      window.removeEventListener('resize', handler)
      window.removeEventListener('orientationchange', handler)
    }
  }, [])
  return v
}

// ══════════════════════════════════════════════════════════════════════════════
// PRODUCT CARD
// ══════════════════════════════════════════════════════════════════════════════
const TIPO_BADGE = { cm: 'cm', mlt: 'ml', grm: 'gr', kg: 'kg', fraccion: '½' }

function ProdCard({ prod, onClick, isFav, onFav, cantCarrito, isHighlighted }) {
  const tipo     = tipoProd(prod)
  const enCarro  = cantCarrito > 0
  const tipoTxt  = TIPO_BADGE[tipo]

  return (
    <Card
      onClick={() => onClick(prod)}
      className={cn(
        'group relative cursor-pointer select-none px-2.5 pt-2.5 pb-2 rounded-md transition-all',
        'hover:-translate-y-px hover:border-primary/60 hover:shadow-md',
        enCarro    ? 'bg-primary-soft border-primary/40' : 'bg-card border-border',
        isHighlighted && 'ring-2 ring-primary/40 border-primary',
      )}
    >
      {/* Estrella favorito */}
      <button
        type="button"
        onClick={e => { e.stopPropagation(); onFav(prod.key) }}
        title={isFav ? 'Quitar de favoritos' : 'Agregar a favoritos'}
        className={cn(
          'absolute top-1.5 right-1.5 leading-none transition-opacity',
          isFav ? 'opacity-100 text-warning' : 'opacity-40 text-muted-foreground hover:opacity-100',
        )}
      >
        <Star className={cn('size-3.5', isFav && 'fill-current')} />
      </button>

      {/* Badge cantidad en carrito */}
      {enCarro && (
        <span className="absolute top-1.5 left-1.5 inline-flex items-center justify-center px-1.5 py-0.5 text-[9px] font-bold leading-none rounded-full bg-primary text-primary-foreground tabular">
          {cantCarrito}
        </span>
      )}

      {/* Badge tipo fracción/cm */}
      {tipoTxt && (
        <span className="absolute bottom-1.5 right-1.5 text-[9px] font-mono px-1 py-px rounded bg-muted text-muted-foreground">
          {tipoTxt}
        </span>
      )}

      <div className={cn('text-[17px] mb-1', enCarro && 'mt-2')}>
        {iconCat(prod.categoria)}
      </div>
      <div className="text-[11px] font-semibold text-foreground leading-snug mb-0.5 pr-3">
        {prod.nombre}
      </div>
      <div className="text-[11px] font-mono text-success">
        {cop(prod.precio)}
      </div>
    </Card>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// SECCIÓN
// ══════════════════════════════════════════════════════════════════════════════
function Seccion({ icono, titulo, cantidad, productos, carrito, favKeys, onClickProd, onFav, columnas = 6, highlightedKey }) {
  if (!productos.length) return null
  return (
    <section className="mb-6">
      {/* Header sección */}
      <div className="flex items-center gap-2 mb-2.5">
        <span className="text-sm">{icono}</span>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {titulo}
        </span>
        <div className="flex-1 h-px bg-border" />
        <span className="text-[10px] font-mono text-muted-foreground">{cantidad}</span>
      </div>

      {/* Grid */}
      <div
        className="grid gap-[7px]"
        style={{ gridTemplateColumns: `repeat(${columnas}, minmax(0, 1fr))` }}
      >
        {productos.map(p => (
          <ProdCard
            key={p.key}
            prod={p}
            onClick={onClickProd}
            isFav={favKeys.includes(p.key)}
            onFav={onFav}
            cantCarrito={carrito.filter(c => c.key === p.key).reduce((s, c) => s + (c.qty || 1), 0)}
            isHighlighted={p.key === highlightedKey}
          />
        ))}
      </div>
    </section>
  )
}

// ── Portal root dedicado (evita overlay negro en PWA iOS/Android) ─────────────
function getPortalRoot() {
  let el = document.getElementById('modal-portal-root')
  if (!el) {
    el = document.createElement('div')
    el.id = 'modal-portal-root'
    el.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;pointer-events:none;'
    document.body.appendChild(el)
  }
  return el
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL BASE
// ══════════════════════════════════════════════════════════════════════════════
// Shell unificado: Dialog shadcn + footer Cancelar/Confirmar.
// API legacy preservada para que los 6 modales hijos sigan funcionando sin cambios.
function Modal({ show, onClose, title, subtitle, children, onConfirm, okLabel = 'Agregar al carrito', okDisabled, maxWidth = 'sm:max-w-[390px]' }) {
  if (!show) return null
  return (
    <Dialog open={show} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent
        className={cn(
          'p-0 gap-0 overflow-hidden max-h-[85vh] overflow-y-auto',
          maxWidth,
        )}
      >
        <DialogHeader className="px-[18px] pt-4 pb-3 border-b border-border">
          <DialogTitle className="text-sm font-bold">{title}</DialogTitle>
          {subtitle && (
            <DialogDescription className="text-[11px] mt-0.5">{subtitle}</DialogDescription>
          )}
        </DialogHeader>
        <div className="px-[18px] py-3.5">{children}</div>
        <DialogFooter className="px-[18px] pb-[18px] flex-row gap-2 sm:justify-stretch">
          <Button variant="secondary" onClick={onClose} className="flex-1 h-10 text-xs">
            Cancelar
          </Button>
          <Button
            onClick={onConfirm}
            disabled={okDisabled}
            className="flex-[2] h-10 text-xs font-semibold"
          >
            {okLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PrecioEditor({ precioCalc, precioFinal, onChange, desc }) {
  const mod = precioFinal !== precioCalc
  return (
    <div className={cn(
      'rounded-md bg-muted px-3 py-2.5 border',
      mod ? 'border-warning/60' : 'border-border',
    )}>
      <div className="flex justify-between items-center gap-2.5">
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-muted-foreground mb-0.5">{desc || '—'}</div>
          {mod && <div className="text-[9px] text-warning">✏️ Precio especial · base {cop(precioCalc)}</div>}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-sm text-muted-foreground">$</span>
          <input
            type="number" min="0"
            value={precioFinal === 0 ? '' : precioFinal}
            onChange={e => onChange(parseInt(e.target.value) || 0)}
            className={cn(
              'w-[100px] bg-transparent border-0 border-b text-right text-lg font-mono font-bold outline-none px-0 py-0.5 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none',
              mod ? 'text-warning border-warning' : 'text-primary border-primary/40',
            )}
          />
        </div>
      </div>
      {mod && (
        <button
          type="button"
          onClick={() => onChange(precioCalc)}
          className="mt-1 text-[9px] text-muted-foreground bg-transparent border-0 cursor-pointer p-0"
        >↩ Volver al precio original</button>
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
// MODAL GRM — Puntillas por gramos / por pesos
// ══════════════════════════════════════════════════════════════════════════════
const PESO_CAJA_GR = 500

function ModalGrm({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [modo,  setModo]  = useState('pesos')  // 'pesos' | 'gramos'
  const [valor, setValor] = useState('')
  if (!prod) return null

  const precioCaja = prod.precio                    // precio 1 caja (500 gr)
  const precioGr   = precioCaja / PESO_CAJA_GR      // pesos por gramo

  const valorNum  = parseFloat(valor) || 0
  const gramosCalc  = modo === 'pesos'
    ? (valorNum > 0 ? Math.round((valorNum / precioGr) * 10) / 10 : 0)
    : valorNum
  const totalCalc   = modo === 'pesos'
    ? valorNum
    : Math.round(valorNum * precioGr)

  const valido = valorNum > 0 && gramosCalc > 0 && totalCalc > 0

  const ACCESOS = [
    { label: 'Caja completa', gr: 500,  icon: '📦' },
    { label: '½ caja',        gr: 250,  icon: '½'  },
    { label: '¼ caja',        gr: 125,  icon: '¼'  },
  ]

  const confirmar = () => {
    if (!valido) return
    const grDesc = gramosCalc >= 500
      ? `${gramosCalc / 500} caja${gramosCalc / 500 !== 1 ? 's' : ''}`
      : `${gramosCalc} gr`
    onConfirm({ gramos: gramosCalc, total: totalCalc, desc: grDesc })
  }

  return (
    <Modal show title={prod.nombre}
      subtitle={`$${precioGr.toFixed(0)}/gr · ${cop(precioCaja)} por caja (500 gr)`}
      onClose={onClose} onConfirm={confirmar} okDisabled={!valido}
      okLabel="Agregar al carrito">

      {/* Accesos rápidos */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        {ACCESOS.map(a => {
          const activo = modo === 'gramos' && parseFloat(valor) === a.gr
          return (
            <button key={a.gr} onClick={() => { setModo('gramos'); setValor(String(a.gr)) }}
              style={{
                flex: 1, padding: '8px 4px', borderRadius: 8, cursor: 'pointer', textAlign: 'center',
                background: activo ? t.accentSub : (t.id === 'caramelo' ? '#f1f5f9' : '#111'),
                border: `1px solid ${activo ? t.accent : t.border}`,
                color: activo ? t.accent : t.text,
                fontSize: 11, fontFamily: 'inherit', transition: 'all .15s',
              }}>
              <div style={{ fontSize: 16, marginBottom: 3 }}>{a.icon}</div>
              <div style={{ fontWeight: 600 }}>{a.label}</div>
              <div style={{ fontSize: 10, color: t.textMuted, marginTop: 1 }}>
                {cop(Math.round(a.gr * precioGr))}
              </div>
            </button>
          )
        })}
      </div>

      {/* Toggle modo */}
      <div style={{
        display: 'flex', background: t.id === 'caramelo' ? '#f1f5f9' : '#111',
        border: `1px solid ${t.border}`, borderRadius: 8, padding: 3, marginBottom: 12, gap: 3,
      }}>
        {[
          { key: 'pesos',  label: '$ Pesos',    hint: 'El cliente dice cuánto plata' },
          { key: 'gramos', label: 'gr Gramos',  hint: 'Sabes exactamente cuántos gramos' },
        ].map(m => (
          <button key={m.key} onClick={() => { setModo(m.key); setValor('') }} style={{
            flex: 1, padding: '7px 6px', borderRadius: 6, cursor: 'pointer',
            background: modo === m.key ? t.card : 'transparent',
            border: `1px solid ${modo === m.key ? t.accent + '55' : 'transparent'}`,
            color: modo === m.key ? t.accent : t.textMuted,
            fontSize: 11, fontFamily: 'inherit', fontWeight: modo === m.key ? 600 : 400,
            transition: 'all .15s',
          }}>{m.label}</button>
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
          {modo === 'pesos' ? '$' : 'gr'}
        </span>
        <input
          autoFocus type="number" min="1" value={valor}
          onChange={e => setValor(e.target.value)}
          placeholder={modo === 'pesos' ? 'ej: 2000' : 'ej: 250'}
          style={{
            flex: 1, background: 'transparent', border: 'none',
            color: t.text, fontSize: 26, fontFamily: 'monospace',
            outline: 'none', textAlign: 'center',
            MozAppearance: 'textfield', appearance: 'textfield',
          }}
        />
      </div>

      {/* Resultado */}
      {valido && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: t.accentSub, border: `1px solid ${t.accent}33`,
          borderRadius: 8, padding: '10px 14px', marginBottom: 4,
        }}>
          <div>
            <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 2 }}>
              {modo === 'pesos' ? 'Gramos a entregar' : 'Total a cobrar'}
            </div>
            <div style={{ fontSize: 18, fontFamily: 'monospace', fontWeight: 700, color: t.accent }}>
              {modo === 'pesos' ? `${gramosCalc} gr` : cop(totalCalc)}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 2 }}>
              {modo === 'pesos' ? 'Total' : 'Gramos'}
            </div>
            <div style={{ fontSize: 13, color: t.text, fontFamily: 'monospace' }}>
              {modo === 'pesos' ? cop(totalCalc) : `${gramosCalc} gr`}
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL KG — Productos por kilo (Acronal, Yeso, Cemento Blanco, etc.)
// ══════════════════════════════════════════════════════════════════════════════
function ModalKg({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [kg, setKg] = useState('')
  const [precioCustom, setPrecioCustom] = useState(null)
  if (!prod) return null

  // Para medio kilo: usar precios_fraccion['1/2'].precio si existe,
  // de lo contrario calcular 0.5 × precio.
  // SQL para fijar el precio de fracción en Railway:
  //   UPDATE productos
  //   SET precios_fraccion = jsonb_set(COALESCE(precios_fraccion,'{}'),'{1/2}','{"precio":7000}')
  //   WHERE nombre ILIKE '%acronal%';
  const fracHalf = prod.precios_fraccion?.['1/2']?.precio ?? null

  const calcPrecioKg = (v) => {
    if (v === 0) return 0
    const ent = Math.floor(v)
    const med = (v % 1).toFixed(1) === '0.5'
    const baseEntera = ent * (prod.precio || 0)
    const baseMedio  = med
      ? (fracHalf !== null ? fracHalf : Math.round((prod.precio || 0) * 0.5))
      : 0
    return Math.round(baseEntera + baseMedio)
  }

  const kgNum     = parseFloat(kg) || 0
  const totalCalc = calcPrecioKg(kgNum)
  const precioFinal = precioCustom !== null ? precioCustom : totalCalc
  const valido    = kgNum > 0

  const ACCESOS = [
    { label: '½ kg',  kg: 0.5 },
    { label: '1 kg',  kg: 1   },
    { label: '1½ kg', kg: 1.5 },
    { label: '2 kg',  kg: 2   },
    { label: '2½ kg', kg: 2.5 },
    { label: '3 kg',  kg: 3   },
  ]

  const kgDesc = (v) => {
    const ent = Math.floor(v)
    const med = (v % 1).toFixed(1) === '0.5'
    if (med && ent === 0) return '½ kg'
    if (med) return `${ent}½ kg`
    return `${ent} kg`
  }

  const confirmar = () => {
    if (!valido) return
    onConfirm({ kg: kgNum, total: precioFinal, desc: kgDesc(kgNum) })
  }

  return (
    <Modal show title={prod.nombre}
      subtitle={`${cop(prod.precio)}/kg${fracHalf !== null ? ` · ½kg: ${cop(fracHalf)}` : ''}`}
      onClose={onClose} onConfirm={confirmar} okDisabled={!valido}
      okLabel="Agregar al carrito">

      {/* Accesos rápidos */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 16 }}>
        {ACCESOS.map(a => {
          const activo = parseFloat(kg) === a.kg
          return (
            <button key={a.kg} onClick={() => { setKg(String(a.kg)); setPrecioCustom(null) }}
              style={{
                padding: '8px 4px', borderRadius: 8, cursor: 'pointer', textAlign: 'center',
                background: activo ? t.accentSub : (t.id === 'caramelo' ? '#f1f5f9' : '#111'),
                border: `1px solid ${activo ? t.accent : t.border}`,
                color: activo ? t.accent : t.text,
                fontSize: 12, fontFamily: 'inherit', transition: 'all .15s',
              }}>
              <div style={{ fontWeight: 600 }}>{a.label}</div>
              <div style={{ fontSize: 10, color: t.textMuted, marginTop: 2 }}>
                {cop(calcPrecioKg(a.kg))}
              </div>
            </button>
          )
        })}
      </div>

      {/* Input personalizado */}
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad personalizada (kg)
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        background: t.id === 'caramelo' ? '#f8fafc' : '#111',
        border: `1px solid ${t.accent}66`, borderRadius: 8,
        padding: '10px 14px', marginBottom: 8,
      }}>
        <input autoFocus type="number" min="0.5" step="0.5" value={kg}
          onChange={e => { setKg(e.target.value); setPrecioCustom(null) }}
          style={{
            flex: 1, background: 'transparent', border: 'none',
            color: t.text, fontSize: 26, fontFamily: 'monospace',
            outline: 'none', textAlign: 'center',
            MozAppearance: 'textfield', appearance: 'textfield',
          }}
          placeholder="0"
        />
        <span style={{ fontSize: 13, color: t.textMuted }}>kg</span>
      </div>
      <PrecioEditor precioCalc={totalCalc} precioFinal={precioFinal} onChange={setPrecioCustom} desc={kgDesc(kgNum)} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL QTY SIMPLE
// ══════════════════════════════════════════════════════════════════════════════
function ModalQty({ prod, onClose, onConfirm }) {
  const t = useTheme()
  const [qtyStr, setQtyStr] = useState('1')  // string para permitir borrar el campo
  const [precioCustom, setPrecioCustom] = useState(null)
  if (!prod) return null

  const qty       = parseInt(qtyStr) || 0
  const may       = prod.mayorista
  const esMayorista = may && qty >= may.umbral
  const precioUnit  = esMayorista ? may.precio : prod.precio
  const totalCalc   = qty * precioUnit
  const precioFinal = precioCustom !== null ? precioCustom : totalCalc
  const desc      = `${qty} ${qty === 1 ? 'unidad' : 'unidades'}${esMayorista ? ' (mayorista)' : ''}`
  const valido    = qty >= 1

  const cambiarQtyNum = (fn) => {
    setQtyStr(String(Math.max(1, fn(qty))))
    setPrecioCustom(null)
  }

  return (
    <Modal show title={prod.nombre} subtitle={`Precio unitario: ${cop(prod.precio)}${may ? ` · Mayorista ×${may.umbral}: ${cop(may.precio)}` : ''}`}
      onClose={onClose}
      onConfirm={() => valido && onConfirm({ qty, total: precioFinal, desc })}
      okDisabled={!valido}>
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
        Cantidad
      </div>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14,
        background: t.id === 'caramelo' ? '#f8fafc' : '#111',
        border: `1px solid ${esMayorista ? t.blue : t.accent}66`, borderRadius: 8,
        padding: 14, marginBottom: 14,
      }}>
        <button onClick={() => cambiarQtyNum(q => Math.max(1, q - 1))} style={{ width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 20 }}>−</button>
        <input
          autoFocus
          type="number" min="1"
          value={qtyStr}
          onChange={e => { setQtyStr(e.target.value); setPrecioCustom(null) }}
          onBlur={e => { if (!parseInt(e.target.value) || parseInt(e.target.value) < 1) setQtyStr('1') }}
          style={{
            width: 60, background: 'transparent', border: 'none',
            borderBottom: `1px solid ${esMayorista ? t.blue : t.accent}66`,
            color: t.text, fontSize: 26, fontFamily: 'monospace',
            outline: 'none', textAlign: 'center', padding: '2px 0',
            MozAppearance: 'textfield', appearance: 'textfield',
          }}
        />
        <button onClick={() => cambiarQtyNum(q => q + 1)} style={{ width: 34, height: 34, background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, color: t.text, cursor: 'pointer', fontSize: 20 }}>+</button>
      </div>

      {/* Indicador mayorista */}
      {may && (
        <div style={{
          padding: '6px 10px', borderRadius: 7, marginBottom: 10, fontSize: 11,
          background: esMayorista ? `${t.blue}18` : t.tableAlt,
          border: `1px solid ${esMayorista ? t.blue + '44' : t.border}`,
          color: esMayorista ? t.blue : t.textMuted,
          textAlign: 'center', fontWeight: esMayorista ? 600 : 400,
          transition: 'all .2s',
        }}>
          {esMayorista
            ? `✓ Precio mayorista: ${cop(may.precio)} c/u (desde ${may.umbral} uds)`
            : `Mayorista desde ${may.umbral} uds → ${cop(may.precio)} c/u`
          }
        </div>
      )}

      <PrecioEditor precioCalc={totalCalc} precioFinal={precioFinal} onChange={setPrecioCustom} desc={desc} />
    </Modal>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// CARRITO ITEM
// ══════════════════════════════════════════════════════════════════════════════
function CartItem({ item, idx, onRemove, onQtyChange, onQtySet }) {
  const [editingQty, setEditingQty] = useState(false)
  const [qtyInput,   setQtyInput]   = useState(String(item.qty))
  const inputRef = useRef(null)

  useEffect(() => {
    if (editingQty && inputRef.current) inputRef.current.select()
  }, [editingQty])

  const commitEdit = () => {
    const n = parseInt(qtyInput)
    if (n >= 1) onQtySet(idx, n)
    setEditingQty(false)
  }

  return (
    <div className="px-3.5 py-2 border-b border-border animate-in fade-in slide-in-from-right-1 duration-150">
      {/* Fila principal: nombre + total + trash */}
      <div className={cn('flex items-center gap-2', item.tipo === 'simple' && 'mb-1.5')}>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] text-foreground truncate">{item.nombre}</div>
          <div className="text-[10px] text-muted-foreground mt-px">{item.desc}</div>
        </div>
        <div className="text-[11px] font-mono text-success min-w-[54px] text-right tabular">{cop(item.total)}</div>
        <button
          type="button"
          onClick={() => onRemove(idx)}
          title="Eliminar"
          className="text-muted-foreground hover:text-primary transition-colors shrink-0 px-1 py-0.5"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>

      {/* Fila multiplicadores — solo productos simples */}
      {item.tipo === 'simple' && (
        <div className="flex items-center gap-1 flex-wrap">
          {[1, 2, 3, 5, 10].map(m => (
            <button
              key={m}
              type="button"
              onClick={() => onQtySet(idx, m)}
              className={cn(
                'px-1.5 py-0.5 rounded text-[10px] border transition-colors',
                item.qty === m
                  ? 'bg-primary-soft border-primary text-primary font-bold'
                  : 'bg-muted border-border text-muted-foreground hover:border-primary/40',
              )}
            >×{m}</button>
          ))}
          {editingQty ? (
            <input
              ref={inputRef}
              type="number" min="1"
              value={qtyInput}
              onChange={e => setQtyInput(e.target.value)}
              onBlur={commitEdit}
              onKeyDown={e => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditingQty(false) }}
              className="w-10 text-[11px] font-mono text-center bg-transparent border-0 border-b border-primary text-primary outline-none px-0 py-px [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
            />
          ) : (
            <span
              onDoubleClick={() => { setQtyInput(String(item.qty)); setEditingQty(true) }}
              title="Doble clic para cantidad personalizada"
              className="text-[10px] font-mono text-muted-foreground cursor-text px-1.5 py-0.5 rounded border border-dashed border-border min-w-[24px] text-center"
            >{item.qty}</span>
          )}
        </div>
      )}
    </div>
  )
}




// ══════════════════════════════════════════════════════════════════════════════
// MODAL CHECKOUT
// ══════════════════════════════════════════════════════════════════════════════
function ModalCheckout({ show, total, metodo, setMetodo, onClose, onConfirm, enviando }) {
  const [recibido, setRecibido] = useState('')

  useEffect(() => { if (show) setRecibido('') }, [show])

  if (!show) return null
  const recNum = parseInt(recibido) || 0
  const cambio = recibido !== '' && recNum >= total ? recNum - total : null

  const METODOS = [
    { key: 'efectivo',      label: 'Efectivo',  icon: '💵' },
    { key: 'transferencia', label: 'Transfer.', icon: '📲' },
    { key: 'datafono',      label: 'Datáfono',  icon: '💳' },
  ]

  return (
    <Dialog open={show} onOpenChange={(o) => { if (!o && !enviando) onClose() }}>
      <DialogContent className="p-0 gap-0 overflow-hidden sm:max-w-[360px]">
        <DialogHeader className="px-[18px] pt-4 pb-3 border-b border-border">
          <DialogTitle className="text-[15px] font-bold">Confirmar venta</DialogTitle>
        </DialogHeader>
        <div className="px-[18px] py-4">
          {/* Total */}
          <div className="text-center mb-5">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Total a cobrar</div>
            <div className="text-[38px] font-mono font-extrabold text-primary tabular">{cop(total)}</div>
          </div>

          {/* Método de pago */}
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Método de pago</div>
          <div className="grid grid-cols-3 gap-1.5 mb-4">
            {METODOS.map(m => {
              const active = metodo === m.key
              return (
                <button
                  key={m.key}
                  type="button"
                  onClick={() => setMetodo(m.key)}
                  className={cn(
                    'flex flex-col items-center gap-0.5 py-2 px-1 rounded-md border text-[10px] transition-colors',
                    active
                      ? 'bg-primary-soft border-primary text-primary'
                      : 'bg-muted border-border text-muted-foreground hover:border-primary/40',
                  )}
                >
                  <span className="text-base">{m.icon}</span>{m.label}
                </button>
              )
            })}
          </div>

          {/* Recibido + cambio (solo efectivo) */}
          {metodo === 'efectivo' && (
            <>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Recibido (opcional)</div>
              <div className="flex items-center gap-2 bg-muted border border-border rounded-md px-3 py-2.5 mb-2.5">
                <span className="text-sm text-muted-foreground">$</span>
                <input
                  autoFocus
                  type="number" min="0"
                  value={recibido}
                  onChange={e => setRecibido(e.target.value)}
                  placeholder={String(total)}
                  className="flex-1 bg-transparent border-0 text-foreground text-[22px] font-mono outline-none py-0.5 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
                />
              </div>
              {cambio !== null && (
                <div className="flex justify-between items-center px-3 py-2 mb-1.5 rounded-md bg-success/10 border border-success/30">
                  <span className="text-[11px] text-success">Cambio</span>
                  <span className="text-xl font-mono font-bold text-success tabular">{cop(cambio)}</span>
                </div>
              )}
            </>
          )}
        </div>
        <DialogFooter className="px-[18px] pb-[18px] flex-row gap-2 sm:justify-stretch">
          <Button variant="secondary" onClick={onClose} disabled={enviando} className="flex-1 h-10 text-xs">
            Cancelar
          </Button>
          <Button onClick={onConfirm} disabled={enviando} className="flex-[2] h-10 text-[13px] font-bold">
            {enviando ? 'Registrando...' : '✓ Registrar venta'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// MODAL MISCELÁNEA
// ══════════════════════════════════════════════════════════════════════════════
function ModalMiscelanea({ show, onClose, onConfirm }) {
  const [monto, setMonto] = useState('')
  const [desc,  setDesc]  = useState('')

  useEffect(() => { if (show) { setMonto(''); setDesc('') } }, [show])

  if (!show) return null
  const montoNum = parseInt(monto) || 0
  const valid = montoNum > 0
  const submit = () => valid && onConfirm({ monto: montoNum, desc: desc.trim() || 'Miscelánea' })

  return (
    <Dialog open={show} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="p-0 gap-0 overflow-hidden sm:max-w-[360px]">
        <DialogHeader className="px-[18px] pt-4 pb-3 border-b border-border">
          <DialogTitle className="text-[15px] font-bold">💸 Venta miscelánea</DialogTitle>
          <DialogDescription className="text-[11px] mt-0.5">
            Monto libre · no descuenta inventario
          </DialogDescription>
        </DialogHeader>
        <div className="px-[18px] py-4">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Monto</div>
          <div className="flex items-center gap-2 bg-muted border border-border rounded-md px-3 py-2.5 mb-4">
            <span className="text-sm text-muted-foreground">$</span>
            <input
              autoFocus
              type="number" min="0"
              value={monto}
              onChange={e => setMonto(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submit()}
              placeholder="0"
              className="flex-1 bg-transparent border-0 text-foreground text-[22px] font-mono outline-none py-0.5 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
            />
          </div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Descripción (opcional)</div>
          <input
            type="text"
            value={desc}
            onChange={e => setDesc(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            placeholder="ej: Miscelánea varios"
            className="w-full bg-muted border border-border rounded-md text-foreground text-[13px] px-3 py-2.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        <DialogFooter className="px-[18px] pb-[18px] flex-row gap-2 sm:justify-stretch">
          <Button variant="secondary" onClick={onClose} className="flex-1 h-10 text-xs">Cancelar</Button>
          <Button onClick={submit} disabled={!valid} className="flex-[2] h-10 text-[13px] font-bold">
            Agregar al carrito
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

function ModalColorPreparado({ show, precioBase, nombreProducto, onClose, onConfirm }) {
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
  const submit = () => valid && onConfirm({ desc: desc.trim(), descCompleta, precio: precioFinal })

  return (
    <Dialog open={show} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="p-[22px_20px] gap-0 sm:max-w-[400px] max-h-[90vh] overflow-y-auto">
        <DialogHeader className="space-y-0">
          <DialogTitle className="text-[15px] font-bold">🎨 Color Preparado</DialogTitle>
          {nombreProducto && (
            <div className="text-xs font-semibold text-primary">{nombreProducto}</div>
          )}
          <DialogDescription className="text-[11px]">
            El cliente trae la muestra y se prepara en tienda
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4">
          {/* Descripción */}
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5">Descripción del color</div>
          <input
            autoFocus value={desc} onChange={e => setDesc(e.target.value)}
            placeholder="ej: Vinilo T1 mostaza cliente"
            className="w-full bg-muted border border-primary/40 rounded-md text-foreground text-[13px] px-3 py-2.5 outline-none mb-4 focus-visible:ring-2 focus-visible:ring-ring"
          />

          {/* Cantidad en galones */}
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Galones completos</div>
          <div className="flex items-center justify-center gap-3.5 bg-muted border border-border rounded-md px-3.5 py-2.5 mb-4">
            <button type="button"
              onClick={() => { setQty(q => Math.max(0, q-1)); setModoPrecio(false) }}
              className="w-8 h-8 bg-card border border-border rounded-md text-foreground cursor-pointer text-lg">−</button>
            <input type="number" min="0" value={qty}
              onChange={e => { setQty(parseInt(e.target.value)||0); setModoPrecio(false) }}
              className="w-[52px] bg-transparent border-0 border-b border-border text-foreground text-[22px] font-mono outline-none text-center [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
            />
            <button type="button"
              onClick={() => { setQty(q => q+1); setModoPrecio(false) }}
              className="w-8 h-8 bg-card border border-border rounded-md text-foreground cursor-pointer text-lg">+</button>
          </div>

          {/* Fracción adicional */}
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">Fracción adicional</div>
          <div className="flex flex-wrap gap-1.5 mb-4">
            {FRACS_CP.map(f => {
              const active = frac === f.k
              return (
                <button key={f.k||'gal'} type="button"
                  onClick={() => { if (f.k === null) return; setFrac(active ? null : f.k); setModoPrecio(false) }}
                  className={cn(
                    'px-3 py-1 rounded-full text-[11px] border transition-colors',
                    active
                      ? 'bg-primary-soft border-primary text-primary font-semibold'
                      : f.k
                        ? 'bg-muted border-border text-foreground hover:border-primary/40 cursor-pointer'
                        : 'bg-muted border-border text-muted-foreground cursor-default',
                  )}
                >{f.label}</button>
              )
            })}
          </div>

          {/* Precio total */}
          <div className={cn(
            'rounded-md bg-muted px-3 py-2.5 mb-5 border',
            modoPrecio ? 'border-warning/60' : 'border-border',
          )}>
            <div className="flex justify-between items-center">
              <div>
                <div className="text-[11px] text-muted-foreground">{descCompleta || '—'}</div>
                {modoPrecio && <div className="text-[9px] text-warning">✏️ Precio manual</div>}
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-sm text-muted-foreground">$</span>
                <input type="number" min="0"
                  value={precioFinal === 0 ? '' : precioFinal}
                  onChange={e => { setPrecio(parseInt(e.target.value)||0); setModoPrecio(true) }}
                  className={cn(
                    'w-[100px] bg-transparent border-0 border-b text-right text-lg font-mono font-bold outline-none px-0 py-0.5 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none',
                    modoPrecio ? 'text-warning border-warning' : 'text-primary border-primary/40',
                  )}
                />
              </div>
            </div>
            {modoPrecio && (
              <button type="button" onClick={() => setModoPrecio(false)}
                className="mt-1 text-[9px] text-muted-foreground bg-transparent border-0 cursor-pointer p-0">
                ↩ Volver al precio calculado ({cop(precioCalc)})
              </button>
            )}
          </div>
        </div>

        <DialogFooter className="grid grid-cols-2 gap-2 sm:justify-stretch">
          <Button variant="outline" onClick={onClose} className="h-10 text-[13px]">Cancelar</Button>
          <Button onClick={submit} disabled={!valid} className="h-10 text-[13px] font-semibold">
            Agregar al carrito
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// GRUPO COLORES — tarjeta grande con pills de colores
// ══════════════════════════════════════════════════════════════════════════════
const MOSTRAR_INICIAL = 8

function GrupoColores({ grupo, carrito, onAgregar, onColorPrep }) {
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
    <Card className="px-4 py-3.5 mb-3 rounded-xl">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-2.5">
        <div className="flex items-center gap-1.5">
          <span className="text-base">{grupo.icono}</span>
          <span className="text-[13px] font-bold text-foreground">{grupo.titulo}</span>
          <span className="text-[10px] text-muted-foreground">({etiquetaCount})</span>
        </div>
        {!grupo.sinPrecio && (
          <span className="text-[15px] font-mono font-bold text-primary tabular">{cop(precioBase)}</span>
        )}
      </div>

      {/* Pills de colores */}
      <div className="flex flex-wrap gap-1.5">
        {visibles.map(prod => {
          const color = grupo.getColor(prod)
          const enCarrito = carrito.some(c => c.key === prod.key)
          return (
            <button
              key={prod.key}
              type="button"
              onClick={() => onAgregar(prod)}
              className={cn(
                'px-3 py-1 rounded-full text-[11px] border whitespace-nowrap transition-colors',
                enCarrito
                  ? 'bg-primary-soft border-primary text-primary font-semibold'
                  : 'bg-muted border-border text-foreground hover:border-primary/40',
              )}
            >
              {enCarrito && <span className="mr-1 text-[9px]">✓</span>}
              {color}
            </button>
          )
        })}

        {/* Ver más / menos */}
        {hay_mas && (
          <button
            type="button"
            onClick={() => setExpandido(v => !v)}
            className="px-3 py-1 rounded-full text-[11px] bg-transparent border border-dashed border-border text-muted-foreground hover:border-primary/40 hover:text-foreground transition-colors"
          >
            {expandido ? '▲ ver menos' : `+${grupo.items.length - MOSTRAR_INICIAL} más`}
          </button>
        )}

        {/* Botón color preparado */}
        {onColorPrep && !grupo.sinColorPrep && !grupo.sinPrecio && (
          <button
            type="button"
            onClick={() => onColorPrep(precioBase, grupo.titulo)}
            className="px-3 py-1 rounded-full text-[11px] bg-transparent border border-primary/40 text-primary hover:bg-primary-soft inline-flex items-center gap-1 transition-colors"
          >
            🎨 Color preparado
          </button>
        )}
      </div>
    </Card>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// VISTA GRUPOS — contenedor que usa GrupoColores + cards sueltas
// ══════════════════════════════════════════════════════════════════════════════
function VistaGrupos({ prods, subcatKey, carrito, onClickProd, favKeys, onFav, columnas, onColorPrep }) {
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
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 mt-1">
            Otros
          </div>
          <div
            className="grid gap-2"
            style={{ gridTemplateColumns: `repeat(${columnas}, minmax(0, 1fr))` }}
          >
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
function SelectorCliente({ clienteSeleccionado, onSeleccionar }) {
  const [busq,       setBusq]       = useState('')
  const [resultados, setResultados] = useState([])
  const [buscando,   setBuscando]   = useState(false)
  const [abierto,    setAbierto]    = useState(false)
  const [modalNuevo, setModalNuevo] = useState(false)
  const timer = useRef(null)
  const { authFetch } = useAuth()

  const buscar = (q) => {
    setBusq(q)
    clearTimeout(timer.current)
    if (!q.trim() || q.trim().length < 2) { setResultados([]); setAbierto(false); return }
    setBuscando(true)
    setAbierto(true)
    timer.current = setTimeout(async () => {
      try {
        const r = await authFetch(`${API_BASE}/clientes/buscar?q=${encodeURIComponent(q)}`)
        const d = await r.json()
        setResultados(d.clientes || [])
      } catch { setResultados([]) }
      finally { setBuscando(false) }
    }, 350)
  }

  // c.id es el PK integer de la tabla clientes (FK en ventas.cliente_id)
  // c['Identificacion'] es la cédula/NIT — distinto, no usar como FK
  const seleccionar = (c) => {
    const nombre = c['Nombre tercero'] || ''
    const id = c.id != null ? c.id : null
    onSeleccionar({ nombre, id, datos: c })
    setBusq(''); setResultados([]); setAbierto(false)
  }

  const limpiar = () => { onSeleccionar(null); setBusq('') }

  if (clienteSeleccionado) return (
    <div className="px-3.5 py-2 border-t border-border">
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground mb-1">Cliente</div>
      <div className="flex items-center gap-2 bg-primary-soft border border-primary/30 rounded-md px-2.5 py-1.5">
        <User className="size-3.5 text-primary shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="text-xs font-semibold text-primary truncate">{clienteSeleccionado.nombre}</div>
          {clienteSeleccionado.id && (
            <div className="text-[10px] text-muted-foreground">ID: {clienteSeleccionado.id}</div>
          )}
        </div>
        <button
          type="button"
          onClick={limpiar}
          title="Quitar cliente"
          className="text-muted-foreground hover:text-primary px-0.5 shrink-0"
        >
          <X className="size-3.5" />
        </button>
      </div>
    </div>
  )

  return (
    <div className="px-3.5 py-2 border-t border-border relative">
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground mb-1">Cliente (opcional)</div>
      <div className="flex gap-1.5">
        <input
          value={busq}
          onChange={e => buscar(e.target.value)}
          onFocus={() => busq && setAbierto(true)}
          placeholder="Buscar por nombre o cédula/NIT..."
          className="flex-1 min-w-0 bg-muted border border-border rounded text-foreground text-[11px] px-2 py-1.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <button
          type="button"
          onClick={() => setModalNuevo(true)}
          title="Registrar cliente nuevo"
          className="shrink-0 bg-primary-soft border border-primary/40 text-primary rounded px-2 py-1 hover:bg-primary-soft/80"
        >
          <Plus className="size-3.5" />
        </button>
      </div>

      {/* Dropdown resultados */}
      {abierto && (resultados.length > 0 || buscando) && (
        <div className="absolute left-3.5 right-3.5 top-full z-50 bg-card border border-border rounded-md shadow-md overflow-hidden mt-1">
          {buscando && (
            <div className="flex items-center gap-2 px-3 py-2.5 text-[11px] text-muted-foreground">
              <Loader2 className="size-3 animate-spin" /> Buscando…
            </div>
          )}
          {!buscando && resultados.length === 0 && (
            <div className="px-3 py-2.5 text-[11px] text-muted-foreground">
              Sin resultados —{' '}
              <button
                type="button"
                onClick={() => { setModalNuevo(true); setAbierto(false) }}
                className="text-primary hover:underline"
              >
                registrar cliente nuevo
              </button>
            </div>
          )}
          {resultados.map((c, i) => (
            <button
              key={i}
              type="button"
              onClick={() => seleccionar(c)}
              className="w-full text-left px-3 py-2 border-b border-border last:border-0 hover:bg-muted transition-colors"
            >
              <div className="text-xs font-medium text-foreground">{c['Nombre tercero']}</div>
              <div className="text-[10px] text-muted-foreground">
                {c['Tipo de identificacion']} {c['Identificacion']}
                {c['Telefono'] && c['Telefono'] !== '000-0000000-' ? ` · ${c['Telefono']}` : ''}
              </div>
            </button>
          ))}
          <button
            type="button"
            onClick={() => { setModalNuevo(true); setAbierto(false) }}
            className="w-full px-3 py-2 text-[11px] text-primary bg-primary-soft text-center font-medium hover:bg-primary-soft/80"
          >
            + Registrar cliente nuevo
          </button>
        </div>
      )}

      {/* Modal nuevo cliente — reusa ModalCliente de TabClientes */}
      {modalNuevo && (
        <ModalCliente
          cliente={null}
          nombreInicial={busq}
          onClose={() => setModalNuevo(false)}
          onGuardado={(c) => seleccionar(c)}
          authFetch={authFetch}
        />
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// PANEL CARRITO (compartido desktop + drawer móvil)
// ══════════════════════════════════════════════════════════════════════════════
function PanelCarrito({ carrito, totalCarrito, vendedor, setVendedor, metodo, setMetodo,
                        clienteSeleccionado, setClienteSeleccionado,
                        removeItem, qtyChange, qtySet, onCheckout, calcCambio, setCalcCambio,
                        enviando, sticky, mobile }) {
  const totalQty = carrito.reduce((s, c) => s + (c.qty || 1), 0)

  const METODOS = [
    { key: 'efectivo',      label: 'Efectivo',  icon: '💵' },
    { key: 'transferencia', label: 'Transfer.', icon: '📲' },
    { key: 'datafono',      label: 'Datáfono',  icon: '💳' },
  ]

  return (
    <div
      className={cn(
        'bg-card overflow-hidden',
        mobile ? '' : 'border border-border rounded-xl',
        sticky && 'sticky top-[70px]',
      )}
    >
      {/* Header (solo desktop) */}
      {!mobile && (
        <div className="px-3.5 py-3 border-b border-border flex items-center justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Carrito</span>
          <div
            className={cn(
              'w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9px] font-bold text-primary-foreground transition-colors',
              carrito.length ? 'bg-primary' : 'bg-border',
            )}
          >
            {totalQty}
          </div>
        </div>
      )}

      {/* Items */}
      <div className={cn(mobile ? '' : 'max-h-[280px] overflow-y-auto')}>
        {carrito.length === 0 ? (
          <div className="px-3.5 py-7 text-center text-muted-foreground text-xs leading-relaxed">
            <ShoppingCart className="size-7 mx-auto mb-1.5 opacity-25" />
            Toca un producto para agregarlo
          </div>
        ) : (
          carrito.map((item, idx) => (
            <CartItem key={item.id} item={item} idx={idx} onRemove={removeItem} onQtyChange={qtyChange} onQtySet={qtySet} />
          ))
        )}
      </div>

      {/* Total */}
      {carrito.length > 0 && (
        <div className="px-3.5 py-2.5 border-t border-border">
          <div className="flex justify-between items-baseline">
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Total</span>
            <span className={cn('font-mono font-bold text-foreground tabular', mobile ? 'text-2xl' : 'text-xl')}>
              {cop(totalCarrito)}
            </span>
          </div>
        </div>
      )}

      {/* Cliente */}
      <SelectorCliente
        clienteSeleccionado={clienteSeleccionado}
        onSeleccionar={setClienteSeleccionado}
      />

      {/* Vendedor */}
      <div className="px-3.5 py-2 border-t border-border flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground min-w-[54px]">Vendedor</span>
        <select
          value={vendedor}
          onChange={e => { setVendedor(e.target.value); localStorage.setItem('vr_vendedor', e.target.value) }}
          className={cn(
            'flex-1 bg-muted border border-border rounded text-foreground outline-none cursor-pointer focus-visible:ring-2 focus-visible:ring-ring',
            mobile ? 'text-sm px-2.5 py-1.5' : 'text-[11px] px-2 py-1',
          )}
        >
          {['Andres', 'Farid M', 'Farid D', 'Karolay'].map(v => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>

      {/* Método de pago */}
      <div className="grid grid-cols-3 gap-1.5 px-3.5 pt-2 pb-3">
        {METODOS.map(m => {
          const active = metodo === m.key
          return (
            <button
              key={m.key}
              type="button"
              onClick={() => setMetodo(m.key)}
              className={cn(
                'flex flex-col items-center gap-0.5 rounded-md border transition-colors',
                mobile ? 'py-2.5 px-1 text-xs' : 'py-1.5 px-1 text-[10px]',
                active
                  ? 'bg-primary-soft border-primary text-primary'
                  : 'bg-muted border-border text-muted-foreground hover:border-primary/40',
              )}
            >
              <span className={mobile ? 'text-lg' : 'text-sm'}>{m.icon}</span>{m.label}
            </button>
          )
        })}
      </div>

      {/* Toggle calcular cambio */}
      {metodo === 'efectivo' && (
        <button
          type="button"
          onClick={() => setCalcCambio(v => !v)}
          className={cn(
            'mx-3.5 mb-2 px-2.5 py-1.5 flex items-center gap-2 rounded-md border transition-colors w-[calc(100%-28px)]',
            calcCambio
              ? 'bg-primary-soft border-primary/40'
              : 'bg-transparent border-border hover:border-primary/40',
          )}
        >
          <div
            className={cn(
              'w-7 h-4 rounded-full relative shrink-0 transition-colors',
              calcCambio ? 'bg-primary' : 'bg-border',
            )}
          >
            <div
              className={cn(
                'absolute top-0.5 w-3 h-3 rounded-full bg-white transition-[left]',
                calcCambio ? 'left-3.5' : 'left-0.5',
              )}
            />
          </div>
          <span className={cn('text-[11px] font-semibold', calcCambio ? 'text-primary' : 'text-muted-foreground')}>
            Calcular cambio
          </span>
        </button>
      )}

      {/* Botón registrar */}
      <button
        type="button"
        onClick={() => carrito.length && onCheckout()}
        disabled={!carrito.length || enviando}
        className={cn(
          'mx-3.5 mb-3.5 w-[calc(100%-28px)] rounded-md font-semibold tracking-wide transition-colors',
          mobile ? 'py-4 text-[15px]' : 'py-3 text-xs',
          carrito.length
            ? 'bg-primary text-primary-foreground hover:bg-primary-hover'
            : 'bg-border text-muted-foreground cursor-not-allowed',
        )}
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
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()

  const { data: dataProd, loading, error } = useFetch('/productos',        [refreshKey])
  const topUrl  = `/ventas/top?periodo=mes${selectedVendor ? `&vendor_id=${selectedVendor}` : ''}`
  const frecUrl = `/productos/frecuentes?limit=12${selectedVendor ? `&vendor_id=${selectedVendor}` : ''}`
  const { data: dataTop }  = useFetch(topUrl,  [refreshKey, selectedVendor])
  const { data: dataFrec } = useFetch(frecUrl, [refreshKey, selectedVendor])

  const [favKeys,   setFavKeys]   = useState(loadFavs)
  const [busq,      setBusq]      = useState('')
  const [filtro,    setFiltro]    = useState('todos')
  const [columnas,  setColumnas]  = useState(() => window.innerWidth < 768 ? 2 : 6)
  const [carrito,   setCarrito]   = useState(loadCart)
  const [metodo,    setMetodo]    = useState('efectivo')
  const [vendedor,  setVendedor]  = useState(() => localStorage.getItem('vr_vendedor') || 'Andres')
  const [clienteSeleccionado, setClienteSeleccionado] = useState(null) // {nombre, id} | null
  const [modalFrac, setModalFrac] = useState(null)
  const [modalCm,   setModalCm]   = useState(null)
  const [modalQty,  setModalQty]  = useState(null)
  const [modalMlt,  setModalMlt]  = useState(null)
  const [modalGrm,  setModalGrm]  = useState(null)
  const [modalKg,   setModalKg]   = useState(null)
  const [toast,           setToast]           = useState(null)
  const [carritoToast,    setCarritoToast]    = useState(null)
  const [pulseCarrito,    setPulseCarrito]    = useState(false)
  const [enviando,        setEnviando]        = useState(false)
  const [subcatFiltro,    setSubcatFiltro]    = useState(null)
  const [modalColorPrep,  setModalColorPrep]  = useState(false)
  const [precioBaseColor, setPrecioBaseColor] = useState(0)
  const [carritoAbierto,  setCarritoAbierto]  = useState(false)
  const [modalCheckout,   setModalCheckout]   = useState(false)
  const [calcCambio,      setCalcCambio]      = useState(false)
  const [modalMisc,       setModalMisc]       = useState(false)
  const [highlightedIdx,  setHighlightedIdx]  = useState(-1)
  const searchRef = useRef(null)
  const isMobile = useIsMobile()

  // Sincronizar carrito con sessionStorage
  useEffect(() => { saveCart(carrito) }, [carrito])

  // Autofocus buscador al montar
  useEffect(() => { searchRef.current?.focus() }, [])

  const mostrarCarritoToast = (nombre) => {
    setCarritoToast(`✓ ${nombre} agregado`)
    setTimeout(() => setCarritoToast(null), 1500)
    setPulseCarrito(true)
    setTimeout(() => setPulseCarrito(false), 600)
  }

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

  // Frecuentes — match exacto por clave (key)
  const frecKeys = (dataFrec?.frecuentes || []).map(x => x.key)
  const frecuentes = frecKeys.map(k => productos.find(p => p.key === k)).filter(Boolean).slice(0, 12)

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
    if (prod.tipo === 'grm')      { setModalGrm(prod);  return }
    if (prod.tipo === 'kg')       { setModalKg(prod);   return }
    // Simple: primer click = directo, segundo click = editar qty
    const ya = carrito.find(c => c.key === prod.key && c.tipo === 'simple')
    if (ya) { setModalQty(prod) }
    else {
      setCarrito(prev => [...prev, {
        id: Date.now(), key: prod.key, nombre: prod.nombre,
        precio: prod.precio, qty: 1, total: prod.precio,
        desc: '1 unidad', tipo: 'simple',
        unidad: prod.unidad_medida || 'Unidad',
        mayorista: prod.mayorista || null,
      }])
      if (isMobile) mostrarCarritoToast(prod.nombre)
    }
  }, [carrito, isMobile])

  // ── Confirmaciones ─────────────────────────────────────────────────────────
  const confirmarMlt = ({ ml, total, desc }) => {
    const nombre = modalMlt.nombre
    setCarrito(p => [...p, {
      id: Date.now(), key: modalMlt.key, nombre: modalMlt.nombre,
      precio: total, qty: ml, total, desc, tipo: 'mlt',
      unidad: modalMlt.unidad_medida || 'MLT',
    }])
    setModalMlt(null)
    if (isMobile) mostrarCarritoToast(nombre)
  }
  const confirmarGrm = ({ gramos, total, desc }) => {
    const nombre = modalGrm.nombre
    setCarrito(p => [...p, {
      id: Date.now(), key: modalGrm.key, nombre: modalGrm.nombre,
      precio: total, qty: gramos, total, desc, tipo: 'grm',
      unidad: modalGrm.unidad_medida || 'Gramos',
    }])
    setModalGrm(null)
    if (isMobile) mostrarCarritoToast(nombre)
  }
  const confirmarKg = ({ kg, total, desc }) => {
    const nombre = modalKg.nombre
    setCarrito(p => [...p, {
      id: Date.now(), key: modalKg.key, nombre: modalKg.nombre,
      precio: total, qty: kg, total, desc, tipo: 'kg',
      unidad: modalKg.unidad_medida || 'Kg',
    }])
    setModalKg(null)
    if (isMobile) mostrarCarritoToast(nombre)
  }
  const confirmarFrac = ({ unidades, fracKey, total, desc }) => {
    const nombre = modalFrac.nombre
    // Calcular cantidad real: unidades enteras + fracción decimal
    const FRAC_DEC = { '3/4': 0.75, '1/2': 0.5, '1/4': 0.25, '1/3': 0.333, '1/8': 0.125, '1/10': 0.1, '1/16': 0.0625, '2/3': 0.667, '3/8': 0.375 }
    const fracDec = fracKey ? (FRAC_DEC[fracKey] || 0) : 0
    const cantReal = (unidades || 0) + fracDec
    setCarrito(p => [...p, { id: Date.now(), key: modalFrac.key, nombre: modalFrac.nombre, precio: total, qty: cantReal || 1, total, desc, tipo: 'fraccion', unidad: modalFrac.unidad_medida || 'Galón' }])
    setModalFrac(null)
    if (isMobile) mostrarCarritoToast(nombre)
  }
  const confirmarCm = ({ cm, total, desc }) => {
    const nombre = modalCm.nombre
    setCarrito(p => [...p, { id: Date.now(), key: modalCm.key, nombre: modalCm.nombre, precio: total, qty: cm || 1, total, desc, tipo: 'cm', unidad: modalCm.unidad_medida || 'Cms' }])
    setModalCm(null)
    if (isMobile) mostrarCarritoToast(nombre)
  }
  const confirmarQty = ({ qty, total, desc }) => {
    const nombre = modalQty.nombre
    setCarrito(prev => {
      const idx = prev.findIndex(c => c.key === modalQty.key && c.tipo === 'simple')
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], qty, total, desc }
        return next
      }
      return [...prev, { id: Date.now(), key: modalQty.key, nombre: modalQty.nombre, precio: modalQty.precio, qty, total, desc, tipo: 'simple', unidad: modalQty.unidad_medida || 'Unidad', mayorista: modalQty.mayorista || null }]
    })
    setModalQty(null)
    if (isMobile) mostrarCarritoToast(nombre)
  }

  // ── Color preparado ───────────────────────────────────────────────────────
  const [nombreProductoColor, setNombreProductoColor] = useState('')
  const abrirColorPrep = useCallback((precioBase, nombreProducto) => {
    setPrecioBaseColor(precioBase)
    setNombreProductoColor(nombreProducto || '')
    setModalColorPrep(true)
  }, [])
  const confirmarColorPrep = useCallback(({ desc, descCompleta, precio }) => {
    setCarrito(prev => [...prev, {
      id: Date.now(), key: `color_prep_${Date.now()}`,
      nombre: nombreProductoColor ? `🎨 ${nombreProductoColor} — ${desc}` : `🎨 Color Preparado: ${desc}`,
      precio, qty: 1, total: precio,
      desc: descCompleta || '1 galón', tipo: 'simple',
      unidad: 'Galón',
    }])
    setModalColorPrep(false)
  }, [])

  // ── Carrito ops ────────────────────────────────────────────────────────────
  const qtyChange = (idx, d) => setCarrito(prev => {
    const next = [...prev], it = { ...next[idx] }
    it.qty = Math.max(1, it.qty + d)
    const may = it.mayorista
    const pUnit = (may && it.qty >= may.umbral) ? may.precio : it.precio
    it.total = pUnit * it.qty
    it.desc  = `${it.qty} ${it.qty === 1 ? 'unidad' : 'unidades'}${may && it.qty >= may.umbral ? ' (mayorista)' : ''}`
    next[idx] = it; return next
  })
  const qtySet = (idx, qty) => setCarrito(prev => {
    const next = [...prev], it = { ...next[idx] }
    it.qty = Math.max(1, qty)
    const may = it.mayorista
    const pUnit = (may && it.qty >= may.umbral) ? may.precio : it.precio
    it.total = pUnit * it.qty
    it.desc  = `${it.qty} ${it.qty === 1 ? 'unidad' : 'unidades'}${may && it.qty >= may.umbral ? ' (mayorista)' : ''}`
    next[idx] = it; return next
  })
  const removeItem   = idx => setCarrito(p => p.filter((_, i) => i !== idx))
  const totalCarrito = carrito.reduce((s, c) => s + c.total, 0)

  // ── Miscelánea ─────────────────────────────────────────────────────────────
  const confirmarMisc = ({ monto, desc }) => {
    const nombre = desc || 'Miscelánea'
    setCarrito(prev => [...prev, {
      id: Date.now(), key: `misc_${Date.now()}`,
      nombre, precio: monto, qty: 1, total: monto,
      desc: 'Miscelánea (monto libre)', tipo: 'misc',
      unidad: 'Unidad',
    }])
    setModalMisc(false)
    if (isMobile) mostrarCarritoToast(nombre)
  }

  // ── Registrar ──────────────────────────────────────────────────────────────
  const registrar = async () => {
    if (!carrito.length || enviando) return
    setEnviando(true)
    const totalSnapshot = totalCarrito
    try {
      const res = await authFetch(`${API_BASE}/venta-rapida`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          productos: carrito.map(c => ({ nombre: c.nombre, cantidad: c.qty, total: c.total, unidad_medida: c.unidad || '' })),
          metodo, vendedor,
          cliente_nombre: clienteSeleccionado?.nombre || '',
          cliente_id:     clienteSeleccionado?.id     || null,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setCarrito([])
      setClienteSeleccionado(null)
      setModalCheckout(false)
      setToast(`✅ Venta #${data.consecutivo} · ${cop(totalSnapshot)}`)
    } catch (e) {
      setToast(`⚠️ Error: ${e.message}`)
    } finally {
      setEnviando(false)
      setTimeout(() => setToast(null), 4000)
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
  const highlightedKey = prodsFiltrados[highlightedIdx]?.key || null
  const seccionProps = { carrito, favKeys, onClickProd: clickProd, onFav: toggleFav, columnas }

  // Qué mostrar según filtro activo
  const mostrarSeccion = (key) => !busq.trim() && (filtro === 'todos' || filtro === key)

  const totalItems = carrito.reduce((s, c) => s + (c.qty || 1), 0)

  return (
    <div style={{ position: 'relative', overflow: 'hidden', maxWidth: '100vw' }}>
      <style>{`
        .vr-filtros::-webkit-scrollbar { display: none }
        .vr-filtros { -ms-overflow-style: none; scrollbar-width: none }
        @keyframes cartPulse{0%{transform:scale(1)}50%{transform:scale(1.05)}100%{transform:scale(1)}}
      `}</style>

      {/* ══ LAYOUT DESKTOP: grid | MÓVIL: columna ══ */}
      <div style={{
        display: isMobile ? 'block' : 'grid',
        gridTemplateColumns: '1fr 310px',
        gap: 16, alignItems: 'start',
        width: '100%', minWidth: 0, overflow: 'hidden',
      }}>

      {/* ══ PANEL IZQUIERDO ══ */}
      <div>

        {/* ── Botones de filtro + selector columnas ── */}
        <div style={{ marginBottom: 12 }}>
        <div className="vr-filtros" style={{
          display: 'flex', alignItems: 'center', gap: 6,
          overflowX: 'auto', paddingBottom: 4,
          flexWrap: isMobile ? 'nowrap' : 'wrap',
          WebkitOverflowScrolling: 'touch',
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

          {/* Selector de columnas — 2/3 en móvil, 4/5/6 en desktop */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ fontSize: 10, color: t.textMuted, marginRight: 2 }}>Col:</span>
            {(isMobile ? [2, 3] : [4, 5, 6]).map(n => (
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

        {/* ── Frecuentes ── */}
        {frecuentes.length > 0 && !busq.trim() && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 7 }}>
              🔥 Más vendidos
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {frecuentes.map(prod => (
                <button
                  key={prod.key}
                  onClick={() => clickProd(prod)}
                  style={{
                    padding: '4px 11px', borderRadius: 99, fontSize: 11,
                    background: carrito.some(c => c.key === prod.key) ? t.accentSub : (t.id === 'caramelo' ? '#f1f5f9' : '#1a1a1a'),
                    border: `1px solid ${carrito.some(c => c.key === prod.key) ? t.accent : t.border}`,
                    color: carrito.some(c => c.key === prod.key) ? t.accent : t.text,
                    cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap', transition: 'all .15s',
                  }}
                >
                  {iconCat(prod.categoria)} {prod.nombre}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Búsqueda ── */}
        <div style={{ position: 'relative', marginBottom: 10 }}>
          <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: t.textMuted, pointerEvents: 'none' }}>🔍</span>
          <input
            ref={searchRef}
            value={busq}
            onChange={e => { setBusq(e.target.value); if (e.target.value) setFiltro('todos'); setHighlightedIdx(-1) }}
            onKeyDown={e => {
              if (!busq.trim() || !prodsFiltrados.length) return
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setHighlightedIdx(i => Math.min(i + 1, prodsFiltrados.length - 1))
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                setHighlightedIdx(i => Math.max(i - 1, 0))
              } else if (e.key === 'Enter') {
                e.preventDefault()
                const prod = highlightedIdx >= 0 ? prodsFiltrados[highlightedIdx] : prodsFiltrados[0]
                if (prod) clickProd(prod)
              }
            }}
            placeholder="Buscar producto... (Enter agrega el primero)"
            style={{
              width: '100%', background: t.card, border: `1px solid ${t.border}`,
              borderRadius: 8, padding: '8px 10px 8px 30px',
              color: t.text, fontFamily: 'inherit', fontSize: 12, outline: 'none',
            }}
            onFocus={e => e.currentTarget.style.borderColor = t.accent + '88'}
            onBlur={e  => e.currentTarget.style.borderColor = t.border}
          />
        </div>

        {/* ── Venta miscelánea ── */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
          <button
            onClick={() => setModalMisc(true)}
            style={{
              padding: '4px 12px', borderRadius: 99, fontSize: 11,
              background: 'transparent', border: `1px solid ${t.border}`,
              color: t.textMuted, cursor: 'pointer', fontFamily: 'inherit',
              display: 'flex', alignItems: 'center', gap: 5, transition: 'all .15s',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = t.accent + '66'; e.currentTarget.style.color = t.text }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.textMuted }}
          >
            💸 Venta miscelánea
          </button>
        </div>

        {/* ── Subcategorías ── */}
        {subcatsDisp.length > 0 && !busq.trim() && (
          <div style={{
            display: 'flex', gap: 6, overflowX: 'auto', paddingBottom: 4, marginBottom: 12,
            scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch',
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
          <Seccion icono="🔍" titulo={`"${busq}"`} cantidad={prodsFiltrados.length} productos={prodsFiltrados} highlightedKey={highlightedKey} {...seccionProps} />
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
          carrito={carrito} totalCarrito={totalCarrito}
          vendedor={vendedor} setVendedor={setVendedor}
          metodo={metodo} setMetodo={setMetodo}
          clienteSeleccionado={clienteSeleccionado}
          setClienteSeleccionado={setClienteSeleccionado}
          removeItem={removeItem} qtyChange={qtyChange} qtySet={qtySet}
          onCheckout={() => calcCambio ? setModalCheckout(true) : registrar()}
          calcCambio={calcCambio} setCalcCambio={setCalcCambio}
          enviando={enviando}
          sticky
        />
      )}

      </div>{/* fin grid */}

      {/* ══ MÓVIL: barra inferior fija del carrito — solo cuando hay ítems ══ */}
      {isMobile && totalItems > 0 && createPortal(
        <div style={{
          position: 'fixed', bottom: 'calc(64px + env(safe-area-inset-bottom, 0px))', left: 0, right: 0,
          zIndex: 200, padding: '8px 12px',
          background: t.header,
          borderTop: `1px solid ${t.border}`,
          boxShadow: '0 -4px 20px rgba(0,0,0,.15)',
          display: 'flex', gap: 8, boxSizing: 'border-box',
        }}>
          {/* Botón izquierdo: ver carrito */}
          <button
            onClick={() => setCarritoAbierto(true)}
            style={{
              flex: 1, padding: '14px 12px',
              background: totalItems > 0 ? t.accent : t.card,
              border: `1px solid ${totalItems > 0 ? t.accent : t.border}`,
              borderRadius: 11, color: totalItems > 0 ? '#fff' : t.textMuted,
              fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
              cursor: 'pointer', display: 'flex',
              alignItems: 'center', justifyContent: 'center', gap: 8,
              transition: 'all .2s',
            }}
          >
            <span style={{ fontSize: 17 }}>🛒</span>
            {totalItems > 0
              ? <span>{totalItems} {totalItems === 1 ? 'ítem' : 'ítems'} · {cop(totalCarrito)}</span>
              : <span>Carrito vacío</span>
            }
          </button>
          {/* Toggle cambio sutil — solo efectivo */}
          {totalItems > 0 && metodo === 'efectivo' && (
            <button
              onClick={() => setCalcCambio(v => !v)}
              title={calcCambio ? 'Desactivar cambio' : 'Calcular cambio'}
              style={{
                flexShrink: 0,
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
                background: calcCambio ? `${t.accent}20` : 'transparent',
                border: `1px solid ${calcCambio ? t.accent + '55' : t.border}`,
                borderRadius: 10, padding: '6px 8px',
                cursor: 'pointer', transition: 'all .18s',
              }}
            >
              <div style={{
                width: 24, height: 14, borderRadius: 7,
                background: calcCambio ? t.accent : t.border,
                position: 'relative', transition: 'background .15s',
              }}>
                <div style={{
                  position: 'absolute', top: 2, left: calcCambio ? 12 : 2,
                  width: 10, height: 10, borderRadius: '50%', background: '#fff',
                  transition: 'left .15s',
                }} />
              </div>
              <span style={{ fontSize: 8, color: calcCambio ? t.accent : t.textMuted, fontWeight: 700, letterSpacing: '.02em' }}>
                💱
              </span>
            </button>
          )}
          {/* Botón derecho: checkout — solo cuando hay ítems */}
          {totalItems > 0 && (
            <button
              onClick={enviando ? undefined : () => {
                if (calcCambio) setModalCheckout(true)
                else registrar()
              }}
              disabled={enviando}
              style={{
                padding: '12px 18px',
                background: t.accent, border: 'none',
                borderRadius: 11, color: '#fff',
                fontSize: 13, fontWeight: 700, fontFamily: 'inherit',
                cursor: enviando ? 'not-allowed' : 'pointer',
                whiteSpace: 'nowrap', flexShrink: 0,
                opacity: enviando ? 0.7 : 1,
                transition: 'all .2s',
              }}
            >
              {enviando ? '⏳' : '✓ Registrar'}
            </button>
          )}
        </div>
      , document.body)}

      {/* ══ MÓVIL: drawer del carrito ══ */}
      {isMobile && carritoAbierto && createPortal(
        <div
          onClick={e => e.target === e.currentTarget && setCarritoAbierto(false)}
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: '#00000077', zIndex: 300,
            display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
          }}
        >
          <div
            onPointerDown={e => e.stopPropagation()}
            style={{
              background: t.card, borderRadius: '18px 18px 0 0',
              maxHeight: 'calc(100dvh - 130px - env(safe-area-inset-bottom, 0px))',
              overflow: 'hidden', display: 'flex', flexDirection: 'column',
              animation: 'drawerUp .25s cubic-bezier(.34,1.2,.64,1)',
            }}
          >
            <style>{`@keyframes drawerUp{from{transform:translateY(100%)}to{transform:translateY(0)}}`}</style>
            {/* Handle */}
            <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 4px' }}>
              <div style={{ width: 36, height: 4, borderRadius: 99, background: t.border }} />
            </div>
            {/* Header */}
            <div style={{ padding: '8px 18px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: `1px solid ${t.border}` }}>
              <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>🛒 Carrito</span>
              <button onClick={() => setCarritoAbierto(false)} style={{ background: 'none', border: 'none', color: t.textMuted, fontSize: 20, cursor: 'pointer', padding: '4px 8px' }}>✕</button>
            </div>
            {/* Content */}
            <div style={{ overflowY: 'auto', flex: 1, paddingBottom: 16, WebkitOverflowScrolling: 'touch' }}>
              <PanelCarrito
                carrito={carrito} totalCarrito={totalCarrito}
                vendedor={vendedor} setVendedor={setVendedor}
                metodo={metodo} setMetodo={setMetodo}
                clienteSeleccionado={clienteSeleccionado}
                setClienteSeleccionado={setClienteSeleccionado}
                removeItem={removeItem} qtyChange={qtyChange} qtySet={qtySet}
                onCheckout={() => {
                  if (calcCambio) { setModalCheckout(true); setCarritoAbierto(false) }
                  else { setCarritoAbierto(false); registrar() }
                }}
                calcCambio={calcCambio} setCalcCambio={setCalcCambio}
                enviando={enviando}
                mobile
              />
            </div>
          </div>
        </div>
      , document.body)}

      {/* Modal checkout */}
      <ModalCheckout
        show={modalCheckout}
        total={totalCarrito}
        metodo={metodo}
        setMetodo={setMetodo}
        onClose={() => setModalCheckout(false)}
        onConfirm={registrar}
        enviando={enviando}
      />

      {/* Modal miscelánea */}
      <ModalMiscelanea
        show={modalMisc}
        onClose={() => setModalMisc(false)}
        onConfirm={confirmarMisc}
      />

      {/* Modal color preparado */}
      <ModalColorPreparado
        show={modalColorPrep}
        nombreProducto={nombreProductoColor}
        precioBase={precioBaseColor}
        onClose={() => setModalColorPrep(false)}
        onConfirm={confirmarColorPrep}
      />

      {/* Modales */}
      {modalFrac && <ModalFraccion key={modalFrac.key} prod={modalFrac} onClose={() => setModalFrac(null)} onConfirm={confirmarFrac} />}
      {modalCm   && <ModalCm       key={modalCm.key}   prod={modalCm}   onClose={() => setModalCm(null)}   onConfirm={confirmarCm}  />}
      {modalQty  && <ModalQty      key={modalQty.key}   prod={modalQty}  onClose={() => setModalQty(null)}  onConfirm={confirmarQty} />}
      {modalMlt  && <ModalMlt      key={modalMlt.key}   prod={modalMlt}  onClose={() => setModalMlt(null)}  onConfirm={confirmarMlt} />}
      {modalGrm  && <ModalGrm      key={modalGrm.key}   prod={modalGrm}  onClose={() => setModalGrm(null)}  onConfirm={confirmarGrm} />}
      {modalKg   && <ModalKg       key={modalKg.key}    prod={modalKg}   onClose={() => setModalKg(null)}   onConfirm={confirmarKg}  />}

      {/* Toast carrito móvil — confirmación al agregar producto */}
      {isMobile && carritoToast && (
        <div style={{
          position: 'fixed', bottom: 140, left: 16, right: 16,
          background: t.green, color: '#fff',
          borderRadius: 12, padding: '12px 16px',
          fontSize: 13, fontWeight: 600,
          zIndex: 9999, textAlign: 'center',
          animation: 'carritoToastAnim 1.5s ease forwards',
        }}>
          <style>{`@keyframes carritoToastAnim{0%{opacity:0;transform:translateY(8px)}13%{opacity:1;transform:translateY(0)}80%{opacity:1}100%{opacity:0}}`}</style>
          {carritoToast}
        </div>
      )}

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
