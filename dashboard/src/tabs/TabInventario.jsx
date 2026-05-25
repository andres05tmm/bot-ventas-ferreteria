/*
 * TabInventario — catálogo navegable con edición inline de precio, stock,
 * fracciones y mayorista; modales crear/editar/eliminar.
 * Wave 2.b: migrado a primitives shadcn + tokens semantic.
 */
import { useState, useRef, useCallback, useMemo } from 'react'
import { useFetch, API_BASE } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useIsMobile } from '../components/shared.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog.jsx'
import {
  Search, Plus, Pencil, Trash2, ChevronDown, ChevronUp, Check, X,
  AlertCircle, Package, Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ─── helpers ──────────────────────────────────────────────────────────────────
const nl = s => (s || '').toLowerCase()
const cop = v => v == null || isNaN(v) ? '$0' : '$' + Math.round(v).toLocaleString('es-CO')

function catIcon(cat) {
  const c = nl(cat)
  if (c.includes('pint') || c.includes('disol'))                              return '🎨'
  if (c.includes('thinner') || c.includes('varsol'))                          return '🧪'
  if (c.includes('lija') || c.includes('esmeril'))                            return '🪚'
  if (c.includes('tornill') || c.includes('clav') || c.includes('puntilla'))  return '🔩'
  if (c.includes('adhesiv') || c.includes('pega') || c.includes('silicon'))   return '🧲'
  if (c.includes('ferret') || c.includes('herram') || c.includes('artículo')) return '🔧'
  if (c.includes('construc') || c.includes('imperme'))                        return '🏗️'
  if (c.includes('electric'))                                                  return '⚡'
  return '📦'
}

// Clases tokenizadas por unidad de medida — solo si no es "Unidad" genérica
const UNIDAD_CLASS = {
  'galón':  'bg-warning/10 text-warning border-warning/30',
  'galon':  'bg-warning/10 text-warning border-warning/30',
  'kg':     'bg-success/10 text-success border-success/30',
  'gramos': 'bg-success/10 text-success border-success/30',
  'grm':    'bg-success/10 text-success border-success/30',
  'mts':    'bg-primary/10 text-primary border-primary/30',
  'cms':    'bg-primary/10 text-primary border-primary/30',
  'lts':    'bg-primary/10 text-primary border-primary/30',
  'lt':     'bg-primary/10 text-primary border-primary/30',
  'mlt':    'bg-primary/10 text-primary border-primary/30',
}
const unidadClass = u => UNIDAD_CLASS[nl(u).replace('ó', 'o')] || 'bg-muted text-muted-foreground border-border'

// ─── subcategorías ────────────────────────────────────────────────────────────
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
const getSubcats = k => SUBCATS[k.toLowerCase()] || []

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

// ─── fracciones ───────────────────────────────────────────────────────────────
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
const FRACS_ORDEN = ['3/4','1/2','1/4','1/8','1/10','1/16']

// ─── editor precio inline ─────────────────────────────────────────────────────
function PrecioInline({ value, prodKey, onSaved, authFetch }) {
  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState(value || 0)
  const [estado,   setEstado]   = useState('idle')
  const ref = useRef()

  const abrir  = (e) => { e.stopPropagation(); setVal(value || 0); setEstado('idle'); setEditando(true); setTimeout(() => ref.current?.select(), 20) }
  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = async () => {
    if (Number(val) === Number(value)) { cerrar(); return }
    setEstado('saving')
    try {
      const r = await authFetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/precio`, {
        method:'PATCH', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ precio: Number(val) }),
      })
      if (!r.ok) throw new Error()
      setEstado('ok'); onSaved(Number(val))
      setTimeout(cerrar, 1000)
    } catch { setEstado('err'); setTimeout(cerrar, 1200) }
  }

  if (editando) return (
    <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
      <span className="text-[10px] text-muted-foreground">$</span>
      <input
        ref={ref} type="number" min="0" value={val}
        onChange={e => setVal(parseInt(e.target.value) || 0)}
        onKeyDown={e => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape') cerrar() }}
        className="w-24 h-7 px-2 text-xs font-mono font-bold text-primary bg-surface border border-primary/50 rounded outline-none focus:border-primary"
      />
      <Button size="icon" className="size-7" onClick={guardar} aria-label="Guardar precio">
        {estado === 'saving' ? <Loader2 className="size-3 animate-spin" aria-hidden="true" /> : <Check className="size-3.5" aria-hidden="true" />}
      </Button>
      <Button size="icon" variant="outline" className="size-7" onClick={cerrar} aria-label="Cancelar edición">
        <X className="size-3.5" aria-hidden="true" />
      </Button>
    </div>
  )

  return (
    <button onClick={abrir} className="group flex items-center gap-1.5 cursor-pointer" title="Clic para editar precio">
      {value ? (
        <span className={cn(
          'font-semibold tabular transition-colors',
          estado === 'err' ? 'text-destructive' : 'text-success',
        )}>
          {cop(value)}
          {estado === 'ok' && <Check className="inline size-3 ml-1 text-success" />}
        </span>
      ) : (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-warning/10 text-warning border border-warning/30 font-semibold">
          Sin precio
        </span>
      )}
      <Pencil className="size-2.5 text-muted-foreground opacity-30 group-hover:opacity-100 transition-opacity" />
    </button>
  )
}

// ─── editor stock inline ──────────────────────────────────────────────────────
function StockInline({ value, prodKey, fracciones, onSaved, authFetch }) {
  const esFracc = !!(fracciones && Object.keys(fracciones).filter(k => k !== 'unidad_suelta').length > 0)
  const fracBtns = useMemo(() => {
    if (!esFracc) return []
    return Object.keys(fracciones).filter(k => k !== 'unidad_suelta')
      .sort((a, b) => (parseFraccion(b) || 0) - (parseFraccion(a) || 0))
  }, [fracciones, esFracc])

  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState('')
  const [estado,   setEstado]   = useState('idle')
  const ref = useRef()

  const display = esFracc ? decimalAFrac(value) : (value !== null && value !== undefined ? String(value) : null)

  const abrir  = (e) => { e.stopPropagation(); setVal(display || ''); setEstado('idle'); setEditando(true); setTimeout(() => { ref.current?.focus(); ref.current?.select() }, 20) }
  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = useCallback(async (strVal) => {
    const src = strVal !== undefined ? strVal : val
    const num = esFracc ? parseFraccion(String(src)) : parseFloat(String(src).replace(',', '.'))
    if (num === null || isNaN(num) || num < 0) { cerrar(); return }
    setEstado('saving')
    try {
      const r = await authFetch(`${API_BASE}/inventario/${encodeURIComponent(prodKey)}/stock`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stock: num }),
      })
      if (!r.ok) throw new Error()
      setEstado('ok'); onSaved(num)
      setTimeout(cerrar, 600)
    } catch { setEstado('err'); setTimeout(cerrar, 800) }
  }, [val, prodKey, esFracc, onSaved])

  const onKey  = e => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape') cerrar() }
  const sumar  = frac => { const b = parseFraccion(val) || 0; setVal(decimalAFrac(b + (parseFraccion(frac) || 0)) || '') }
  const restar = frac => { const b = parseFraccion(val) || 0; setVal(decimalAFrac(Math.max(0, b - (parseFraccion(frac) || 0))) || '0') }

  if (editando) return (
    <div className="flex flex-col items-center gap-1.5" onClick={e => e.stopPropagation()}>
      <div className="flex items-center gap-1">
        <input
          ref={ref} value={val} onChange={e => setVal(e.target.value)} onKeyDown={onKey} onBlur={() => guardar()}
          placeholder={esFracc ? 'ej: 2 3/4' : '0'} inputMode="decimal"
          className={cn(
            'h-7 px-2 text-xs text-center font-mono bg-surface border rounded outline-none',
            esFracc ? 'w-24' : 'w-20',
            estado === 'err' ? 'border-destructive' : 'border-success',
          )}
        />
        <Button size="icon" variant="ghost" className="size-7 text-success hover:text-success" onClick={() => guardar()} aria-label="Guardar stock"><Check className="size-3.5" aria-hidden="true" /></Button>
        <Button size="icon" variant="outline" className="size-7" onClick={cerrar} aria-label="Cancelar edición"><X className="size-3.5" aria-hidden="true" /></Button>
      </div>
      {esFracc && fracBtns.length > 0 && (
        <div className="flex flex-wrap justify-center gap-1">
          {fracBtns.map(frac => (
            <div key={frac} className="flex items-stretch">
              <button onClick={() => restar(frac)} className="px-1.5 text-[10px] font-bold text-primary bg-primary-soft border border-primary/30 rounded-l">−</button>
              <span className="px-1.5 text-[10px] bg-surface border-y border-border flex items-center">{frac}</span>
              <button onClick={() => sumar(frac)} className="px-1.5 text-[10px] font-bold text-success bg-success/10 border border-success/30 rounded-r">+</button>
            </div>
          ))}
        </div>
      )}
      {estado === 'saving' && <span className="text-[10px] text-muted-foreground">Guardando…</span>}
      {estado === 'err'    && <span className="text-[10px] text-destructive">Error</span>}
    </div>
  )

  const hay     = value !== null && value !== undefined
  const esFracV = esFracc && hay && !Number.isInteger(parseFloat(value))
  return (
    <button onClick={abrir} className="group flex items-center justify-center gap-1 cursor-pointer mx-auto" title="Clic para editar stock">
      {hay ? (
        <span className={cn('font-mono text-xs tabular', esFracV ? 'font-semibold text-warning' : 'text-foreground')}>
          {display}{esFracc && <span className="text-[9px] opacity-50 ml-0.5">gal</span>}
        </span>
      ) : (
        <span className="text-[11px] text-muted-foreground opacity-60">—</span>
      )}
      <Pencil className="size-2.5 text-muted-foreground opacity-30 group-hover:opacity-100 transition-opacity" />
    </button>
  )
}

// ─── editor fracciones ────────────────────────────────────────────────────────
function FraccionesEditor({ fracciones, prodKey, onSaved, authFetch }) {
  const [editando, setEditando] = useState(false)
  const [vals,     setVals]     = useState({})
  const [estado,   setEstado]   = useState('idle')

  const abrir = (e) => {
    e?.stopPropagation()
    const init = {}
    FRACS_ORDEN.forEach(f => { const v = fracciones?.[f]; init[f] = v ? (typeof v === 'object' ? v.precio : v) : '' })
    setVals(init); setEditando(true)
  }

  const guardar = async (e) => {
    e?.stopPropagation()
    setEstado('saving')
    const fracs = {}
    FRACS_ORDEN.forEach(f => { if (vals[f] > 0) fracs[f] = parseInt(vals[f]) })
    try {
      const r = await authFetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/fracciones`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fracciones: fracs }),
      })
      if (!r.ok) throw new Error()
      setEstado('ok'); onSaved(fracs)
      setTimeout(() => { setEstado('idle'); setEditando(false) }, 800)
    } catch { setEstado('err'); setTimeout(() => setEstado('idle'), 1500) }
  }

  const hasFracs = fracciones && Object.keys(fracciones).length > 0

  if (!editando) return (
    <div>
      {hasFracs && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {FRACS_ORDEN.filter(f => fracciones[f]).map(f => {
            const precio = typeof fracciones[f] === 'object' ? fracciones[f].precio : fracciones[f]
            return (
              <div key={f} className="bg-surface border border-border rounded-md px-2 py-1">
                <div className="text-[9px] text-muted-foreground leading-none">{f}</div>
                <div className="text-xs font-semibold text-primary tabular leading-tight mt-0.5">{cop(precio)}</div>
              </div>
            )
          })}
        </div>
      )}
      <Button size="sm" variant="outline" onClick={abrir} className="h-7 text-xs border-primary/40 text-primary hover:bg-primary-soft">
        <Pencil className="size-3 mr-1" /> {hasFracs ? 'Editar fracciones' : 'Agregar fracciones'}
      </Button>
    </div>
  )

  return (
    <div onClick={e => e.stopPropagation()} className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {FRACS_ORDEN.map(f => (
          <div key={f}>
            <Label className="text-[9px] text-muted-foreground uppercase tracking-wide">{f}</Label>
            <div className="flex items-center gap-1 mt-1">
              <span className="text-[10px] text-muted-foreground">$</span>
              <input type="number" min="0" value={vals[f] || ''} placeholder="—"
                onChange={e => setVals(v => ({ ...v, [f]: parseInt(e.target.value) || 0 }))}
                className={cn(
                  'w-full h-7 px-2 text-xs font-mono tabular bg-surface border rounded outline-none',
                  vals[f] > 0 ? 'border-primary/50' : 'border-input',
                )}
              />
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={guardar} className={cn('h-8 text-xs', estado === 'ok' && 'bg-success hover:bg-success/90')}>
          {estado === 'saving' ? <><Loader2 className="size-3 mr-1 animate-spin" /> Guardando…</> :
           estado === 'ok'     ? <><Check className="size-3 mr-1" /> Guardado</> :
                                 'Guardar fracciones'}
        </Button>
        <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setEditando(false) }} className="h-8 text-xs">Cancelar</Button>
        {estado === 'err' && <span className="text-[10px] text-destructive">Error</span>}
      </div>
    </div>
  )
}

// ─── editor mayorista ─────────────────────────────────────────────────────────
function MayoristaInline({ mayorista, prodKey, onSaved, topSpacing, authFetch }) {
  const [editando, setEditando] = useState(false)
  const [precio,   setPrecio]   = useState('')
  const [umbral,   setUmbral]   = useState('')
  const [estado,   setEstado]   = useState('idle')

  const abrir  = () => { setPrecio(String(mayorista.precio)); setUmbral(String(mayorista.umbral)); setEstado('idle'); setEditando(true) }
  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = async () => {
    const p = parseInt(precio), u = parseInt(umbral)
    if (isNaN(p) || p <= 0) { cerrar(); return }
    setEstado('saving')
    try {
      const r = await authFetch(`${API_BASE}/catalogo/${encodeURIComponent(prodKey)}/mayorista`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ precio: p, umbral: isNaN(u) ? mayorista.umbral : u }),
      })
      if (!r.ok) throw new Error()
      setEstado('ok')
      onSaved({ ...mayorista, precio: p, umbral: isNaN(u) ? mayorista.umbral : u })
      setTimeout(cerrar, 700)
    } catch { setEstado('err'); setTimeout(cerrar, 1000) }
  }

  return (
    <div className={cn(topSpacing && 'mt-4')}>
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-2">Precio mayorista</div>
      {editando ? (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-muted-foreground">Desde</span>
            <input type="number" min="1" value={umbral} onChange={e => setUmbral(e.target.value)}
              className="w-14 h-7 px-2 text-xs text-center font-mono bg-surface border border-input rounded outline-none focus:border-primary" />
            <span className="text-[10px] text-muted-foreground">uds →</span>
            <span className="text-[10px] text-muted-foreground">$</span>
            <input type="number" min="0" value={precio} onChange={e => setPrecio(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape') cerrar() }}
              autoFocus
              className="w-24 h-7 px-2 text-xs font-mono bg-surface border border-input rounded outline-none focus:border-primary" />
            <span className="text-[10px] text-muted-foreground">c/u</span>
          </div>
          <Button size="sm" onClick={guardar} className={cn('h-8 text-xs', estado === 'ok' && 'bg-success hover:bg-success/90')}>
            {estado === 'saving' ? 'Guardando…' : estado === 'ok' ? <><Check className="size-3 mr-1" /> Guardado</> : 'Guardar'}
          </Button>
          <Button size="sm" variant="outline" onClick={cerrar} className="h-8 text-xs">Cancelar</Button>
          {estado === 'err' && <span className="text-[10px] text-destructive">Error</span>}
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 bg-surface border border-primary/30 rounded-md px-3 py-1.5">
            <span className="text-[10px] text-muted-foreground">Desde {mayorista.umbral} uds:</span>
            <span className="text-sm font-bold text-primary font-mono tabular">{cop(mayorista.precio)}</span>
            <span className="text-[10px] text-muted-foreground">c/u</span>
          </div>
          <Button size="sm" variant="outline" onClick={abrir} className="h-8 text-xs border-primary/40 text-primary hover:bg-primary-soft">
            <Pencil className="size-3 mr-1" /> Editar
          </Button>
        </div>
      )}
    </div>
  )
}

// ─── fila desktop ─────────────────────────────────────────────────────────────
function ProductoRow({ p: pInit, expanded, onToggle, onEdit, onDelete, authFetch }) {
  const [p, setP] = useState(pInit)
  const hasFracs   = p.fracciones && Object.keys(p.fracciones).length > 0
  const expandible = hasFracs || p.mayorista

  const unidad = p.unidad_medida || 'Unidad'
  const esUnidadEspecial = unidad && nl(unidad) !== 'unidad'

  return (
    <>
      <tr
        className={cn('border-b border-border-subtle hover:bg-surface-2/40', expandible && 'cursor-pointer')}
        onClick={() => expandible && onToggle()}
      >
        <td className="px-3 py-2 text-[10px] font-mono text-muted-foreground">{p.codigo || '—'}</td>
        <td className="px-3 py-2 text-sm">
          {p.nombre}
          <div className="flex gap-1 flex-wrap mt-1">
            {hasFracs && (
              <span className="text-[9px] px-1.5 py-px rounded-full bg-primary-soft text-primary border border-primary/30">fracciones</span>
            )}
            {p.mayorista && (
              <span className="text-[9px] px-1.5 py-px rounded-full bg-surface-2 text-secondary-foreground border border-border">mayorista ×{p.mayorista.umbral}</span>
            )}
          </div>
        </td>
        <td className="px-3 py-2" onClick={e => e.stopPropagation()}>
          <PrecioInline value={p.precio} prodKey={p.key} onSaved={v => setP(prev => ({ ...prev, precio: v }))} authFetch={authFetch} />
        </td>
        <td className="px-3 py-2 text-center" onClick={e => e.stopPropagation()}>
          <StockInline
            value={p.stock !== null && p.stock !== undefined ? p.stock : null}
            prodKey={p.key} fracciones={p.fracciones || null}
            onSaved={v => setP(prev => ({ ...prev, stock: v }))}
            authFetch={authFetch}
          />
        </td>
        <td className="px-3 py-2 text-center">
          {esUnidadEspecial ? (
            <span className={cn('text-[9px] font-semibold px-2 py-0.5 rounded-full border', unidadClass(unidad))}>{unidad}</span>
          ) : (
            <span className="text-[10px] text-muted-foreground opacity-40">und</span>
          )}
        </td>
        <td className="px-3 py-2 text-center" onClick={e => e.stopPropagation()}>
          <div className="flex gap-1 justify-center">
            <button onClick={onEdit} className="size-7 rounded-md bg-primary-soft border border-primary/30 text-primary grid place-items-center" title="Editar">
              <Pencil className="size-3.5" />
            </button>
            <button onClick={onDelete} className="size-7 rounded-md bg-destructive/10 border border-destructive/30 text-destructive grid place-items-center" title="Eliminar">
              <Trash2 className="size-3.5" />
            </button>
          </div>
        </td>
        <td className="px-3 py-2 text-center text-muted-foreground">
          {expandible && (expanded ? <ChevronUp className="size-3.5 inline" /> : <ChevronDown className="size-3.5 inline" />)}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-surface-2/40">
          <td colSpan={7} className="px-6 py-3">
            {hasFracs && (
              <FraccionesEditor fracciones={p.fracciones} prodKey={p.key}
                onSaved={v => setP(prev => ({ ...prev, fracciones: v }))} authFetch={authFetch} />
            )}
            {p.mayorista && (
              <MayoristaInline mayorista={p.mayorista} prodKey={p.key}
                onSaved={v => setP(prev => ({ ...prev, mayorista: v }))}
                topSpacing={hasFracs} authFetch={authFetch} />
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ─── card móvil ───────────────────────────────────────────────────────────────
function MobileProductCard({ p: pInit, expanded, onToggle, onEdit, onDelete, authFetch }) {
  const [p, setP] = useState(pInit)
  const hasFracs   = p.fracciones && Object.keys(p.fracciones).length > 0
  const expandible = hasFracs || p.mayorista
  const unidad = p.unidad_medida || 'Unidad'
  const esUnidadEspecial = unidad && nl(unidad) !== 'unidad'

  return (
    <Card className="overflow-hidden">
      <div className="p-3 space-y-2.5">
        <div className="flex justify-between items-start gap-2">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold leading-tight">{p.nombre}</div>
            {p.codigo && <span className="text-[10px] text-muted-foreground font-mono">{p.codigo}</span>}
            <div className="flex gap-1 flex-wrap mt-1.5">
              {esUnidadEspecial && (
                <span className={cn('text-[9px] font-semibold px-2 py-0.5 rounded-full border', unidadClass(unidad))}>{unidad}</span>
              )}
              {hasFracs   && <span className="text-[9px] px-2 py-0.5 rounded-full bg-primary-soft text-primary border border-primary/30">fracciones</span>}
              {p.mayorista && <span className="text-[9px] px-2 py-0.5 rounded-full bg-surface-2 text-secondary-foreground border border-border">mayorista</span>}
            </div>
          </div>
          <div className="flex gap-1.5 shrink-0">
            <button onClick={(e) => { e.stopPropagation(); onEdit() }} className="size-9 rounded-md bg-primary-soft border border-primary/30 text-primary grid place-items-center">
              <Pencil className="size-4" />
            </button>
            <button onClick={(e) => { e.stopPropagation(); onDelete() }} className="size-9 rounded-md bg-destructive/10 border border-destructive/30 text-destructive grid place-items-center">
              <Trash2 className="size-4" />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="bg-surface-2/60 rounded-md px-2.5 py-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-wide">Precio</div>
            <div className="mt-0.5" onClick={e => e.stopPropagation()}>
              <PrecioInline value={p.precio} prodKey={p.key} onSaved={v => setP(prev => ({ ...prev, precio: v }))} authFetch={authFetch} />
            </div>
          </div>
          <div className="bg-surface-2/60 rounded-md px-2.5 py-2">
            <div className="text-[9px] text-muted-foreground uppercase tracking-wide">Stock</div>
            <div className="mt-0.5" onClick={e => e.stopPropagation()}>
              <StockInline value={p.stock !== null && p.stock !== undefined ? p.stock : null}
                prodKey={p.key} fracciones={p.fracciones || null}
                onSaved={v => setP(prev => ({ ...prev, stock: v }))} authFetch={authFetch} />
            </div>
          </div>
        </div>

        {expandible && (
          <Button variant="outline" size="sm" onClick={onToggle} className="w-full h-8 text-xs">
            {expanded ? <><ChevronUp className="size-3 mr-1.5" /> Cerrar detalles</> :
                        <><ChevronDown className="size-3 mr-1.5" /> Ver fracciones / mayorista</>}
          </Button>
        )}
      </div>

      {expanded && (
        <div className="border-t border-border-subtle bg-surface-2/40 p-3 space-y-3">
          {hasFracs && (
            <FraccionesEditor fracciones={p.fracciones} prodKey={p.key}
              onSaved={v => setP(prev => ({ ...prev, fracciones: v }))} authFetch={authFetch} />
          )}
          {p.mayorista && (
            <MayoristaInline mayorista={p.mayorista} prodKey={p.key}
              onSaved={v => setP(prev => ({ ...prev, mayorista: v }))}
              topSpacing={hasFracs} authFetch={authFetch} />
          )}
        </div>
      )}
    </Card>
  )
}

// ─── tabla por categoría ──────────────────────────────────────────────────────
function TablaCat({ prods, onEdit, onDelete, isMobile, authFetch }) {
  const [expanded, setExpanded] = useState({})
  const toggle = useCallback(k => setExpanded(p => ({ ...p, [k]: !p[k] })), [])

  if (isMobile) return (
    <div className="border-t border-border-subtle p-2.5 flex flex-col gap-2">
      {prods.map(p => (
        <MobileProductCard key={p.key} p={p} expanded={!!expanded[p.key]} onToggle={() => toggle(p.key)}
          onEdit={() => onEdit(p)} onDelete={() => onDelete(p)} authFetch={authFetch} />
      ))}
    </div>
  )

  return (
    <div className="border-t border-border-subtle overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-surface-2/60">
            {[
              { h: 'Código',   align: 'left' },
              { h: 'Nombre',   align: 'left' },
              { h: 'Precio',   align: 'left' },
              { h: 'Stock',    align: 'center' },
              { h: 'Unidad',   align: 'center' },
              { h: 'Acciones', align: 'center' },
              { h: '',         align: 'center' },
            ].map((c, i) => (
              <th key={i} className={cn(
                'px-3 py-2 text-[9px] text-muted-foreground uppercase tracking-wide font-medium border-b border-border-subtle',
                c.align === 'center' ? 'text-center' : 'text-left',
              )}>{c.h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {prods.map(p => (
            <ProductoRow key={p.key} p={p} expanded={!!expanded[p.key]} onToggle={() => toggle(p.key)}
              onEdit={() => onEdit(p)} onDelete={() => onDelete(p)} authFetch={authFetch} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── modales ──────────────────────────────────────────────────────────────────
const CATEGORIAS = [
  '1 Artículos de Ferreteria',
  '2 Pinturas y Disolventes',
  '3 Tornilleria',
  '4 Impermeabilizantes y Materiales de Construcción',
  '5 Materiales Electricos',
]
const UNIDADES = ['Unidad', 'Galón', 'Kg', 'Gramos', 'MLT', 'Mts', 'Cms', 'Lt', 'Lts', '25 kg']

const selectClass = 'w-full h-9 px-3 rounded-md border border-input bg-transparent text-sm focus:outline-none focus:ring-2 focus:ring-ring/40'

function ModalEditarProducto({ prod, onClose, onGuardado, authFetch }) {
  const [form, setForm] = useState({
    nombre:        prod.nombre        || '',
    categoria:     prod.categoria     || CATEGORIAS[0],
    precio_unidad: prod.precio        || '',
    unidad_medida: prod.unidad_medida || 'Unidad',
    codigo:        prod.codigo        || '',
  })
  const [estado, setEstado] = useState('idle')
  const [err,    setErr]    = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const guardar = async () => {
    if (!form.nombre.trim()) { setErr('El nombre es obligatorio'); return }
    setEstado('saving'); setErr('')
    try {
      const body = {}
      if (form.nombre        !== prod.nombre)                  body.nombre        = form.nombre.trim()
      if (form.categoria     !== prod.categoria)               body.categoria     = form.categoria
      if (String(form.precio_unidad) !== String(prod.precio))  body.precio_unidad = Number(form.precio_unidad)
      if (form.unidad_medida !== prod.unidad_medida)           body.unidad_medida = form.unidad_medida
      if (form.codigo        !== prod.codigo)                  body.codigo        = form.codigo.trim()
      if (!Object.keys(body).length) { onClose(); return }
      const r = await authFetch(`${API_BASE}/catalogo/${encodeURIComponent(prod.key)}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('ok')
      setTimeout(() => { onGuardado(); onClose() }, 500)
    } catch (e) { setErr(e.message); setEstado('err') }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Editar producto</DialogTitle>
          <p className="text-xs text-muted-foreground">{prod.nombre}</p>
        </DialogHeader>
        <div className="space-y-3.5">
          <div>
            <Label>Nombre *</Label>
            <Input value={form.nombre} onChange={e => set('nombre', e.target.value)} />
          </div>
          <div>
            <Label>Categoría</Label>
            <select className={selectClass} value={form.categoria} onChange={e => set('categoria', e.target.value)}>
              {CATEGORIAS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Precio unitario (COP)</Label>
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">$</span>
                <Input type="number" min="0" className="pl-6" value={form.precio_unidad}
                  onChange={e => set('precio_unidad', e.target.value)} />
              </div>
            </div>
            <div>
              <Label>Unidad DIAN</Label>
              <select className={selectClass} value={form.unidad_medida} onChange={e => set('unidad_medida', e.target.value)}>
                {UNIDADES.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>
          <div>
            <Label>Código (opcional)</Label>
            <Input value={form.codigo} onChange={e => set('codigo', e.target.value)} />
          </div>
        </div>
        {err && (
          <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-xs">
            <AlertCircle className="size-3.5 shrink-0" /> {err}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={guardar} disabled={estado === 'saving' || estado === 'ok'}
            className={cn(estado === 'ok' && 'bg-success hover:bg-success/90')}>
            {estado === 'saving' ? <><Loader2 className="size-3.5 mr-1.5 animate-spin" /> Guardando…</> :
             estado === 'ok'     ? <><Check className="size-3.5 mr-1.5" /> Guardado</> :
                                    'Guardar cambios'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ModalEliminarProducto({ prod, onClose, onEliminado, authFetch }) {
  const [estado,    setEstado]    = useState('idle')
  const [err,       setErr]       = useState('')
  const [archivado, setArchivado] = useState(false)

  const eliminar = async () => {
    setEstado('saving'); setErr('')
    try {
      const r = await authFetch(`${API_BASE}/catalogo/${encodeURIComponent(prod.key)}`, { method: 'DELETE' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error al eliminar')
      setArchivado(!!d.archivado); setEstado('ok')
      setTimeout(() => { onEliminado(); onClose() }, 1000)
    } catch (e) { setErr(e.message); setEstado('err') }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Eliminar producto</DialogTitle>
        </DialogHeader>
        <div>
          <div className="text-sm font-medium">{prod.nombre}</div>
          <div className="text-xs text-muted-foreground mt-0.5">{prod.categoria}</div>
        </div>
        {estado !== 'ok' ? (
          <div className="flex items-start gap-2 p-3 rounded-md bg-warning/10 border border-warning/30 text-warning text-xs">
            <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
            <span>Se elimina del catálogo y del inventario. Si tiene historial de ventas, se desactivará (no aparecerá en el catálogo pero las ventas previas quedan intactas).</span>
          </div>
        ) : (
          <div className="flex items-start gap-2 p-3 rounded-md bg-success/10 border border-success/30 text-success text-xs">
            <Check className="size-3.5 shrink-0 mt-0.5" />
            <span>{archivado
              ? 'Producto desactivado — tiene ventas previas y se conserva en el historial.'
              : 'Producto eliminado del catálogo correctamente.'}</span>
          </div>
        )}
        {err && <div className="text-xs text-destructive">{err}</div>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{estado === 'ok' ? 'Cerrar' : 'Cancelar'}</Button>
          {estado !== 'ok' && (
            <Button variant="destructive" onClick={eliminar} disabled={estado === 'saving'}>
              {estado === 'saving' ? 'Eliminando…' : 'Sí, eliminar'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ModalCrearProducto({ onClose, onCreado, authFetch }) {
  const [form, setForm] = useState({
    nombre: '', categoria: CATEGORIAS[0], precio_unidad: '',
    unidad_medida: 'Unidad', codigo: '', stock_inicial: '',
  })
  const [estado, setEstado] = useState('idle')
  const [errMsg, setErrMsg] = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const guardar = async () => {
    if (!form.nombre.trim())                                      { setErrMsg('El nombre es obligatorio'); return }
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

      const r = await authFetch(`${API_BASE}/catalogo`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Error desconocido')
      if (data.drive_guardado === false) {
        setErrMsg('⚠️ Producto creado localmente pero no se pudo sincronizar con Drive. Se guardará en el próximo reinicio.')
      }
      setEstado('ok')
      setTimeout(() => { onCreado(data); onClose() }, data.drive_guardado === false ? 2200 : 600)
    } catch (e) { setErrMsg(e.message || 'Error al crear el producto'); setEstado('err') }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Crear producto</DialogTitle>
          <p className="text-xs text-muted-foreground">Se guardará en catálogo y en el Excel de productos</p>
        </DialogHeader>
        <div className="space-y-3.5">
          <div>
            <Label>Nombre del producto *</Label>
            <Input autoFocus value={form.nombre} placeholder='Ej: Brocha de 2"'
              onChange={e => set('nombre', e.target.value)}
              onKeyDown={e => e.key === 'Enter' && guardar()} />
          </div>
          <div>
            <Label>Categoría *</Label>
            <select className={selectClass} value={form.categoria} onChange={e => set('categoria', e.target.value)}>
              {CATEGORIAS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Precio unitario (COP) *</Label>
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">$</span>
                <Input type="number" min="0" className="pl-6" value={form.precio_unidad}
                  onChange={e => set('precio_unidad', e.target.value)} placeholder="0" />
              </div>
            </div>
            <div>
              <Label>Unidad (DIAN)</Label>
              <select className={selectClass} value={form.unidad_medida} onChange={e => set('unidad_medida', e.target.value)}>
                {UNIDADES.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Código (opcional)</Label>
              <Input value={form.codigo} placeholder="Ej: 1brocha2" onChange={e => set('codigo', e.target.value)} />
            </div>
            <div>
              <Label>Stock inicial (opcional)</Label>
              <Input type="number" min="0" step="0.01" value={form.stock_inicial} placeholder="0"
                onChange={e => set('stock_inicial', e.target.value)} />
            </div>
          </div>
          <div className="p-2.5 rounded-md bg-primary-soft border border-primary/20 text-[11px] text-primary">
            💡 Galón → pinturas · Kg → productos por peso · Mts/Cms → cables y telas · Unidad → resto
          </div>
        </div>
        {errMsg && (
          <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-xs">
            <AlertCircle className="size-3.5 shrink-0" /> {errMsg}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={guardar} disabled={estado === 'saving' || estado === 'ok'}
            className={cn(estado === 'ok' && 'bg-success hover:bg-success/90')}>
            {estado === 'saving' ? <><Loader2 className="size-3.5 mr-1.5 animate-spin" /> Creando…</> :
             estado === 'ok'     ? <><Check className="size-3.5 mr-1.5" /> Creado</> :
                                    'Crear producto'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── tab principal ────────────────────────────────────────────────────────────
export default function TabInventario({ refreshKey }) {
  const isMobile = useIsMobile()
  const { authFetch } = useAuth()

  const [busqueda,     setBusqueda]     = useState('')
  const [queryActivo,  setQueryActivo]  = useState('')
  const [abierta,      setAbierta]      = useState(null)
  const [subcatActiva, setSubcatActiva] = useState({})
  const [modalCrear,   setModalCrear]   = useState(false)
  const [localRefresh, setLocalRefresh] = useState(0)
  const [editandoProd,   setEditandoProd]   = useState(null)
  const [eliminandoProd, setEliminandoProd] = useState(null)

  const url = queryActivo ? `/catalogo/nav?q=${encodeURIComponent(queryActivo)}` : '/catalogo/nav'
  const { data, loading, error } = useFetch(url, [queryActivo, refreshKey, localRefresh])

  const categorias = data?.categorias || {}
  const total      = data?.total || 0
  const catEntries = Object.entries(categorias)

  const handleBuscar = val => {
    setBusqueda(val)
    clearTimeout(window._invTimer)
    window._invTimer = setTimeout(() => setQueryActivo(val), 300)
  }
  const bumpRefresh = () => setLocalRefresh(r => r + 1)

  return (
    <div className="flex flex-col gap-3.5">
      {modalCrear && (
        <ModalCrearProducto onClose={() => setModalCrear(false)} onCreado={bumpRefresh} authFetch={authFetch} />
      )}
      {editandoProd && (
        <ModalEditarProducto prod={editandoProd} onClose={() => setEditandoProd(null)} onGuardado={bumpRefresh} authFetch={authFetch} />
      )}
      {eliminandoProd && (
        <ModalEliminarProducto prod={eliminandoProd} onClose={() => setEliminandoProd(null)} onEliminado={bumpRefresh} authFetch={authFetch} />
      )}

      {/* Header */}
      <div className={cn('flex justify-between items-center gap-3', isMobile && 'flex-col items-stretch')}>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="text-xs text-muted-foreground flex items-center gap-1.5">
            <Package className="size-3.5" />
            <strong className="text-foreground">{total}</strong> productos ·{' '}
            <strong className="text-foreground">{catEntries.length}</strong> categorías
            {!isMobile && <span className="ml-2 opacity-60">· Clic en precio o stock para editar</span>}
          </div>
          <Button onClick={() => setModalCrear(true)} className={cn(isMobile && 'w-full')}>
            <Plus className="size-3.5 mr-1.5" /> Nuevo producto
          </Button>
        </div>
        <div className="relative">
          <Search className="size-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={busqueda} onChange={e => handleBuscar(e.target.value)}
            placeholder="Buscar producto o código…"
            className={cn('pl-9', isMobile ? 'w-full' : 'w-72')}
          />
        </div>
      </div>

      {loading && (
        <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
          <Loader2 className="size-6 animate-spin text-primary" />
          <span className="text-xs">Cargando…</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-sm">
          <AlertCircle className="size-4 shrink-0" /> Error: {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {catEntries.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              <Package className="size-8 mx-auto opacity-40 mb-2" />
              <span className="text-sm">{busqueda ? 'Sin resultados.' : 'Sin productos.'}</span>
            </div>
          ) : catEntries.map(([cat, prods]) => {
            const catKey     = cat.toLowerCase()
            const label      = cat.replace(/^\d+\s*/, '')
            const expandida  = busqueda ? true : abierta === cat
            const subcats    = getSubcats(catKey)
            const subcatSel  = subcatActiva[cat] || null
            const conFracs   = prods.filter(p => p.fracciones && Object.keys(p.fracciones).length > 0).length
            const sinPrecio  = prods.filter(p => !p.precio).length
            const sinStock   = prods.filter(p => p.stock === null || p.stock === undefined).length
            const prodsVisibles = subcatSel ? filtrarPorSubcat(prods, subcats, subcatSel) : prods

            return (
              <Card key={cat} className={cn('overflow-hidden p-0 gap-0', expandida && 'border-primary/40')}>
                {/* Header categoría */}
                <button
                  onClick={() => !busqueda && setAbierta(p => p === cat ? null : cat)}
                  className={cn(
                    'w-full flex items-center justify-between gap-3 px-4 py-3 text-left',
                    !busqueda && 'cursor-pointer hover:bg-surface-2/40',
                    isMobile && 'py-3.5',
                  )}
                >
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <span className="text-lg">{catIcon(label)}</span>
                    <span className="font-bold text-sm">{label}</span>
                    <span className="text-[11px] text-muted-foreground">{prods.length} productos</span>
                    {conFracs > 0  && <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-soft text-primary">{conFracs} fraccionables</span>}
                    {sinPrecio > 0 && <span className="text-[10px] text-warning">⚠ {sinPrecio} sin precio</span>}
                    {sinStock > 0  && <span className="text-[10px] text-muted-foreground">📦 {sinStock} sin stock</span>}
                  </div>
                  {!busqueda && (
                    expandida
                      ? <ChevronUp className="size-4 text-muted-foreground shrink-0" />
                      : <ChevronDown className="size-4 text-muted-foreground shrink-0" />
                  )}
                </button>

                {/* Subcategorías */}
                {expandida && subcats.length > 0 && (
                  <div className={cn(
                    'px-3 py-2 border-t border-border-subtle flex gap-1.5 bg-surface-2/40',
                    isMobile ? 'overflow-x-auto flex-nowrap' : 'flex-wrap',
                  )}>
                    <button
                      onClick={() => setSubcatActiva(prev => ({ ...prev, [cat]: null }))}
                      className={cn(
                        'text-xs px-3 py-1 rounded-full whitespace-nowrap shrink-0 transition-colors border',
                        !subcatSel
                          ? 'bg-primary text-primary-foreground border-primary font-semibold'
                          : 'border-border text-muted-foreground hover:text-foreground hover:border-primary/40',
                      )}
                    >
                      Todos ({prods.length})
                    </button>
                    {subcats.map(sc => {
                      const cnt = filtrarPorSubcat(prods, subcats, sc.key).length
                      if (cnt === 0) return null
                      const active = subcatSel === sc.key
                      return (
                        <button key={sc.key}
                          onClick={() => setSubcatActiva(prev => ({ ...prev, [cat]: sc.key }))}
                          className={cn(
                            'text-xs px-3 py-1 rounded-full whitespace-nowrap shrink-0 transition-colors border flex items-center gap-1.5',
                            active
                              ? 'bg-primary text-primary-foreground border-primary font-semibold'
                              : 'border-border text-muted-foreground hover:text-foreground hover:border-primary/40',
                          )}
                        >
                          <span>{sc.icono}</span>
                          <span>{sc.label}</span>
                          <span className="text-[10px] opacity-70">({cnt})</span>
                        </button>
                      )
                    })}
                  </div>
                )}

                {/* Tabla */}
                {expandida && (
                  prodsVisibles.length === 0
                    ? <div className="py-5 text-center text-xs text-muted-foreground">Sin productos en esta subcategoría.</div>
                    : <TablaCat prods={prodsVisibles} onEdit={setEditandoProd} onDelete={setEliminandoProd}
                        isMobile={isMobile} authFetch={authFetch} />
                )}
              </Card>
            )
          })}
        </>
      )}
    </div>
  )
}
