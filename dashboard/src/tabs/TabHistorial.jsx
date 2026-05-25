/*
 * TabHistorial — ventas del día con edición y eliminación.
 * Wave 2: migrado a primitives shadcn + tokens.
 * Nota: la fusión con TabHistoricoVentas (calendario mensual) se difiere a
 * Wave 3 — por ahora ambas tabs conviven (/historial y /historico). El cmd+K
 * solo apunta a /historial.
 */
import { useState, useMemo } from 'react'
import { useFetch, cop, API_BASE, useIsMobile } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog.jsx'
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from '@/components/ui/dropdown-menu.jsx'
import {
  Search, Download, Pencil, Trash2, Loader2, X, AlertCircle, ChevronDown,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const FRACS = [
  [3/4,'3/4'],[1/2,'1/2'],[1/4,'1/4'],[1/3,'1/3'],[2/3,'2/3'],
  [1/8,'1/8'],[1/10,'1/10'],[1/16,'1/16'],[3/8,'3/8'],[7/8,'7/8'],
]
const UNIDADES_DECIMAL = ['grm','gramos','kg','cms','mts','lt','lts','25 kg','mlt']
const METODOS = ['efectivo','transferencia','nequi','daviplata','datafono','otro']

function cantidadLegible(val, unidad) {
  if (val === null || val === undefined || val === '') return '—'
  const s = String(val).trim()
  const u = (unidad || '').toLowerCase().replace('ó','o')
  if (UNIDADES_DECIMAL.includes(u)) {
    let n = parseFloat(s.replace(',','.'))
    if (isNaN(n)) {
      const mx = s.match(/^(\d+)\s*y\s*(\d+)\/(\d+)$/)
      if (mx) n = parseFloat(mx[1]) + parseFloat(mx[2])/parseFloat(mx[3])
      const sm = s.match(/^(\d+)\/(\d+)$/)
      if (sm) n = parseFloat(sm[1])/parseFloat(sm[2])
    }
    if (!isNaN(n)) return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '')
    return s
  }
  if (/[\/y]/.test(s) && !/^\d+$/.test(s)) return s
  const n = parseFloat(s.replace(',','.'))
  if (isNaN(n)) return s
  if (Number.isInteger(n)) return String(n)
  const entero = Math.floor(n), frac = n - entero
  for (const [dec, label] of FRACS) {
    if (Math.abs(frac - dec) < 0.005) return entero > 0 ? `${entero} ${label}` : label
  }
  return n.toFixed(2).replace(/\.?0+$/, '')
}

function metodoTone(m) {
  const r = (m || '').toLowerCase()
  if (r.includes('efect'))  return 'bg-success/10 text-success border-success/30'
  if (r.includes('transf')) return 'bg-warning/10 text-warning border-warning/30'
  if (r.includes('nequi') || r.includes('davi')) return 'bg-info/10 text-info border-info/30'
  if (r.includes('tarjet') || r.includes('datafono')) return 'bg-info/10 text-info border-info/30'
  return 'bg-surface-2 text-muted-foreground border-border'
}

// ─────────────────────────────────────────────────────────────────────────────

function ModalEditarVenta({ venta, onClose, onGuardado }) {
  const { authFetch } = useAuth()
  const [form, setForm] = useState({
    producto:        venta.producto || '',
    cantidad:        venta.cantidad || '',
    precio_unitario: venta.precio_unitario || '',
    total:           venta.total || '',
    metodo_pago:     venta.metodo || 'efectivo',
    cliente:         venta.cliente || '',
    vendedor:        venta.vendedor || '',
  })
  const [estado, setEstado] = useState('idle')
  const [err, setErr] = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function guardar() {
    setEstado('saving'); setErr('')
    try {
      const body = {}
      if (form.producto !== venta.producto) body.producto = form.producto
      if (String(form.cantidad) !== String(venta.cantidad)) body.cantidad = Number(form.cantidad)
      if (String(form.precio_unitario) !== String(venta.precio_unitario)) body.precio_unitario = Number(form.precio_unitario)
      if (String(form.total) !== String(venta.total)) body.total = Number(form.total)
      if (form.metodo_pago !== venta.metodo) body.metodo_pago = form.metodo_pago
      if (form.cliente !== venta.cliente) body.cliente = form.cliente
      if (form.vendedor !== venta.vendedor) body.vendedor = form.vendedor
      if (!Object.keys(body).length) { onClose(); return }
      body.producto_original = venta.producto
      const r = await authFetch(`${API_BASE}/ventas/${venta.num}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('ok')
      setTimeout(() => { onGuardado(); onClose() }, 600)
    } catch (e) { setErr(e.message); setEstado('err') }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Editar venta #{venta.num}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Producto</Label>
            <Input value={form.producto} onChange={e => set('producto', e.target.value)} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Cantidad</Label>
              <Input type="number" value={form.cantidad} onChange={e => set('cantidad', e.target.value)} />
            </div>
            <div>
              <Label>V. Unitario</Label>
              <Input type="number" value={form.precio_unitario} onChange={e => set('precio_unitario', e.target.value)} />
            </div>
            <div>
              <Label>Total</Label>
              <Input type="number" value={form.total} onChange={e => set('total', e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Método</Label>
              <select
                value={form.metodo_pago}
                onChange={e => set('metodo_pago', e.target.value)}
                className="w-full h-9 px-3 rounded-md border border-input bg-transparent text-sm"
              >
                {METODOS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <Label>Vendedor</Label>
              <Input value={form.vendedor} onChange={e => set('vendedor', e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Cliente</Label>
            <Input value={form.cliente} onChange={e => set('cliente', e.target.value)} placeholder="Consumidor Final" />
          </div>
          {err && (
            <div className="flex items-center gap-2 p-2 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-xs">
              <AlertCircle className="size-3.5" /> {err}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={guardar} disabled={estado === 'saving'}>
            {estado === 'saving' ? 'Guardando…' : estado === 'ok' ? '✓ Guardado' : 'Guardar cambios'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ModalEliminar({ grupo, onClose, onEliminado }) {
  const { authFetch } = useAuth()
  const [estado, setEstado] = useState('idle')
  const [err, setErr] = useState('')
  const [borrando, setBorrando] = useState(null)

  const consecutivo = grupo[0]?.num
  const totalGrupo = grupo.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const esMultiple = grupo.length > 1

  async function eliminarTodo() {
    setEstado('saving'); setBorrando('todo')
    try {
      const r = await authFetch(`${API_BASE}/ventas/${consecutivo}`, { method: 'DELETE' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('ok')
      setTimeout(() => { onEliminado(); onClose() }, 500)
    } catch (e) { setErr(e.message); setEstado('err'); setBorrando(null) }
  }

  async function eliminarLinea(v, idx) {
    setEstado('saving'); setBorrando(idx)
    try {
      const r = await authFetch(
        `${API_BASE}/ventas/${consecutivo}/linea?producto=${encodeURIComponent(v.producto)}`,
        { method: 'DELETE' }
      )
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('ok')
      setTimeout(() => { onEliminado(); onClose() }, 500)
    } catch (e) { setErr(e.message); setEstado('err'); setBorrando(null) }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Eliminar {esMultiple ? `consecutivo #${consecutivo}` : `venta #${consecutivo}`}</DialogTitle>
        </DialogHeader>

        <div className="border border-border rounded-md overflow-hidden">
          {grupo.map((v, i) => (
            <div
              key={i}
              className={cn('flex items-center justify-between px-3 py-2 text-sm', i < grupo.length - 1 && 'border-b border-border-subtle')}
            >
              <div className="flex-1 min-w-0">
                <span>{v.producto}</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  ×{cantidadLegible(v.cantidad, v.unidad_medida)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-success font-semibold tabular">{cop(v.total)}</span>
                {esMultiple && (
                  <button
                    onClick={() => eliminarLinea(v, i)}
                    disabled={estado === 'saving'}
                    title={`Eliminar solo "${v.producto}"`}
                    className="size-7 rounded-md border border-destructive/30 bg-destructive/5 text-destructive grid place-items-center hover:bg-destructive/10 disabled:opacity-50"
                  >
                    {estado === 'saving' && borrando === i ? <Loader2 className="size-3 animate-spin" /> : <X className="size-3" />}
                  </button>
                )}
              </div>
            </div>
          ))}
          <div className="flex items-center justify-between px-3 py-2 bg-surface-2/50 border-t border-border">
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              Total {esMultiple ? `(${grupo.length} productos)` : ''}
            </span>
            <span className="text-primary font-bold tabular">{cop(totalGrupo)}</span>
          </div>
        </div>

        <div className="flex items-start gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-xs">
          <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
          <span>Se elimina del Excel/Google Sheets y se descuenta de la caja.</span>
        </div>

        {err && (
          <div className="text-xs text-destructive">{err}</div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button variant="destructive" onClick={eliminarTodo} disabled={estado === 'saving'}>
            {estado === 'saving' && borrando === 'todo' ? 'Eliminando…' :
             estado === 'ok' ? '✓ Eliminado' :
             esMultiple ? 'Eliminar todo' : 'Sí, eliminar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

function ExportButton() {
  const { authFetch } = useAuth()
  const [descargando, setDescargando] = useState(null)

  async function descargar(periodo) {
    setDescargando(periodo)
    try {
      const r = await authFetch(`${API_BASE}/export/ventas.xlsx?periodo=${periodo}`)
      if (!r.ok) throw new Error(`Error ${r.status}`)
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ventas_${periodo}.xlsx`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error(e)
    } finally { setDescargando(null) }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={descargando !== null}>
          {descargando ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
          {descargando ? 'Descargando…' : 'Exportar'}
          <ChevronDown className="size-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => descargar('hoy')}>Hoy</DropdownMenuItem>
        <DropdownMenuItem onClick={() => descargar('semana')}>Esta semana</DropdownMenuItem>
        <DropdownMenuItem onClick={() => descargar('mes')}>Este mes</DropdownMenuItem>
        <DropdownMenuItem onClick={() => descargar('todo')}>Todo</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function FiltroBtn({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-3 py-1 text-xs rounded transition-colors',
        active ? 'bg-surface text-foreground shadow-xs font-medium' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

export default function TabHistorial({ refreshKey }) {
  const isMobile = useIsMobile()
  const [refresh, setRefresh] = useState(0)
  const { data, loading, error } = useFetch('/ventas/hoy', [refreshKey, refresh])
  const [busqueda, setBusqueda] = useState('')
  const [filtro, setFiltro]   = useState('todos')
  const [editando, setEditando]     = useState(null)
  const [eliminando, setEliminando] = useState(null)

  const todasVentas = useMemo(() => (data?.ventas || []).map(v => ({
    ...v,
    estado: (v.metodo && v.metodo.trim() && v.metodo !== '—') ? 'pagado' : 'pendiente',
  })), [data])

  const gruposPorConsecutivo = useMemo(() => {
    const mapa = {}
    for (const v of todasVentas) {
      const k = String(v.num)
      if (!mapa[k]) mapa[k] = []
      mapa[k].push(v)
    }
    return mapa
  }, [todasVentas])

  const ventas = useMemo(() => {
    let res = filtro === 'todos' ? todasVentas : todasVentas.filter(v => v.estado === filtro)
    if (busqueda) {
      const q = busqueda.toLowerCase()
      res = res.filter(v =>
        String(v.producto).toLowerCase().includes(q) ||
        String(v.cliente).toLowerCase().includes(q) ||
        String(v.vendedor).toLowerCase().includes(q) ||
        String(v.num).includes(q)
      )
    }
    return res
  }, [todasVentas, filtro, busqueda])

  const total = ventas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const totalTodo = todasVentas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const pagados = todasVentas.filter(v => v.estado === 'pagado').length
  const pendientes = todasVentas.filter(v => v.estado === 'pendiente').length

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-muted-foreground">
        <Loader2 className="size-5 animate-spin mr-2" /> Cargando…
      </div>
    )
  }
  if (error) {
    return (
      <Card className="p-4 border-destructive/40 bg-destructive/5 text-destructive text-sm">
        Error: {error}
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {editando && (
        <ModalEditarVenta venta={editando} onClose={() => setEditando(null)} onGuardado={() => setRefresh(r => r + 1)} />
      )}
      {eliminando && (
        <ModalEliminar grupo={eliminando} onClose={() => setEliminando(null)} onEliminado={() => setRefresh(r => r + 1)} />
      )}

      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Historial de ventas</h1>
          <p className="text-xs text-muted-foreground mt-0.5 capitalize">
            {new Date().toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'America/Bogota' })}
          </p>
        </div>
        <ExportButton />
      </header>

      {/* KPIs */}
      <div className={cn('grid gap-3', isMobile ? 'grid-cols-2' : 'grid-cols-4')}>
        <KpiSmall label="Total hoy"   value={cop(totalTodo)} tone="accent" />
        <KpiSmall label="Registros"   value={todasVentas.length} />
        <KpiSmall label="Pagados"     value={pagados}    tone="success" />
        <KpiSmall label="Sin método"  value={pendientes} tone="warning" />
      </div>

      {/* Filtros */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="inline-flex bg-surface-2 p-1 rounded-md">
          <FiltroBtn active={filtro === 'todos'}     onClick={() => setFiltro('todos')}>Todos</FiltroBtn>
          <FiltroBtn active={filtro === 'pagado'}    onClick={() => setFiltro('pagado')}>Pagados</FiltroBtn>
          <FiltroBtn active={filtro === 'pendiente'} onClick={() => setFiltro('pendiente')}>Pendientes</FiltroBtn>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={busqueda} onChange={e => setBusqueda(e.target.value)} placeholder="Buscar..." className="pl-9" />
        </div>
      </div>

      {/* Tabla */}
      <Card className="overflow-hidden">
        {ventas.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted-foreground">
            {busqueda ? 'Sin resultados.' : 'No hay ventas registradas hoy.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-2/50">
                  {['#','Hora','Producto','Cliente','Cant.','V. Unit.','Total','Vendedor','Método','Estado',''].map((h, i) => (
                    <th key={i} className={cn(
                      'px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold whitespace-nowrap',
                      [4,8,9,10].includes(i) ? 'text-center' : [5,6].includes(i) ? 'text-right' : 'text-left',
                    )}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ventas.map((v, i) => {
                  const grupo = gruposPorConsecutivo[String(v.num)] || [v]
                  const esMultiple = grupo.length > 1
                  return (
                    <tr key={i} className={cn(
                      'border-b border-border-subtle hover:bg-surface-2/40',
                      esMultiple && 'bg-warning/5',
                    )}>
                      <td className="px-3 py-2 text-primary font-semibold tabular whitespace-nowrap">
                        {v.num}
                        {esMultiple && (
                          <span className="ml-1.5 inline-block bg-warning text-warning-foreground text-[9px] font-bold px-1 rounded">
                            ×{grupo.length}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground tabular whitespace-nowrap">{v.hora}</td>
                      <td className="px-3 py-2 max-w-44 truncate">{v.producto}</td>
                      <td className="px-3 py-2 text-muted-foreground text-xs">{v.cliente || 'Consumidor Final'}</td>
                      <td className="px-3 py-2 text-center tabular text-muted-foreground">
                        {cantidadLegible(v.cantidad, v.unidad_medida)}
                        {v.unidad_medida && v.unidad_medida.toLowerCase() !== 'unidad' && (
                          <span className="ml-1 text-[9px] text-muted-foreground">{v.unidad_medida}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right tabular text-muted-foreground">
                        {v.precio_unitario ? cop(v.precio_unitario) : '—'}
                      </td>
                      <td className="px-3 py-2 text-right tabular text-success font-semibold">{cop(v.total)}</td>
                      <td className="px-3 py-2 text-muted-foreground text-xs">{v.vendedor || '—'}</td>
                      <td className="px-3 py-2 text-center">
                        <span className={cn('inline-block px-2 py-0.5 rounded-full text-[10px] font-medium border whitespace-nowrap',
                          metodoTone(v.metodo))}>
                          {v.metodo || '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className={cn(
                          'inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold border',
                          v.estado === 'pagado'
                            ? 'bg-success/10 text-success border-success/30'
                            : 'bg-warning/10 text-warning border-warning/30',
                        )}>
                          {v.estado}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex gap-1 justify-center">
                          <button onClick={() => setEditando(v)} className="size-7 rounded-md hover:bg-surface-2 text-primary grid place-items-center" title="Editar">
                            <Pencil className="size-3.5" />
                          </button>
                          <button onClick={() => setEliminando(grupo)} className="size-7 rounded-md hover:bg-destructive/10 text-destructive grid place-items-center" title="Eliminar">
                            <Trash2 className="size-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-border bg-surface-2/30">
                  <td colSpan={6} className="px-3 py-2 text-right text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                    Subtotal ({ventas.length} registros)
                  </td>
                  <td className="px-3 py-2 text-right text-primary font-bold tabular text-base">{cop(total)}</td>
                  <td colSpan={4} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

function KpiSmall({ label, value, tone = 'foreground' }) {
  return (
    <Card className="p-3">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">{label}</div>
      <div className={cn('text-lg font-semibold tabular leading-none',
        tone === 'success' && 'text-success',
        tone === 'warning' && 'text-warning',
        tone === 'accent'  && 'text-primary',
      )}>
        {value}
      </div>
    </Card>
  )
}
