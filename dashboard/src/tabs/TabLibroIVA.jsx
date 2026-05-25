/**
 * TabLibroIVA.jsx — Libro de IVA · Régimen Simple de Tributación
 *
 * Secciones:
 *   1. Selector de período (bimestral DIAN o fechas custom)
 *   2. KPIs: IVA generado, descontable, neto
 *   3. Cuadro neto: ventas FE - compras - saldo anterior = IVA a pagar
 *   4. Historial de cierres bimestrales con botón "Cerrar período"
 *   5. Libros detallados: ventas FE | compras con IVA
 *
 * Migrado a tokens shadcn + sonner (Wave 4 — Fiscal).
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle, BookOpen, Calendar, CalendarRange, CheckCircle2,
  CreditCard, Lock, Loader2, RefreshCw, Scale, ShoppingCart, Receipt,
} from 'lucide-react'
import { cop, API_BASE, Spinner } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog.jsx'
import { cn } from '@/lib/utils'

// ── Constantes ────────────────────────────────────────────────────────────────

const BIMESTRES = [
  { n:1, label:'Ene – Feb', ini:'01-01', fin:'02-28' },
  { n:2, label:'Mar – Abr', ini:'03-01', fin:'04-30' },
  { n:3, label:'May – Jun', ini:'05-01', fin:'06-30' },
  { n:4, label:'Jul – Ago', ini:'07-01', fin:'08-31' },
  { n:5, label:'Sep – Oct', ini:'09-01', fin:'10-31' },
  { n:6, label:'Nov – Dic', ini:'11-01', fin:'12-31' },
]
const NOMBRES_BIM = ['Ene-Feb','Mar-Abr','May-Jun','Jul-Ago','Sep-Oct','Nov-Dic']

function bimDates(n) {
  const año = new Date().getFullYear()
  const b   = BIMESTRES[n - 1]
  const fin = n === 1
    ? ((año % 4 === 0 && año % 100 !== 0) || año % 400 === 0 ? '02-29' : '02-28')
    : b.fin
  return [`${año}-${b.ini}`, `${año}-${fin}`]
}

function currentBim() { return Math.ceil((new Date().getMonth() + 1) / 2) }

function fmtF(s) {
  if (!s) return '—'
  const [y,m,d] = s.split('-')
  const mn = ['','ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
  return `${d} ${mn[+m]} ${y}`
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

function Th({ children, center, right }) {
  return (
    <th className={cn(
      'h-9 px-3.5 align-middle text-[11px] font-semibold uppercase tracking-wide text-muted-foreground whitespace-nowrap',
      center && 'text-center',
      right  && 'text-right',
      !center && !right && 'text-left',
    )}>
      {children}
    </th>
  )
}

function EmptyState({ msg }) {
  return (
    <div className="border border-dashed border-border rounded-lg py-7 px-4 text-center text-xs text-muted-foreground">
      {msg}
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

// ── KPI ───────────────────────────────────────────────────────────────────────

function Kpi({ label, value, sub, tone = 'primary', icon: Icon }) {
  const toneCls = {
    primary: 'text-primary',
    success: 'text-success',
    warning: 'text-warning',
  }[tone] || 'text-primary'
  const bgIcon = {
    primary: 'bg-primary-soft',
    success: 'bg-success/10',
    warning: 'bg-warning/10',
  }[tone] || 'bg-primary-soft'
  return (
    <Card className="flex-1 min-w-[150px] p-4 relative overflow-hidden">
      <div className="flex justify-between items-start gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
            {label}
          </div>
          <div className="text-xl font-bold text-foreground tabular-nums truncate">{value}</div>
          {sub && <div className="text-[11px] text-muted-foreground mt-1">{sub}</div>}
        </div>
        {Icon && (
          <div className={cn('size-8 rounded-md inline-flex items-center justify-center flex-shrink-0', bgIcon)}>
            <Icon className={cn('size-4', toneCls)} />
          </div>
        )}
      </div>
    </Card>
  )
}

// ── Cuadro IVA neto ───────────────────────────────────────────────────────────

function CuadroNeto({ resumen }) {
  if (!resumen) return null
  const { ventas, compras, iva_neto } = resumen
  const aFavor = iva_neto.a_favor === 'empresa'
  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border">
        <SectionTitle icon={Scale}>Cuadro IVA neto del período</SectionTitle>
      </div>
      <div className="p-5 pt-4 flex flex-col">
        {/* IVA generado */}
        <div className="flex justify-between items-center gap-4 px-4 py-3 bg-muted/40 rounded-t-lg border-b border-border">
          <div className="min-w-0">
            <div className="text-xs font-semibold text-foreground inline-flex items-center gap-1.5">
              <Receipt className="size-3.5 text-primary" />
              IVA generado — ventas con FE emitida
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {ventas.por_tarifa.map(r => `Tarifa ${r.tarifa}%: ${cop(r.iva_valor)}`).join(' · ') || 'Sin facturas electrónicas emitidas'}
            </div>
          </div>
          <div className="text-lg font-bold text-primary tabular-nums min-w-[100px] text-right">
            {cop(ventas.total_iva)}
          </div>
        </div>

        {/* IVA descontable */}
        <div className="flex justify-between items-center gap-4 px-4 py-3 border-b border-border">
          <div className="min-w-0">
            <div className="text-xs font-semibold text-foreground inline-flex items-center gap-1.5">
              <ShoppingCart className="size-3.5 text-success" />
              IVA descontable — compras a proveedores con IVA
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {compras.por_tarifa.map(r => `Tarifa ${r.tarifa}%: ${cop(r.iva_valor)}`).join(' · ') || 'Sin compras con IVA en el período'}
            </div>
          </div>
          <div className="text-lg font-bold text-success tabular-nums min-w-[100px] text-right">
            − {cop(compras.total_iva)}
          </div>
        </div>

        {/* Resultado */}
        <div className={cn(
          'flex justify-between items-center gap-4 px-4 py-4 rounded-b-lg border',
          aFavor
            ? 'bg-success/10 border-success/30'
            : 'bg-primary-soft border-primary/30',
        )}>
          <div className="min-w-0">
            <div className={cn(
              'text-sm font-bold inline-flex items-center gap-1.5',
              aFavor ? 'text-success' : 'text-primary',
            )}>
              {aFavor
                ? <><CheckCircle2 className="size-4" /> Saldo a tu favor este período</>
                : <><CreditCard className="size-4" /> IVA neto a pagar a la DIAN</>}
            </div>
            <div className="text-[11px] text-muted-foreground mt-0.5">
              {aFavor
                ? 'Este saldo se arrastrará automáticamente al cerrar el bimestre'
                : 'Diferencia entre IVA cobrado en facturas y el IVA pagado en compras'}
            </div>
          </div>
          <div className={cn(
            'text-2xl font-bold tabular-nums min-w-[100px] text-right',
            aFavor ? 'text-success' : 'text-primary',
          )}>
            {cop(Math.abs(iva_neto.valor))}
          </div>
        </div>
      </div>
    </Card>
  )
}

// ── Modal Cerrar Bimestre ─────────────────────────────────────────────────────

function ModalCierre({ bimestre, año, open, onClose, onCerrado, authFetch }) {
  const [obs,   setObs]   = useState('')
  const [est,   setEst]   = useState('idle')
  const [res,   setRes]   = useState(null)
  const [err,   setErr]   = useState('')

  const cerrar = async () => {
    setEst('loading'); setErr('')
    try {
      const r = await authFetch(`${API_BASE}/libro-iva/cerrar-bimestre`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ año, bimestre, observaciones: obs }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || JSON.stringify(d))
      setRes(d); setEst('ok')
      toast.success(`Bimestre ${NOMBRES_BIM[bimestre - 1]} ${año} cerrado`)
      setTimeout(() => { onCerrado() }, 1800)
    } catch(e) { setErr(e.message); setEst('error') }
  }

  const handleOpenChange = (o) => { if (!o && est !== 'loading') onClose() }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="inline-flex items-center gap-2">
            <Lock className="size-4 text-primary" />
            Cerrar bimestre {NOMBRES_BIM[bimestre - 1]} {año}
          </DialogTitle>
          <DialogDescription>
            Calculará el IVA neto incluyendo saldo arrastrado del bimestre anterior.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="cierre-obs" className="text-[11px] uppercase tracking-wider text-muted-foreground">
            Observaciones (opcional)
          </Label>
          <Input
            id="cierre-obs"
            value={obs}
            onChange={e => setObs(e.target.value)}
            placeholder="Ej: Declarado el 15 de marzo, pago referencia 123…"
            disabled={est === 'loading'}
          />
        </div>

        {est === 'ok' && res && (
          <div className="rounded-md bg-success/10 border border-success/30 p-3.5 flex flex-col gap-1.5 text-success">
            <div className="text-sm font-bold inline-flex items-center gap-1.5">
              <CheckCircle2 className="size-4" /> Bimestre cerrado
            </div>
            <div className="text-xs opacity-90">IVA ventas FE: {cop(res.iva_ventas)}</div>
            <div className="text-xs opacity-90">IVA descontable: {cop(res.iva_compras)}</div>
            {res.saldo_anterior > 0 && (
              <div className="text-xs opacity-90">Saldo a favor anterior: {cop(res.saldo_anterior)}</div>
            )}
            <div className="text-sm font-bold mt-1">
              {res.a_favor === 'empresa'
                ? `Saldo a tu favor: ${cop(Math.abs(res.iva_neto))} — se arrastra`
                : `IVA a pagar a la DIAN: ${cop(res.iva_neto)}`}
            </div>
          </div>
        )}

        {est === 'error' && <ErrorMsg msg={err} />}

        {est !== 'ok' && (
          <DialogFooter>
            <Button variant="outline" onClick={onClose} disabled={est === 'loading'}>
              Cancelar
            </Button>
            <Button
              onClick={cerrar}
              disabled={est === 'loading'}
              variant={est === 'error' ? 'destructive' : 'default'}
            >
              {est === 'loading'
                ? <><Loader2 className="size-4 mr-1.5 animate-spin" /> Calculando…</>
                : est === 'error'
                  ? <><AlertTriangle className="size-4 mr-1.5" /> Reintentar</>
                  : <><Lock className="size-4 mr-1.5" /> Cerrar bimestre</>}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ── Historial de cierres ──────────────────────────────────────────────────────

function HistorialCierres({ año, refresh, onCerrar, authFetch }) {
  const ref = useRef(authFetch); ref.current = authFetch
  const [data,    setData]    = useState([])
  const [loading, setLoading] = useState(false)

  const cargar = useCallback(async () => {
    setLoading(true)
    try {
      const r = await ref.current(`${API_BASE}/libro-iva/historial-cierres?año=${año}`)
      if (r.ok) setData(await r.json())
    } catch(_){}
    finally { setLoading(false) }
  }, [año, refresh])

  useEffect(() => { cargar() }, [cargar])

  return (
    <Card className="overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border flex justify-between items-center flex-wrap gap-2">
        <SectionTitle icon={Calendar}>Bimestres {año}</SectionTitle>
        <span className="text-[11px] text-muted-foreground">
          Haz clic en "Cerrar" para calcular y guardar el IVA neto
        </span>
      </div>
      {loading ? <Spinner /> : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/40 border-b border-border">
              <tr>
                <Th>Período</Th>
                <Th right>IVA ventas</Th>
                <Th right>IVA compras</Th>
                <Th right>Saldo anterior</Th>
                <Th right>IVA neto</Th>
                <Th center>Estado</Th>
                <Th center>Acción</Th>
              </tr>
            </thead>
            <tbody>
              {BIMESTRES.map(b => {
                const cierre = data.find(d => d.bimestre === b.n)
                const aFavor = cierre && parseInt(cierre.iva_neto) < 0
                return (
                  <tr key={b.n} className="border-b border-border/60 hover:bg-muted/40 transition-colors">
                    <td className="px-3.5 py-2.5 font-semibold text-foreground">{b.label}</td>
                    <td className="px-3.5 py-2.5 text-right text-primary tabular-nums">
                      {cierre ? cop(cierre.iva_ventas) : '—'}
                    </td>
                    <td className="px-3.5 py-2.5 text-right text-success tabular-nums">
                      {cierre ? cop(cierre.iva_compras) : '—'}
                    </td>
                    <td className="px-3.5 py-2.5 text-right text-muted-foreground tabular-nums">
                      {cierre && parseInt(cierre.saldo_anterior) > 0 ? cop(cierre.saldo_anterior) : '—'}
                    </td>
                    <td className={cn(
                      'px-3.5 py-2.5 text-right font-bold tabular-nums',
                      cierre ? (aFavor ? 'text-success' : 'text-primary') : 'text-muted-foreground',
                    )}>
                      {cierre
                        ? (aFavor ? '−' : '') + cop(Math.abs(parseInt(cierre.iva_neto)))
                        : '—'}
                    </td>
                    <td className="px-3.5 py-2.5 text-center">
                      {cierre ? (
                        <span className={cn(
                          'inline-block text-[10px] font-bold px-2 py-0.5 rounded-full',
                          aFavor
                            ? 'bg-success/10 text-success'
                            : 'bg-primary-soft text-primary',
                        )}>
                          {aFavor ? 'A favor' : 'A pagar'}
                        </span>
                      ) : (
                        <span className="text-[10px] text-muted-foreground">Pendiente</span>
                      )}
                    </td>
                    <td className="px-2.5 py-2 text-center">
                      <Button
                        size="sm"
                        variant={cierre ? 'outline' : 'default'}
                        onClick={() => onCerrar(b.n)}
                        className="text-[11px] h-7"
                      >
                        {cierre
                          ? <><RefreshCw className="size-3 mr-1" /> Recalcular</>
                          : <><Lock className="size-3 mr-1" /> Cerrar</>}
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// ── Tabla ventas FE ───────────────────────────────────────────────────────────

function TablaVentasFE({ desde, hasta, authFetch }) {
  const ref = useRef(authFetch); ref.current = authFetch
  const [data, setData] = useState(null)
  const [load, setLoad] = useState(false)
  const [err,  setErr]  = useState(null)

  const cargar = useCallback(async () => {
    setLoad(true); setErr(null)
    try {
      const r = await ref.current(`${API_BASE}/libro-iva/ventas?desde=${desde}&hasta=${hasta}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch(e){ setErr(e.message) } finally { setLoad(false) }
  }, [desde, hasta])

  useEffect(() => { cargar() }, [cargar])

  if (load) return <Spinner />
  if (err)  return <div className="p-4"><ErrorMsg msg={err} /></div>
  if (!data || data.registros.length === 0) {
    return <div className="p-4"><EmptyState msg="Sin facturas electrónicas emitidas con IVA en este período." /></div>
  }

  const tot = data.totales
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead className="bg-muted/40 border-b border-border">
          <tr>
            <Th>Fecha</Th><Th>FE #</Th><Th>Cliente</Th><Th>NIT</Th><Th>Concepto</Th>
            <Th center>Tarifa</Th><Th right>Total c/IVA</Th><Th right>Base</Th><Th right>IVA</Th>
          </tr>
        </thead>
        <tbody>
          {data.registros.map((r,i) => (
            <tr key={i} className="border-b border-border/60 hover:bg-muted/40 transition-colors">
              <td className="px-3.5 py-2 text-muted-foreground whitespace-nowrap">{fmtF(r.fecha)}</td>
              <td className="px-2.5 py-2 text-primary font-bold">{r.factura_numero || '—'}</td>
              <td className="px-3.5 py-2 text-foreground max-w-[130px] truncate">{r.cliente_nombre}</td>
              <td className="px-3 py-2 text-muted-foreground font-mono text-[10px]">
                {r.nit_cliente === '222222222222' ? '—' : r.nit_cliente}
              </td>
              <td className="px-3.5 py-2 text-muted-foreground max-w-[160px] truncate">{r.concepto}</td>
              <td className="px-2.5 py-2 text-center">
                <span className="inline-block text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-primary-soft text-primary">
                  {r.tarifa_iva}%
                </span>
              </td>
              <td className="px-3.5 py-2 text-right text-muted-foreground tabular-nums">{cop(r.total_con_iva)}</td>
              <td className="px-3.5 py-2 text-right text-foreground tabular-nums">{cop(r.base_gravable)}</td>
              <td className="px-3.5 py-2 text-right text-primary font-bold tabular-nums">{cop(r.iva_valor)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-muted/60 border-t border-border">
            <td colSpan={6} className="px-3.5 py-2.5 text-[10px] text-muted-foreground font-semibold text-right">
              {tot.num_lineas} líneas
            </td>
            <td className="px-3.5 py-2.5 text-right text-muted-foreground tabular-nums">{cop(tot.total_con_iva)}</td>
            <td className="px-3.5 py-2.5 text-right text-foreground font-bold tabular-nums">{cop(tot.base_gravable)}</td>
            <td className="px-3.5 py-2.5 text-right text-primary font-bold text-sm tabular-nums">{cop(tot.iva_generado)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

// ── Tabla compras IVA descontable ─────────────────────────────────────────────

function TablaComprasIVA({ desde, hasta, authFetch }) {
  const ref = useRef(authFetch); ref.current = authFetch
  const [data, setData] = useState(null)
  const [load, setLoad] = useState(false)
  const [err,  setErr]  = useState(null)

  const cargar = useCallback(async () => {
    setLoad(true); setErr(null)
    try {
      const r = await ref.current(`${API_BASE}/libro-iva/compras?desde=${desde}&hasta=${hasta}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch(e){ setErr(e.message) } finally { setLoad(false) }
  }, [desde, hasta])

  useEffect(() => { cargar() }, [cargar])

  if (load) return <Spinner />
  if (err)  return <div className="p-4"><ErrorMsg msg={err} /></div>
  if (!data || data.registros.length === 0) {
    return (
      <div className="p-4">
        <EmptyState msg="Sin compras con IVA en este período. Al registrar compras en el tab Compras, activa el toggle 'Precio incluye IVA'." />
      </div>
    )
  }

  const tot = data.totales
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead className="bg-muted/40 border-b border-border">
          <tr>
            <Th>Fecha</Th><Th>Proveedor</Th><Th>Concepto</Th>
            <Th center>Tarifa</Th><Th right>Cantidad</Th>
            <Th right>Total c/IVA</Th><Th right>Base</Th><Th right>IVA desc.</Th>
          </tr>
        </thead>
        <tbody>
          {data.registros.map((r,i) => (
            <tr key={i} className="border-b border-border/60 hover:bg-muted/40 transition-colors">
              <td className="px-3.5 py-2 text-muted-foreground whitespace-nowrap">{fmtF(r.fecha)}</td>
              <td className="px-3.5 py-2 text-foreground max-w-[130px] truncate">{r.proveedor}</td>
              <td className="px-3.5 py-2 text-muted-foreground max-w-[160px] truncate">{r.concepto}</td>
              <td className="px-2.5 py-2 text-center">
                <span className="inline-block text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-success/10 text-success">
                  {r.tarifa_iva}%
                </span>
              </td>
              <td className="px-3.5 py-2 text-right text-muted-foreground">{r.cantidad}</td>
              <td className="px-3.5 py-2 text-right text-muted-foreground tabular-nums">{cop(r.total_con_iva)}</td>
              <td className="px-3.5 py-2 text-right text-foreground tabular-nums">{cop(r.base_gravable)}</td>
              <td className="px-3.5 py-2 text-right text-success font-bold tabular-nums">{cop(r.iva_valor)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-muted/60 border-t border-border">
            <td colSpan={5} className="px-3.5 py-2.5 text-[10px] text-muted-foreground font-semibold text-right">
              {tot.num_lineas} compras
            </td>
            <td className="px-3.5 py-2.5 text-right text-muted-foreground tabular-nums">{cop(tot.total_con_iva)}</td>
            <td className="px-3.5 py-2.5 text-right text-foreground font-bold tabular-nums">{cop(tot.base_gravable)}</td>
            <td className="px-3.5 py-2.5 text-right text-success font-bold text-sm tabular-nums">{cop(tot.iva_descontable)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function TabLibroIVA() {
  const { authFetch } = useAuth()

  const año = new Date().getFullYear()
  const [bim,   setBim]   = useState(currentBim())
  const [modo,  setModo]  = useState('bimestral')
  const [desde, setDesde] = useState(() => bimDates(currentBim())[0])
  const [hasta, setHasta] = useState(() => bimDates(currentBim())[1])

  const [resumen,    setResumen]    = useState(null)
  const [loadRes,    setLoadRes]    = useState(false)
  const [vista,      setVista]      = useState('ventas')
  const [modalBim,   setModalBim]   = useState(null)
  const [cierreRfsh, setCierreRfsh] = useState(0)

  const aplicarBim = n => {
    setBim(n)
    const [d,h] = bimDates(n)
    setDesde(d); setHasta(h)
  }

  useEffect(() => {
    if (!desde || !hasta) return
    setLoadRes(true)
    authFetch(`${API_BASE}/libro-iva/resumen?desde=${desde}&hasta=${hasta}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setResumen(d) })
      .catch(() => {})
      .finally(() => setLoadRes(false))
  }, [desde, hasta])

  return (
    <div className="flex flex-col gap-5">

      {/* Banner RST */}
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-primary-soft border border-primary/30 text-primary text-xs">
        <BookOpen className="size-5 flex-shrink-0" />
        <div>
          <strong>Libro de IVA — Régimen Simple de Tributación</strong>
          <span className="ml-2.5 opacity-75 text-[11px]">
            IVA extraído de precio final · Solo FE emitidas · Saldo bimestral arrastrado automáticamente
          </span>
        </div>
      </div>

      {/* Selector período */}
      <Card className="px-5 py-3.5">
        <div className="flex gap-2.5 flex-wrap items-end">
          {/* Toggle modo */}
          <div className="flex border border-border rounded-md overflow-hidden">
            {[
              { k: 'bimestral', label: 'Bimestral', icon: Calendar },
              { k: 'custom',    label: 'Fechas',    icon: CalendarRange },
            ].map(m => {
              const Icon = m.icon
              const active = modo === m.k
              return (
                <button
                  key={m.k}
                  type="button"
                  onClick={() => setModo(m.k)}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-3.5 py-1.5 text-[11px] font-semibold transition-colors',
                    active
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  <Icon className="size-3" />
                  {m.label}
                </button>
              )
            })}
          </div>

          {modo === 'bimestral' ? (
            <div className="flex gap-1.5 flex-wrap">
              {BIMESTRES.map(b => {
                const active = bim === b.n
                return (
                  <button
                    key={b.n}
                    type="button"
                    onClick={() => aplicarBim(b.n)}
                    className={cn(
                      'inline-flex items-center px-3.5 py-1.5 rounded-md text-[11px] border transition-colors',
                      active
                        ? 'bg-primary-soft border-primary text-primary font-bold'
                        : 'bg-transparent border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
                    )}
                  >
                    {b.label}
                  </button>
                )
              })}
            </div>
          ) : (
            <div className="flex gap-2.5 items-end flex-wrap">
              <div className="space-y-1">
                <Label htmlFor="iva-desde" className="text-[10px] uppercase tracking-wider text-muted-foreground">Desde</Label>
                <Input id="iva-desde" type="date" value={desde} onChange={e => setDesde(e.target.value)} className="h-8 text-xs" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="iva-hasta" className="text-[10px] uppercase tracking-wider text-muted-foreground">Hasta</Label>
                <Input id="iva-hasta" type="date" value={hasta} onChange={e => setHasta(e.target.value)} className="h-8 text-xs" />
              </div>
            </div>
          )}

          <div className="text-[11px] text-muted-foreground self-center">
            {fmtF(desde)} → {fmtF(hasta)}
          </div>
        </div>
      </Card>

      {/* KPIs */}
      {loadRes && !resumen && <Spinner />}
      {resumen && (
        <div className="flex gap-2.5 flex-wrap">
          <Kpi
            label="IVA generado (FE)"
            value={cop(resumen.ventas.total_iva)}
            sub={`Base: ${cop(resumen.ventas.total_base)}`}
            tone="primary"
            icon={Receipt}
          />
          <Kpi
            label="IVA descontable"
            value={cop(resumen.compras.total_iva)}
            sub={`Total compras: ${cop(resumen.compras.total_bruto)}`}
            tone="success"
            icon={ShoppingCart}
          />
          <Kpi
            label="IVA neto del período"
            value={cop(Math.abs(resumen.iva_neto.valor))}
            sub={resumen.iva_neto.a_favor === 'empresa' ? 'Saldo a tu favor' : 'A pagar a la DIAN'}
            tone={resumen.iva_neto.a_favor === 'empresa' ? 'success' : 'primary'}
            icon={Scale}
          />
        </div>
      )}

      {/* Cuadro neto */}
      {resumen && <CuadroNeto resumen={resumen} />}

      {/* Historial cierres */}
      <HistorialCierres
        año={año}
        refresh={cierreRfsh}
        authFetch={authFetch}
        onCerrar={n => setModalBim(n)}
      />

      {/* Libros detallados */}
      <Card className="overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border flex justify-between items-center flex-wrap gap-2">
          <SectionTitle icon={vista === 'ventas' ? Receipt : ShoppingCart}>
            {vista === 'ventas' ? 'Libro IVA ventas — FE emitidas' : 'Libro IVA compras — IVA descontable'}
          </SectionTitle>
          <div className="flex gap-1.5">
            {[
              { k: 'ventas',  label: 'Ventas FE', icon: Receipt },
              { k: 'compras', label: 'Compras',   icon: ShoppingCart },
            ].map(v => {
              const Icon = v.icon
              const active = vista === v.k
              return (
                <button
                  key={v.k}
                  type="button"
                  onClick={() => setVista(v.k)}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md text-[11px] border transition-colors',
                    active
                      ? 'bg-primary-soft border-primary text-primary font-bold'
                      : 'bg-transparent border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
                  )}
                >
                  <Icon className="size-3" />
                  {v.label}
                </button>
              )
            })}
          </div>
        </div>
        {vista === 'ventas'
          ? <TablaVentasFE   desde={desde} hasta={hasta} authFetch={authFetch} />
          : <TablaComprasIVA desde={desde} hasta={hasta} authFetch={authFetch} />}
      </Card>

      {/* Nota */}
      <div className="px-4 py-3 rounded-lg text-[11px] text-muted-foreground bg-muted/40 border border-border leading-relaxed">
        <strong className="text-foreground">Flujo bimestral:</strong> Al finalizar cada bimestre, haz clic en "Cerrar" para
        calcular el IVA neto. Si el saldo es a tu favor, se arrastra automáticamente
        al siguiente período. Si hay que pagar, ese es el valor exacto para declarar ante la DIAN.
        Recuerda marcar el toggle <strong className="text-foreground">"Precio incluye IVA"</strong> al registrar compras de proveedores
        para acumular el IVA descontable.
      </div>

      {/* Modal cierre */}
      <ModalCierre
        open={modalBim != null}
        bimestre={modalBim || 1}
        año={año}
        authFetch={authFetch}
        onClose={() => setModalBim(null)}
        onCerrado={() => { setModalBim(null); setCierreRfsh(r => r + 1) }}
      />
    </div>
  )
}
