/*
 * KpiCard — tarjeta de métrica compacta, tokenizada y reutilizable.
 *
 * Diseñado bajo ui-ux-pro-max: contraste 4.5:1+, focus-ring visible,
 * touch target >=44px, easing ease-out-quad, motion con propósito
 * (affordance del onClick), scale-feedback sutil (-translate-y).
 *
 * Props:
 *   tone        — 'success' | 'info' | 'warning' | 'danger' | 'primary' | 'muted' | 'default'
 *   label       — etiqueta superior (uppercase)
 *   value       — valor principal (string | number | ReactNode)
 *   sub         — texto secundario debajo del valor
 *   icon        — componente lucide-react
 *   deltaPct    — número opcional para mostrar tendencia ↑/↓ vs anterior
 *   spark       — array de puntos [{ total }, …] para sparkline (>=3)
 *   onClick     — vuelve la card clickeable + focusable + aria-button
 *   actionLabel — chip discreto en hover/focus indicando la acción
 *   loading     — atenúa el valor
 *   compact     — versión densa (p-2.5 en vez de p-3)
 */
import { TrendingUp, TrendingDown, ArrowRight } from 'lucide-react'
import { ResponsiveContainer, LineChart, Line } from 'recharts'
import { Card } from '@/components/ui/card.jsx'
import { cn } from '@/lib/utils'

const TONES = {
  success: { color: 'hsl(var(--success))',     bg: 'bg-success/[0.05]',     border: 'border-success/25     hover:border-success/45'     },
  info:    { color: 'hsl(var(--info))',        bg: 'bg-info/[0.05]',        border: 'border-info/25        hover:border-info/45'        },
  warning: { color: 'hsl(var(--warning))',     bg: 'bg-warning/[0.05]',     border: 'border-warning/25     hover:border-warning/45'     },
  danger:  { color: 'hsl(var(--destructive))', bg: 'bg-destructive/[0.05]', border: 'border-destructive/25 hover:border-destructive/45' },
  primary: { color: 'hsl(var(--accent))',      bg: 'bg-accent/[0.05]',      border: 'border-accent/25      hover:border-accent/45'      },
  muted:   { color: 'hsl(var(--muted-foreground))', bg: 'bg-muted/40',      border: 'border-border         hover:border-border'         },
  default: { color: 'hsl(var(--foreground))',  bg: 'bg-surface',            border: 'border-border         hover:border-border'         },
}

export default function KpiCard({
  tone = 'default',
  label,
  value,
  sub,
  icon: Icon,
  deltaPct,
  spark,
  onClick,
  actionLabel,
  loading,
  compact = false,
}) {
  const t = TONES[tone] || TONES.default
  const clickable = typeof onClick === 'function'

  return (
    <Card
      className={cn(
        'relative overflow-hidden transition-all duration-base ease-out-quad group',
        compact ? 'p-2.5' : 'p-3',
        t.bg, t.border,
        clickable
          ? 'cursor-pointer text-left w-full hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40'
          : 'hover:-translate-y-px hover:shadow-md',
      )}
      {...(clickable ? {
        onClick,
        role: 'button',
        tabIndex: 0,
        'aria-label': actionLabel || label,
        onKeyDown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } },
      } : {})}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground truncate">
          {label}
        </span>
        <div className="flex items-center gap-1.5">
          {clickable && actionLabel && (
            <span
              className={cn(
                'hidden sm:inline-flex items-center gap-1 h-5 px-1.5 rounded-md',
                'text-[10px] font-medium tabular',
                'opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0',
                'group-focus-visible:opacity-100 group-focus-visible:translate-x-0',
                'transition-all duration-base ease-out-quad',
              )}
              style={{
                background: `color-mix(in srgb, ${t.color} 14%, transparent)`,
                color: t.color,
              }}
            >
              {actionLabel}
              <ArrowRight className="size-2.5" aria-hidden="true" />
            </span>
          )}
          {Icon && (
            <span
              className="grid place-items-center rounded-md size-6 shrink-0"
              style={{ background: `color-mix(in srgb, ${t.color} 12%, transparent)`, color: t.color }}
            >
              <Icon className="size-3" aria-hidden="true" />
            </span>
          )}
        </div>
      </div>

      <div className={cn(
        'mt-1.5 text-lg font-semibold tracking-tight tabular leading-none',
        loading && 'opacity-50',
      )}>
        {value}
      </div>

      {(sub || (deltaPct !== null && deltaPct !== undefined) || spark) && (
        <div className="mt-1.5 flex items-end justify-between gap-2">
          <div className="text-[10.5px] text-muted-foreground leading-snug truncate">
            {deltaPct !== null && deltaPct !== undefined && Math.abs(deltaPct) > 0.5 && (
              <span className={cn(
                'inline-flex items-center gap-0.5 mr-1 font-semibold tabular',
                deltaPct >= 0 ? 'text-success' : 'text-destructive',
              )}>
                {deltaPct >= 0
                  ? <TrendingUp className="size-2.5" aria-hidden="true" />
                  : <TrendingDown className="size-2.5" aria-hidden="true" />}
                {deltaPct >= 0 ? '+' : ''}{deltaPct.toFixed(1)}%
              </span>
            )}
            {sub}
          </div>
          {Array.isArray(spark) && spark.length >= 3 && (
            <div className="shrink-0 w-[56px] h-[20px] opacity-90" aria-hidden="true">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={spark.map(d => ({ v: Number(d?.total ?? d) || 0 }))}>
                  <Line type="monotone" dataKey="v" stroke={t.color} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
