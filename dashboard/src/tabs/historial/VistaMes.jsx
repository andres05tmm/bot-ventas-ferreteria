/**
 * VistaMes — calendario heatmap mensual + desglose por día.
 * Antes vivía como TabHistoricoVentas.jsx; absorbida por el wrapper
 * TabHistorial con Tabs internos Día/Mes (Fase D).
 */
import { useState, useEffect, useCallback } from 'react'
import { toast } from 'sonner'
import {
  Calendar, ChevronLeft, ChevronRight, CreditCard, Download,
  Edit3, FileSpreadsheet, Loader2, RefreshCw, Save, Smartphone, Trophy,
  TrendingUp, Wallet, X,
} from 'lucide-react'
import { API_BASE, cop, useIsMobile } from '../../components/shared.jsx'
import { useAuth } from '../../hooks/useAuth.js'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { cn } from '@/lib/utils'

const MESES = [
  'Enero','Febrero','Marzo','Abril','Mayo','Junio',
  'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre',
]
const DIAS_SEMANA = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom']

function diasEnMes(mes, año) { return new Date(año, mes, 0).getDate() }
function formatFecha(año, mes, dia) {
  return `${año}-${String(mes).padStart(2,'0')}-${String(dia).padStart(2,'0')}`
}
function intensidad(valor, max) {
  if (!max || !valor) return 0
  return Math.min(valor / max, 1)
}
function formatK(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2).replace('.', ',')}M`
  if (n >= 100_000) return `${Math.round(n / 1_000)}k`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace('.', ',')}k`
  return String(n)
}

// ── KPI tokenizado ───────────────────────────────────────────────────────────

function KpiCard({ label, value, icon: Icon, tone = 'primary' }) {
  const toneCls = {
    primary: 'text-primary',
    success: 'text-success',
    warning: 'text-warning',
    info:    'text-foreground',
    muted:   'text-muted-foreground',
  }[tone] || 'text-primary'
  const bgIcon = {
    primary: 'bg-primary-soft',
    success: 'bg-success/10',
    warning: 'bg-warning/10',
    info:    'bg-muted',
    muted:   'bg-muted',
  }[tone] || 'bg-primary-soft'
  return (
    <Card className="p-3.5">
      <div className="flex justify-between items-start gap-2">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
            {label}
          </div>
          <div className="text-lg font-bold text-foreground tabular-nums truncate">{value}</div>
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

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function VistaMes() {
  const mobile = useIsMobile()
  const hoy = new Date()
  const { authFetch } = useAuth()

  const [año, setAño]   = useState(hoy.getFullYear())
  const [mes, setMes]   = useState(hoy.getMonth() + 1)
  const [celdas, setCeldas]       = useState({})
  const [diario, setDiario]       = useState({})
  const [guardando, setGuardando] = useState(false)
  const [syncing, setSyncing]     = useState(false)
  const [loading, setLoading]     = useState(false)
  const [editMode, setEditMode]   = useState(false)

  const cargar = useCallback(() => {
    setLoading(true)
    Promise.all([
      authFetch(`${API_BASE}/historico/ventas?año=${año}&mes=${mes}`).then(r => r.ok ? r.json() : {}),
      authFetch(`${API_BASE}/historico/diario?año=${año}&mes=${mes}`).then(r => r.ok ? r.json() : {}),
    ])
      .then(([ventas, diar]) => {
        const str = {}
        Object.entries(ventas).forEach(([k, v]) => {
          if (v && v > 0) str[k] = String(v)
        })
        setCeldas(str)
        setDiario(diar || {})
      })
      .catch(() => { setCeldas({}); setDiario({}) })
      .finally(() => setLoading(false))
  }, [año, mes])

  useEffect(() => { cargar() }, [cargar])

  const valores    = Object.values(celdas).map(v => parseInt(v) || 0)
  const totalMes   = valores.reduce((a, b) => a + b, 0)
  const diasVenta  = valores.filter(v => v > 0).length
  const promedio   = diasVenta ? Math.round(totalMes / diasVenta) : 0
  const maxDia     = Math.max(...valores, 1)
  const mejorDia   = valores.length ? Math.max(...valores) : 0

  const totalEfectivo      = Object.values(diario).reduce((a, d) => a + (d.efectivo || 0), 0)
  const totalTransferencia = Object.values(diario).reduce((a, d) => a + (d.transferencia || 0), 0)
  const totalDatafono      = Object.values(diario).reduce((a, d) => a + (d.datafono || 0), 0)
  const hayDesglose        = totalEfectivo > 0 || totalTransferencia > 0 || totalDatafono > 0

  const filasTabla = Object.entries(diario)
    .filter(([, d]) => d.ventas > 0)
    .sort(([a], [b]) => b.localeCompare(a))

  const numDias   = diasEnMes(mes, año)
  const primerDia = new Date(año, mes - 1, 1).getDay()
  const offset    = primerDia === 0 ? 6 : primerDia - 1
  const hoyStr    = formatFecha(hoy.getFullYear(), hoy.getMonth() + 1, hoy.getDate())
  const esMesActual = año === hoy.getFullYear() && mes === (hoy.getMonth() + 1)

  function cambiar(fecha, valor) {
    const solo = valor.replace(/[^0-9]/g, '')
    setCeldas(prev => ({ ...prev, [fecha]: solo }))
  }

  async function guardar() {
    setGuardando(true)
    const datos = {}
    Object.entries(celdas).forEach(([k, v]) => {
      const n = parseInt(v)
      if (n > 0) datos[k] = n
    })
    try {
      const res = await authFetch(`${API_BASE}/historico/ventas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ año, mes, datos }),
      })
      const json = await res.json()
      if (json.ok) {
        toast.success(`${json.registros} días guardados en Drive`)
        setEditMode(false)
      } else {
        toast.error(json.error || 'Error al guardar')
      }
    } catch {
      toast.error('No se pudo conectar con el servidor')
    } finally { setGuardando(false) }
  }

  async function syncRango() {
    setSyncing(true)
    try {
      const res  = await authFetch(`${API_BASE}/historico/sync-rango?dias=60`, { method: 'POST' })
      const json = await res.json()
      if (json.ok) {
        toast.success(`${json.nuevos} días nuevos, ${json.actualizados} actualizados`)
        cargar()
      } else {
        toast.error(json.detail || 'Error al sincronizar')
      }
    } catch {
      toast.error('No se pudo conectar con el servidor')
    } finally { setSyncing(false) }
  }

  async function sincronizarDesdeExcel() {
    setSyncing(true)
    try {
      const res  = await authFetch(`${API_BASE}/historico/sincronizar-excel`, { method: 'POST' })
      const json = await res.json()
      if (json.ok) {
        toast.success(`${json.registros} días importados desde Excel de Drive`)
        cargar()
      } else {
        toast.error(json.error || 'Error al sincronizar')
      }
    } catch {
      toast.error('No se pudo conectar con el servidor')
    } finally { setSyncing(false) }
  }

  function mesAnterior() {
    if (mes === 1) { setMes(12); setAño(a => a - 1) }
    else setMes(m => m - 1)
  }
  function mesSiguiente() {
    if (mes === 12) { setMes(1); setAño(a => a + 1) }
    else setMes(m => m + 1)
  }

  // Devuelve la opacidad para el heatmap (0..1) según intensidad
  function heatOpacity(val) {
    const i = intensidad(val, maxDia)
    if (i === 0) return 0
    return 0.08 + i * 0.22
  }

  return (
    <div className={cn('mx-auto max-w-3xl', mobile ? 'px-2' : '')}>

      {/* Nav de mes — el título global lo provee el wrapper TabHistorial */}
      <div className="flex items-center justify-end mb-5 flex-wrap gap-2.5">
        <div className="flex items-center gap-1.5">
          <Button variant="outline" size="icon" onClick={mesAnterior} className="h-8 w-8"
                  aria-label="Mes anterior">
            <ChevronLeft className="size-4" aria-hidden="true" />
          </Button>
          <div className="flex gap-1.5 items-center bg-card border border-border rounded-md px-3 py-1.5">
            <select
              value={mes}
              onChange={e => setMes(Number(e.target.value))}
              className="bg-transparent border-0 text-foreground text-sm font-semibold cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
            >
              {MESES.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
            </select>
            <select
              value={año}
              onChange={e => setAño(Number(e.target.value))}
              className="bg-transparent border-0 text-foreground text-sm font-semibold cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
            >
              {[2024,2025,2026,2027].map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <Button variant="outline" size="icon" onClick={mesSiguiente} className="h-8 w-8"
                  aria-label="Mes siguiente">
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>

          {esMesActual && (
            <span className="text-[9px] text-primary font-bold bg-primary-soft px-2 py-0.5 rounded-full tracking-wider ml-1">
              MES ACTUAL
            </span>
          )}
        </div>
      </div>

      {/* KPIs */}
      <div className={cn('grid gap-2.5 mb-5', mobile ? 'grid-cols-2' : 'grid-cols-4')}>
        <KpiCard label="Total del mes"  value={cop(totalMes)} icon={Wallet}     tone="primary" />
        <KpiCard label="Días con venta" value={diasVenta}     icon={Calendar}   tone="warning" />
        <KpiCard label="Promedio / día" value={cop(promedio)} icon={TrendingUp} tone="success" />
        <KpiCard label="Mejor día"      value={cop(mejorDia)} icon={Trophy}     tone="info" />
      </div>

      {/* Calendario */}
      <Card className={cn('mb-4', mobile ? 'p-2.5' : 'p-4')}>
        {loading ? (
          <div className="flex justify-center py-10">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-7 gap-1 mb-2">
              {DIAS_SEMANA.map(d => (
                <div key={d} className="text-center text-[10px] font-semibold text-muted-foreground py-1 tracking-wider uppercase">
                  {d}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: offset }).map((_, i) => <div key={`e${i}`} />)}
              {Array.from({ length: numDias }, (_, i) => i + 1).map(dia => {
                const fecha    = formatFecha(año, mes, dia)
                const valor    = celdas[fecha] ?? ''
                const valNum   = parseInt(valor) || 0
                const tieneVal = valNum > 0
                const esHoy    = fecha === hoyStr
                const esFuturo = new Date(año, mes - 1, dia) > hoy

                return (
                  <DiaCell
                    key={dia}
                    dia={dia}
                    valor={valor}
                    tieneVal={tieneVal}
                    esHoy={esHoy}
                    esFuturo={esFuturo}
                    editMode={editMode}
                    heatOpacity={heatOpacity(valNum)}
                    onChange={v => cambiar(fecha, v)}
                    mobile={mobile}
                  />
                )
              })}
            </div>

            {/* Leyenda heatmap */}
            <div className="flex items-center justify-end gap-1.5 mt-3 pt-2.5 border-t border-border">
              <span className="text-[9px] text-muted-foreground">Menos</span>
              {[0, 0.2, 0.4, 0.7, 1].map((lv, i) => (
                <div
                  key={i}
                  className="size-3 rounded-sm border border-border"
                  style={{
                    background: lv === 0
                      ? 'hsl(var(--bg-surface))'
                      : `hsl(var(--accent) / ${(0.08 + lv * 0.22).toFixed(3)})`,
                  }}
                />
              ))}
              <span className="text-[9px] text-muted-foreground">Más</span>
            </div>
          </>
        )}
      </Card>

      {/* Métodos de pago */}
      {hayDesglose && (
        <div className={cn('grid gap-2.5 mb-4', mobile ? 'grid-cols-2' : 'grid-cols-3')}>
          <KpiCard label="Efectivo"      value={cop(totalEfectivo)}      icon={Wallet}      tone="success" />
          <KpiCard label="Transferencia" value={cop(totalTransferencia)} icon={Smartphone}  tone="info" />
          <KpiCard label="Datáfono"      value={cop(totalDatafono)}      icon={CreditCard}  tone="warning" />
        </div>
      )}

      {/* Tabla desglose */}
      {filasTabla.length > 0 && (
        <Card className="overflow-hidden mb-4">
          <div className="px-3.5 py-2.5 border-b border-border flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground inline-flex items-center gap-2">
              <FileSpreadsheet className="size-4 text-muted-foreground" />
              Desglose por día
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/40">
                <tr>
                  {['Fecha','Ventas','Efectivo','Transf.','Datáfono','Gastos','Caja Neta'].map((h, i) => (
                    <th
                      key={h}
                      className={cn(
                        'px-2.5 py-2 text-[10px] font-semibold text-muted-foreground tracking-wider whitespace-nowrap',
                        i === 0 ? 'text-left' : 'text-right',
                      )}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filasTabla.map(([fecha, d], idx) => {
                  const cajaNeta = (d.ventas || 0) - (d.gastos || 0) - (d.abonos_proveedores || 0)
                  return (
                    <tr key={fecha} className={cn(idx % 2 === 1 && 'bg-muted/40', 'hover:bg-muted/60')}>
                      <td className="px-2.5 py-1.5 text-muted-foreground font-medium">
                        {fecha.slice(5).replace('-', '/')}
                      </td>
                      <Td val={d.ventas}        tone="foreground" />
                      <Td val={d.efectivo}      tone="success" />
                      <Td val={d.transferencia} tone="info" />
                      <Td val={d.datafono}      tone="warning" />
                      <Td val={d.gastos}        tone={d.gastos > 0 ? 'primary' : 'muted'} />
                      <Td val={cajaNeta}        tone={cajaNeta >= 0 ? 'success' : 'primary'} bold />
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border bg-muted/60">
                  <td className="px-2.5 py-2 font-bold text-foreground text-[11px]">TOTAL</td>
                  <Td val={totalMes}           tone="foreground" bold />
                  <Td val={totalEfectivo}      tone="success"    bold />
                  <Td val={totalTransferencia} tone="info"       bold />
                  <Td val={totalDatafono}      tone="warning"    bold />
                  <Td val={Object.values(diario).reduce((a, d) => a + (d.gastos || 0), 0)} tone="primary" bold />
                  <Td val={Object.values(diario).reduce((a, d) => a + (d.ventas || 0) - (d.gastos || 0) - (d.abonos_proveedores || 0), 0)} tone="success" bold />
                </tr>
              </tfoot>
            </table>
          </div>
        </Card>
      )}

      {/* Acciones */}
      <Card className="p-3.5">
        <div className="flex flex-wrap gap-2 items-center">
          <Button
            size="sm"
            variant={editMode ? 'default' : 'outline'}
            onClick={() => setEditMode(!editMode)}
            className="h-8 text-[11px]"
          >
            {editMode
              ? <><X className="size-3 mr-1.5" /> Cancelar edición</>
              : <><Edit3 className="size-3 mr-1.5" /> Editar manualmente</>}
          </Button>

          {editMode && (
            <Button size="sm" onClick={guardar} disabled={guardando} className="h-8 text-[11px]">
              {guardando
                ? <><Loader2 className="size-3 mr-1.5 animate-spin" /> Guardando…</>
                : <><Save className="size-3 mr-1.5" /> Guardar {MESES[mes-1]}</>}
            </Button>
          )}

          <div className="flex-1" />

          <Button
            size="sm" variant="outline" onClick={syncRango} disabled={syncing}
            title="Importa totales de los últimos 60 días desde el registro de ventas"
            className="h-8 text-[11px]"
          >
            {syncing
              ? <><Loader2 className="size-3 mr-1.5 animate-spin" /> Sincronizando…</>
              : <><RefreshCw className="size-3 mr-1.5" /> Sync desde ventas</>}
          </Button>

          <Button
            size="sm" variant="outline" onClick={sincronizarDesdeExcel} disabled={syncing}
            title="Importar desde historico_ventas.xlsx en Drive"
            className="h-8 text-[11px]"
          >
            <Download className="size-3 mr-1.5" /> Desde Excel
          </Button>
        </div>

        <p className="text-[10px] text-muted-foreground mt-2.5 text-center leading-relaxed">
          El total de hoy se actualiza en vivo desde Google Sheets ·
          Al ejecutar <code className="text-primary">/cerrar</code> queda guardado en el histórico automáticamente.
        </p>
      </Card>
    </div>
  )
}

// ── DiaCell ───────────────────────────────────────────────────────────────────

function DiaCell({ dia, valor, tieneVal, esHoy, esFuturo, editMode, heatOpacity, onChange, mobile }) {
  const heatBg = heatOpacity > 0
    ? { background: `hsl(var(--accent) / ${heatOpacity.toFixed(3)})` }
    : null

  return (
    <div
      className={cn(
        'flex flex-col items-center gap-0.5 rounded-md border transition-all',
        esHoy
          ? 'border-primary bg-primary-soft'
          : 'border-border bg-card hover:border-success/60',
        esFuturo && 'opacity-35',
        editMode ? 'cursor-text' : 'cursor-default',
        mobile ? 'px-0.5 pt-1.5 pb-1 min-h-12' : 'px-1 pt-1.5 pb-1 min-h-14',
      )}
      style={!esHoy ? (heatBg || {}) : {}}
    >
      <span className={cn(
        'text-[10px] font-bold select-none leading-none',
        esHoy ? 'text-primary' : 'text-muted-foreground',
      )}>
        {dia}
      </span>

      {editMode && !esFuturo ? (
        <input
          type="text"
          inputMode="numeric"
          value={valor}
          onChange={e => onChange(e.target.value)}
          placeholder="—"
          className={cn(
            'w-[92%] bg-transparent border-0 outline-none text-center py-0.5 font-inherit',
            tieneVal
              ? 'border-b border-success/55 text-success font-bold'
              : 'border-b border-border text-muted-foreground',
            mobile ? 'text-[9px]' : 'text-[10px]',
          )}
        />
      ) : (
        <span className={cn(
          'tabular-nums leading-tight',
          tieneVal
            ? 'text-success font-semibold opacity-100'
            : 'text-muted-foreground opacity-50',
          mobile ? 'text-[11px]' : 'text-[13px]',
        )}>
          {tieneVal ? formatK(parseInt(valor)) : '—'}
        </span>
      )}

      {esHoy && <div className="size-1 rounded-full bg-primary mt-0.5" />}
    </div>
  )
}

// ── Td ────────────────────────────────────────────────────────────────────────

function Td({ val, tone, bold }) {
  const n = parseFloat(val) || 0
  const toneCls = {
    foreground: 'text-foreground',
    primary:    'text-primary',
    success:    'text-success',
    warning:    'text-warning',
    info:       'text-foreground',
    muted:      'text-muted-foreground',
  }[tone] || 'text-foreground'
  return (
    <td className={cn(
      'px-2.5 py-1.5 text-right tabular-nums whitespace-nowrap',
      n === 0 ? 'text-muted-foreground opacity-40' : toneCls,
      bold && 'font-bold',
    )}>
      {n === 0 ? '—' : cop(n)}
    </td>
  )
}
