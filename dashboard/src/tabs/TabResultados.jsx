/*
 * TabResultados — P&L + proyección de caja, con Top productos como sub-tab.
 * Wave 1.b: migrado a primitives shadcn + tokens.
 * Endpoints /resultados y /proyeccion sin cambios.
 */
import { useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { useFetch, cop, num, useIsMobile } from '../components/shared.jsx'
import { Card } from '@/components/ui/card.jsx'
import KpiCard from '@/components/KpiCard.jsx'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs.jsx'
import { ChevronDown, ChevronUp, Loader2, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import TabTopProductos from './TabTopProductos.jsx'

function fmtDia(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

// ─────────────────────────────────────────────────────────────────────────────
// MiniKpi — wrapper sobre KpiCard compartido para mantener call sites.
// Mapea legacy tones ('accent' → 'primary', 'neutral' → 'default') sin
// duplicar tokens. Sin icono por diseño (financiero/denso).
function MiniKpi({ label, value, sub, tone = 'neutral' }) {
  const mapped = tone === 'accent' ? 'primary' : tone === 'neutral' ? 'default' : tone
  return <KpiCard label={label} value={value} sub={sub} tone={mapped} />
}

function EstadoResultados({ d, periodo }) {
  const [verCmv, setVerCmv] = useState(false)
  const filas = [
    { label: '(+) Ventas totales',          valor: d.total_ventas,   tone: 'success', bold: true },
    { label: '(−) Costo mercancía vendida',  valor: -d.cmv,           tone: 'danger',  negativo: true },
    { label: '= Utilidad bruta',              valor: d.utilidad_bruta, tone: d.utilidad_bruta >= 0 ? 'accent' : 'danger', bold: true, sep: true },
    { label: '(−) Gastos operativos',         valor: -d.total_gastos,  tone: 'danger',  negativo: true },
    { label: '= Utilidad neta',               valor: d.utilidad_neta,  tone: d.utilidad_neta >= 0 ? 'success' : 'danger', bold: true, grande: true, sep: true },
  ]

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Estado de resultados · {periodo === 'semana' ? 'Esta semana' : 'Este mes'}
        </h2>
        {!d.tiene_cmv && (
          <span className="inline-flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-full bg-warning/10 text-warning border border-warning/30">
            <AlertTriangle className="size-3" /> CMV en $0 — registra compras con /compra
          </span>
        )}
      </div>

      <div className="border border-border rounded-md overflow-hidden">
        {filas.map((f, i) => (
          <div
            key={i}
            className={cn(
              'flex items-center justify-between px-4',
              f.grande ? 'py-3.5 bg-success/5' : f.sep ? 'py-3 bg-surface-2' : 'py-3',
              f.sep ? 'border-t-2 border-border' : i > 0 && 'border-t border-border-subtle',
            )}
          >
            <span className={cn(
              f.bold ? 'text-foreground font-semibold' : 'text-secondary-foreground',
              f.grande ? 'text-sm' : 'text-sm',
            )}>
              {f.label}
            </span>
            <span className={cn(
              'tabular',
              f.bold ? 'font-bold' : 'font-medium',
              f.grande ? 'text-base' : 'text-sm',
              f.tone === 'success' && 'text-success',
              f.tone === 'danger'  && 'text-danger',
              f.tone === 'accent'  && 'text-primary',
            )}>
              {f.negativo && f.valor < 0 ? `−${cop(Math.abs(f.valor))}` : cop(f.valor)}
            </span>
          </div>
        ))}

        {/* Márgenes */}
        <div className="flex border-t border-border bg-surface-2/50">
          {[
            { label: 'Margen bruto', valor: d.margen_bruto_pct },
            { label: 'Margen neto',  valor: d.margen_neto_pct },
            { label: 'Cobertura CMV', valor: d.cobertura_cmv_pct, suffix: '% productos' },
          ].map((m, i) => (
            <div key={i} className={cn('flex-1 px-4 py-2.5 text-center', i > 0 && 'border-l border-border')}>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">{m.label}</div>
              <div className={cn(
                'text-sm font-bold tabular',
                (m.valor || 0) >= 0 ? 'text-primary' : 'text-danger',
              )}>
                {m.valor != null ? `${m.valor}${m.suffix || '%'}` : '—'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Detalle CMV */}
      {d.cmv_detalle?.length > 0 && (
        <div className="mt-4">
          <button
            onClick={() => setVerCmv(v => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs border border-border rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-2"
          >
            {verCmv ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
            {verCmv ? 'Ocultar' : 'Ver'} detalle CMV ({d.cmv_detalle.length} productos)
          </button>

          {verCmv && (
            <div className="overflow-x-auto mt-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface-2/50">
                    {['Producto', 'Cant.', 'Ingresos', 'CMV', 'Margen %'].map((h, i) => (
                      <th key={i} className={cn(
                        'px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold',
                        i > 0 ? 'text-right' : 'text-left',
                      )}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.cmv_detalle.map((row, i) => (
                    <tr key={i} className="border-b border-border-subtle hover:bg-surface-2/40">
                      <td className="px-3 py-2">{row.producto}</td>
                      <td className="px-3 py-2 text-right text-muted-foreground tabular">{num(row.cantidad)}</td>
                      <td className="px-3 py-2 text-right text-success tabular">{cop(row.ingresos)}</td>
                      <td className="px-3 py-2 text-right text-danger tabular">{cop(row.cmv)}</td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn('font-semibold tabular',
                          row.margen_pct >= 30 ? 'text-success' :
                          row.margen_pct >= 15 ? 'text-warning' : 'text-danger',
                        )}>{row.margen_pct}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {d.sin_costo?.length > 0 && (
        <div className="mt-3 p-3 rounded-md bg-warning/10 border border-warning/30 text-xs text-warning">
          <strong>{d.sin_costo.length} productos sin costo registrado</strong> — su CMV aparece como $0.
          Registra precios de compra con <code className="bg-surface px-1.5 py-0.5 rounded text-foreground">/compra</code> en Telegram.
          {d.sin_costo.length <= 5 && (
            <div className="mt-1.5 text-muted-foreground">{d.sin_costo.join(' · ')}</div>
          )}
        </div>
      )}
    </Card>
  )
}

function ProyeccionCaja({ pd }) {
  const isMobile = useIsMobile()
  const positivo = pd.proy_caja_fin_mes >= 0
  const serie    = pd.serie_diaria || []
  const hoy      = pd.dia_del_mes

  return (
    <Card className="p-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-4">
        Proyección de caja — cierre del mes
      </h2>

      {!pd.tiene_datos ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          Sin suficientes ventas recientes para proyectar.
        </p>
      ) : (
        <>
          <div className={cn('grid gap-3 mb-4', isMobile ? 'grid-cols-1' : 'grid-cols-3')}>
            <MiniKpi label="Caja hoy"          value={cop(pd.efectivo_actual)} />
            <MiniKpi label="Ingreso prom/día"   value={cop(pd.prom_ventas_dia)}  tone="success" />
            <MiniKpi label="Gasto prom/día"     value={cop(pd.prom_gastos_dia)}  tone="danger" />
            <MiniKpi label="Neto prom/día"      value={cop(pd.prom_neto_dia)}    tone={pd.prom_neto_dia >= 0 ? 'accent' : 'danger'} />
            <MiniKpi label="Días restantes"     value={pd.dias_restantes} />
            <MiniKpi label="Caja proyectada"
              value={cop(pd.proy_caja_fin_mes)}
              tone={positivo ? 'success' : 'danger'}
              sub="fin de mes" />
          </div>

          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={serie} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="gradReal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="hsl(var(--accent))" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="hsl(var(--accent))" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradProy" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="hsl(var(--info))" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="hsl(var(--info))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border-subtle))" />
              <XAxis dataKey="dia" tick={{ fill: 'hsl(var(--text-muted))', fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: 'hsl(var(--text-muted))', fontSize: 9 }} axisLine={false} tickLine={false}
                tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
              />
              <Tooltip
                contentStyle={{
                  background: 'hsl(var(--bg-surface))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 8,
                  fontSize: 11,
                  color: 'hsl(var(--text-primary))',
                }}
                formatter={(v) => [cop(v), 'Caja']}
                labelFormatter={d => `Día ${d}`}
              />
              <ReferenceLine x={hoy} stroke="hsl(var(--accent))" strokeDasharray="4 4"
                label={{ value: 'Hoy', fill: 'hsl(var(--accent))', fontSize: 9 }} />
              <Area
                type="monotone" dataKey="valor"
                data={serie.filter(s => s.real)}
                stroke="hsl(var(--accent))" fill="url(#gradReal)" strokeWidth={2}
                dot={false} name="Real"
              />
              <Area
                type="monotone" dataKey="valor"
                data={serie.filter(s => !s.real)}
                stroke="hsl(var(--info))" fill="url(#gradProy)" strokeWidth={2}
                strokeDasharray="5 3" dot={false} name="Proyectado"
              />
            </AreaChart>
          </ResponsiveContainer>

          <div className={cn('grid gap-3 mt-4', isMobile ? 'grid-cols-1' : 'grid-cols-2')}>
            {[
              { label: 'Ventas acumuladas',    real: pd.ventas_mes_actual,  proy: pd.proy_ventas_mes,  tone: 'success' },
              { label: 'Gastos acumulados',    real: pd.gastos_mes_actual,  proy: pd.proy_gastos_mes,  tone: 'danger' },
            ].map((row, i) => (
              <div key={i} className="p-3 rounded-md bg-surface-2/50 border border-border">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2">{row.label}</div>
                <div className="flex items-baseline justify-between">
                  <div>
                    <div className="text-[10px] text-muted-foreground">Actual</div>
                    <div className={cn('font-semibold tabular',
                      row.tone === 'success' ? 'text-success' : 'text-danger')}>
                      {cop(row.real)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] text-muted-foreground">Fin de mes</div>
                    <div className={cn('text-base font-bold tabular',
                      row.tone === 'success' ? 'text-success' : 'text-danger')}>
                      {cop(row.proy)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <p className="mt-3 text-[10px] text-muted-foreground italic">
            * Proyección basada en promedio de los últimos 14 días con ventas.
          </p>
        </>
      )}
    </Card>
  )
}

function GraficaHistorica({ historico }) {
  if (!historico?.length) return null
  const data = historico.map(h => ({ dia: fmtDia(h.fecha), ventas: h.ventas, gastos: h.gastos }))
  return (
    <Card className="p-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
        Ventas vs gastos por día
      </h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border-subtle))" />
          <XAxis dataKey="dia" tick={{ fill: 'hsl(var(--text-muted))', fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: 'hsl(var(--text-muted))', fontSize: 9 }} axisLine={false} tickLine={false}
            tickFormatter={v => v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v} />
          <Tooltip
            contentStyle={{
              background: 'hsl(var(--bg-surface))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 8, fontSize: 11,
              color: 'hsl(var(--text-primary))',
            }}
            formatter={v => [cop(v)]}
          />
          <Bar dataKey="ventas" name="Ventas" fill="hsl(var(--success))" radius={[3,3,0,0]} maxBarSize={22} />
          <Bar dataKey="gastos" name="Gastos" fill="hsl(var(--danger))"  radius={[3,3,0,0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

export default function TabResultados({ refreshKey }) {
  const [periodo, setPeriodo] = useState('mes')
  const { data: rd, loading: rl, error: re } = useFetch(`/resultados?periodo=${periodo}`, [periodo, refreshKey])
  const { data: pd, loading: pl, error: pe } = useFetch('/proyeccion', [refreshKey])

  return (
    <div className="space-y-5">
      {/* Header con tabs internas */}
      <Tabs defaultValue="resultados" className="space-y-5">
        <header className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Resultados financieros</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Estado de resultados · Proyección de caja · Top productos</p>
          </div>
          <TabsList>
            <TabsTrigger value="resultados">P&amp;L</TabsTrigger>
            <TabsTrigger value="top">Top productos</TabsTrigger>
          </TabsList>
        </header>

        <TabsContent value="resultados" className="space-y-5">
          {/* Periodo selector */}
          <div className="flex justify-end">
            <div className="inline-flex bg-surface-2 p-1 rounded-md">
              {[['semana','Esta semana'],['mes','Este mes']].map(([v, lbl]) => (
                <button key={v} onClick={() => setPeriodo(v)}
                  className={cn(
                    'px-3 py-1 text-xs rounded transition-colors',
                    periodo === v ? 'bg-surface text-foreground shadow-xs font-medium' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>

          {rd && !rl && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <MiniKpi label="Ventas"          value={cop(rd.total_ventas)}   sub="Ingresos del período"   tone="success" />
              <MiniKpi label="CMV"             value={cop(rd.cmv)}            sub="Costo de lo vendido"    tone="danger" />
              <MiniKpi label="Utilidad bruta"  value={cop(rd.utilidad_bruta)} sub={`Margen ${rd.margen_bruto_pct}%`} tone="accent" />
              <MiniKpi label="Utilidad neta"   value={cop(rd.utilidad_neta)}  sub="Después de gastos"
                tone={rd.utilidad_neta >= 0 ? 'success' : 'danger'} />
            </div>
          )}

          {rl && (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="size-5 animate-spin mr-2" /> Cargando…
            </div>
          )}
          {re && (
            <Card className="p-4 border-destructive/40 bg-destructive/5 text-destructive text-sm">
              Error resultados: {re}
            </Card>
          )}
          {rd && !rl && <EstadoResultados d={rd} periodo={periodo} />}
          {rd && !rl && <GraficaHistorica historico={rd.historico} />}

          {pl && (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              <Loader2 className="size-5 animate-spin mr-2" /> Calculando proyección…
            </div>
          )}
          {pe && (
            <Card className="p-4 border-destructive/40 bg-destructive/5 text-destructive text-sm">
              Error proyección: {pe}
            </Card>
          )}
          {pd && !pl && <ProyeccionCaja pd={pd} />}
        </TabsContent>

        <TabsContent value="top" className="space-y-5">
          <TabTopProductos refreshKey={refreshKey} embedded />
        </TabsContent>
      </Tabs>
    </div>
  )
}
