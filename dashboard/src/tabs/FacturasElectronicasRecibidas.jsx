/**
 * FacturasElectronicasRecibidas.jsx
 * Sección que muestra FE de proveedores pendientes de respuesta DIAN.
 * Migrada a tokens shadcn + sonner toasts (Wave 4 — Fiscal).
 */
import { useState } from 'react'
import { toast } from 'sonner'
import { AlertTriangle, CheckCircle2, Clock, Inbox, Loader2, Mail } from 'lucide-react'
import { useFetch, cop, API_BASE, Spinner } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useRealtime } from '../hooks/useRealtime.js'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog.jsx'
import { Label } from '@/components/ui/label.jsx'
import { cn } from '@/lib/utils'

function BadgeEvento({ fecha, label }) {
  const activo = Boolean(fecha)
  return (
    <div
      className={cn(
        'inline-flex items-center gap-1 text-[10px]',
        activo ? 'text-success' : 'text-muted-foreground',
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full flex-shrink-0',
          activo ? 'bg-success' : 'bg-border',
        )}
      />
      {label}
    </div>
  )
}

function ModalReclamo({ open, cufe, id, onClose, onEnviado }) {
  const { authFetch } = useAuth()
  const [motivo,   setMotivo]   = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error,    setError]    = useState('')

  const cerrar = () => {
    setMotivo(''); setError(''); setEnviando(false)
    onClose()
  }

  const enviar = async () => {
    if (!motivo.trim()) { setError('El motivo es obligatorio'); return }
    setEnviando(true); setError('')
    try {
      const r = await authFetch(`${API_BASE}/proveedores/reclamar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cufe, compra_fiscal_id: id, motivo: motivo.trim() }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      onEnviado(); cerrar()
    } catch (e) {
      setError(e.message)
      setEnviando(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && cerrar()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="inline-flex items-center gap-2">
            <AlertTriangle className="size-4 text-warning" />
            Reclamar factura
          </DialogTitle>
          <DialogDescription>
            Se enviará el evento 031 a la DIAN con el motivo del reclamo.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="motivo-reclamo">Motivo</Label>
          <textarea
            id="motivo-reclamo"
            autoFocus
            value={motivo}
            onChange={e => setMotivo(e.target.value)}
            placeholder="Describe el motivo (ej: mercancía no recibida, diferencia en cantidades...)"
            rows={4}
            className="w-full rounded-md border border-input bg-surface text-foreground text-sm px-3 py-2 resize-y focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          {error && (
            <div className="text-xs text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-2.5 py-1.5">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={cerrar} disabled={enviando}>Cancelar</Button>
          <Button
            onClick={enviar}
            disabled={enviando}
            className="bg-warning text-warning-foreground hover:bg-warning/90"
          >
            {enviando ? <Loader2 className="size-4 mr-1.5 animate-spin" /> : <AlertTriangle className="size-4 mr-1.5" />}
            {enviando ? 'Enviando…' : 'Enviar reclamo'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function FacturasElectronicasRecibidas() {
  const { authFetch } = useAuth()
  const [filtro,       setFiltro]       = useState('pendiente')
  const [refresh,      setRefresh]      = useState(0)
  const [aceptando,    setAceptando]    = useState(null)
  const [modalReclamo, setModalReclamo] = useState(null)

  const { data, loading } = useFetch(
    `/proveedores/facturas-electronicas?estado=${filtro}&limit=30`,
    [filtro, refresh]
  )
  const facturas = data || []

  // ── Tiempo real: recargar cuando llega una factura nueva por Gmail o al reconectar ──
  useRealtime((type) => {
    if (type === 'compra_fiscal_importada' || type === 'reconnected') {
      setRefresh(x => x + 1)
    }
  })

  const aceptar = async (fac) => {
    setAceptando(fac.id)
    try {
      const r = await authFetch(`${API_BASE}/proveedores/aceptar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cufe: fac.cufe_proveedor, compra_fiscal_id: fac.id }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      toast.success('Factura aceptada ante la DIAN (032 + 033)')
      setRefresh(x => x + 1)
    } catch (e) {
      toast.error(e.message)
    } finally {
      setAceptando(null)
    }
  }

  const FILTROS = [
    { key: 'pendiente', label: 'Pendientes', icon: Clock },
    { key: 'aceptada',  label: 'Aceptadas',  icon: CheckCircle2 },
    { key: 'reclamada', label: 'Reclamadas', icon: AlertTriangle },
  ]

  return (
    <div className="mt-9">
      {/* Header */}
      <div className="mb-3.5">
        <div className="inline-flex items-center gap-2 text-sm font-bold text-foreground">
          <Mail className="size-4 text-muted-foreground" />
          Facturas electrónicas recibidas
        </div>
        <div className="text-xs text-muted-foreground mt-0.5">
          FE de proveedores recibidas por correo — requieren respuesta ante la DIAN
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {FILTROS.map(f => {
          const Icon = f.icon
          const active = filtro === f.key
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFiltro(f.key)}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs border transition-colors',
                active
                  ? 'bg-primary-soft border-primary text-primary'
                  : 'bg-transparent border-border text-muted-foreground hover:border-primary/40 hover:text-foreground',
              )}
            >
              <Icon className="size-3" />
              {f.label}
            </button>
          )
        })}
      </div>

      {/* Lista */}
      {loading ? (
        <Spinner />
      ) : facturas.length === 0 ? (
        <div className="border border-dashed border-border rounded-lg py-7 px-4 text-center text-muted-foreground text-xs">
          <Inbox className="size-6 mx-auto mb-2 opacity-40" />
          {filtro === 'pendiente'
            ? 'No hay facturas pendientes de aceptar.'
            : `No hay facturas ${filtro === 'aceptada' ? 'aceptadas' : 'reclamadas'}.`}
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {facturas.map(fac => {
            const enProceso  = aceptando === fac.id
            const estado     = fac.evento_estado
            const estadoCls  =
              estado === 'aceptada'  ? 'text-success'
            : estado === 'reclamada' ? 'text-warning'
            :                          'text-muted-foreground'
            const estadoLbl =
              estado === 'aceptada'  ? 'Aceptada'
            : estado === 'reclamada' ? 'Reclamada'
            :                          'Pendiente'
            const EstadoIcon =
              estado === 'aceptada'  ? CheckCircle2
            : estado === 'reclamada' ? AlertTriangle
            :                          Clock
            return (
              <Card key={fac.id} className="overflow-hidden bg-card border-border">
                {/* Cabecera */}
                <div className="px-4 py-3 border-b border-border flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-semibold text-foreground truncate">
                      {fac.proveedor || 'Proveedor desconocido'}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {fac.numero_factura && `N° ${fac.numero_factura} · `}
                      {fac.fecha} · {fac.costo_total ? cop(fac.costo_total) : '—'}
                    </div>
                  </div>
                  <div className={cn('inline-flex items-center gap-1 text-[10px] font-semibold whitespace-nowrap', estadoCls)}>
                    <EstadoIcon className="size-3" />
                    {estadoLbl}
                  </div>
                </div>

                {/* Badges eventos */}
                <div className="px-4 py-2.5 flex flex-wrap gap-4">
                  <BadgeEvento fecha={fac.evento_030_at} label="030 Acuse" />
                  <BadgeEvento fecha={fac.evento_031_at} label="031 Reclamo" />
                  <BadgeEvento fecha={fac.evento_032_at} label="032 Recibo bien" />
                  <BadgeEvento fecha={fac.evento_033_at} label="033 Aceptación" />
                  {fac.evento_error && (
                    <div className="text-[10px] text-destructive bg-destructive/10 border border-destructive/30 rounded px-2 py-0.5 max-w-full truncate">
                      ⚠ {fac.evento_error}
                    </div>
                  )}
                </div>

                {/* Acciones — solo si está pendiente */}
                {estado === 'pendiente' && (
                  <div className="px-4 pb-3.5 flex gap-2">
                    <Button
                      onClick={() => aceptar(fac)}
                      disabled={enProceso}
                      className="flex-[2] bg-success text-success-foreground hover:bg-success/90 disabled:opacity-60"
                    >
                      {enProceso
                        ? <><Loader2 className="size-4 mr-1.5 animate-spin" /> Enviando…</>
                        : <><CheckCircle2 className="size-4 mr-1.5" /> Aceptar</>}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setModalReclamo({ cufe: fac.cufe_proveedor, id: fac.id })}
                      disabled={enProceso}
                      className="flex-1 border-warning/60 text-warning hover:bg-warning/10 hover:text-warning"
                    >
                      <AlertTriangle className="size-4 mr-1.5" />
                      Reclamar
                    </Button>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {/* Modal reclamo */}
      <ModalReclamo
        open={!!modalReclamo}
        cufe={modalReclamo?.cufe}
        id={modalReclamo?.id}
        onClose={() => setModalReclamo(null)}
        onEnviado={() => {
          setRefresh(x => x + 1)
          toast.warning('Reclamo enviado a la DIAN')
        }}
      />
    </div>
  )
}
