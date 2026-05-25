/**
 * TabComprasFiscal.jsx — Compras Fiscales (Contabilidad / Libro IVA)
 *
 * - Registro contable: NO modifica inventario ni kárdex
 * - Campos extra: número de factura, notas fiscales
 * - Editar ítem / factura agrupada / enviar a Almacén
 *
 * Migrado a tokens shadcn + sonner (Wave 4 — Fiscal).
 */
import { useState, useRef, useEffect } from 'react'
import { toast } from 'sonner'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import {
  AlertTriangle, BarChart3, ChevronRight, ClipboardList, DollarSign,
  FileBarChart, FileText, Hash, Loader2, Package, Pencil, Plus, Receipt,
  ShoppingCart, StickyNote, Truck, X,
} from 'lucide-react'
import { useFetch, cop, num, API_BASE, useIsMobile } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog.jsx'
import { cn } from '@/lib/utils'

const DIAS_OPTIONS = [
  { label: '7 días',  value: 7  },
  { label: '15 días', value: 15 },
  { label: '30 días', value: 30 },
  { label: '90 días', value: 90 },
]

const PROV_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
  'hsl(var(--chart-6))',
]
const TARIFAS_IVA = [5, 19]

function agruparCompras(lista) {
  const map = new Map()
  lista.forEach(c => {
    const key = c.numero_factura ? c.numero_factura : `_solo_${c.id}`
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(c)
  })
  return Array.from(map.entries()).map(([key, items]) => ({
    key,
    isGroup: items.length >= 2 && !key.startsWith('_solo_'),
    items,
  }))
}

function calcIVA(total, tarifa) {
  if (!total || !tarifa) return { base: total || 0, iva: 0 }
  const base = Math.round(parseFloat(total) * 100 / (100 + parseFloat(tarifa)))
  const iva  = Math.round(parseFloat(total) - base)
  return { base, iva }
}

// ── Helpers UI tokenizados ────────────────────────────────────────────────────

function SectionTitle({ icon: Icon, children }) {
  return (
    <div className="inline-flex items-center gap-2 text-sm font-semibold text-foreground">
      {Icon && <Icon className="size-4 text-muted-foreground" />}
      {children}
    </div>
  )
}

function PeriodChip({ active, children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'px-3 py-1 rounded-md text-[11px] border transition-colors',
        active
          ? 'bg-primary-soft border-primary text-primary font-bold'
          : 'bg-transparent border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-10">
      <Loader2 className="size-5 animate-spin text-muted-foreground" />
    </div>
  )
}

function ErrorMsg({ msg }) {
  return (
    <div className="text-xs text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-3 py-2">
      {msg}
    </div>
  )
}

function EmptyState({ msg = 'Sin datos para este período.' }) {
  return <div className="text-xs text-muted-foreground py-4">{msg}</div>
}

function KpiCard({ label, value, sub, icon: Icon, tone = 'primary' }) {
  const toneCls = {
    primary: 'text-primary',
    success: 'text-success',
    warning: 'text-warning',
    muted:   'text-muted-foreground',
  }[tone] || 'text-primary'
  const bgIcon = {
    primary: 'bg-primary-soft',
    success: 'bg-success/10',
    warning: 'bg-warning/10',
    muted:   'bg-muted',
  }[tone] || 'bg-primary-soft'
  return (
    <Card className="flex-1 min-w-[140px] p-3.5">
      <div className="flex justify-between items-start gap-2">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
            {label}
          </div>
          <div className="text-lg font-bold text-foreground tabular-nums truncate">{value}</div>
          {sub && <div className="text-[11px] text-muted-foreground mt-1 truncate">{sub}</div>}
        </div>
        {Icon && (
          <div className={cn('size-7 rounded-md inline-flex items-center justify-center flex-shrink-0', bgIcon)}>
            <Icon className={cn('size-3.5', toneCls)} />
          </div>
        )}
      </div>
    </Card>
  )
}

// ── IVA toggle reutilizable ───────────────────────────────────────────────────

function IvaToggle({ incluye, tarifa, onIncluyeChange, onTarifaChange, size = 'md' }) {
  const sm = size === 'sm'
  return (
    <div className={cn('flex items-center flex-wrap', sm ? 'gap-1.5' : 'gap-2.5')}>
      <button
        type="button"
        onClick={() => onIncluyeChange(!incluye)}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-md font-semibold border transition-colors',
          sm ? 'px-2 py-0.5 text-[10px]' : 'px-3.5 py-1.5 text-[11px]',
          incluye
            ? 'bg-success/10 border-success/40 text-success'
            : 'bg-muted border-border text-muted-foreground',
        )}
      >
        <span className={cn(
          'rounded-full relative flex-shrink-0 transition-colors',
          sm ? 'w-5 h-3' : 'w-7 h-4',
          incluye ? 'bg-success' : 'bg-border',
        )}>
          <span className={cn(
            'absolute rounded-full bg-white transition-[left] duration-150',
            sm ? 'top-0.5 size-2' : 'top-0.5 size-3',
            incluye
              ? (sm ? 'left-[10px]' : 'left-[14px]')
              : (sm ? 'left-0.5'    : 'left-0.5'),
          )} />
        </span>
        {sm ? (incluye ? 'IVA' : 'Sin') : (incluye ? 'Incluye IVA' : 'Sin IVA')}
      </button>
      {incluye && TARIFAS_IVA.map(tv => (
        <button
          key={tv}
          type="button"
          onClick={() => onTarifaChange(tv)}
          className={cn(
            'rounded-md font-bold border transition-colors',
            sm ? 'px-2 py-0.5 text-[10px]' : 'px-3.5 py-1.5 text-[11px]',
            tarifa === tv
              ? 'bg-primary-soft border-primary text-primary'
              : 'bg-transparent border-border text-muted-foreground hover:border-primary/40',
          )}
        >
          {tv}%
        </button>
      ))}
    </div>
  )
}

// ── Buscador de productos ─────────────────────────────────────────────────────

function ProductoSearchInput({ value, onChange, placeholder, className }) {
  const { authFetch } = useAuth()
  const [todos, setTodos] = useState([])
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const cargar = async () => {
    if (todos.length > 0) return
    try {
      const r = await authFetch(`${API_BASE}/productos`)
      const d = await r.json()
      const nombres = (d.productos || []).map(p => p.nombre).sort((a,b) => a.localeCompare(b))
      setTodos(nombres)
    } catch {}
  }

  const filtrados = value.trim().length >= 1
    ? todos.filter(n => n.toLowerCase().includes(value.toLowerCase()))
    : todos.slice(0, 30)

  useEffect(() => {
    const handler = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div ref={ref} className="relative">
      <Input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => { cargar(); setOpen(true) }}
        placeholder={placeholder || 'Buscar producto del catálogo…'}
        autoComplete="off"
        className={className}
      />
      {open && filtrados.length > 0 && (
        <div className="absolute top-[calc(100%+3px)] left-0 right-0 z-50 max-h-56 overflow-y-auto rounded-md border border-border bg-popover shadow-lg">
          {filtrados.map(n => {
            const selected = n.toLowerCase() === value.toLowerCase()
            return (
              <div
                key={n}
                onMouseDown={e => { e.preventDefault(); onChange(n); setOpen(false) }}
                className={cn(
                  'px-3 py-1.5 cursor-pointer text-xs hover:bg-primary-soft transition-colors border-b border-border/40 last:border-0',
                  selected ? 'text-primary font-bold' : 'text-foreground',
                )}
              >
                {n}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Modal Editar Factura (grupo completo) ─────────────────────────────────────

function ModalEditarFactura({ factura, open, onClose, onSaved, authFetch }) {
  const isMobile = useIsMobile()

  const [proveedor,     setProveedor]     = useState('')
  const [numeroFactura, setNumeroFactura] = useState('')
  const [notasFiscales, setNotasFiscales] = useState('')
  const [filas,         setFilas]         = useState({})
  const [guardando,     setGuardando]     = useState(false)
  const [err,           setErr]           = useState(null)

  useEffect(() => {
    if (factura) {
      setProveedor(factura.proveedor === 'Sin proveedor' ? '' : (factura.proveedor || ''))
      setNumeroFactura(factura.numero_factura || '')
      setNotasFiscales(factura.items[0]?.notas_fiscales || '')
      setFilas(Object.fromEntries(factura.items.map(c => [c.id, {
        producto:   c.producto,
        cantidad:   String(c.cantidad),
        costoUnit:  String(c.costo_unitario),
        incluyeIva: c.incluye_iva,
        tarifaIva:  c.tarifa_iva || 19,
      }])))
      setErr(null)
    }
  }, [factura])

  if (!factura) return null

  const setFila = (id, campo, valor) =>
    setFilas(prev => ({ ...prev, [id]: { ...prev[id], [campo]: valor } }))

  const totalFila = (id) => {
    const f = filas[id]; if (!f) return 0
    const q = parseFloat(f.cantidad), p = parseFloat(f.costoUnit)
    return isNaN(q) || isNaN(p) ? 0 : q * p
  }
  const totalGeneral  = factura.items.reduce((s, c) => s + totalFila(c.id), 0)
  const totalIvaTotal = factura.items.reduce((s, c) => {
    const f = filas[c.id]
    if (!f?.incluyeIva || !f.tarifaIva) return s
    return s + calcIVA(totalFila(c.id), f.tarifaIva).iva
  }, 0)

  const guardarTodos = async () => {
    for (const c of factura.items) {
      const f = filas[c.id]
      if (!f.producto.trim())              { setErr(`Producto vacío en fila "${c.producto}"`); return }
      if (!(parseFloat(f.cantidad)  > 0))  { setErr(`Cantidad inválida en "${f.producto}"`); return }
      if (!(parseFloat(f.costoUnit) > 0))  { setErr(`Costo inválido en "${f.producto}"`);    return }
    }
    setGuardando(true); setErr(null)

    const resultados = await Promise.allSettled(
      factura.items.map(c => {
        const f = filas[c.id]
        return authFetch(`${API_BASE}/compras-fiscal/${c.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            producto:       f.producto.trim(),
            cantidad:       parseFloat(f.cantidad),
            costo_unitario: parseFloat(f.costoUnit),
            proveedor:      proveedor.trim(),
            incluye_iva:    f.incluyeIva,
            tarifa_iva:     f.incluyeIva ? f.tarifaIva : 0,
            numero_factura: numeroFactura.trim(),
            notas_fiscales: notasFiscales.trim(),
          }),
        }).then(async r => {
          const d = await r.json()
          if (!r.ok) throw new Error(d.detail || 'Error')
          return d
        })
      })
    )

    setGuardando(false)
    const ok = resultados.filter(r => r.status === 'fulfilled').length
    const ko = resultados.filter(r => r.status === 'rejected')
    if (ko.length > 0) {
      setErr(`${ko.length} ítem(s) fallaron: ${ko.map(r => r.reason?.message).join(', ')}`)
    }
    if (ok > 0) {
      onSaved(`${ok} de ${factura.items.length} ítems de la factura actualizados`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="inline-flex items-center gap-2">
            <Pencil className="size-4 text-primary" />
            Editar Factura
            <span className="text-primary font-mono">{factura.numero_factura}</span>
          </DialogTitle>
          <DialogDescription>
            Solo contabilidad · no modifica inventario · {factura.items.length} ítems
          </DialogDescription>
        </DialogHeader>

        {err && <ErrorMsg msg={err} />}

        {/* Campos globales */}
        <div className={cn('grid gap-2.5', isMobile ? 'grid-cols-1' : 'grid-cols-2')}>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Proveedor (aplica a todos)</Label>
            <Input value={proveedor} onChange={e => setProveedor(e.target.value)} placeholder="Ej: Ferrisariato" />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Número de Factura</Label>
            <Input value={numeroFactura} onChange={e => setNumeroFactura(e.target.value)} placeholder="Ej: FV-2024-001234" />
          </div>
          <div className="col-span-full space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Notas Fiscales (aplica a todos)</Label>
            <textarea
              value={notasFiscales}
              onChange={e => setNotasFiscales(e.target.value)}
              placeholder="Observaciones para el Libro IVA…"
              rows={2}
              className="w-full rounded-md border border-input bg-surface text-foreground text-sm px-3 py-2 resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
        </div>

        {/* Tabla de ítems */}
        <div className="border border-border rounded-md overflow-hidden overflow-x-auto">
          <div
            className="grid bg-muted/40 px-3 py-2 text-[10px] text-muted-foreground font-semibold uppercase tracking-wider border-b border-border min-w-[480px]"
            style={{ gridTemplateColumns: '2fr 80px 110px 160px 90px' }}
          >
            <span className="px-1">Producto</span>
            <span className="px-1">Cantidad</span>
            <span className="px-1">Costo unit.</span>
            <span className="px-1">IVA</span>
            <span className="px-1 text-right">Total</span>
          </div>
          {factura.items.map((c, ri) => {
            const f = filas[c.id]; if (!f) return null
            const tot = totalFila(c.id)
            return (
              <div
                key={c.id}
                className={cn(
                  'grid items-center gap-1.5 px-3 py-2.5 min-w-[480px]',
                  ri < factura.items.length - 1 && 'border-b border-border',
                )}
                style={{ gridTemplateColumns: '2fr 80px 110px 160px 90px' }}
              >
                <div className="px-1">
                  <ProductoSearchInput
                    value={f.producto}
                    onChange={v => setFila(c.id, 'producto', v)}
                    className="h-7 text-[11px]"
                    placeholder="Producto…"
                  />
                </div>
                <div className="px-1">
                  <Input
                    type="number" min="0" step="0.01"
                    value={f.cantidad}
                    onChange={e => setFila(c.id, 'cantidad', e.target.value)}
                    className="h-7 text-[11px]"
                  />
                </div>
                <div className="px-1 relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-[10px]">$</span>
                  <Input
                    type="number" min="0"
                    value={f.costoUnit}
                    onChange={e => setFila(c.id, 'costoUnit', e.target.value)}
                    className="h-7 text-[11px] pl-5"
                  />
                </div>
                <div className="px-1">
                  <IvaToggle
                    incluye={f.incluyeIva}
                    tarifa={f.tarifaIva}
                    onIncluyeChange={v => setFila(c.id, 'incluyeIva', v)}
                    onTarifaChange={v => setFila(c.id, 'tarifaIva', v)}
                    size="sm"
                  />
                </div>
                <div className="px-1 text-right">
                  <span className="text-xs text-primary font-bold tabular-nums">{cop(tot)}</span>
                  {f.incluyeIva && f.tarifaIva > 0 && tot > 0 && (
                    <div className="text-[10px] text-success mt-0.5">
                      IVA {cop(calcIVA(tot, f.tarifaIva).iva)}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          <div className="flex justify-end gap-6 px-4 py-2.5 bg-muted/40 border-t border-border text-xs">
            {totalIvaTotal > 0 && (
              <span className="text-success font-semibold">IVA total: {cop(totalIvaTotal)}</span>
            )}
            <span className="text-primary font-bold tabular-nums">
              Total general: {cop(totalGeneral)}
            </span>
          </div>
        </div>

        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={guardarTodos} disabled={guardando}>
            {guardando && <Loader2 className="size-4 mr-1.5 animate-spin" />}
            {guardando ? 'Guardando…' : 'Guardar todos los cambios'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── Modal Enviar al Almacén ───────────────────────────────────────────────────

function ModalEnviarAlmacen({ factura, open, onClose, onSaved, authFetch }) {
  const [filas, setFilas] = useState({})
  const [enviando, setEnviando] = useState(false)
  const [err, setErr] = useState(null)

  useEffect(() => {
    if (factura) {
      setFilas(Object.fromEntries(factura.items.map(c => [c.id, {
        producto:  c.producto,
        cantidad:  String(c.cantidad),
        costoUnit: String(c.costo_unitario),
        checked:   !c.compra_origen_id,
      }])))
      setErr(null)
    }
  }, [factura])

  if (!factura) return null

  const setFila = (id, campo, valor) =>
    setFilas(prev => ({ ...prev, [id]: { ...prev[id], [campo]: valor } }))

  const seleccionados = factura.items.filter(c => filas[c.id]?.checked && !c.compra_origen_id)
  const totalSel = seleccionados.reduce((s, c) => {
    const f = filas[c.id]
    return s + (parseFloat(f.cantidad) || 0) * (parseFloat(f.costoUnit) || 0)
  }, 0)

  const confirmar = async () => {
    if (seleccionados.length === 0) return
    setEnviando(true); setErr(null)
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal/bulk-to-compras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: seleccionados.map(c => {
            const f = filas[c.id]
            return {
              id:             c.id,
              producto:       f.producto.trim(),
              cantidad:       parseFloat(f.cantidad),
              costo_unitario: parseFloat(f.costoUnit),
            }
          }),
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')

      let msg = `${d.procesados} ítem(s) enviados al Almacén`
      if (d.ya_existian > 0)     msg += ` · ${d.ya_existian} ya existían`
      if (d.errores?.length > 0) msg += ` · ${d.errores.length} error(es)`
      onSaved(msg)
    } catch (e) { setErr(e.message) }
    finally { setEnviando(false) }
  }

  const COLS = '28px 2fr 80px 110px 80px 90px'

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="inline-flex items-center gap-2">
            <Package className="size-4 text-primary" />
            Enviar a Almacén
            <span className="text-primary font-mono">{factura.numero_factura}</span>
          </DialogTitle>
          <DialogDescription>Revisa y ajusta antes de confirmar</DialogDescription>
        </DialogHeader>

        <div className="rounded-md bg-primary-soft border border-primary/30 px-3.5 py-2.5 text-[11px] text-muted-foreground flex gap-2 items-start">
          <Package className="size-3.5 text-primary mt-0.5 flex-shrink-0" />
          <span>
            Esta acción creará registros en <strong className="text-foreground">Compras (inventario)</strong>.
            Los nombres y cantidades son editables antes de confirmar.
          </span>
        </div>

        {err && <ErrorMsg msg={err} />}

        <div className="border border-border rounded-md overflow-hidden overflow-x-auto">
          <div
            className="grid items-center gap-1.5 bg-muted/40 px-3 py-1.5 text-[10px] text-muted-foreground font-semibold uppercase tracking-wider border-b border-border min-w-[460px]"
            style={{ gridTemplateColumns: COLS }}
          >
            <span />
            <span className="px-1">Producto</span>
            <span className="px-1">Cant.</span>
            <span className="px-1">Costo unit.</span>
            <span className="px-1 text-right">Total</span>
            <span className="px-1">Estado</span>
          </div>
          {factura.items.map((c, ri) => {
            const f = filas[c.id]; if (!f) return null
            const yaEnAlm = !!c.compra_origen_id
            const tot = (parseFloat(f.cantidad) || 0) * (parseFloat(f.costoUnit) || 0)
            return (
              <div
                key={c.id}
                className={cn(
                  'grid items-center gap-1.5 px-3 py-2 min-w-[460px]',
                  ri < factura.items.length - 1 && 'border-b border-border',
                  yaEnAlm && 'opacity-50',
                )}
                style={{ gridTemplateColumns: COLS }}
              >
                <div className="flex justify-center">
                  <input
                    type="checkbox"
                    checked={f.checked}
                    disabled={yaEnAlm}
                    onChange={e => setFila(c.id, 'checked', e.target.checked)}
                    className="size-4 accent-primary cursor-pointer disabled:cursor-default"
                  />
                </div>
                <div className="px-1">
                  <ProductoSearchInput
                    value={f.producto}
                    onChange={v => setFila(c.id, 'producto', v)}
                    className="h-7 text-[11px]"
                    placeholder="Producto…"
                  />
                </div>
                <div className="px-1">
                  <Input
                    type="number" min="0" step="0.01"
                    value={f.cantidad}
                    disabled={yaEnAlm}
                    onChange={e => setFila(c.id, 'cantidad', e.target.value)}
                    className="h-7 text-[11px]"
                  />
                </div>
                <div className="px-1 relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-[10px]">$</span>
                  <Input
                    type="number" min="0"
                    value={f.costoUnit}
                    disabled={yaEnAlm}
                    onChange={e => setFila(c.id, 'costoUnit', e.target.value)}
                    className="h-7 text-[11px] pl-5"
                  />
                </div>
                <div className="px-1 text-right text-xs text-primary font-bold tabular-nums">{cop(tot)}</div>
                <div className="px-1">
                  {yaEnAlm ? (
                    <span className="text-[10px] text-muted-foreground font-semibold bg-muted border border-border rounded px-2 py-0.5">
                      Ya en almacén
                    </span>
                  ) : (
                    <span className={cn('text-[10px] font-semibold', f.checked ? 'text-success' : 'text-muted-foreground')}>
                      {f.checked ? 'Incluido' : '—'}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        <div className="flex justify-between items-center px-4 py-2.5 rounded-md bg-muted/40 border border-border text-xs">
          <span className="text-muted-foreground">
            <strong className="text-foreground">{seleccionados.length}</strong> ítem(s) seleccionados
          </span>
          <span className="text-primary font-bold tabular-nums">Total: {cop(totalSel)}</span>
        </div>

        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button
            onClick={confirmar}
            disabled={enviando || seleccionados.length === 0}
          >
            {enviando
              ? <><Loader2 className="size-4 mr-1.5 animate-spin" /> Enviando…</>
              : <><Package className="size-4 mr-1.5" /> Enviar {seleccionados.length} ítem(s) al Almacén</>}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── Modal Editar Fiscal (un ítem) ─────────────────────────────────────────────

function ModalEditarFiscal({ compra, open, onClose, onSaved, authFetch }) {
  const [producto,       setProducto]      = useState('')
  const [cantidad,       setCantidad]      = useState('')
  const [costoUnit,      setCostoUnit]     = useState('')
  const [proveedor,      setProveedor]     = useState('')
  const [incluyeIva,     setIncluyeIva]    = useState(false)
  const [tarifaIva,      setTarifaIva]     = useState(19)
  const [numeroFactura,  setNumeroFactura] = useState('')
  const [notasFiscales,  setNotasFiscales] = useState('')
  const [guardando,      setGuardando]     = useState(false)
  const [err,            setErr]           = useState(null)

  useEffect(() => {
    if (compra) {
      setProducto(compra.producto || '')
      setCantidad(String(compra.cantidad || ''))
      setCostoUnit(String(compra.costo_unitario || ''))
      setProveedor(compra.proveedor === 'Sin proveedor' ? '' : (compra.proveedor || ''))
      setIncluyeIva(compra.incluye_iva || false)
      setTarifaIva(compra.tarifa_iva || 19)
      setNumeroFactura(compra.numero_factura || '')
      setNotasFiscales(compra.notas_fiscales || '')
      setErr(null)
    }
  }, [compra])

  if (!compra) return null

  const guardar = async () => {
    if (!producto.trim())           { setErr('El producto es obligatorio'); return }
    if (parseFloat(cantidad) <= 0)  { setErr('Cantidad inválida'); return }
    if (parseFloat(costoUnit) <= 0) { setErr('Costo inválido'); return }
    setGuardando(true); setErr(null)
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal/${compra.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto:       producto.trim(),
          cantidad:       parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor:      proveedor.trim(),
          incluye_iva:    incluyeIva,
          tarifa_iva:     incluyeIva ? tarifaIva : 0,
          numero_factura: numeroFactura.trim(),
          notas_fiscales: notasFiscales.trim(),
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      onSaved()
    } catch (e) { setErr(e.message) }
    finally { setGuardando(false) }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="inline-flex items-center gap-2">
            <Pencil className="size-4 text-primary" />
            Editar Compra Fiscal
          </DialogTitle>
          <DialogDescription>Solo contabilidad · no modifica inventario</DialogDescription>
        </DialogHeader>

        {err && <ErrorMsg msg={err} />}

        <div className="grid grid-cols-2 gap-2.5">
          <div className="col-span-2 space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Producto *</Label>
            <ProductoSearchInput value={producto} onChange={setProducto} />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Cantidad *</Label>
            <Input type="number" min="0" step="0.01" value={cantidad} onChange={e => setCantidad(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Costo unitario *</Label>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">$</span>
              <Input type="number" min="0" value={costoUnit} onChange={e => setCostoUnit(e.target.value)} className="pl-6" />
            </div>
          </div>
          <div className="col-span-2 space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Proveedor</Label>
            <Input value={proveedor} onChange={e => setProveedor(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Número de Factura</Label>
            <Input value={numeroFactura} onChange={e => setNumeroFactura(e.target.value)} placeholder="Ej: FV-2024-001234" />
          </div>
          <div className="col-span-2 space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">IVA</Label>
            <IvaToggle incluye={incluyeIva} tarifa={tarifaIva} onIncluyeChange={setIncluyeIva} onTarifaChange={setTarifaIva} />
          </div>
          <div className="col-span-2 space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Notas Fiscales</Label>
            <textarea
              value={notasFiscales}
              onChange={e => setNotasFiscales(e.target.value)}
              placeholder="Observaciones para el Libro IVA…"
              rows={3}
              className="w-full rounded-md border border-input bg-surface text-foreground text-sm px-3 py-2 resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
        </div>

        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={guardar} disabled={guardando}>
            {guardando && <Loader2 className="size-4 mr-1.5 animate-spin" />}
            {guardando ? 'Guardando…' : 'Guardar'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function TabComprasFiscal({ refreshKey }) {
  const isMobile = useIsMobile()
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()
  const [dias, setDias] = useState(30)
  const [localRefresh, setLocalRefresh] = useState(0)
  const vendorParam = selectedVendor ? '&vendor_id=' + selectedVendor : ''
  const { data, loading, error } = useFetch(
    `/compras-fiscal?dias=${dias}${vendorParam}`,
    [dias, refreshKey, localRefresh, selectedVendor]
  )

  const [formOpen,      setFormOpen]      = useState(false)
  const [producto,      setProducto]      = useState('')
  const [cantidad,      setCantidad]      = useState('')
  const [costoUnit,     setCostoUnit]     = useState('')
  const [proveedor,     setProveedor]     = useState('')
  const [incluyeIva,    setIncluyeIva]    = useState(true)
  const [tarifaIva,     setTarifaIva]     = useState(19)
  const [numFactura,    setNumFactura]    = useState('')
  const [notasFiscales, setNotasFiscales] = useState('')
  const [guardando,     setGuardando]     = useState(false)

  const [editando, setEditando] = useState(null)
  const [editandoFactura, setEditandoFactura] = useState(null)
  const [enviandoCompra, setEnviandoCompra] = useState({})
  const [expandedGroups, setExpandedGroups] = useState({})
  const [modalEnviarAlmacen, setModalEnviarAlmacen] = useState(null)

  const totalBruto = cantidad && costoUnit ? parseFloat(cantidad) * parseFloat(costoUnit) : 0
  const { base: baseCalc, iva: ivaCalc } = incluyeIva
    ? calcIVA(totalBruto, tarifaIva)
    : { base: totalBruto, iva: 0 }

  const registrarCompraFiscal = async () => {
    if (!producto.trim())                         { toast.error('El producto es obligatorio'); return }
    if (!cantidad || parseFloat(cantidad) <= 0)   { toast.error('La cantidad debe ser mayor a 0'); return }
    if (!costoUnit || parseFloat(costoUnit) <= 0) { toast.error('El costo unitario debe ser mayor a 0'); return }
    setGuardando(true)
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto:       producto.trim(),
          cantidad:       parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor:      proveedor.trim(),
          incluye_iva:    incluyeIva,
          tarifa_iva:     incluyeIva ? tarifaIva : 0,
          numero_factura: numFactura.trim(),
          notas_fiscales: notasFiscales.trim(),
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      const ivaMsg = incluyeIva ? ` · IVA ${tarifaIva}%: ${cop(ivaCalc)}` : ''
      toast.success(`${cantidad} ${producto.trim()} — Total: ${cop(totalBruto)}${ivaMsg}`)
      setProducto(''); setCantidad(''); setCostoUnit(''); setProveedor('')
      setIncluyeIva(false); setTarifaIva(19); setNumFactura(''); setNotasFiscales('')
      setFormOpen(false)
      setLocalRefresh(r => r + 1)
    } catch (e) { toast.error(e.message) }
    finally { setGuardando(false) }
  }

  const enviarACompras = async (compra) => {
    setEnviandoCompra(prev => ({ ...prev, [compra.id]: true }))
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal/${compra.id}/to-compras`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      toast.success(d.ya_existia
        ? 'Esta compra fiscal ya estaba vinculada a Almacén'
        : 'Compra enviada a Almacén (Compras normales)')
      setLocalRefresh(r => r + 1)
    } catch (e) { toast.error(e.message) }
    finally { setEnviandoCompra(prev => ({ ...prev, [compra.id]: false })) }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  const d        = data || {}
  const compras  = d.compras || []
  const porProv  = Object.entries(d.por_proveedor || {}).sort((a, b) => b[1] - a[1])
  const porProd  = Object.entries(d.por_producto  || {}).slice(0, 10)
  const total    = d.total_invertido || 0
  const pieData  = porProv.map(([name, value]) => ({ name, value }))
  const sinDatos = compras.length === 0
  const agrupados = agruparCompras(compras)

  const totalIvaDescontable = compras
    .filter(c => c.incluye_iva && c.tarifa_iva > 0)
    .reduce((s, c) => s + calcIVA(c.costo_total, c.tarifa_iva).iva, 0)
  const conFactura  = compras.filter(c => c.numero_factura).length
  const sinFactura  = compras.length - conFactura
  const yaEnAlmacen = compras.filter(c => !!c.compra_origen_id).length

  return (
    <div className="flex flex-col gap-4">
      <ModalEditarFiscal
        open={editando != null}
        compra={editando}
        onClose={() => setEditando(null)}
        onSaved={() => {
          setEditando(null)
          toast.success('Compra fiscal actualizada')
          setLocalRefresh(r => r + 1)
        }}
        authFetch={authFetch}
      />
      <ModalEditarFactura
        open={editandoFactura != null}
        factura={editandoFactura}
        onClose={() => setEditandoFactura(null)}
        onSaved={(resumenMsg) => {
          setEditandoFactura(null)
          toast.success(resumenMsg)
          setLocalRefresh(r => r + 1)
        }}
        authFetch={authFetch}
      />
      <ModalEnviarAlmacen
        open={modalEnviarAlmacen != null}
        factura={modalEnviarAlmacen}
        onClose={() => setModalEnviarAlmacen(null)}
        onSaved={(resumenMsg) => {
          setModalEnviarAlmacen(null)
          toast.success(resumenMsg)
          setLocalRefresh(r => r + 1)
        }}
        authFetch={authFetch}
      />

      {/* Header */}
      <div className="flex justify-between items-center flex-wrap gap-2.5">
        <div>
          <div className="text-sm font-bold text-foreground inline-flex items-center gap-2">
            <Receipt className="size-4 text-muted-foreground" />
            Compras Fiscales
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            Registro contable · fuente del Libro IVA · últimos {dias} días
          </div>
        </div>
        <div className="flex gap-1.5 items-center flex-wrap">
          {DIAS_OPTIONS.map(o => (
            <PeriodChip key={o.value} active={dias === o.value} onClick={() => setDias(o.value)}>
              {o.label}
            </PeriodChip>
          ))}
          <Button
            size="sm"
            variant={formOpen ? 'default' : 'outline'}
            onClick={() => setFormOpen(f => !f)}
            className="h-7 text-[11px]"
          >
            {formOpen
              ? <><X className="size-3 mr-1" /> Cerrar</>
              : <><Plus className="size-3 mr-1" /> Nueva compra fiscal</>}
          </Button>
        </div>
      </div>

      {/* Aviso contextual */}
      <div className="px-3.5 py-2.5 rounded-md bg-primary-soft border border-primary/30 text-[11px] text-muted-foreground flex items-start gap-2">
        <Receipt className="size-3.5 text-primary mt-0.5 flex-shrink-0" />
        <span>
          Las compras fiscales son el <strong className="text-foreground">registro contable oficial</strong>.
          No actualizan el inventario ni el kárdex.
          Usa el botón <strong className="text-foreground">→ Almacén</strong> para enviar una compra también al módulo operativo.
        </span>
      </div>

      {/* Formulario */}
      {formOpen && (
        <Card className="p-5">
          <SectionTitle icon={Plus}>Registrar Compra Fiscal</SectionTitle>
          <div className="grid grid-cols-2 gap-2.5 mt-3 mb-3">
            <div className="col-span-2 space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Producto *</Label>
              <ProductoSearchInput value={producto} onChange={setProducto} placeholder="Buscar o escribir nombre del producto…" />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Cantidad *</Label>
              <Input type="number" min="0" step="0.01" value={cantidad} onChange={e => setCantidad(e.target.value)} placeholder="0" />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Costo unitario *</Label>
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">$</span>
                <Input type="number" min="0" value={costoUnit} onChange={e => setCostoUnit(e.target.value)} placeholder="0" className="pl-6" />
              </div>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Proveedor (opcional)</Label>
              <Input value={proveedor} onChange={e => setProveedor(e.target.value)} placeholder="Ej: Ferrisariato, Distribuidora Central..." />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Número de Factura</Label>
              <Input value={numFactura} onChange={e => setNumFactura(e.target.value)} placeholder="Ej: FV-2024-001234 (requerido para facturación electrónica)" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">IVA en esta compra</Label>
              <IvaToggle incluye={incluyeIva} tarifa={tarifaIva} onIncluyeChange={setIncluyeIva} onTarifaChange={setTarifaIva} />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Notas Fiscales (opcional)</Label>
              <textarea
                value={notasFiscales}
                onChange={e => setNotasFiscales(e.target.value)}
                placeholder="Observaciones para el Libro IVA…"
                rows={2}
                className="w-full rounded-md border border-input bg-surface text-foreground text-sm px-3 py-2 resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>

          {cantidad && costoUnit && (
            <div className="flex gap-4 flex-wrap px-3.5 py-2.5 rounded-md bg-muted/60 border border-border mb-3 text-xs">
              <span className="text-muted-foreground">Total bruto: <strong className="text-primary">{cop(totalBruto)}</strong></span>
              {incluyeIva && (
                <>
                  <span className="text-muted-foreground">Base (sin IVA): <strong className="text-foreground">{cop(baseCalc)}</strong></span>
                  <span className="text-muted-foreground">IVA {tarifaIva}%: <strong className="text-success">{cop(ivaCalc)}</strong></span>
                </>
              )}
            </div>
          )}

          {incluyeIva && (
            <div className="px-3.5 py-2 rounded-md mb-3 bg-success/10 border border-success/30 text-[11px] text-success">
              El IVA descontable ({cop(ivaCalc)}) quedará registrado en el Libro IVA automáticamente.
            </div>
          )}

          <Button onClick={registrarCompraFiscal} disabled={guardando}>
            {guardando
              ? <><Loader2 className="size-4 mr-1.5 animate-spin" /> Guardando…</>
              : <><Receipt className="size-4 mr-1.5" /> Registrar compra fiscal</>}
          </Button>
        </Card>
      )}

      {sinDatos ? (
        <Card className="p-8 text-center">
          <Receipt className="size-8 mx-auto mb-3 text-muted-foreground" />
          <div className="text-foreground font-semibold mb-2">Sin compras fiscales registradas</div>
          <div className="text-muted-foreground text-xs max-w-sm mx-auto leading-relaxed">
            Registra compras directamente aquí, o envía una compra del módulo de Almacén
            usando el botón <strong className="text-foreground">→ Fiscal</strong>.
          </div>
        </Card>
      ) : (
        <>
          {/* KPIs */}
          <div className="flex gap-2.5 flex-wrap">
            <KpiCard label="Total invertido"    value={cop(total)}               sub={`Últimos ${dias} días`}             icon={DollarSign}    tone="primary" />
            <KpiCard label="IVA descontable"    value={cop(totalIvaDescontable)} sub="Crédito fiscal"                     icon={FileBarChart}  tone="success" />
            <KpiCard label="Compras fiscales"   value={compras.length}           sub="Registros"                           icon={Receipt}       tone="muted" />
            <KpiCard
              label="Con factura"
              value={conFactura}
              sub={sinFactura > 0 ? `${sinFactura} sin nro.` : 'Todas tienen nro.'}
              icon={ClipboardList}
              tone={sinFactura > 0 ? 'warning' : 'success'}
            />
            <KpiCard label="Enviadas a almacén" value={yaEnAlmacen} sub={`de ${compras.length}`} icon={Package} tone="muted" />
          </div>

          {/* Por proveedor */}
          <Card className="p-5">
            <SectionTitle icon={Truck}>Por Proveedor</SectionTitle>
            {porProv.length === 0 ? <EmptyState /> : (
              <div className="flex gap-3 items-center flex-wrap mt-3">
                <ResponsiveContainer width={120} height={120}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2}>
                      {pieData.map((_, i) => <Cell key={i} fill={PROV_COLORS[i % PROV_COLORS.length]} />)}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: 'hsl(var(--bg-surface))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: 8,
                        color: 'hsl(var(--text-primary))',
                        fontSize: 11,
                      }}
                      formatter={v => [cop(v)]}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 min-w-[140px] flex flex-col gap-1.5">
                  {porProv.map(([prov, val], i) => (
                    <div key={i} className="flex justify-between items-center gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="size-2 rounded-full flex-shrink-0"
                          style={{ background: PROV_COLORS[i % PROV_COLORS.length] }}
                        />
                        <span className="text-[11px] text-muted-foreground truncate">{prov}</span>
                      </div>
                      <span className="text-[11px] font-bold text-foreground flex-shrink-0 tabular-nums">{cop(val)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          {/* Productos más comprados */}
          <Card className="p-5">
            <SectionTitle icon={BarChart3}>Productos más Comprados</SectionTitle>
            {porProd.length === 0 ? <EmptyState /> : (
              <div className="flex flex-col gap-2.5 mt-3">
                {porProd.map(([prod, val], i) => (
                  <div key={i} className="flex items-center gap-2.5">
                    <span className="text-muted-foreground text-[11px] min-w-[22px] text-right font-bold">#{i+1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-baseline gap-2 mb-1">
                        <span className="text-[11px] text-foreground truncate">{prod}</span>
                        <span className="text-xs text-primary font-bold flex-shrink-0 tabular-nums">{cop(val)}</span>
                      </div>
                      <div className="h-[3px] bg-border rounded-sm">
                        <div
                          className="h-full bg-primary rounded-sm"
                          style={{ width: `${(val / (porProd[0]?.[1] || 1)) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Detalle */}
          <Card className="overflow-hidden">
            <div className="px-5 py-3.5 border-b border-border flex items-center justify-between flex-wrap gap-2">
              <SectionTitle icon={FileBarChart}>Detalle de Compras Fiscales</SectionTitle>
              <div className="flex items-center gap-2">
                {sinFactura > 0 && (
                  <span className="inline-flex items-center gap-1 text-[10px] bg-warning/10 border border-warning/40 text-warning rounded-full px-2.5 py-0.5 font-semibold">
                    <AlertTriangle className="size-3" /> {sinFactura} sin nro.
                  </span>
                )}
                <span className="text-[11px] text-muted-foreground">
                  {agrupados.length} entradas · {compras.length} ítems
                </span>
              </div>
            </div>

            <div className="flex justify-between items-center px-5 py-2.5 bg-muted/40 border-b border-border">
              <span className="text-[11px] text-muted-foreground font-semibold uppercase tracking-wider">Total Fiscal</span>
              <div className="flex gap-4 items-center">
                <span className="text-sm text-primary font-bold tabular-nums">{cop(total)}</span>
                {totalIvaDescontable > 0 && (
                  <span className="text-[11px] text-success font-semibold">IVA {cop(totalIvaDescontable)}</span>
                )}
              </div>
            </div>

            <div className="flex flex-col">
              {agrupados.map((grupo, gi) => {
                const isLast = gi === agrupados.length - 1

                if (grupo.isGroup) {
                  const expanded       = !!expandedGroups[grupo.key]
                  const items          = grupo.items
                  const totalGrupo     = items.reduce((s, x) => s + (x.costo_total || 0), 0)
                  const tieneIva       = items.some(x => x.incluye_iva && x.tarifa_iva > 0)
                  const enAlmacenCount = items.filter(x => !!x.compra_origen_id).length
                  const todosEnAlmacen = enAlmacenCount === items.length
                  const primerItem     = items[0]
                  const toggleExpanded = () => setExpandedGroups(prev => ({ ...prev, [grupo.key]: !prev[grupo.key] }))

                  return (
                    <div key={grupo.key} className={cn(!isLast && 'border-b border-border')}>
                      <div className="px-5 py-3 flex items-center gap-2.5 flex-wrap hover:bg-muted/40 transition-colors">
                        <button
                          type="button"
                          onClick={toggleExpanded}
                          className="flex items-center gap-2.5 flex-1 min-w-0 text-left"
                        >
                          <ChevronRight className={cn(
                            'size-3.5 text-muted-foreground flex-shrink-0 transition-transform',
                            expanded && 'rotate-90',
                          )} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap mb-1">
                              <span className="text-sm font-bold text-foreground font-mono">{grupo.key}</span>
                              <span className="text-[11px] text-muted-foreground italic">
                                {primerItem.proveedor || 'Sin proveedor'}
                              </span>
                              <span className="text-[10px] text-muted-foreground bg-muted rounded px-2 py-0.5 border border-border">
                                {items.length} ítems
                              </span>
                            </div>
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-sm text-primary font-bold tabular-nums">{cop(totalGrupo)}</span>
                              {tieneIva && (
                                <span className="text-[10px] text-success font-semibold bg-success/10 border border-success/30 rounded px-2 py-0.5">
                                  IVA
                                </span>
                              )}
                              {todosEnAlmacen ? (
                                <span className="text-[10px] text-success font-semibold bg-success/10 border border-success/30 rounded px-2 py-0.5">
                                  En Almacén
                                </span>
                              ) : enAlmacenCount > 0 ? (
                                <span className="text-[10px] text-primary font-semibold bg-primary-soft border border-primary/30 rounded px-2 py-0.5">
                                  {enAlmacenCount} de {items.length} en almacén
                                </span>
                              ) : null}
                            </div>
                          </div>
                        </button>

                        <div className="flex gap-1.5 flex-shrink-0">
                          <Button
                            variant="outline" size="sm"
                            onClick={() => setEditandoFactura({
                              numero_factura: grupo.key,
                              proveedor: primerItem.proveedor,
                              items,
                            })}
                            title="Editar factura"
                            className="h-7 text-[11px]"
                          >
                            <Pencil className="size-3 mr-1" />
                            {isMobile ? '' : 'Editar factura'}
                          </Button>
                          {todosEnAlmacen ? (
                            <Button
                              variant="outline" size="sm"
                              disabled
                              title="Todo en almacén"
                              className="h-7 text-[11px] border-success/40 text-success"
                            >
                              <Package className="size-3 mr-1" />
                              {isMobile ? '' : 'Todo en Almacén'}
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              onClick={() => setModalEnviarAlmacen({
                                numero_factura: grupo.key,
                                proveedor:      primerItem.proveedor,
                                items,
                              })}
                              title={enAlmacenCount > 0 ? '→ Almacén (parcial)' : '→ Almacén'}
                              className="h-7 text-[11px]"
                            >
                              <Package className="size-3 mr-1" />
                              {isMobile ? '' : (enAlmacenCount > 0 ? '→ Almacén (parcial)' : '→ Almacén')}
                            </Button>
                          )}
                        </div>
                      </div>

                      {expanded && (
                        <div className="border-t border-border">
                          {isMobile ? (
                            <div className="flex flex-col">
                              {items.map(c => {
                                const { iva } = c.incluye_iva && c.tarifa_iva ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                                const enAlmacenFila = !!c.compra_origen_id
                                return (
                                  <div key={c.id} className="px-4 py-2.5 border-t border-border/40 flex flex-col gap-1.5">
                                    <div className="flex justify-between items-start gap-2">
                                      <span className="text-sm font-semibold text-foreground flex-1 leading-snug">{c.producto}</span>
                                      <div className="flex gap-1 flex-shrink-0">
                                        <Button variant="outline" size="icon" onClick={() => setEditando(c)} className="h-7 w-7" title="Editar ítem" aria-label="Editar ítem">
                                          <Pencil className="size-3" aria-hidden="true" />
                                        </Button>
                                        {!enAlmacenFila && (
                                          <Button
                                            variant="outline" size="icon"
                                            onClick={() => !enviandoCompra[c.id] && enviarACompras(c)}
                                            disabled={!!enviandoCompra[c.id]}
                                            title="Agregar a almacén"
                                            aria-label="Agregar a almacén"
                                            className="h-7 w-7"
                                          >
                                            {enviandoCompra[c.id] ? <Loader2 className="size-3 animate-spin" aria-hidden="true" /> : <Package className="size-3" aria-hidden="true" />}
                                          </Button>
                                        )}
                                      </div>
                                    </div>
                                    <div className="flex gap-1.5 flex-wrap items-center">
                                      <span className="text-[11px] text-muted-foreground bg-muted rounded px-2 py-0.5 border border-border">
                                        {num(c.cantidad)} × {cop(c.costo_unitario)}
                                      </span>
                                      <span className="text-xs text-primary font-bold tabular-nums">{cop(c.costo_total)}</span>
                                      {c.incluye_iva && c.tarifa_iva > 0 && (
                                        <span className="text-[11px] text-success font-semibold bg-success/10 border border-success/30 rounded px-2 py-0.5">
                                          IVA {cop(iva)} ({c.tarifa_iva}%)
                                        </span>
                                      )}
                                      {enAlmacenFila && (
                                        <span className="text-[11px] text-success font-semibold bg-success/10 border border-success/30 rounded px-2 py-0.5">
                                          Almacén
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          ) : (
                            <>
                              <div
                                className="grid items-center gap-1 px-5 py-1.5 bg-muted/40 text-[10px] text-muted-foreground font-semibold uppercase tracking-wider"
                                style={{ gridTemplateColumns: '2fr 70px 90px 90px 60px 100px 36px' }}
                              >
                                <span>Producto</span>
                                <span>Cant.</span>
                                <span>Costo unit.</span>
                                <span>Total</span>
                                <span>IVA</span>
                                <span>Almacén</span>
                                <span />
                              </div>
                              {items.map(c => {
                                const { iva } = c.incluye_iva && c.tarifa_iva ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                                const enAlmacenFila = !!c.compra_origen_id
                                const cargandoFila = !!enviandoCompra[c.id]
                                return (
                                  <div
                                    key={c.id}
                                    className="grid items-center gap-1 px-5 py-2 border-t border-border/40 text-xs"
                                    style={{ gridTemplateColumns: '2fr 70px 90px 90px 60px 100px 36px' }}
                                  >
                                    <span className="text-foreground font-medium truncate">{c.producto}</span>
                                    <span className="text-muted-foreground tabular-nums">{num(c.cantidad)}</span>
                                    <span className="text-muted-foreground tabular-nums">{cop(c.costo_unitario)}</span>
                                    <span className="text-primary font-bold tabular-nums">{cop(c.costo_total)}</span>
                                    <span className={cn(c.incluye_iva && c.tarifa_iva ? 'text-success' : 'text-muted-foreground')}>
                                      {c.incluye_iva && c.tarifa_iva ? `${c.tarifa_iva}%` : '—'}
                                    </span>
                                    {enAlmacenFila ? (
                                      <span className="text-success text-[11px] font-semibold inline-flex items-center gap-1">
                                        <Package className="size-3" /> Almacén
                                      </span>
                                    ) : (
                                      <Button
                                        size="sm" variant="outline"
                                        onClick={() => !cargandoFila && enviarACompras(c)}
                                        disabled={cargandoFila}
                                        title="Agregar a almacén"
                                        className="h-6 text-[10px] px-2"
                                      >
                                        {cargandoFila ? <Loader2 className="size-3 animate-spin" /> : <><Package className="size-3 mr-1" />Almacén</>}
                                      </Button>
                                    )}
                                    <Button
                                      variant="outline" size="icon"
                                      onClick={() => setEditando(c)}
                                      title="Editar"
                                      aria-label="Editar factura"
                                      className="h-7 w-7"
                                    >
                                      <Pencil className="size-3" aria-hidden="true" />
                                    </Button>
                                  </div>
                                )
                              })}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  )
                }

                // ── Individual ──
                const c = grupo.items[0]
                const { iva } = c.incluye_iva && c.tarifa_iva ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                const enAlmacenItem = !!c.compra_origen_id
                const cargando = !!enviandoCompra[c.id]
                const tieneNroFact = !!c.numero_factura

                return (
                  <div key={c.id} className={cn('px-5 py-3', !isLast && 'border-b border-border')}>
                    <div className="flex justify-between mb-1.5">
                      <span className="text-[11px] text-muted-foreground">{String(c.fecha || '').slice(0, 10)}</span>
                      <span className="text-[11px] text-muted-foreground italic">{c.proveedor || 'Sin proveedor'}</span>
                    </div>
                    <div className="text-sm font-semibold text-foreground mb-1 leading-snug">{c.producto || '—'}</div>
                    {c.notas_fiscales && (
                      <div className="text-[10px] text-muted-foreground mb-1.5 inline-flex items-center gap-1">
                        <StickyNote className="size-3" />
                        {c.notas_fiscales.length > 60 ? c.notas_fiscales.slice(0,60) + '…' : c.notas_fiscales}
                      </div>
                    )}
                    <div className="flex gap-1.5 flex-wrap items-center mb-2">
                      <span className="text-[11px] text-muted-foreground bg-muted rounded px-2 py-0.5 border border-border">
                        {num(c.cantidad)} uds × {cop(c.costo_unitario)}
                      </span>
                      <span className="text-xs text-primary font-bold tabular-nums">{cop(c.costo_total)}</span>
                      {c.incluye_iva && c.tarifa_iva > 0 && (
                        <span className="text-[11px] text-success font-semibold bg-success/10 border border-success/30 rounded px-2 py-0.5">
                          IVA {cop(iva)} ({c.tarifa_iva}%)
                        </span>
                      )}
                      {tieneNroFact ? (
                        <span className="text-[10px] text-muted-foreground font-mono bg-muted rounded px-2 py-0.5 border border-border">
                          {c.numero_factura}
                        </span>
                      ) : (
                        <span className="text-[10px] text-warning bg-warning/10 border border-warning/30 rounded px-2 py-0.5 inline-flex items-center gap-1">
                          <AlertTriangle className="size-2.5" /> sin nro.
                        </span>
                      )}
                    </div>
                    <div className="flex gap-1.5">
                      <Button
                        variant="outline" size="sm"
                        onClick={() => setEditando(c)}
                        className={cn('h-8 text-xs', isMobile ? 'flex-none' : 'flex-1')}
                      >
                        <Pencil className="size-3 mr-1" />
                        {isMobile ? '' : 'Editar'}
                      </Button>
                      <Button
                        variant="outline" size="sm"
                        onClick={() => !enAlmacenItem && !cargando && enviarACompras(c)}
                        disabled={enAlmacenItem || cargando}
                        className={cn(
                          'flex-1 h-8 text-xs',
                          enAlmacenItem && 'border-success/40 text-success',
                        )}
                      >
                        {cargando
                          ? <Loader2 className="size-3 mr-1 animate-spin" />
                          : <Package className="size-3 mr-1" />}
                        {enAlmacenItem ? 'En Almacén' : '→ Almacén'}
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
