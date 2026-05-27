/**
 * TabProveedores.jsx
 * Gestión de cuentas por pagar, facturas y abonos a proveedores.
 *
 * Migrado a tokens shadcn + sonner (Wave 4 — Fiscal).
 */
import { useState, useCallback, useRef, useEffect } from 'react'
import { toast } from 'sonner'
import {
  Banknote, Camera, CheckCircle2, ChevronDown, Circle, ClipboardList, Clock,
  CreditCard, FileText, Image as ImageIcon, Loader2, Paperclip,
  Plus, Upload, X,
} from 'lucide-react'
import { useFetch, cop, useIsMobile, API_BASE } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { Card } from '@/components/ui/card.jsx'
import KpiCard from '@/components/KpiCard.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog.jsx'
import { cn } from '@/lib/utils'

// ── Helpers ───────────────────────────────────────────────────────────────────

function estadoCls(estado) {
  if (estado === 'pagada')  return 'bg-success/10 border-success/30 text-success'
  if (estado === 'parcial') return 'bg-warning/10 border-warning/30 text-warning'
  return 'bg-primary-soft border-primary/30 text-primary'
}

function estadoLabel(estado) {
  if (estado === 'pagada')  return 'PAGADA'
  if (estado === 'parcial') return 'PARCIAL'
  return 'PENDIENTE'
}

function diasDesde(fecha) {
  if (!fecha) return null
  return Math.floor((Date.now() - new Date(fecha)) / 86400000)
}

function semaforoCls(dias) {
  if (dias === null) return 'bg-muted-foreground'
  if (dias <= 7)  return 'bg-success'
  if (dias <= 30) return 'bg-warning'
  return 'bg-destructive'
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

// ── Barra de progreso de deuda ────────────────────────────────────────────────

function BarraDeuda({ pagado, total }) {
  const pct = total > 0 ? Math.min((pagado / total) * 100, 100) : 0
  const cls = pct >= 100 ? 'bg-success' : pct > 50 ? 'bg-warning' : 'bg-primary'
  return (
    <div className="w-full h-1.5 rounded-full bg-border overflow-hidden">
      <div
        className={cn('h-full rounded-full transition-[width] duration-300', cls)}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ── Factura Card (acordeón) ───────────────────────────────────────────────────

function FacturaCard({ fac, mobile, onAbonar }) {
  const [open, setOpen] = useState(false)
  const dias = diasDesde(fac.fecha)

  return (
    <Card className="overflow-hidden mb-2.5 hover:shadow-md transition-shadow">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={cn(
          'w-full text-left flex items-center gap-2.5 bg-card',
          mobile ? 'p-3' : 'px-4 py-3.5',
        )}
      >
        <div className="flex flex-col items-center gap-1 min-w-[44px]">
          <span className={cn('size-2.5 rounded-full', semaforoCls(dias))} />
          <span className="text-[10px] text-muted-foreground font-bold tracking-wide">{fac.id}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className={cn(
            'font-semibold text-foreground truncate',
            mobile ? 'text-xs' : 'text-sm',
          )}>
            {fac.proveedor}
          </div>
          <div className="text-[11px] text-muted-foreground mt-0.5">
            {fac.descripcion} · {fac.fecha}
          </div>
          <div className="mt-1.5">
            <BarraDeuda pagado={fac.pagado} total={fac.total} />
          </div>
        </div>

        <div className="text-right flex-shrink-0">
          <div className="text-sm font-bold text-foreground tabular-nums">{cop(fac.total)}</div>
          <span className={cn(
            'inline-block text-[9px] font-bold tracking-wide px-1.5 py-0.5 rounded-full mt-1 border',
            estadoCls(fac.estado),
          )}>
            {estadoLabel(fac.estado)}
          </span>
        </div>

        <ChevronDown className={cn(
          'size-3.5 text-muted-foreground transition-transform ml-1 flex-shrink-0',
          open && 'rotate-180',
        )} />
      </button>

      {open && (
        <div className={cn(
          'bg-background border-t border-border',
          mobile ? 'p-3' : 'px-4 py-3.5',
        )}>
          <div className="grid grid-cols-3 gap-2 mb-3">
            {[
              { label: 'Total factura', value: cop(fac.total),     cls: 'text-foreground' },
              { label: 'Pagado',        value: cop(fac.pagado),    cls: 'text-success' },
              { label: 'Pendiente',     value: cop(fac.pendiente), cls: 'text-primary' },
            ].map(({ label, value, cls }) => (
              <div key={label} className="bg-card border border-border rounded-md px-2.5 py-2 text-center">
                <div className="text-[10px] text-muted-foreground mb-0.5">{label}</div>
                <div className={cn('text-xs font-bold tabular-nums', cls)}>{value}</div>
              </div>
            ))}
          </div>

          {fac.abonos?.length > 0 && (
            <div className="mb-3">
              <div className="text-[11px] font-semibold text-muted-foreground mb-1.5 uppercase tracking-wider">
                Abonos
              </div>
              {fac.abonos.map((ab, i) => (
                <div key={i} className="flex justify-between items-center gap-2 py-1.5 border-b border-border/60 text-xs">
                  <span className="text-muted-foreground">{ab.fecha}</span>
                  <span className="text-success font-semibold tabular-nums">+{cop(ab.monto)}</span>
                  {ab.foto_url && (
                    <a
                      href={ab.foto_url} target="_blank" rel="noreferrer"
                      className="text-primary text-[11px] hover:underline inline-flex items-center gap-1"
                    >
                      <Paperclip className="size-3" /> comprobante
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}

          {fac.foto_url && (
            <a
              href={fac.foto_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-[11px] text-primary hover:underline px-2.5 py-1 rounded-md border border-primary/40 bg-primary-soft mb-2.5"
            >
              <FileText className="size-3" /> Ver factura original
            </a>
          )}

          {fac.estado !== 'pagada' && (
            <Button onClick={() => onAbonar(fac)} size="sm" className="h-8 text-xs">
              <Banknote className="size-3.5 mr-1.5" />
              Registrar abono
            </Button>
          )}
        </div>
      )}
    </Card>
  )
}

// ── Selector de foto ──────────────────────────────────────────────────────────

function SelectorFoto({ label, onChange, preview, onClear }) {
  const ref = useRef(null)
  return (
    <div className="space-y-1.5 mb-3">
      <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</Label>
      {preview ? (
        <div className="relative inline-block w-full">
          <img
            src={preview} alt="preview"
            className="w-full max-h-36 object-cover rounded-md border border-border"
          />
          <button
            type="button"
            onClick={onClear}
            aria-label="Quitar foto"
            className="absolute top-1 right-1 bg-foreground/70 text-background border-none rounded-full size-5 cursor-pointer inline-flex items-center justify-center"
          >
            <X className="size-3" aria-hidden="true" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => ref.current?.click()}
          className="w-full border-2 border-dashed border-border rounded-md px-3 py-4 text-center text-muted-foreground text-xs hover:border-primary hover:bg-primary-soft transition-colors"
        >
          <Camera className="size-4 mx-auto mb-1" />
          Toca para adjuntar foto o PDF
          <div className="text-[10px] mt-1 text-muted-foreground">
            JPG · PNG · PDF — máx 10 MB
          </div>
        </button>
      )}
      <input ref={ref} type="file" accept="image/*,application/pdf" className="hidden" onChange={onChange} />
    </div>
  )
}

// ── Indicador de paso ─────────────────────────────────────────────────────────

function StepDots({ paso, total = 2 }) {
  return (
    <div className="flex gap-1.5">
      {Array.from({ length: total }, (_, i) => i + 1).map(n => (
        <span
          key={n}
          className={cn(
            'size-2 rounded-full transition-colors',
            paso >= n ? 'bg-primary' : 'bg-border',
          )}
        />
      ))}
    </div>
  )
}

// ── Modal Nueva Factura ───────────────────────────────────────────────────────

function ModalNuevaFactura({ open, onClose, onCreada }) {
  const { authFetch } = useAuth()
  const [form, setForm] = useState({ proveedor: '', total: '', descripcion: '', fecha: '' })
  const [foto, setFoto] = useState(null)
  const [preview, setPreview] = useState(null)
  const [paso, setPaso] = useState(1)
  const [estado, setEstado] = useState('idle')
  const [facCreada, setFacCreada] = useState(null)
  const [err, setErr] = useState('')

  const [comprasSinFac, setComprasSinFac] = useState([])
  const [comprasSel,    setComprasSel]    = useState(new Set())
  const [cargandoComp,  setCargandoComp]  = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  // Reset al cerrar
  useEffect(() => {
    if (!open) {
      setForm({ proveedor: '', total: '', descripcion: '', fecha: '' })
      setFoto(null); setPreview(null); setPaso(1); setEstado('idle')
      setFacCreada(null); setErr('')
      setComprasSinFac([]); setComprasSel(new Set())
    }
  }, [open])

  useEffect(() => {
    const prov = form.proveedor.trim()
    if (prov.length < 3) { setComprasSinFac([]); setComprasSel(new Set()); return }
    const timer = setTimeout(async () => {
      setCargandoComp(true)
      try {
        const r = await authFetch(`${API_BASE}/proveedores/compras-sin-factura?proveedor=${encodeURIComponent(prov)}`)
        const d = await r.json()
        if (r.ok) setComprasSinFac(Array.isArray(d) ? d : [])
        else setComprasSinFac([])
      } catch { setComprasSinFac([]) }
      finally { setCargandoComp(false) }
    }, 600)
    return () => clearTimeout(timer)
  }, [form.proveedor])

  const toggleCompra = id =>
    setComprasSel(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })

  const seleccionarFoto = e => {
    const file = e.target.files[0]
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { setErr('La foto no puede superar 10 MB'); return }
    setFoto(file)
    setPreview(file.type.startsWith('image/') ? URL.createObjectURL(file) : null)
    setErr('')
  }

  const limpiarFoto = () => { setFoto(null); setPreview(null) }

  const guardarDatos = async () => {
    if (!form.proveedor.trim()) { setErr('El proveedor es obligatorio'); return }
    if (!form.total || isNaN(Number(form.total))) { setErr('El total debe ser un número'); return }
    setErr(''); setEstado('saving')
    try {
      const r = await authFetch(`${API_BASE}/proveedores/facturas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          proveedor:   form.proveedor.trim(),
          total:       Number(form.total),
          descripcion: form.descripcion.trim() || 'Sin descripción',
          fecha:       form.fecha || undefined,
          compras_ids: [...comprasSel],
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setFacCreada(d.factura)
      setEstado('idle')
      setPaso(2)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  const finalizarConFoto = async () => {
    if (!foto) {
      toast.success('Factura creada')
      onCreada(facCreada); onClose(); return
    }
    setEstado('uploading')
    try {
      const fd = new FormData()
      fd.append('foto', foto)
      const r = await authFetch(`${API_BASE}/proveedores/facturas/${facCreada.id}/foto`, {
        method: 'POST', body: fd,
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error subiendo foto')
      setEstado('ok')
      toast.success('Factura creada con foto')
      setTimeout(() => { onCreada({ ...facCreada, foto_url: d.url }); onClose() }, 500)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <DialogTitle className="inline-flex items-center gap-2 flex-1">
              <FileText className="size-4 text-primary" />
              {paso === 1 ? 'Nueva Factura' : `${facCreada?.id} creada`}
            </DialogTitle>
            <StepDots paso={paso} />
          </div>
        </DialogHeader>

        {paso === 1 && (
          <>
            <div className="space-y-1">
              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">Proveedor *</Label>
              <Input value={form.proveedor} onChange={e => set('proveedor', e.target.value)} placeholder="Ej: Pinturas Davinci" />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">Total de la factura *</Label>
              <Input value={form.total} onChange={e => set('total', e.target.value)} placeholder="350000" type="number" />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">Descripción (opcional)</Label>
              <Input value={form.descripcion} onChange={e => set('descripcion', e.target.value)} placeholder="Ej: surtido brochas y rodillos" />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">Fecha (por defecto hoy)</Label>
              <Input value={form.fecha} onChange={e => set('fecha', e.target.value)} type="date" />
            </div>

            {(cargandoComp || comprasSinFac.length > 0) && (
              <div className="space-y-1.5">
                <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  Compras sin factura{comprasSinFac.length > 0 ? ` (${comprasSinFac.length})` : ''}
                </Label>
                {cargandoComp ? (
                  <div className="text-muted-foreground text-xs py-2 inline-flex items-center gap-1.5">
                    <Loader2 className="size-3 animate-spin" /> Buscando…
                  </div>
                ) : (
                  <div className="border border-border rounded-md max-h-44 overflow-y-auto">
                    {comprasSinFac.map(c => {
                      const sel = comprasSel.has(c.id)
                      return (
                        <label key={c.id} className={cn(
                          'flex items-center gap-2 px-3 py-2 cursor-pointer border-b border-border/40 last:border-0',
                          sel && 'bg-primary-soft',
                        )}>
                          <input
                            type="checkbox"
                            checked={sel}
                            onChange={() => toggleCompra(c.id)}
                            className="accent-primary flex-shrink-0"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-xs text-foreground font-medium truncate">{c.producto}</div>
                            <div className="text-[10px] text-muted-foreground">
                              {c.fecha} · {c.cantidad} uds · {cop(c.costo_total)}
                            </div>
                          </div>
                        </label>
                      )
                    })}
                  </div>
                )}
                {comprasSel.size > 0 && (
                  <div className="text-[11px] text-primary">
                    {comprasSel.size} compra(s) seleccionada(s) → se vincularán a esta factura
                  </div>
                )}
              </div>
            )}

            {err && <ErrorMsg msg={err} />}

            <Button onClick={guardarDatos} disabled={estado === 'saving'} className="w-full">
              {estado === 'saving' && <Loader2 className="size-4 mr-1.5 animate-spin" />}
              {estado === 'saving' ? 'Guardando…' : 'Siguiente → Foto'}
            </Button>
          </>
        )}

        {paso === 2 && (
          <>
            <div className="rounded-md bg-primary-soft border border-primary/30 px-3 py-2.5 text-xs">
              <div className="text-foreground font-semibold">{facCreada?.proveedor}</div>
              <div className="text-muted-foreground mt-0.5">
                {facCreada?.descripcion} · {cop(facCreada?.total)}
              </div>
            </div>

            <SelectorFoto
              label="Foto de la factura (opcional)"
              onChange={seleccionarFoto}
              preview={preview}
              onClear={limpiarFoto}
            />
            {foto && !preview && (
              <div className="text-[11px] text-muted-foreground inline-flex items-center gap-1.5">
                <Paperclip className="size-3" /> {foto.name}
              </div>
            )}

            {err && <ErrorMsg msg={err} />}

            <Button
              onClick={finalizarConFoto}
              disabled={estado === 'uploading' || estado === 'ok'}
              className="w-full"
            >
              {estado === 'uploading'
                ? <><Upload className="size-4 mr-1.5 animate-pulse" /> Subiendo a Drive…</>
                : estado === 'ok'
                  ? <><CheckCircle2 className="size-4 mr-1.5" /> Listo</>
                  : foto
                    ? 'Guardar con foto'
                    : 'Guardar sin foto'}
            </Button>

            {!foto && estado === 'idle' && (
              <button
                type="button"
                onClick={() => { onCreada(facCreada); onClose() }}
                className="w-full mt-1 py-2 text-muted-foreground text-xs hover:text-foreground transition-colors"
              >
                Omitir foto por ahora
              </button>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ── Modal Abono ───────────────────────────────────────────────────────────────

function ModalAbono({ factura, open, onClose, onAbonado }) {
  const { authFetch } = useAuth()
  const [monto, setMonto] = useState('')
  const [foto, setFoto] = useState(null)
  const [preview, setPreview] = useState(null)
  const [paso, setPaso] = useState(1)
  const [estado, setEstado] = useState('idle')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open) {
      setMonto(''); setFoto(null); setPreview(null)
      setPaso(1); setEstado('idle'); setErr('')
    }
  }, [open])

  if (!factura) return null

  const seleccionarFoto = e => {
    const file = e.target.files[0]
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { setErr('La foto no puede superar 10 MB'); return }
    setFoto(file)
    if (file.type.startsWith('image/')) setPreview(URL.createObjectURL(file))
    setErr('')
  }

  const registrarAbono = async () => {
    const montoNum = Number(monto)
    if (!monto || isNaN(montoNum) || montoNum <= 0) {
      setErr('El monto debe ser mayor a 0'); return
    }
    if (montoNum > factura.pendiente) {
      setErr(`El abono supera el pendiente. Máximo: ${cop(factura.pendiente)}`)
      return
    }
    setErr(''); setEstado('saving')
    try {
      const r = await authFetch(`${API_BASE}/proveedores/abonos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fac_id: factura.id, monto: Number(monto) }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('idle'); setPaso(2)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  const finalizarConFoto = async () => {
    if (!foto) {
      toast.success('Abono registrado')
      onAbonado(); onClose(); return
    }
    setEstado('uploading')
    try {
      const fd = new FormData()
      fd.append('foto', foto)
      const r = await authFetch(`${API_BASE}/proveedores/abonos/${factura.id}/foto`, {
        method: 'POST', body: fd,
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error subiendo comprobante')
      setEstado('ok')
      toast.success('Abono registrado con comprobante')
      setTimeout(() => { onAbonado(); onClose() }, 500)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <DialogTitle className="inline-flex items-center gap-2 flex-1">
              <Banknote className="size-4 text-primary" />
              {paso === 1 ? 'Registrar Abono' : 'Abono registrado'}
            </DialogTitle>
            <StepDots paso={paso} />
          </div>
          <DialogDescription>{factura.id} · {factura.proveedor}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-2">
          {[
            { label: 'Total factura', value: cop(factura.total),     cls: 'text-foreground' },
            { label: 'Pendiente',     value: cop(factura.pendiente), cls: 'text-primary' },
          ].map(({ label, value, cls }) => (
            <div key={label} className="bg-background border border-border rounded-md px-2.5 py-2 text-center">
              <div className="text-[10px] text-muted-foreground">{label}</div>
              <div className={cn('text-sm font-bold tabular-nums', cls)}>{value}</div>
            </div>
          ))}
        </div>

        {paso === 1 && (
          <>
            <div className="space-y-1">
              <Label className="text-[11px] uppercase tracking-wider text-muted-foreground">Monto del abono</Label>
              <Input
                value={monto} onChange={e => setMonto(e.target.value)}
                placeholder={`Máx. ${cop(factura.pendiente)}`}
                type="number"
              />
            </div>
            {err && <ErrorMsg msg={err} />}
            <Button onClick={registrarAbono} disabled={estado === 'saving'} className="w-full">
              {estado === 'saving' && <Loader2 className="size-4 mr-1.5 animate-spin" />}
              {estado === 'saving' ? 'Registrando…' : 'Siguiente → Comprobante'}
            </Button>
          </>
        )}

        {paso === 2 && (
          <>
            <SelectorFoto
              label="Foto del comprobante de pago (opcional)"
              onChange={seleccionarFoto}
              preview={preview}
              onClear={() => { setFoto(null); setPreview(null) }}
            />
            {foto && !preview && (
              <div className="text-[11px] text-muted-foreground inline-flex items-center gap-1.5">
                <Paperclip className="size-3" /> {foto.name}
              </div>
            )}
            {err && <ErrorMsg msg={err} />}
            <Button
              onClick={finalizarConFoto}
              disabled={estado === 'uploading' || estado === 'ok'}
              className="w-full"
            >
              {estado === 'uploading'
                ? <><Upload className="size-4 mr-1.5 animate-pulse" /> Subiendo a Drive…</>
                : estado === 'ok'
                  ? <><CheckCircle2 className="size-4 mr-1.5" /> Listo</>
                  : foto
                    ? 'Guardar con comprobante'
                    : 'Guardar sin foto'}
            </Button>
            {!foto && estado === 'idle' && (
              <button
                type="button"
                onClick={() => { onAbonado(); onClose() }}
                className="w-full mt-1 py-2 text-muted-foreground text-xs hover:text-foreground transition-colors"
              >
                Omitir comprobante por ahora
              </button>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ── Resumen por proveedor ─────────────────────────────────────────────────────

function ResumenProveedores({ data }) {
  if (!data?.por_proveedor) return null
  const provs = Object.entries(data.por_proveedor)
    .filter(([, v]) => v.deuda > 0)
    .sort(([, a], [, b]) => b.deuda - a.deuda)

  if (!provs.length) return null

  return (
    <Card className="p-3.5 mb-4">
      <div className="text-[11px] font-bold text-muted-foreground mb-2.5 tracking-wider uppercase">
        Deuda por proveedor
      </div>
      {provs.map(([nombre, v]) => {
        const pct = (v.deuda / (v.deuda + v.pagado || 1)) * 100
        const cls = pct > 70 ? 'bg-primary' : pct > 40 ? 'bg-warning' : 'bg-success'
        return (
          <div key={nombre} className="mb-2.5 last:mb-0">
            <div className="flex justify-between mb-1">
              <span className="text-xs text-foreground font-medium">{nombre}</span>
              <span className="text-xs text-primary font-bold tabular-nums">{cop(v.deuda)}</span>
            </div>
            <div className="h-1 rounded-full bg-border overflow-hidden">
              <div className={cn('h-full rounded-full', cls)} style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
    </Card>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function TabProveedores({ refreshKey }) {
  const mobile = useIsMobile()

  const [localRefresh, setLocalRefresh] = useState(0)
  const [filtro, setFiltro]             = useState('pendientes')
  const [modalFactura, setModalFactura] = useState(false)
  const [modalAbono,   setModalAbono]   = useState(null)

  const reload = () => setLocalRefresh(r => r + 1)

  const { data, loading, error } = useFetch(
    `/proveedores/facturas?solo_pendientes=${filtro === 'pendientes'}`,
    [refreshKey, localRefresh, filtro]
  )
  const { data: resumen } = useFetch('/proveedores/resumen', [refreshKey, localRefresh])

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error cargando facturas: ${error}`} />

  const facturas    = data?.facturas || []
  const totalDeuda  = data?.total_deuda  || 0
  const totalPagado = data?.total_pagado || 0
  const nPend       = data?.n_pendientes || 0
  const nParc       = data?.n_parciales  || 0

  return (
    <div className="space-y-4">
      {/* Titulo lo provee HeaderBar global (lee de routes.jsx).
          Aqui solo el CTA primario para la accion mas comun. */}
      <div className="flex items-center justify-end">
        <Button size="sm" onClick={() => setModalFactura(true)}>
          <Plus className="size-3.5 mr-1.5" /> Nueva Factura
        </Button>
      </div>

      <div className={cn(
        'grid gap-4',
        mobile ? 'grid-cols-2' : 'grid-cols-4',
      )}>
        <KpiCard label="Deuda total"  value={cop(totalDeuda)}  icon={CreditCard}   tone="primary" headerBand />
        <KpiCard label="Total pagado" value={cop(totalPagado)} icon={CheckCircle2} tone="success" headerBand />
        <KpiCard label="Pendientes"   value={nPend}            icon={Circle}       tone="primary" headerBand />
        <KpiCard label="En proceso"   value={nParc}            icon={Clock}        tone="warning" headerBand />
      </div>

      <ResumenProveedores data={resumen} />

      <div className="flex gap-1.5 flex-wrap">
        {[
          { k: 'pendientes', label: 'Pendientes', icon: Clock },
          { k: 'todas',      label: 'Todas',      icon: ClipboardList },
        ].map(({ k, label, icon: Icon }) => {
          const active = filtro === k
          return (
            <button
              key={k}
              type="button"
              onClick={() => setFiltro(k)}
              className={cn(
                'inline-flex items-center gap-1.5 px-3.5 py-1 rounded-full text-[11px] border transition-colors',
                active
                  ? 'bg-primary-soft border-primary text-primary font-bold'
                  : 'bg-transparent border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
              )}
            >
              <Icon className="size-3" />
              {label}
            </button>
          )
        })}
      </div>

      {facturas.length === 0 ? (
        <Card className="p-8 text-center">
          <FileText className="size-8 mx-auto mb-2.5 text-muted-foreground" />
          <div className="text-muted-foreground text-sm">
            {filtro === 'pendientes' ? 'No hay facturas pendientes' : 'No hay facturas registradas'}
          </div>
          <div className="text-muted-foreground text-xs mt-1.5">
            Usa "/factura Proveedor Total" en Telegram o el botón "Nueva Factura"
          </div>
        </Card>
      ) : (
        facturas.map(fac => (
          <FacturaCard
            key={fac.id} fac={fac} mobile={mobile}
            onAbonar={f => setModalAbono(f)}
          />
        ))
      )}

      <div className="px-3.5 py-2.5 rounded-md bg-primary-soft border border-primary/20 text-[11px] text-muted-foreground leading-relaxed">
        <strong className="text-foreground">Almacenamiento:</strong> Las fotos de facturas y comprobantes se guardan en Drive →{' '}
        <code className="text-primary">Facturas_Proveedores / Proveedor</code>{' '}
        · Los abonos se registran automáticamente en el histórico diario.
      </div>

      <ModalNuevaFactura
        open={modalFactura}
        onClose={() => setModalFactura(false)}
        onCreada={() => reload()}
      />
      <ModalAbono
        open={modalAbono != null}
        factura={modalAbono}
        onClose={() => setModalAbono(null)}
        onAbonado={() => reload()}
      />
    </div>
  )
}
