/**
 * TabFacturacion.jsx — Facturación Electrónica DIAN (MATIAS API)
 *
 * Secciones:
 *   1. KPIs  — emitidas, $ facturado, errores
 *   2. Panel emitir — ventas sin FE del día seleccionado + emisión por fila
 *   3. Historial  — facturas_electronicas con descarga de PDF
 *
 * Migrado a tokens shadcn + sonner (Wave 4 — Fiscal).
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle, CheckCircle2, ClipboardList, Clock, Copy, Download,
  FileText, Landmark, Loader2, RefreshCw, Receipt, DollarSign, XCircle,
} from 'lucide-react'
import { cop, API_BASE, Spinner, useIsMobile } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog.jsx'
import { cn } from '@/lib/utils'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtFecha(str) {
  if (!str) return '—'
  const utcStr = (str.includes('T') && !str.endsWith('Z') && !str.includes('+')) ? str + 'Z' : str
  const d = new Date(utcStr)
  if (isNaN(d)) return str
  return d.toLocaleDateString('es-CO', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
    timeZone: 'America/Bogota',
  })
}

function fmtFechaSolo(str) {
  if (!str) return '—'
  const d = new Date(str + 'T12:00:00')
  if (isNaN(d)) return str
  return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function cufeCorto(cufe) {
  if (!cufe || cufe.length < 16) return cufe || '—'
  return cufe.slice(0, 16) + '…' + cufe.slice(-8)
}

function copiarCufe(cufe) {
  if (!cufe) return
  navigator.clipboard.writeText(cufe)
    .then(() => toast.success('CUFE copiado al portapapeles'))
    .catch(() => {})
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
    <div className="border border-dashed border-border rounded-lg py-7 px-4 text-center text-xs text-muted-foreground mx-4 my-4">
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

function EstadoBadge({ estado }) {
  const cfg = {
    emitida:     { cls: 'bg-success/10 text-success border-success/30',          icon: CheckCircle2,   label: 'Emitida'   },
    error:       { cls: 'bg-destructive/10 text-destructive border-destructive/30', icon: XCircle,    label: 'Error'     },
    sin_factura: { cls: 'bg-warning/10 text-warning border-warning/30',          icon: Clock,          label: 'Pendiente' },
  }[estado] || { cls: 'bg-muted text-muted-foreground border-border', icon: Clock, label: estado }
  const Icon = cfg.icon
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-bold whitespace-nowrap',
      cfg.cls,
    )}>
      <Icon className="size-3" />
      {cfg.label}
    </span>
  )
}

function MetodoBadge({ metodo }) {
  const raw = (metodo || '').toLowerCase()
  let cls = 'bg-muted text-muted-foreground'
  if (raw.includes('efect'))                                   cls = 'bg-success/10 text-success'
  else if (raw.includes('nequi'))                              cls = 'bg-primary-soft text-primary'
  else if (raw.includes('transf'))                             cls = 'bg-warning/10 text-warning'
  else if (raw.includes('tarjet') || raw.includes('dataf'))    cls = 'bg-primary-soft text-primary'
  return (
    <span className={cn('inline-block px-2 py-0.5 rounded-full text-[10px] font-medium whitespace-nowrap', cls)}>
      {metodo || '—'}
    </span>
  )
}

// ── KPI ───────────────────────────────────────────────────────────────────────

function KpiMini({ label, value, tone = 'primary', icon: Icon }) {
  const toneCls = {
    primary:     'text-primary',
    success:     'text-success',
    destructive: 'text-destructive',
    muted:       'text-muted-foreground',
  }[tone] || 'text-primary'
  const bgIcon = {
    primary:     'bg-primary-soft',
    success:     'bg-success/10',
    destructive: 'bg-destructive/10',
    muted:       'bg-muted',
  }[tone] || 'bg-primary-soft'
  return (
    <Card className="flex-1 min-w-[140px] p-4">
      <div className="flex justify-between items-start gap-3">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            {label}
          </div>
          <div className="text-xl font-bold text-foreground tabular-nums truncate">{value}</div>
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

// ── Modal confirmación emisión ────────────────────────────────────────────────

function ModalEmitir({ venta, open, onClose, onEmitida }) {
  const { authFetch } = useAuth()
  const [estado, setEstado] = useState('idle')
  const [error,  setError]  = useState('')
  const [result, setResult] = useState(null)

  if (!venta) return null

  const esConsumidorFinal = !venta.cliente_nombre || venta.cliente_nombre === 'Consumidor Final'

  const emitir = async () => {
    setEstado('loading'); setError('')
    try {
      const r = await authFetch(`${API_BASE}/facturacion/emitir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ venta_id: venta.id }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || JSON.stringify(d))
      setResult(d); setEstado('ok')
      toast.success(`Factura ${d.numero} emitida`)
      setTimeout(() => { onEmitida() }, 1800)
    } catch (e) { setError(e.message); setEstado('error') }
  }

  const handleOpenChange = (o) => { if (!o && estado !== 'loading') onClose() }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="inline-flex items-center gap-2">
            <FileText className="size-4 text-primary" />
            Emitir Factura Electrónica
          </DialogTitle>
          <DialogDescription>
            Consecutivo #{venta.consecutivo} — {fmtFechaSolo(venta.fecha)}
          </DialogDescription>
        </DialogHeader>

        {/* Datos */}
        <div className="rounded-md border border-border overflow-hidden bg-muted/40">
          {[
            ['Cliente',  venta.cliente_nombre || 'Consumidor Final'],
            ['Total',    cop(venta.total)],
            ['Método',   venta.metodo_pago || 'efectivo'],
            ['Vendedor', venta.vendedor || '—'],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 px-3.5 py-2 border-b border-border last:border-0">
              <span className="text-[11px] text-muted-foreground">{k}</span>
              <span className="text-xs font-semibold text-foreground truncate">{v}</span>
            </div>
          ))}
        </div>

        {esConsumidorFinal && estado === 'idle' && (
          <div className="rounded-md bg-warning/10 border border-warning/30 px-3.5 py-2.5 text-xs text-warning leading-relaxed">
            <AlertTriangle className="size-3.5 inline mr-1 -mt-0.5" />
            <strong>Sin datos fiscales del cliente.</strong> La factura se emitirá como
            "Consumidor Final" con NIT genérico 222222222222. Válido para ventas ordinarias.
          </div>
        )}

        {estado === 'ok' && result && (
          <div className="rounded-md bg-success/10 border border-success/30 p-3.5 flex flex-col gap-1.5 text-success">
            <div className="text-sm font-bold inline-flex items-center gap-1.5">
              <CheckCircle2 className="size-4" /> Factura {result.numero} emitida ante la DIAN
            </div>
            <div className="text-xs opacity-90">CUFE: {cufeCorto(result.cufe)}</div>
            <div className="text-[11px] opacity-75">
              {result.pdf_telegram
                ? 'Sin correo registrado — PDF enviado al grupo de Telegram.'
                : 'PDF enviado al correo del cliente automáticamente.'}
            </div>
          </div>
        )}

        {estado === 'error' && <ErrorMsg msg={error} />}

        {estado !== 'ok' && (
          <DialogFooter>
            <Button variant="outline" onClick={onClose} disabled={estado === 'loading'}>
              Cancelar
            </Button>
            <Button
              onClick={emitir}
              disabled={estado === 'loading'}
              variant={estado === 'error' ? 'destructive' : 'default'}
            >
              {estado === 'loading'
                ? <><Loader2 className="size-4 mr-1.5 animate-spin" /> Enviando a DIAN…</>
                : estado === 'error'
                  ? <><AlertTriangle className="size-4 mr-1.5" /> Reintentar</>
                  : <><FileText className="size-4 mr-1.5" /> Emitir Factura DIAN</>}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ── Sección: ventas pendientes de FE ──────────────────────────────────────────

function PanelEmitir({ onEmitida }) {
  const isMob = useIsMobile()
  const { authFetch } = useAuth()
  const authFetchRef = useRef(authFetch)
  authFetchRef.current = authFetch

  const [fecha,     setFecha]     = useState(() =>
    new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })
  )
  const [ventas,    setVentas]    = useState([])
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState(null)
  const [emitiendo, setEmitiendo] = useState(null)

  const cargar = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await authFetchRef.current(`${API_BASE}/facturacion/ventas-pendientes?fecha=${fecha}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setVentas(await r.json())
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }, [fecha])

  useEffect(() => { cargar() }, [cargar])

  return (
    <Card className="overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-border flex justify-between items-center flex-wrap gap-2.5">
        <SectionTitle icon={ClipboardList}>Ventas sin Factura Electrónica</SectionTitle>
        <div className="flex items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="fac-fecha" className="text-[10px] uppercase tracking-wider text-muted-foreground">Fecha</Label>
            <Input
              id="fac-fecha"
              type="date"
              value={fecha}
              onChange={e => setFecha(e.target.value)}
              className="h-8 text-xs"
            />
          </div>
          <Button variant="outline" size="sm" onClick={cargar} className="h-8 text-[11px]">
            <RefreshCw className="size-3 mr-1" /> Actualizar
          </Button>
        </div>
      </div>

      {/* Contenido */}
      {loading && <Spinner />}
      {!loading && error && <div className="p-4"><ErrorMsg msg={error} /></div>}
      {!loading && !error && ventas.length === 0 && (
        <EmptyState msg={`Todas las ventas del ${fmtFechaSolo(fecha)} tienen factura emitida.`} />
      )}
      {!loading && !error && ventas.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/40 border-b border-border">
              <tr>
                <Th>#</Th>
                <Th>Hora</Th>
                <Th>Cliente</Th>
                <Th>Vendedor</Th>
                <Th center>Método</Th>
                <Th right>Total</Th>
                <Th center>Acción</Th>
              </tr>
            </thead>
            <tbody>
              {ventas.map(v => {
                const cf = !v.cliente_nombre || v.cliente_nombre === 'Consumidor Final'
                return (
                  <tr key={v.id} className="border-b border-border/60 hover:bg-muted/40 transition-colors">
                    <td className="px-3.5 py-2.5 text-primary font-bold">{v.consecutivo}</td>
                    <td className="px-3.5 py-2.5 text-muted-foreground italic whitespace-nowrap">
                      {v.hora ? String(v.hora).slice(0, 5) : '—'}
                    </td>
                    <td className="px-3.5 py-2.5 text-foreground max-w-[180px]">
                      {v.cliente_nombre || 'Consumidor Final'}
                      {cf && (
                        <span className="ml-1.5 inline-block text-[9px] font-bold px-1.5 py-0.5 rounded bg-warning/10 text-warning">
                          CF
                        </span>
                      )}
                    </td>
                    <td className="px-3.5 py-2.5 text-muted-foreground text-[11px]">{v.vendedor || '—'}</td>
                    <td className="px-3.5 py-2.5 text-center">
                      <MetodoBadge metodo={v.metodo_pago} />
                    </td>
                    <td className="px-3.5 py-2.5 text-right text-success font-bold tabular-nums">
                      {cop(v.total)}
                    </td>
                    <td className="px-2.5 py-2 text-center">
                      <Button size="sm" onClick={() => setEmitiendo(v)} className="h-7 text-[11px]">
                        <FileText className="size-3 mr-1" />
                        {isMob ? 'FE' : 'Emitir FE'}
                      </Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr className="bg-muted/60 border-t border-border">
                <td colSpan={5} className="px-3.5 py-2.5 text-[10px] text-muted-foreground font-semibold text-right">
                  {ventas.length} venta{ventas.length !== 1 ? 's' : ''} pendiente{ventas.length !== 1 ? 's' : ''}
                </td>
                <td className="px-3.5 py-2.5 text-right text-primary font-bold text-sm tabular-nums">
                  {cop(ventas.reduce((a, v) => a + (Number(v.total) || 0), 0))}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <ModalEmitir
        open={emitiendo != null}
        venta={emitiendo}
        onClose={() => setEmitiendo(null)}
        onEmitida={() => { setEmitiendo(null); cargar(); onEmitida() }}
      />
    </Card>
  )
}

// ── Sección: historial ────────────────────────────────────────────────────────

function Historial({ refreshKey }) {
  const isMob = useIsMobile()
  const { authFetch } = useAuth()
  const authFetchRef = useRef(authFetch)
  authFetchRef.current = authFetch

  const [facturas,   setFacturas]   = useState([])
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState(null)
  const [filtro,     setFiltro]     = useState('todas')
  const [pdfLoading, setPdfLoading] = useState(null)

  const cargar = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await authFetchRef.current(`${API_BASE}/facturacion/lista?limite=100`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setFacturas(await r.json())
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }, [])

  useEffect(() => { cargar() }, [cargar, refreshKey])

  const descargarPDF = async (cufe, numero) => {
    if (!cufe || cufe === '—') return
    setPdfLoading(cufe)
    try {
      const r = await authFetchRef.current(`${API_BASE}/facturacion/pdf/${cufe}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const blob = await r.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `${numero || 'factura'}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      toast.error(`Error descargando PDF: ${e.message}`)
    } finally { setPdfLoading(null) }
  }

  const filtradas = facturas.filter(f => filtro === 'todas' ? true : f.estado === filtro)

  const totalEmitidas = facturas.filter(f => f.estado === 'emitida').length
  const totalMonto    = facturas.filter(f => f.estado === 'emitida').reduce((a, f) => a + (Number(f.total) || 0), 0)
  const totalErrores  = facturas.filter(f => f.estado === 'error').length

  const FILTROS = [
    { k: 'todas',   label: 'Todas',    icon: ClipboardList },
    { k: 'emitida', label: 'Emitidas', icon: CheckCircle2 },
    { k: 'error',   label: 'Errores',  icon: XCircle },
  ]

  return (
    <div className="flex flex-col gap-3">
      {/* KPIs */}
      <div className="flex gap-2.5 flex-wrap">
        <KpiMini label="Facturas emitidas" value={totalEmitidas}  tone="success"     icon={CheckCircle2} />
        <KpiMini label="$ Total facturado" value={cop(totalMonto)} tone="primary"    icon={DollarSign} />
        <KpiMini
          label="Con errores"
          value={totalErrores}
          tone={totalErrores > 0 ? 'destructive' : 'muted'}
          icon={XCircle}
        />
      </div>

      {/* Tabla */}
      <Card className="overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border flex justify-between items-center flex-wrap gap-2.5">
          <SectionTitle icon={Receipt}>Historial de Facturas Electrónicas</SectionTitle>
          <div className="flex gap-1.5 flex-wrap items-center">
            {FILTROS.map(f => {
              const Icon = f.icon
              const active = filtro === f.k
              return (
                <button
                  key={f.k}
                  type="button"
                  onClick={() => setFiltro(f.k)}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] border transition-colors',
                    active
                      ? 'bg-primary-soft border-primary text-primary font-bold'
                      : 'bg-transparent border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
                  )}
                >
                  <Icon className="size-3" />
                  {f.label}
                </button>
              )
            })}
            <Button variant="ghost" size="icon" onClick={cargar} className="h-7 w-7">
              <RefreshCw className="size-3.5" />
            </Button>
          </div>
        </div>

        {loading && <Spinner />}
        {!loading && error && <div className="p-4"><ErrorMsg msg={error} /></div>}
        {!loading && !error && filtradas.length === 0 && (
          <EmptyState msg="No hay facturas electrónicas registradas." />
        )}
        {!loading && !error && filtradas.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/40 border-b border-border">
                <tr>
                  <Th>Número</Th>
                  <Th>Fecha emisión</Th>
                  <Th center>Venta #</Th>
                  <Th>Cliente</Th>
                  <Th right>Total</Th>
                  <Th center>Estado</Th>
                  {!isMob && <Th>CUFE</Th>}
                  <Th center>PDF</Th>
                </tr>
              </thead>
              <tbody>
                {filtradas.map(f => (
                  <tr key={f.id} className="border-b border-border/60 hover:bg-muted/40 transition-colors">
                    <td className="px-3.5 py-2.5 text-primary font-bold whitespace-nowrap">{f.numero || '—'}</td>
                    <td className="px-3.5 py-2.5 text-muted-foreground whitespace-nowrap text-[11px]">{fmtFecha(f.fecha_emision)}</td>
                    <td className="px-3.5 py-2.5 text-center text-muted-foreground">
                      {f.venta_consecutivo != null ? `#${f.venta_consecutivo}` : '—'}
                    </td>
                    <td className="px-3.5 py-2.5 text-foreground max-w-[180px] truncate">
                      {f.cliente_nombre || 'Consumidor Final'}
                    </td>
                    <td className="px-3.5 py-2.5 text-right text-success font-semibold tabular-nums">{cop(f.total)}</td>
                    <td className="px-3.5 py-2.5 text-center">
                      <EstadoBadge estado={f.estado} />
                    </td>
                    {!isMob && (
                      <td className="px-3.5 py-2.5 text-muted-foreground font-mono text-[10px]">
                        {f.estado === 'error'
                          ? <span className="text-destructive text-[11px]">{f.error_msg?.slice(0, 60) || '—'}</span>
                          : (
                            <button
                              type="button"
                              title={f.cufe}
                              onClick={() => copiarCufe(f.cufe)}
                              className="inline-flex items-center gap-1 cursor-copy font-mono text-[11px] hover:text-foreground transition-colors"
                            >
                              {cufeCorto(f.cufe)}
                              <Copy className="size-3 opacity-60" />
                            </button>
                          )
                        }
                      </td>
                    )}
                    <td className="px-2.5 py-2 text-center">
                      {f.cufe && f.estado === 'emitida' ? (
                        <Button
                          variant="outline"
                          size="icon"
                          onClick={() => descargarPDF(f.cufe, f.numero)}
                          disabled={pdfLoading === f.cufe}
                          title="Descargar PDF"
                          className="h-8 w-8"
                        >
                          {pdfLoading === f.cufe
                            ? <Loader2 className="size-3.5 animate-spin" />
                            : <Download className="size-3.5" />}
                        </Button>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-muted/60 border-t border-border">
                  <td colSpan={isMob ? 3 : 4} className="px-3.5 py-2.5 text-[10px] text-muted-foreground font-semibold text-right">
                    {filtradas.length} factura{filtradas.length !== 1 ? 's' : ''}
                  </td>
                  <td className="px-3.5 py-2.5 text-right text-primary font-bold text-sm tabular-nums">
                    {cop(filtradas.filter(f => f.estado === 'emitida').reduce((a, f) => a + (Number(f.total) || 0), 0))}
                  </td>
                  <td colSpan={isMob ? 2 : 3} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function TabFacturacion({ refreshKey }) {
  const [histRefresh, setHistRefresh] = useState(0)

  return (
    <div className="flex flex-col gap-5">
      {/* Banner DIAN */}
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl bg-primary-soft border border-primary/30 text-primary text-xs">
        <Landmark className="size-5 flex-shrink-0" />
        <div>
          <strong>Facturación Electrónica DIAN</strong> vía MATIAS API · UBL 2.1
          <span className="ml-2.5 opacity-75 text-[11px]">
            Las facturas se envían al correo del cliente automáticamente.
          </span>
        </div>
      </div>

      <PanelEmitir onEmitida={() => setHistRefresh(r => r + 1)} />
      <Historial refreshKey={`${refreshKey}-${histRefresh}`} />
    </div>
  )
}
