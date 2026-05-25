/*
 * TabGastos — egresos con KPIs, gráficas (histórico + categorías) y tabla detalle.
 * Wave 3.a: migrado a primitives shadcn + tokens semantic.
 */
import { useState } from 'react'
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useFetch, API_BASE } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useIsMobile } from '../components/shared.jsx'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'
import { Card, CardTitle } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog.jsx'
import { toast } from 'sonner'
import {
  Plus, Wallet, BarChart3, Folder, ClipboardList, TrendingDown,
  Banknote, Landmark, Loader2, AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const cop = v => v == null || isNaN(v) ? '$0' : '$' + Math.round(v).toLocaleString('es-CO')

const DIAS_OPTIONS = [
  { label: 'Hoy',     value: 1 },
  { label: '7 días',  value: 7 },
  { label: '15 días', value: 15 },
  { label: '30 días', value: 30 },
]

// Paleta tokenizada para las categorías (usa HSL de los tokens semánticos)
const CAT_COLORS = [
  'hsl(var(--danger))',
  'hsl(var(--warning))',
  'hsl(var(--accent))',
  'hsl(var(--success))',
  'hsl(var(--ring))',
  'hsl(var(--accent-hover))',
  'hsl(var(--text-muted))',
  'hsl(var(--border-strong))',
]

const CATEGORIAS = ['General', 'Transporte', 'Alimentación', 'Servicios', 'Materiales', 'Arriendo', 'Otro']

function fmtFecha(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

// ─── KPI ──────────────────────────────────────────────────────────────────────
function Kpi({ label, value, sub, icon: Icon, tone = 'default' }) {
  const toneClass = {
    default: 'text-foreground', danger: 'text-destructive', warning: 'text-warning',
    muted: 'text-muted-foreground',
  }[tone]
  return (
    <Card className="p-4 flex-1 min-w-40">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
          <div className={cn('text-xl font-bold tabular tracking-tight mt-1.5', toneClass)}>{value}</div>
          {sub && <div className="text-[11px] text-muted-foreground mt-1">{sub}</div>}
        </div>
        {Icon && (
          <div className={cn('size-9 rounded-md grid place-items-center bg-surface-2 shrink-0', toneClass)}>
            <Icon className="size-4" />
          </div>
        )}
      </div>
    </Card>
  )
}

// ─── Dialog registrar gasto ───────────────────────────────────────────────────
export function ModalRegistrarGasto({ open, onClose, onSaved, authFetch }) {
  const [concepto,  setConcepto]  = useState('')
  const [monto,     setMonto]     = useState('')
  const [categoria, setCategoria] = useState('General')
  const [origen,    setOrigen]    = useState('caja')
  const [guardando, setGuardando] = useState(false)

  const reset = () => { setConcepto(''); setMonto(''); setCategoria('General'); setOrigen('caja'); setGuardando(false) }
  const cerrar = () => { reset(); onClose() }

  const registrar = async () => {
    if (!concepto.trim())                 { toast.error('El concepto es obligatorio'); return }
    if (!monto || parseInt(monto) <= 0)   { toast.error('El monto debe ser mayor a 0'); return }
    setGuardando(true)
    try {
      const r = await authFetch(`${API_BASE}/gastos`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concepto: concepto.trim(), monto: parseInt(monto), categoria, origen }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      toast.success(d.mensaje || 'Gasto registrado')
      onSaved()
      cerrar()
    } catch (e) { toast.error(e.message); setGuardando(false) }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && cerrar()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Registrar gasto</DialogTitle>
        </DialogHeader>
        <div className="space-y-3.5">
          <div>
            <Label>Concepto *</Label>
            <Input autoFocus value={concepto} onChange={e => setConcepto(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && registrar()}
              placeholder="Ej: Almuerzo, transporte, material…" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Monto *</Label>
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">$</span>
                <Input type="number" min="0" value={monto} className="pl-6 font-mono"
                  onChange={e => setMonto(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && registrar()}
                  placeholder="0" />
              </div>
            </div>
            <div>
              <Label>Categoría</Label>
              <select value={categoria} onChange={e => setCategoria(e.target.value)}
                className="w-full h-9 px-3 rounded-md border border-input bg-transparent text-sm focus:outline-none focus:ring-2 focus:ring-ring/40">
                {CATEGORIAS.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div>
            <Label>Origen</Label>
            <div className="flex gap-2 mt-1">
              {[
                { k: 'caja',    l: 'De caja', icon: Banknote },
                { k: 'externo', l: 'Externo', icon: Landmark },
              ].map(o => {
                const active = origen === o.k
                const Icon = o.icon
                return (
                  <button key={o.k} onClick={() => setOrigen(o.k)}
                    className={cn(
                      'flex-1 h-10 rounded-md text-xs font-semibold border transition-colors flex items-center justify-center gap-1.5',
                      active ? 'bg-primary-soft text-primary border-primary' : 'border-border text-muted-foreground hover:border-primary/40',
                    )}>
                    <Icon className="size-3.5" /> {o.l}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={cerrar}>Cancelar</Button>
          <Button onClick={registrar} disabled={guardando}>
            {guardando ? <><Loader2 className="size-3.5 mr-1.5 animate-spin" /> Guardando…</> : <><TrendingDown className="size-3.5 mr-1.5" /> Registrar gasto</>}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Tab principal ────────────────────────────────────────────────────────────
export default function TabGastos({ refreshKey }) {
  const isMobile = useIsMobile()
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()
  const [dias, setDias] = useState(7)
  const [localRefresh, setLocalRefresh] = useState(0)
  const [formOpen, setFormOpen] = useState(false)
  const vendorParam = selectedVendor ? '&vendor_id=' + selectedVendor : ''
  const { data, loading, error } = useFetch(`/gastos?dias=${dias}${vendorParam}`, [dias, refreshKey, localRefresh, selectedVendor])

  if (loading) return (
    <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
      <Loader2 className="size-6 animate-spin text-primary" />
      <span className="text-xs">Cargando…</span>
    </div>
  )
  if (error) return (
    <div className="flex items-center gap-2 p-3 rounded-md bg-destructive/10 border border-destructive/30 text-destructive text-sm">
      <AlertCircle className="size-4 shrink-0" /> Error cargando gastos: {error}
    </div>
  )

  const d          = data || {}
  const gastos     = d.gastos || []
  const historico  = (d.historico || []).map(h => ({ dia: fmtFecha(h.fecha), total: h.total }))
  const porCat     = Object.entries(d.por_categoria || {}).sort((a, b) => b[1] - a[1])
  const pieData    = porCat.map(([name, value]) => ({ name, value }))
  const total      = d.total || 0
  const promDiario = dias > 0 ? total / dias : 0

  return (
    <div className="flex flex-col gap-4">
      <ModalRegistrarGasto open={formOpen} onClose={() => setFormOpen(false)} onSaved={() => setLocalRefresh(r => r + 1)} authFetch={authFetch} />

      {/* Header */}
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <div className="text-base font-bold">Gastos</div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            {gastos.length} registros · últimos {dias} {dias === 1 ? 'día' : 'días'}
          </div>
        </div>
        <div className="flex gap-1.5 items-center flex-wrap">
          {DIAS_OPTIONS.map(o => (
            <button key={o.value} onClick={() => setDias(o.value)}
              className={cn(
                'text-xs px-3 py-1.5 rounded-md border transition-colors',
                dias === o.value
                  ? 'bg-primary text-primary-foreground border-primary font-semibold'
                  : 'border-border text-muted-foreground hover:text-foreground hover:border-primary/40',
              )}>
              {o.label}
            </button>
          ))}
          <Button onClick={() => setFormOpen(true)} className="ml-2">
            <Plus className="size-3.5 mr-1.5" /> Nuevo gasto
          </Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="flex gap-3 flex-wrap">
        <Kpi label="Total gastos"    value={cop(total)}      sub={`Últimos ${dias} días`}  icon={TrendingDown} tone="danger" />
        <Kpi label="Promedio diario" value={cop(promDiario)} sub="Gasto diario promedio"    icon={BarChart3}    tone="warning" />
        <Kpi label="Categorías"      value={porCat.length}   sub="Tipos de gasto"           icon={Folder}       tone="muted" />
        <Kpi label="Registros"       value={gastos.length}   sub="Egresos registrados"      icon={ClipboardList} tone="muted" />
      </div>

      {gastos.length === 0 ? (
        <Card className="p-8 text-center">
          <Wallet className="size-8 mx-auto text-muted-foreground opacity-40 mb-2" />
          <div className="text-sm text-muted-foreground">Sin gastos registrados en este período.</div>
        </Card>
      ) : (
        <>
          {/* Gráficas */}
          <div className={cn('grid gap-3', isMobile ? 'grid-cols-1' : 'grid-cols-2')}>
            {dias > 1 && (
              <Card className="p-4">
                <CardTitle className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-3">Gastos por día</CardTitle>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={historico} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border-subtle))" />
                    <XAxis dataKey="dia" tick={{ fill: 'hsl(var(--text-muted))', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: 'hsl(var(--text-muted))', fontSize: 9 }} axisLine={false} tickLine={false}
                      tickFormatter={v => v >= 1e3 ? `${(v / 1e3).toFixed(0)}k` : v} />
                    <Tooltip
                      contentStyle={{ background: 'hsl(var(--bg-surface))', border: '1px solid hsl(var(--border))', borderRadius: 8, color: 'hsl(var(--text-primary))', fontSize: 11 }}
                      formatter={v => [cop(v), 'Gastos']} />
                    <Bar dataKey="total" fill="hsl(var(--danger))" radius={[3, 3, 0, 0]} maxBarSize={28} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            )}

            <Card className="p-4">
              <CardTitle className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground mb-3">Por categoría</CardTitle>
              {porCat.length === 0 ? (
                <div className="py-6 text-center text-xs text-muted-foreground">Sin categorías.</div>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={120}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2}>
                        {pieData.map((_, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: 'hsl(var(--bg-surface))', border: '1px solid hsl(var(--border))', borderRadius: 8, color: 'hsl(var(--text-primary))', fontSize: 11 }}
                        formatter={v => [cop(v)]} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-col gap-1.5 mt-2">
                    {porCat.slice(0, 5).map(([cat, val], i) => (
                      <div key={i} className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <span className="size-2 rounded-full shrink-0" style={{ background: CAT_COLORS[i % CAT_COLORS.length] }} />
                          <span className="text-[11px] text-secondary-foreground">{cat}</span>
                        </div>
                        <span className="text-[11px] font-semibold tabular">{cop(val)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Card>
          </div>

          {/* Tabla detalle */}
          <Card className="p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-border-subtle">
              <CardTitle className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Detalle de gastos</CardTitle>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-surface-2/60">
                    {['Fecha', 'Hora', 'Concepto', 'Categoría', 'Origen', 'Monto'].map((h, i) => (
                      <th key={i} className={cn(
                        'px-3 py-2 text-[9px] font-medium text-muted-foreground uppercase tracking-wide border-b border-border-subtle whitespace-nowrap',
                        i === 5 ? 'text-right' : 'text-left',
                      )}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {gastos.map((g, i) => (
                    <tr key={i} className="border-b border-border-subtle hover:bg-surface-2/40">
                      <td className="px-3 py-2 text-xs text-muted-foreground tabular whitespace-nowrap">{g.fecha}</td>
                      <td className="px-3 py-2 text-[11px] text-muted-foreground tabular">{g.hora || '—'}</td>
                      <td className="px-3 py-2">{g.concepto || '—'}</td>
                      <td className="px-3 py-2">
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-soft text-primary border border-primary/30">
                          {g.categoria || 'Sin categoría'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-[11px] text-muted-foreground">{g.origen || '—'}</td>
                      <td className="px-3 py-2 text-right font-semibold text-destructive tabular">-{cop(g.monto)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-surface-2/60 border-t border-border-subtle">
                    <td colSpan={5} className="px-3 py-2.5 text-right text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
                      Total ({gastos.length} registros)
                    </td>
                    <td className="px-3 py-2.5 text-right text-base font-bold text-destructive tabular">-{cop(total)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
