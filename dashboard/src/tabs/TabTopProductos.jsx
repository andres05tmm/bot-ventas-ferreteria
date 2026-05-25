/*
 * TabTopProductos — Top10 productos por ingresos/frecuencia/categoría.
 * Wave 1.b: migrado a primitives shadcn + tokens.
 * Vista barras inline + tabla. Endpoint /ventas/top2 sin cambios.
 */
import { useState } from 'react'
import { useFetch, cop, num } from '../components/shared.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Button } from '@/components/ui/button.jsx'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs.jsx'
import { DollarSign, Repeat, FolderTree, BarChart3, Table as TableIcon, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

const MEDAL = ['🥇','🥈','🥉']

function shortVal(v, criterio) {
  if (criterio === 'frecuencia') return `${num(v)}×`
  if (v >= 1e6) return `$${(v/1e6).toFixed(1)}M`
  if (v >= 1e3) return `$${(v/1e3).toFixed(0)}k`
  return `$${num(v)}`
}

function PosBadge({ i }) {
  if (i < 3) return <span className="text-base w-6 text-center shrink-0">{MEDAL[i]}</span>
  return (
    <span className="size-6 rounded-md bg-primary-soft text-primary text-xs font-bold grid place-items-center shrink-0">
      {i + 1}
    </span>
  )
}

function BarRow({ item, i, max, criterio }) {
  const pct = max > 0 ? Math.round((item.valor / max) * 100) : 0
  return (
    <div className="flex items-center gap-3 py-2.5 border-b border-border-subtle last:border-0">
      <PosBadge i={i} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <span className={cn('text-sm truncate', i === 0 && 'font-semibold')}>{item.producto}</span>
          <span className="text-sm font-semibold tabular text-primary shrink-0">
            {criterio === 'frecuencia' ? `${num(item.valor)}×` : cop(item.valor)}
          </span>
        </div>
        <div className="h-1.5 bg-surface-2 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-slow',
              i === 0 ? 'bg-primary' : i === 1 ? 'bg-primary/80' : i === 2 ? 'bg-primary/60' : 'bg-muted-foreground/50',
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <span className="text-xs text-muted-foreground tabular w-14 text-right shrink-0">
        {criterio === 'ingresos' ? `${num(item.frecuencia || 0)}×` : cop(item.ingresos || 0)}
      </span>
    </div>
  )
}

function TopTable({ top, criterio }) {
  const total = top.reduce((a, p) => a + p.valor, 0)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground text-left">#</th>
            <th className="px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground text-left">Producto</th>
            <th className="px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground text-left hidden md:table-cell">Categoría</th>
            <th className="px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground text-right">
              {criterio === 'frecuencia' ? 'Ventas' : 'Ingresos'}
            </th>
            <th className="px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground text-right hidden sm:table-cell">
              {criterio === 'ingresos' ? 'Registros' : 'Total $'}
            </th>
            <th className="px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground text-right">% total</th>
          </tr>
        </thead>
        <tbody>
          {top.map((row, i) => {
            const pct = total > 0 ? (row.valor / total) * 100 : 0
            return (
              <tr key={i} className="border-b border-border-subtle hover:bg-surface-2/40">
                <td className="px-3 py-2"><PosBadge i={row.posicion - 1} /></td>
                <td className="px-3 py-2 font-medium">{row.producto}</td>
                <td className="px-3 py-2 text-muted-foreground hidden md:table-cell">{row.categoria || '—'}</td>
                <td className="px-3 py-2 text-right tabular font-semibold text-primary">
                  {criterio === 'frecuencia' ? `${num(row.valor)}×` : cop(row.valor)}
                </td>
                <td className="px-3 py-2 text-right tabular text-muted-foreground hidden sm:table-cell">
                  {criterio === 'ingresos' ? num(row.frecuencia) : cop(row.ingresos)}
                </td>
                <td className="px-3 py-2 text-right tabular text-muted-foreground">{pct.toFixed(1)}%</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CategoriaCard({ cat, prods }) {
  const max = prods[0]?.valor || 1
  return (
    <Card className="p-5">
      <div className="flex items-center gap-3 mb-3 pb-3 border-b border-border-subtle">
        <span className="w-[3px] h-4 bg-primary rounded-full" />
        <h3 className="font-semibold text-sm flex-1">{cat.replace(/^\d+\s*/, '')}</h3>
        <span className="text-xs px-2 py-0.5 rounded-full bg-surface-2 text-muted-foreground">
          {prods.length} productos
        </span>
      </div>
      {prods.map((item, i) => (
        <BarRow key={i} item={item} i={i} max={max} criterio="ingresos" />
      ))}
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

const CRITERIOS = [
  { id: 'ingresos',   icon: DollarSign, label: 'Ingresos',   desc: 'Dinero generado por producto' },
  { id: 'frecuencia', icon: Repeat,     label: 'Frecuencia', desc: 'Veces vendido' },
  { id: 'categoria',  icon: FolderTree, label: 'Por categoría', desc: 'Top 5 por categoría' },
]

export default function TabTopProductos({ refreshKey, embedded = false }) {
  const [periodo,  setPeriodo]  = useState('semana')
  const [criterio, setCriterio] = useState('ingresos')
  const [vista,    setVista]    = useState('grafico')

  const { data, loading, error } = useFetch(
    `/ventas/top2?periodo=${periodo}&criterio=${criterio}`,
    [periodo, criterio, refreshKey]
  )

  const top    = data?.top || []
  const porCat = data?.por_categoria || {}
  const esCat  = criterio === 'categoria'
  const cats   = Object.entries(porCat)
  const max    = top[0]?.valor || 1

  const total          = top.reduce((a, p) => a + p.valor, 0)
  const totalRegistros = top.reduce((a, p) => a + (p.frecuencia || 1), 0)
  const ticketProm     = totalRegistros > 0 ? total / totalRegistros : 0
  const periodoLabel   = periodo === 'semana' ? 'Esta semana' : 'Este mes'

  return (
    <div className="space-y-5">
      {/* Header */}
      {!embedded && (
        <header className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Top productos</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              {CRITERIOS.find(c => c.id === criterio)?.desc} · {periodoLabel.toLowerCase()}
            </p>
          </div>
          <PeriodoSelector periodo={periodo} setPeriodo={setPeriodo} />
        </header>
      )}
      {embedded && (
        <div className="flex items-center justify-end">
          <PeriodoSelector periodo={periodo} setPeriodo={setPeriodo} />
        </div>
      )}

      {/* Criterio chips */}
      <div className="flex gap-2 flex-wrap">
        {CRITERIOS.map(c => {
          const Icon = c.icon
          const active = criterio === c.id
          return (
            <button
              key={c.id}
              onClick={() => setCriterio(c.id)}
              className={cn(
                'inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs border transition-colors',
                active
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-surface text-secondary-foreground border-border hover:bg-surface-2',
              )}
            >
              <Icon className="size-3.5" />
              <span>{c.label}</span>
            </button>
          )
        })}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="size-5 animate-spin mr-2" /> Cargando…
        </div>
      )}
      {error && (
        <Card className="p-4 border-destructive/40 bg-destructive/5 text-destructive text-sm">
          Error: {error}
        </Card>
      )}

      {!loading && !error && !esCat && top.length > 0 && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <MiniKpi label="Total generado"
              value={criterio === 'frecuencia' ? `${num(total)}×` : cop(total)}
              sub={`${top.length} productos · ${periodoLabel.toLowerCase()}`} />
            {criterio === 'ingresos' && (
              <MiniKpi label="Ticket promedio" value={cop(Math.round(ticketProm))} sub="por transacción registrada" />
            )}
            <MiniKpi label="Producto líder"
              value={top[0]?.producto?.split(' ').slice(0, 2).join(' ') || '—'}
              sub={criterio === 'frecuencia'
                ? `${num(top[0]?.valor || 0)} veces vendido`
                : `${cop(top[0]?.valor || 0)} generados`} />
          </div>

          {/* Toggle vista */}
          <div className="flex justify-end">
            <div className="inline-flex bg-surface-2 p-1 rounded-md">
              <ViewToggle active={vista === 'grafico'} onClick={() => setVista('grafico')}>
                <BarChart3 className="size-3.5" /> Barras
              </ViewToggle>
              <ViewToggle active={vista === 'tabla'} onClick={() => setVista('tabla')}>
                <TableIcon className="size-3.5" /> Tabla
              </ViewToggle>
            </div>
          </div>

          <Card className={vista === 'grafico' ? 'p-5' : 'p-0 overflow-hidden'}>
            {vista === 'grafico' ? (
              <>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                  Top 10 — {criterio === 'frecuencia' ? 'Veces vendido' : 'Ingresos generados'}
                </h2>
                {top.map((item, i) => (
                  <BarRow key={i} item={item} i={i} max={max} criterio={criterio} />
                ))}
              </>
            ) : (
              <TopTable top={top} criterio={criterio} />
            )}
          </Card>
        </>
      )}

      {!loading && !error && esCat && (
        cats.length === 0 ? (
          <p className="py-12 text-center text-sm text-muted-foreground">Sin datos.</p>
        ) : (
          <div className="space-y-4">
            {cats.map(([cat, prods]) => (
              <CategoriaCard key={cat} cat={cat} prods={prods} />
            ))}
          </div>
        )
      )}

      {!loading && !error && !esCat && top.length === 0 && (
        <p className="py-12 text-center text-sm text-muted-foreground">Sin datos para este período.</p>
      )}
    </div>
  )
}

function PeriodoSelector({ periodo, setPeriodo }) {
  return (
    <div className="inline-flex bg-surface-2 p-1 rounded-md">
      {[['semana','Semana'],['mes','Mes']].map(([v, lbl]) => (
        <button
          key={v}
          onClick={() => setPeriodo(v)}
          className={cn(
            'px-3 py-1 text-xs rounded transition-colors',
            periodo === v ? 'bg-surface text-foreground shadow-xs font-medium' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {lbl}
        </button>
      ))}
    </div>
  )
}

function ViewToggle({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 px-3 py-1 text-xs rounded transition-colors',
        active ? 'bg-surface text-foreground shadow-xs font-medium' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

function MiniKpi({ label, value, sub }) {
  return (
    <Card className="p-4">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">{label}</div>
      <div className="text-xl font-semibold tracking-tight tabular leading-none">{value}</div>
      {sub && <p className="mt-2 text-xs text-muted-foreground">{sub}</p>}
    </Card>
  )
}
