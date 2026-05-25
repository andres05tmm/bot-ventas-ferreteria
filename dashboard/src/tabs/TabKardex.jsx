/*
 * TabKardex — kárdex por producto, método promedio ponderado.
 * Wave 2: migrado a primitives shadcn + tokens.
 */
import { useState } from 'react'
import { useFetch, cop, num } from '../components/shared.jsx'
import { Card } from '@/components/ui/card.jsx'
import { Input } from '@/components/ui/input.jsx'
import {
  Search, Package, ChevronRight, ArrowUp, ArrowDown,
  Loader2, FileText,
} from 'lucide-react'
import { cn } from '@/lib/utils'

function MovRow({ m }) {
  const entrada = m.tipo === 'entrada'
  return (
    <tr className="border-b border-border-subtle hover:bg-surface-2/40">
      <td className="px-3 py-2 text-muted-foreground text-xs whitespace-nowrap">{m.fecha}</td>
      <td className="px-3 py-2 text-muted-foreground text-xs">{m.hora}</td>
      <td className="px-3 py-2">
        <span className={cn(
          'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border',
          entrada
            ? 'bg-success/10 text-success border-success/30'
            : 'bg-warning/10 text-warning border-warning/30',
        )}>
          {entrada ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
          {entrada ? 'Entrada' : 'Salida'}
        </span>
      </td>
      <td className="px-3 py-2 text-secondary-foreground text-xs">{m.concepto}</td>
      <td className={cn('px-3 py-2 text-right font-semibold tabular', entrada ? 'text-success' : 'text-transparent')}>
        {entrada ? `+${num(m.entrada)}` : ''}
      </td>
      <td className="px-3 py-2 text-right font-semibold tabular text-warning">
        {!entrada && m.salida > 0 ? `-${num(m.salida)}` : ''}
      </td>
      <td className="px-3 py-2 text-right font-semibold tabular">{num(m.saldo)}</td>
      <td className="px-3 py-2 text-right text-muted-foreground tabular">{cop(m.costo_unitario)}</td>
      <td className="px-3 py-2 text-right text-primary font-semibold tabular">{cop(m.costo_promedio)}</td>
      <td className="px-3 py-2 text-right text-foreground tabular">{cop(m.valor_total)}</td>
    </tr>
  )
}

function ProductoKardex({ item }) {
  const [open, setOpen] = useState(false)
  const movs = item.movimientos || []

  return (
    <Card className="overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between gap-4 px-4 py-3 hover:bg-surface-2/50 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <Package className="size-4 text-muted-foreground shrink-0" />
          <div className="text-left min-w-0">
            <div className="font-semibold text-sm truncate">{item.producto}</div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              {movs.length} movimiento{movs.length !== 1 ? 's' : ''}
            </div>
          </div>
        </div>
        <div className="hidden md:flex items-center gap-6 text-right shrink-0">
          <MiniStat label="Entradas" value={num(item.total_entradas)} tone="success" />
          <MiniStat label="Stock"    value={num(item.stock_actual)}    tone={item.stock_actual > 0 ? 'foreground' : 'danger'} />
          <MiniStat label="Costo prom." value={cop(item.costo_promedio)} tone="accent" />
          <MiniStat label="Valor inv."  value={cop(item.valor_inventario)} tone="foreground" />
        </div>
        <ChevronRight className={cn('size-4 text-muted-foreground transition-transform shrink-0', open && 'rotate-90')} />
      </button>

      {open && (
        <div className="border-t border-border overflow-x-auto">
          {item.salidas_est > 0 && (
            <div className="px-4 py-2 bg-surface-2/50 border-b border-border-subtle text-xs text-muted-foreground">
              Salidas estimadas: <strong className="text-warning">{num(item.salidas_est)}</strong> unidades
              (total entradas − stock actual).
            </div>
          )}
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-2/50">
                {['Fecha','Hora','Tipo','Concepto','Entrada','Salida','Saldo','Costo Unit.','C. Prom.','Valor'].map((h, i) => (
                  <th key={i} className={cn(
                    'px-3 py-2 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold border-b border-border whitespace-nowrap',
                    [4,5,6,7,8,9].includes(i) ? 'text-right' : 'text-left',
                  )}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {movs.map((m, i) => <MovRow key={i} m={m} />)}
            </tbody>
            <tfoot>
              <tr className="bg-surface-2/30 border-t border-border">
                <td colSpan={4} className="px-3 py-2 text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">Totales</td>
                <td className="px-3 py-2 text-right text-success font-bold tabular">{num(item.total_entradas)}</td>
                <td className="px-3 py-2 text-right text-warning font-bold tabular">{num(item.salidas_est)}</td>
                <td className="px-3 py-2 text-right font-bold tabular">{num(item.stock_actual)}</td>
                <td colSpan={2} />
                <td className="px-3 py-2 text-right font-bold tabular">{cop(item.valor_inventario)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </Card>
  )
}

function MiniStat({ label, value, tone = 'foreground' }) {
  return (
    <div className="text-right">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn('font-semibold text-sm tabular',
        tone === 'success' && 'text-success',
        tone === 'danger'  && 'text-danger',
        tone === 'accent'  && 'text-primary',
      )}>
        {value}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────

export default function TabKardex({ refreshKey }) {
  const [busqueda, setBusqueda] = useState('')
  const [query, setQuery] = useState('')

  const { data, loading, error } = useFetch(
    query ? `/kardex?producto=${encodeURIComponent(query)}` : '/kardex',
    [query, refreshKey]
  )

  function handleSearch(v) {
    setBusqueda(v)
    clearTimeout(window._kardexTimer)
    window._kardexTimer = setTimeout(() => setQuery(v), 300)
  }

  const items      = data?.kardex || []
  const totalValor = data?.valor_inventario_total || 0
  const tieneDatos = data?.tiene_datos

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Kárdex de inventario</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Movimientos por producto · método promedio ponderado (NIIF pymes)
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={busqueda}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Buscar producto..."
            className="pl-9"
          />
        </div>
      </header>

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

      {!loading && !error && !tieneDatos && (
        <Card className="p-8 text-center">
          <FileText className="size-10 text-muted-foreground mx-auto mb-3" />
          <h2 className="font-semibold text-base mb-2">El Kárdex se construye automáticamente</h2>
          <p className="text-sm text-muted-foreground max-w-md mx-auto mb-4 leading-relaxed">
            Cada vez que registres una compra de mercancía en Telegram, el sistema construye el kárdex con promedio ponderado.
          </p>
          <code className="inline-block bg-surface-2 text-primary border border-border px-3 py-1.5 rounded-md text-xs">
            /compra 20 brocha 2" a 2500 de Ferrisariato
          </code>
        </Card>
      )}

      {!loading && !error && tieneDatos && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Card className="p-4">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 font-semibold">Productos</div>
              <div className="text-xl font-semibold tabular leading-none">{items.length}</div>
              <p className="text-xs text-muted-foreground mt-1.5">Con historial de compras</p>
            </Card>
            <Card className="p-4">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-2 font-semibold">Valor inventario</div>
              <div className="text-xl font-semibold tabular leading-none text-primary">{cop(totalValor)}</div>
              <p className="text-xs text-muted-foreground mt-1.5">Costo promedio × stock</p>
            </Card>
          </div>

          {items.length === 0 ? (
            <Card className="p-8 text-center text-sm text-muted-foreground">
              Sin resultados para la búsqueda.
            </Card>
          ) : (
            <div className="space-y-2">
              {items.map(item => <ProductoKardex key={item.producto} item={item} />)}
            </div>
          )}
        </>
      )}
    </div>
  )
}
