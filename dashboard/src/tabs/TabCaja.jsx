/*
 * TabCaja — apertura/cierre, KPIs, venta varia, desglose por método, gastos del día.
 * Wave 3.a: migrado a primitives shadcn + tokens semantic.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFetch, API_BASE } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useIsMobile } from '../components/shared.jsx'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog.jsx'
import { toast } from 'sonner'
import {
  Lock, Unlock, Wallet, TrendingUp, TrendingDown, Calculator,
  Plus, X, Banknote, Smartphone, CreditCard, Receipt, AlertCircle, Loader2,
} from 'lucide-react'
import KpiCard from '@/components/KpiCard.jsx'
import { cn } from '@/lib/utils'

const cop = v => v == null || isNaN(v) ? '$0' : '$' + Math.round(v).toLocaleString('es-CO')

function MetodoRow({ label, valor, icon: Icon }) {
  if (!valor) return null
  return (
    <div className="flex justify-between items-center py-2.5 border-b border-border-subtle last:border-0">
      <div className="flex items-center gap-2.5">
        <Icon className="size-4 text-muted-foreground" />
        <span className="text-sm text-secondary-foreground">{label}</span>
      </div>
      <span className="text-sm font-semibold tabular">{cop(valor)}</span>
    </div>
  )
}

// ─── Dialog cerrar caja ───────────────────────────────────────────────────────
function ModalCerrarCaja({ open, onClose, onConfirm, cerrando }) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Cerrar caja del día</DialogTitle>
        </DialogHeader>
        <div className="flex items-start gap-2 p-3 rounded-md bg-warning/10 border border-warning/30 text-warning text-xs">
          <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
          <span>El cierre consolida ventas, efectivo y gastos del día. Esta acción no se puede deshacer.</span>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={cerrando}>
            {cerrando ? <><Loader2 className="size-3.5 mr-1.5 animate-spin" /> Cerrando…</> : <><Lock className="size-3.5 mr-1.5" /> Sí, cerrar caja</>}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Dialog venta varia ───────────────────────────────────────────────────────
const METODOS = [
  { val: 'efectivo',      label: 'Efectivo',      icon: Banknote,   classes: 'border-success bg-success/10 text-success' },
  { val: 'transferencia', label: 'Transferencia', icon: Smartphone, classes: 'border-primary bg-primary/10 text-primary' },
  { val: 'datafono',      label: 'Datáfono',      icon: CreditCard, classes: 'border-warning bg-warning/10 text-warning' },
]

function ModalVentaVaria({ open, onClose, onSaved, authFetch }) {
  const [monto,  setMonto]  = useState('')
  const [metodo, setMetodo] = useState('efectivo')
  const [desc,   setDesc]   = useState('')
  const [enviando, setEnviando] = useState(false)

  const reset = () => { setMonto(''); setDesc(''); setMetodo('efectivo'); setEnviando(false) }
  const cerrar = () => { reset(); onClose() }

  const registrar = async () => {
    const m = parseFloat(String(monto).replace(/[^0-9.]/g, ''))
    if (!m || m <= 0) { toast.error('Ingresa un monto válido'); return }
    setEnviando(true)
    try {
      const r = await authFetch(`${API_BASE}/ventas/varia`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          monto: m, metodo_pago: metodo,
          descripcion: desc.trim() || 'Venta Varia',
          vendedor: 'Dashboard',
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      toast.success(`Venta varia de ${cop(m)} registrada (${metodo})`)
      onSaved()
      cerrar()
    } catch (e) { toast.error(e.message); setEnviando(false) }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && cerrar()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Registrar venta varia</DialogTitle>
          <p className="text-xs text-muted-foreground">Para cuadrar ventas que no se alcanzaron a anotar</p>
        </DialogHeader>
        <div className="space-y-3.5">
          <div>
            <Label>Monto *</Label>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
              <Input autoFocus type="number" min="0" className="pl-6 font-mono" value={monto}
                onChange={e => setMonto(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && registrar()}
                placeholder="0" />
            </div>
          </div>
          <div>
            <Label>Descripción (opcional)</Label>
            <Input value={desc} onChange={e => setDesc(e.target.value)}
              placeholder="Ej: Sobrante cierre, ventas no anotadas…" />
          </div>
          <div>
            <Label>Método de pago</Label>
            <div className="flex gap-2 mt-1">
              {METODOS.map(op => {
                const active = metodo === op.val
                const Icon = op.icon
                return (
                  <button key={op.val} onClick={() => setMetodo(op.val)}
                    className={cn(
                      'flex-1 h-10 rounded-md text-xs font-semibold border-2 transition-colors flex items-center justify-center gap-1.5',
                      active ? op.classes : 'border-border text-muted-foreground hover:border-primary/40',
                    )}>
                    <Icon className="size-3.5" /> {op.label}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={cerrar}>Cancelar</Button>
          <Button onClick={registrar} disabled={enviando || !monto}>
            {enviando ? <><Loader2 className="size-3.5 mr-1.5 animate-spin" /> Registrando…</> : 'Registrar venta varia'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Tab principal ────────────────────────────────────────────────────────────
export default function TabCaja({ refreshKey }) {
  const navigate = useNavigate()
  const isMobile = useIsMobile()
  const { authFetch } = useAuth()
  const [localRefresh, setLocalRefresh] = useState(0)
  const { data, loading, error } = useFetch('/caja', [refreshKey, localRefresh])

  const [montoApertura, setMontoApertura] = useState('')
  const [abriendo, setAbriendo] = useState(false)
  const [cerrando, setCerrando] = useState(false)
  const [confirmCerrar, setConfirmCerrar] = useState(false)
  const [variaOpen, setVariaOpen] = useState(false)

  const bump = () => setLocalRefresh(r => r + 1)

  const abrirCaja = async () => {
    setAbriendo(true)
    try {
      const r = await authFetch(`${API_BASE}/caja/abrir`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monto_apertura: parseInt(montoApertura) || 0 }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      toast.success(d.mensaje || 'Caja abierta')
      setMontoApertura(''); bump()
    } catch (e) { toast.error(e.message) }
    finally { setAbriendo(false) }
  }

  const cerrarCaja = async () => {
    setCerrando(true)
    try {
      const r = await authFetch(`${API_BASE}/caja/cerrar`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      toast.success('Caja cerrada')
      setConfirmCerrar(false); bump()
    } catch (e) { toast.error(e.message) }
    finally { setCerrando(false) }
  }

  if (loading) return (
    <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
      <Loader2 className="size-6 animate-spin text-primary" />
      <span className="text-xs">Cargando…</span>
    </div>
  )
  if (error) return (
    <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-sm">
      <AlertCircle className="size-4 shrink-0" /> Error cargando caja: {error}
    </div>
  )

  const d = data || {}
  const abierta = d.abierta
  const gastos  = d.gastos || []

  return (
    <div className="flex flex-col gap-4">
      <ModalCerrarCaja open={confirmCerrar} onClose={() => setConfirmCerrar(false)} onConfirm={cerrarCaja} cerrando={cerrando} />
      <ModalVentaVaria open={variaOpen} onClose={() => setVariaOpen(false)} onSaved={bump} authFetch={authFetch} />

      {/* KPIs — primero, para glance inmediato */}
      <div className={cn('grid gap-3', isMobile ? 'grid-cols-2' : 'grid-cols-4')}>
        <KpiCard headerBand tone="muted"   label="Apertura"          value={cop(d.monto_apertura)}    sub="Base inicial"                  icon={Wallet} />
        <KpiCard headerBand tone="success" label="Ventas hoy"        value={cop(d.total_ventas)}      sub="Efectivo + transf. + datáfono" icon={TrendingUp} />
        <KpiCard headerBand tone="danger"  label="Gastos"            value={cop(d.total_gastos)}      sub="Todos los egresos"             icon={TrendingDown}
          onClick={() => navigate('/gastos')} actionLabel="Ver gastos" />
        <KpiCard headerBand tone="primary" label="Efectivo esperado" value={cop(d.efectivo_esperado)} sub="Caja − gastos en efectivo"     icon={Calculator} />
      </div>

      {/* Estado + Acciones — debajo, acción del día */}
      <Card className="p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className={cn(
              'size-10 rounded-full grid place-items-center',
              abierta ? 'bg-success/15 text-success' : 'bg-surface-2 text-muted-foreground',
            )}>
              {abierta ? <Unlock className="size-5" /> : <Lock className="size-5" />}
            </div>
            <div>
              <div className={cn('font-semibold text-sm', abierta ? 'text-success' : 'text-muted-foreground')}>
                Caja {abierta ? 'abierta' : 'cerrada'}
              </div>
              {d.fecha && <div className="text-[11px] text-muted-foreground mt-0.5">{d.fecha}</div>}
            </div>
          </div>

          {abierta && (
            <Button variant="outline" onClick={() => setConfirmCerrar(true)} className="border-destructive/40 text-destructive hover:bg-destructive/10">
              <Lock className="size-3.5 mr-1.5" /> Cerrar caja
            </Button>
          )}
        </div>

        {!abierta && (
          <div className="mt-4 pt-4 border-t border-border-subtle flex items-center gap-2 flex-wrap">
            <span className="text-xs text-secondary-foreground">Monto apertura:</span>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
              <Input type="number" min="0" value={montoApertura}
                onChange={e => setMontoApertura(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && abrirCaja()}
                placeholder="0"
                className="pl-6 w-32 font-mono" />
            </div>
            <Button onClick={abrirCaja} disabled={abriendo} className="bg-success hover:bg-success/90">
              {abriendo ? <><Loader2 className="size-3.5 mr-1.5 animate-spin" /> Abriendo…</> : <><Unlock className="size-3.5 mr-1.5" /> Abrir caja</>}
            </Button>
          </div>
        )}
      </Card>

      {/* Venta Varia (botón abre dialog) */}
      <Card className="p-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="size-9 rounded-md bg-primary-soft text-primary grid place-items-center">
              <Receipt className="size-4" />
            </div>
            <div>
              <div className="font-semibold text-sm">Venta Varia</div>
              <div className="text-[11px] text-muted-foreground mt-0.5">Para cuadrar ventas que no se alcanzaron a anotar</div>
            </div>
          </div>
          <Button onClick={() => setVariaOpen(true)}>
            <Plus className="size-3.5 mr-1.5" /> Registrar
          </Button>
        </div>
      </Card>

      {/* Desglose por método */}
      <div className={cn('grid gap-3', isMobile ? 'grid-cols-1' : 'grid-cols-2')}>
        <Card className="p-4">
          <CardHeader className="p-0 mb-3">
            <CardTitle className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Ingresos por método</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <MetodoRow label="Efectivo"      valor={d.efectivo}       icon={Banknote} />
            <MetodoRow label="Transferencia" valor={d.transferencias} icon={Smartphone} />
            <MetodoRow label="Datáfono"      valor={d.datafono}       icon={CreditCard} />
            {!d.efectivo && !d.transferencias && !d.datafono && (
              <div className="text-xs text-muted-foreground py-3">Sin ventas registradas hoy.</div>
            )}
            <div className="flex justify-between pt-3 mt-1">
              <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Total</span>
              <span className="text-lg font-bold text-success tabular">{cop(d.total_ventas)}</span>
            </div>
          </CardContent>
        </Card>

        <Card className="p-4">
          <CardHeader className="p-0 mb-3">
            <CardTitle className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Resumen efectivo</CardTitle>
          </CardHeader>
          <CardContent className="p-0 flex flex-col gap-2">
            {[
              { label: 'Apertura',           valor: d.monto_apertura,    color: 'text-secondary-foreground' },
              { label: '+ Ventas efectivo',  valor: d.efectivo,          color: 'text-success' },
              { label: '− Gastos de caja',   valor: -d.total_gastos_caja, color: 'text-destructive' },
            ].map((row, i) => (
              <div key={i} className="flex justify-between py-1.5 border-b border-border-subtle">
                <span className="text-xs text-secondary-foreground">{row.label}</span>
                <span className={cn('text-sm font-semibold tabular', row.color)}>
                  {row.valor < 0 ? `-${cop(Math.abs(row.valor))}` : cop(row.valor)}
                </span>
              </div>
            ))}
            <div className="flex justify-between pt-2">
              <span className="text-sm font-bold">= Efectivo en caja</span>
              <span className="text-lg font-bold text-primary tabular">{cop(d.efectivo_esperado)}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Gastos del día */}
      <Card className="p-0 overflow-hidden">
        <div className="px-4 py-3 border-b border-border-subtle">
          <CardTitle className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
            Gastos del día ({gastos.length})
          </CardTitle>
        </div>
        {gastos.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">Sin gastos registrados hoy.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2/60">
                  {['Hora', 'Concepto', 'Categoría', 'Origen', 'Monto'].map((h, i) => (
                    <th key={i} className={cn(
                      'px-3 py-2 text-[9px] font-medium text-muted-foreground uppercase tracking-wide border-b border-border-subtle',
                      i === 4 ? 'text-right' : 'text-left',
                    )}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gastos.map((g, i) => (
                  <tr key={i} className="border-b border-border-subtle hover:bg-surface-2/40">
                    <td className="px-3 py-2 text-[11px] text-muted-foreground tabular">{g.hora || '—'}</td>
                    <td className="px-3 py-2">{g.concepto || '—'}</td>
                    <td className="px-3 py-2">
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-soft text-primary border border-primary/30">
                        {g.categoria || 'Gasto'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-[11px] text-muted-foreground">{g.origen || '—'}</td>
                    <td className="px-3 py-2 text-right font-semibold text-destructive tabular">-{cop(g.monto)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-surface-2/60 border-t border-border-subtle">
                  <td colSpan={4} className="px-3 py-2.5 text-right text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Total gastos</td>
                  <td className="px-3 py-2.5 text-right text-base font-bold text-destructive tabular">-{cop(d.total_gastos)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
