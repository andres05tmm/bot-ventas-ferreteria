/**
 * TabCompras.jsx — Compras a Proveedores (Almacén)
 * - Registro operativo: actualiza inventario + kárdex
 * - Editar por fila / Enviar a Fiscal por fila
 *
 * Migrado a tokens shadcn + sonner (Wave 4 — Fiscal).
 */
import { useState, useRef, useEffect } from 'react'
import { toast } from 'sonner'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import {
  BarChart3, ChevronRight, DollarSign, FileBarChart, Hash, Loader2, Package,
  Pencil, Plus, ShoppingCart, Truck, X,
} from 'lucide-react'
import { useFetch, cop, num, API_BASE } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'
import { Card } from '@/components/ui/card.jsx'
import KpiCard from '@/components/KpiCard.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog.jsx'
import { cn } from '@/lib/utils'

const DIAS_OPTIONS = [
  { label: '7 días',  value: 7  },
  { label: '15 días', value: 15 },
  { label: '30 días', value: 30 },
  { label: '90 días', value: 90 },
]

// Paleta de colores para PieChart (tokens semantic via HSL CSS vars + tonos fijos para diversidad)
const PROV_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
  'hsl(var(--chart-6))',
]
const TARIFAS_IVA = [5, 19]

function calcIVA(total, tarifa) {
  if (!total || !tarifa) return { base: total || 0, iva: 0 }
  const base = Math.round(parseFloat(total) * 100 / (100 + parseFloat(tarifa)))
  const iva  = Math.round(parseFloat(total) - base)
  return { base, iva }
}

function agruparCompras(lista) {
  const map = new Map()
  lista.forEach(c => {
    const fecha = String(c.fecha || '').slice(0, 10)
    const prov  = c.proveedor || 'Sin proveedor'
    const key   = `${prov}__${fecha}`
    if (!map.has(key)) map.set(key, { prov, fecha, items: [] })
    map.get(key).items.push(c)
  })
  return Array.from(map.values()).map(g => ({
    ...g,
    isGroup: g.items.length >= 2 && g.prov !== 'Sin proveedor',
  }))
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

// ── Buscador de productos ─────────────────────────────────────────────────────

function ProductoSearchInput({ value, onChange, placeholder }) {
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

// ── Toggle IVA ────────────────────────────────────────────────────────────────

function IvaToggle({ incluye, tarifa, onIncluyeChange, onTarifaChange }) {
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <button
        type="button"
        onClick={() => onIncluyeChange(!incluye)}
        className={cn(
          'inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md text-[11px] font-semibold border transition-colors',
          incluye
            ? 'bg-success/10 border-success/40 text-success'
            : 'bg-muted border-border text-muted-foreground',
        )}
      >
        <span className={cn(
          'w-7 h-4 rounded-full relative flex-shrink-0 transition-colors',
          incluye ? 'bg-success' : 'bg-border',
        )}>
          <span className={cn(
            'absolute top-0.5 size-3 rounded-full bg-white transition-[left] duration-150',
            incluye ? 'left-[14px]' : 'left-0.5',
          )} />
        </span>
        {incluye ? 'Incluye IVA' : 'Sin IVA'}
      </button>
      {incluye && TARIFAS_IVA.map(tv => (
        <button
          key={tv}
          type="button"
          onClick={() => onTarifaChange(tv)}
          className={cn(
            'px-3.5 py-1.5 rounded-md text-[11px] font-bold border transition-colors',
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

// ── Modal Editar ──────────────────────────────────────────────────────────────

function ModalEditar({ compra, open, onClose, onSaved, authFetch }) {
  const [producto,   setProducto]   = useState(compra?.producto || '')
  const [cantidad,   setCantidad]   = useState(String(compra?.cantidad || ''))
  const [costoUnit,  setCostoUnit]  = useState(String(compra?.costo_unitario || ''))
  const [proveedor,  setProveedor]  = useState(compra?.proveedor === 'Sin proveedor' ? '' : (compra?.proveedor || ''))
  const [incluyeIva, setIncluyeIva] = useState(compra?.incluye_iva || false)
  const [tarifaIva,  setTarifaIva]  = useState(compra?.tarifa_iva || 19)
  const [guardando,  setGuardando]  = useState(false)
  const [err,        setErr]        = useState(null)

  useEffect(() => {
    if (compra) {
      setProducto(compra.producto || '')
      setCantidad(String(compra.cantidad || ''))
      setCostoUnit(String(compra.costo_unitario || ''))
      setProveedor(compra.proveedor === 'Sin proveedor' ? '' : (compra.proveedor || ''))
      setIncluyeIva(compra.incluye_iva || false)
      setTarifaIva(compra.tarifa_iva || 19)
      setErr(null)
    }
  }, [compra])

  if (!compra) return null

  const guardar = async () => {
    if (!producto.trim())              { setErr('El producto es obligatorio'); return }
    if (parseFloat(cantidad) <= 0)     { setErr('Cantidad inválida'); return }
    if (parseFloat(costoUnit) <= 0)    { setErr('Costo inválido'); return }
    setGuardando(true); setErr(null)
    try {
      const r = await authFetch(`${API_BASE}/compras/${compra.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto:       producto.trim(),
          cantidad:       parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor:      proveedor.trim(),
          incluye_iva:    incluyeIva,
          tarifa_iva:     incluyeIva ? tarifaIva : 0,
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
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="inline-flex items-center gap-2">
            <Pencil className="size-4 text-primary" />
            Editar Compra
          </DialogTitle>
        </DialogHeader>

        {err && <ErrorMsg msg={err} />}

        <div className="grid grid-cols-2 gap-2.5">
          <div className="col-span-2 space-y-1">
            <Label htmlFor="ed-prod" className="text-[10px] uppercase tracking-wider text-muted-foreground">Producto *</Label>
            <ProductoSearchInput value={producto} onChange={setProducto} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ed-cant" className="text-[10px] uppercase tracking-wider text-muted-foreground">Cantidad *</Label>
            <Input id="ed-cant" type="number" min="0" step="0.01" value={cantidad} onChange={e => setCantidad(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ed-cost" className="text-[10px] uppercase tracking-wider text-muted-foreground">Costo unitario *</Label>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-xs">$</span>
              <Input id="ed-cost" type="number" min="0" value={costoUnit} onChange={e => setCostoUnit(e.target.value)} className="pl-6" />
            </div>
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="ed-prov" className="text-[10px] uppercase tracking-wider text-muted-foreground">Proveedor</Label>
            <Input id="ed-prov" value={proveedor} onChange={e => setProveedor(e.target.value)} />
          </div>
          <div className="col-span-2 space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">IVA</Label>
            <IvaToggle incluye={incluyeIva} tarifa={tarifaIva} onIncluyeChange={setIncluyeIva} onTarifaChange={setTarifaIva} />
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

export default function TabCompras({ refreshKey }) {
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()
  const [dias, setDias] = useState(30)
  const [localRefresh, setLocalRefresh] = useState(0)
  const vendorParam = selectedVendor ? '&vendor_id=' + selectedVendor : ''
  const { data, loading, error } = useFetch(
    `/compras?dias=${dias}${vendorParam}`,
    [dias, refreshKey, localRefresh, selectedVendor]
  )

  const [formOpen,   setFormOpen]   = useState(false)
  const [producto,   setProducto]   = useState('')
  const [cantidad,   setCantidad]   = useState('')
  const [costoUnit,  setCostoUnit]  = useState('')
  const [proveedor,  setProveedor]  = useState('')
  const [incluyeIva, setIncluyeIva] = useState(true)
  const [tarifaIva,  setTarifaIva]  = useState(19)
  const [guardando,  setGuardando]  = useState(false)

  const [editando, setEditando] = useState(null)
  const [enviandoFiscal, setEnviandoFiscal] = useState({})
  const [expandedGroups, setExpandedGroups] = useState({})

  const totalBruto = cantidad && costoUnit ? parseFloat(cantidad) * parseFloat(costoUnit) : 0
  const { base: baseCalc, iva: ivaCalc } = incluyeIva
    ? calcIVA(totalBruto, tarifaIva)
    : { base: totalBruto, iva: 0 }

  const registrarCompra = async () => {
    if (!producto.trim())                         { toast.error('El producto es obligatorio'); return }
    if (!cantidad || parseFloat(cantidad) <= 0)   { toast.error('La cantidad debe ser mayor a 0'); return }
    if (!costoUnit || parseFloat(costoUnit) <= 0) { toast.error('El costo unitario debe ser mayor a 0'); return }
    setGuardando(true)
    try {
      const r = await authFetch(`${API_BASE}/compras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto:       producto.trim(),
          cantidad:       parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor:      proveedor.trim(),
          incluye_iva:    incluyeIva,
          tarifa_iva:     incluyeIva ? tarifaIva : 0,
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      const ivaMsg = incluyeIva ? ` · IVA ${tarifaIva}%: ${cop(ivaCalc)}` : ''
      toast.success(`${cantidad} ${producto.trim()} — Total: ${cop(totalBruto)}${ivaMsg}`)
      setProducto(''); setCantidad(''); setCostoUnit(''); setProveedor('')
      setIncluyeIva(false); setTarifaIva(19); setFormOpen(false)
      setLocalRefresh(r => r + 1)
    } catch (e) { toast.error(e.message) }
    finally { setGuardando(false) }
  }

  const enviarAFiscal = async (compra) => {
    setEnviandoFiscal(prev => ({ ...prev, [compra.id]: true }))
    try {
      const r = await authFetch(`${API_BASE}/compras/${compra.id}/to-fiscal`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      toast.success(d.ya_existia
        ? 'Esta compra ya estaba en Compras Fiscal'
        : 'Compra enviada a Contabilidad Fiscal')
      setLocalRefresh(r => r + 1)
    } catch (e) { toast.error(e.message) }
    finally { setEnviandoFiscal(prev => ({ ...prev, [compra.id]: false })) }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  const d         = data || {}
  const compras   = d.compras || []
  const porProv   = Object.entries(d.por_proveedor || {}).sort((a, b) => b[1] - a[1])
  const porProd   = Object.entries(d.por_producto  || {}).slice(0, 10)
  const total     = d.total_invertido || 0
  const pieData   = porProv.map(([name, value]) => ({ name, value }))
  const sinDatos  = compras.length === 0
  const agrupados = agruparCompras(compras)

  return (
    <div className="flex flex-col gap-4">
      <ModalEditar
        open={editando != null}
        compra={editando}
        onClose={() => setEditando(null)}
        onSaved={() => {
          setEditando(null)
          toast.success('Compra actualizada')
          setLocalRefresh(r => r + 1)
        }}
        authFetch={authFetch}
      />

      {/* Header */}
      <div className="flex justify-between items-center flex-wrap gap-2.5">
        <div>
          <div className="text-sm font-bold text-foreground inline-flex items-center gap-2">
            <ShoppingCart className="size-4 text-muted-foreground" />
            Compras a Proveedores
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            Historial de mercancía comprada · últimos {dias} días
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
              : <><Plus className="size-3 mr-1" /> Nueva compra</>}
          </Button>
        </div>
      </div>

      {/* Form */}
      {formOpen && (
        <Card className="p-5">
          <SectionTitle icon={Plus}>Registrar Compra</SectionTitle>
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
                <Input
                  type="number" min="0" value={costoUnit}
                  onChange={e => setCostoUnit(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && registrarCompra()}
                  placeholder="0" className="pl-6"
                />
              </div>
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">Proveedor (opcional)</Label>
              <Input value={proveedor} onChange={e => setProveedor(e.target.value)}
                placeholder="Ej: Ferrisariato, Distribuidora Central..." />
            </div>
            <div className="col-span-2 space-y-1">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">IVA en esta compra</Label>
              <IvaToggle incluye={incluyeIva} tarifa={tarifaIva} onIncluyeChange={setIncluyeIva} onTarifaChange={setTarifaIva} />
            </div>
          </div>

          {cantidad && costoUnit && (
            <div className="flex gap-4 flex-wrap px-3.5 py-2.5 rounded-md bg-muted/60 border border-border mb-3 text-xs">
              <span className="text-muted-foreground">
                Total bruto: <strong className="text-primary">{cop(totalBruto)}</strong>
              </span>
              {incluyeIva && (
                <>
                  <span className="text-muted-foreground">
                    Base (sin IVA): <strong className="text-foreground">{cop(baseCalc)}</strong>
                  </span>
                  <span className="text-muted-foreground">
                    IVA {tarifaIva}%: <strong className="text-success">{cop(ivaCalc)}</strong>
                  </span>
                </>
              )}
            </div>
          )}

          {incluyeIva && (
            <div className="px-3.5 py-2 rounded-md mb-3 bg-success/10 border border-success/30 text-[11px] text-success">
              Al enviar esta compra a Compras Fiscal, el IVA ({cop(ivaCalc)}) se registrará como crédito descontable en el Libro IVA.
            </div>
          )}

          <Button onClick={registrarCompra} disabled={guardando}>
            {guardando
              ? <><Loader2 className="size-4 mr-1.5 animate-spin" /> Guardando…</>
              : <><Package className="size-4 mr-1.5" /> Registrar compra</>}
          </Button>
        </Card>
      )}

      {sinDatos ? (
        <Card className="p-8 text-center">
          <Package className="size-8 mx-auto mb-3 text-muted-foreground" />
          <div className="text-foreground font-semibold mb-2">Sin compras registradas</div>
          <div className="text-muted-foreground text-xs max-w-sm mx-auto">
            Las compras también se pueden registrar en Telegram:
          </div>
          <code className="inline-block mt-2.5 bg-muted text-primary border border-border px-3.5 py-1.5 rounded-md text-xs">
            /compra 20 brocha 2" a 2500
          </code>
        </Card>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            <KpiCard label="Total invertido" value={cop(total)}     sub={`Últimos ${dias} días`} icon={DollarSign} tone="primary" topAccent iconStyle="filled" />
            <KpiCard label="Compras"          value={compras.length} sub="Registros"              icon={Package}    tone="muted"   topAccent iconStyle="filled" />
            <KpiCard label="Proveedores"      value={porProv.length} sub="Distintos"              icon={Truck}      tone="muted"   topAccent iconStyle="filled" />
            <KpiCard label="Productos"        value={Object.keys(d.por_producto||{}).length} sub="Artículos" icon={Hash} tone="muted" topAccent iconStyle="filled" />
          </div>

          {/* Por proveedor */}
          <Card className="p-5">
            <SectionTitle icon={Truck}>Por Proveedor</SectionTitle>
            {porProv.length === 0 ? (
              <div className="text-xs text-muted-foreground py-4">Sin datos para este período.</div>
            ) : (
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
                      formatter={v => [cop(v)]} />
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
            {porProd.length === 0 ? (
              <div className="text-xs text-muted-foreground py-4">Sin datos para este período.</div>
            ) : (
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
            <div className="px-5 py-3.5 border-b border-border flex justify-between items-center flex-wrap gap-2">
              <SectionTitle icon={FileBarChart}>Detalle de Compras</SectionTitle>
              <span className="text-[11px] text-muted-foreground">
                {agrupados.length} entradas · {compras.length} ítems
              </span>
            </div>

            <div className="flex justify-between items-center px-5 py-2.5 bg-muted/40 border-b border-border">
              <span className="text-[11px] text-muted-foreground font-semibold uppercase tracking-wider">Total Invertido</span>
              <span className="text-sm text-primary font-bold tabular-nums">{cop(total)}</span>
            </div>

            <div className="flex flex-col">
              {agrupados.map((grupo, gi) => {
                const isLast = gi === agrupados.length - 1

                // ── Grupo / acordeón ──
                if (grupo.isGroup) {
                  const key         = `${grupo.prov}__${grupo.fecha}`
                  const expanded    = !!expandedGroups[key]
                  const items       = grupo.items
                  const totalGrupo  = items.reduce((s, x) => s + (x.costo_total || 0), 0)
                  const tieneIva    = items.some(x => x.incluye_iva && x.tarifa_iva > 0)
                  const yaEnFiscal  = items.filter(x => !!x.compra_fiscal_id).length
                  const todosEnFisc = yaEnFiscal === items.length
                  const toggle      = () => setExpandedGroups(prev => ({ ...prev, [key]: !prev[key] }))

                  return (
                    <div key={key} className={cn(!isLast && 'border-b border-border')}>
                      <button
                        type="button"
                        className="w-full text-left px-5 py-3 flex items-center gap-2.5 flex-wrap hover:bg-muted/40 transition-colors"
                        onClick={toggle}
                      >
                        <ChevronRight className={cn(
                          'size-3.5 text-muted-foreground flex-shrink-0 transition-transform',
                          expanded && 'rotate-90',
                        )} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <span className="text-sm font-bold text-foreground">{grupo.prov}</span>
                            <span className="text-[11px] text-muted-foreground">{grupo.fecha}</span>
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
                            {todosEnFisc ? (
                              <span className="text-[10px] text-success font-semibold bg-success/10 border border-success/30 rounded px-2 py-0.5">
                                Todo en Fiscal
                              </span>
                            ) : yaEnFiscal > 0 ? (
                              <span className="text-[10px] text-primary font-semibold bg-primary-soft border border-primary/30 rounded px-2 py-0.5">
                                {yaEnFiscal} de {items.length} en fiscal
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </button>

                      {expanded && (
                        <div className="border-t border-border">
                          <div className="grid items-center gap-1 px-5 py-1.5 bg-muted/40 text-[10px] text-muted-foreground font-semibold uppercase tracking-wider"
                            style={{ gridTemplateColumns: '2fr 70px 90px 90px 60px 80px' }}
                          >
                            <span>Producto</span>
                            <span>Cant.</span>
                            <span>Costo unit.</span>
                            <span>Total</span>
                            <span>Fiscal</span>
                            <span />
                          </div>
                          {items.map(c => {
                            const yaEnFiscalFila = !!c.compra_fiscal_id
                            const cargando = !!enviandoFiscal[c.id]
                            return (
                              <div
                                key={c.id}
                                className="grid items-center gap-1 px-5 py-2 border-t border-border/40 text-xs"
                                style={{ gridTemplateColumns: '2fr 70px 90px 90px 60px 80px' }}
                              >
                                <span className="text-foreground font-medium truncate">{c.producto}</span>
                                <span className="text-muted-foreground tabular-nums">{num(c.cantidad)}</span>
                                <span className="text-muted-foreground tabular-nums">{cop(c.costo_unitario)}</span>
                                <span className="text-primary font-bold tabular-nums">{cop(c.costo_total)}</span>
                                <span className={cn(yaEnFiscalFila ? 'text-success' : 'text-muted-foreground')}>
                                  {yaEnFiscalFila ? '✓' : '—'}
                                </span>
                                <div className="flex gap-1">
                                  <Button
                                    variant="outline"
                                    size="icon"
                                    onClick={() => setEditando(c)}
                                    className="h-7 w-7"
                                    title="Editar"
                                    aria-label="Editar compra"
                                  >
                                    <Pencil className="size-3" aria-hidden="true" />
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="icon"
                                    onClick={() => !yaEnFiscalFila && !cargando && enviarAFiscal(c)}
                                    disabled={yaEnFiscalFila || cargando}
                                    title={yaEnFiscalFila ? 'Ya en Fiscal' : 'Enviar a Fiscal'}
                                    aria-label={yaEnFiscalFila ? 'Ya en Fiscal' : 'Enviar a Fiscal'}
                                    className={cn(
                                      'h-7 w-7',
                                      yaEnFiscalFila && 'border-success/40 text-success',
                                    )}
                                  >
                                    {cargando ? <Loader2 className="size-3 animate-spin" /> : <FileBarChart className="size-3" />}
                                  </Button>
                                </div>
                              </div>
                            )
                          })}
                          <div className="flex justify-end px-5 py-2 bg-muted/40 border-t border-border text-xs">
                            <span className="text-primary font-bold tabular-nums">Total pedido: {cop(totalGrupo)}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                }

                // ── Individual ──
                const c = grupo.items[0]
                const { iva } = c.incluye_iva && c.tarifa_iva ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                const yaEnFiscal = !!c.compra_fiscal_id
                const cargando = !!enviandoFiscal[c.id]

                return (
                  <div key={c.id} className={cn('px-5 py-3', !isLast && 'border-b border-border')}>
                    <div className="flex justify-between mb-1.5">
                      <span className="text-[11px] text-muted-foreground">{String(c.fecha || '').slice(0, 10)}</span>
                      <span className="text-[11px] text-muted-foreground italic">{c.proveedor || 'Sin proveedor'}</span>
                    </div>
                    <div className="text-sm font-semibold text-foreground mb-2 leading-snug">
                      {c.producto || '—'}
                    </div>
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
                    </div>
                    <div className="flex gap-1.5">
                      <Button
                        variant="outline" size="sm"
                        onClick={() => setEditando(c)}
                        className="flex-1 h-8 text-xs"
                      >
                        <Pencil className="size-3 mr-1" /> Editar
                      </Button>
                      <Button
                        variant="outline" size="sm"
                        onClick={() => !yaEnFiscal && !cargando && enviarAFiscal(c)}
                        disabled={yaEnFiscal || cargando}
                        className={cn(
                          'flex-1 h-8 text-xs',
                          yaEnFiscal && 'border-success/40 text-success',
                        )}
                      >
                        {cargando
                          ? <Loader2 className="size-3 mr-1 animate-spin" />
                          : <FileBarChart className="size-3 mr-1" />}
                        {yaEnFiscal ? 'En Fiscal' : '→ Fiscal'}
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

