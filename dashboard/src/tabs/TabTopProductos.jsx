import { useState, useEffect, useRef } from 'react'
import {
  useTheme, useFetch, Spinner, ErrorMsg, EmptyState, cop, num,
} from '../components/shared.jsx'

const POS_COLORS = [
  '#D42010','#E85A10','#F59E0B',
  '#64748B','#64748B','#64748B','#64748B','#64748B','#64748B','#64748B',
]
const MEDAL = ['🥇','🥈','🥉']

function AnimNum({ target, format = v => v, duration = 900 }) {
  const [val, setVal] = useState(0)
  const raf = useRef(null)
  useEffect(() => {
    if (!target) return
    const start = Date.now()
    const tick = () => {
      const p    = Math.min(1, (Date.now() - start) / duration)
      const ease = 1 - Math.pow(1 - p, 3)
      setVal(Math.round(target * ease))
      if (p < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [target])
  return <>{format(val)}</>
}

function AnimBar({ pct, color, delay = 0 }) {
  const [w, setW] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => setW(pct), delay + 80)
    return () => clearTimeout(t)
  }, [pct, delay])
  return (
    <div style={{ height: 6, borderRadius: 99, overflow: 'hidden', background: 'rgba(128,128,128,.13)', flex: 1 }}>
      <div style={{
        height: '100%', borderRadius: 99,
        background: `linear-gradient(90deg, ${color}cc, ${color})`,
        width: `${w}%`,
        transition: 'width .7s cubic-bezier(.22,1,.36,1)',
        boxShadow: `0 0 8px ${color}55`,
      }}/>
    </div>
  )
}

function KpiCard({ label, value, sub, accent, t }) {
  return (
    <div style={{
      background: t.card, border: `1px solid ${t.border}`, borderRadius: 14,
      padding: '16px 20px', flex: 1, minWidth: 0, position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', top: -18, right: -18, width: 72, height: 72, borderRadius: '50%', background: `${accent}10`, pointerEvents: 'none' }}/>
      <div style={{ fontSize: 9, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: accent, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: t.textMuted, marginTop: 5 }}>{sub}</div>}
    </div>
  )
}

function PodioCard({ item, t, criterio }) {
  const pos   = item.posicion
  const color = POS_COLORS[pos - 1]
  const h     = pos === 1 ? 90 : pos === 2 ? 70 : 54
  const isFirst = pos === 1
  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <div style={{
        background: t.card, border: `1.5px solid ${color}44`, borderRadius: 12,
        padding: '12px 14px', width: '100%', textAlign: 'center', position: 'relative',
      }}>
        {isFirst && (
          <div style={{
            position: 'absolute', top: -1, left: '50%', transform: 'translateX(-50%)',
            background: color, color: '#fff', fontSize: 8, fontWeight: 800,
            letterSpacing: '.12em', padding: '2px 10px', borderRadius: '0 0 8px 8px', textTransform: 'uppercase',
          }}>LÍDER</div>
        )}
        <div style={{ fontSize: 22, marginBottom: 6, marginTop: isFirst ? 6 : 0 }}>{MEDAL[pos - 1]}</div>
        <div style={{
          fontSize: 11, fontWeight: 600, color: t.text, lineHeight: 1.35, marginBottom: 8,
          overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', minHeight: 30,
        }}>{item.producto}</div>
        <div style={{ fontSize: 16, fontWeight: 800, color, fontVariantNumeric: 'tabular-nums' }}>
          {criterio === 'frecuencia' ? `${num(item.valor)}×` : cop(item.valor)}
        </div>
        {criterio === 'ingresos' && item.frecuencia != null && (
          <div style={{ fontSize: 10, color: t.textMuted, marginTop: 4 }}>{num(item.frecuencia)} registros</div>
        )}
      </div>
      <div style={{
        width: '60%', height: h,
        background: `linear-gradient(180deg, ${color}99 0%, ${color}33 100%)`,
        borderRadius: '8px 8px 0 0', border: `1px solid ${color}44`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 18, fontWeight: 900, color,
      }}>#{pos}</div>
    </div>
  )
}

function ListRow({ item, max, t, criterio, delay }) {
  const color = POS_COLORS[item.posicion - 1]
  const pct   = max > 0 ? (item.valor / max) * 100 : 0
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '10px 0', borderBottom: `1px solid ${t.border}`,
      animation: 'fadeSlideIn .35s ease both', animationDelay: `${delay}ms`,
    }}>
      <div style={{
        width: 28, height: 28, borderRadius: 8, flexShrink: 0,
        background: `${color}18`, border: `1px solid ${color}33`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 700, color,
      }}>{item.posicion}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 5 }}>
          <span style={{ fontSize: 12, color: t.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {item.producto}
          </span>
          <span style={{ fontSize: 12, fontWeight: 700, color, flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
            {criterio === 'frecuencia' ? `${num(item.valor)}×` : cop(item.valor)}
          </span>
        </div>
        <AnimBar pct={pct} color={color} delay={delay} />
      </div>
      <div style={{ fontSize: 10, color: t.textMuted, minWidth: 34, textAlign: 'right', flexShrink: 0 }}>
        {pct.toFixed(1)}%
      </div>
    </div>
  )
}

function TablaDetalle({ top, criterio, t }) {
  const total = top.reduce((a, p) => a + p.valor, 0)
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: t.tableAlt }}>
            {['#','Producto','Categoría',
              criterio === 'frecuencia' ? 'Ventas' : 'Ingresos',
              criterio === 'ingresos'   ? 'Registros' : 'Total $',
              '% Total',
            ].map((h, i) => (
              <th key={i} style={{
                padding: '9px 14px', fontSize: 9, fontWeight: 600, color: t.textMuted,
                textTransform: 'uppercase', letterSpacing: '.09em',
                textAlign: i < 3 ? 'left' : 'right', borderBottom: `1px solid ${t.border}`,
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {top.map((row, i) => {
            const color = POS_COLORS[row.posicion - 1]
            const pct   = total > 0 ? (row.valor / total) * 100 : 0
            return (
              <tr key={i}
                style={{ borderBottom: `1px solid ${t.border}`, transition: 'background .12s' }}
                onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <td style={{ padding: '10px 14px' }}>
                  {row.posicion <= 3
                    ? <span style={{ fontSize: 16 }}>{MEDAL[row.posicion - 1]}</span>
                    : <span style={{
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        width: 22, height: 22, borderRadius: 6,
                        background: `${color}15`, border: `1px solid ${color}33`,
                        fontSize: 10, fontWeight: 700, color,
                      }}>{row.posicion}</span>
                  }
                </td>
                <td style={{ padding: '10px 14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 3, height: 18, borderRadius: 99, background: color, flexShrink: 0 }}/>
                    <span style={{ color: t.text, fontWeight: 500 }}>{row.producto}</span>
                  </div>
                </td>
                <td style={{ padding: '10px 14px', color: t.textMuted, fontSize: 11 }}>{row.categoria || '—'}</td>
                <td style={{ padding: '10px 14px', textAlign: 'right', color, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                  {criterio === 'frecuencia' ? `${num(row.valor)}×` : cop(row.valor)}
                </td>
                <td style={{ padding: '10px 14px', textAlign: 'right', color: t.textMuted, fontVariantNumeric: 'tabular-nums' }}>
                  {criterio === 'ingresos' ? num(row.frecuencia) : cop(row.ingresos)}
                </td>
                <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6 }}>
                    <div style={{ width: 48, height: 3, background: t.border, borderRadius: 99, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 99 }}/>
                    </div>
                    <span style={{ fontSize: 10, color: t.textMuted, minWidth: 30, textAlign: 'right' }}>
                      {pct.toFixed(1)}%
                    </span>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
        <tfoot>
          <tr style={{ borderTop: `2px solid ${t.border}`, background: t.tableAlt }}>
            <td colSpan={3} style={{ padding: '9px 14px', fontSize: 9, color: t.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.07em' }}>
              Total · {top.length} productos
            </td>
            <td style={{ padding: '9px 14px', textAlign: 'right', color: t.accent, fontWeight: 800, fontVariantNumeric: 'tabular-nums' }}>
              {criterio === 'frecuencia'
                ? `${num(top.reduce((a,p)=>a+p.valor,0))}×`
                : cop(top.reduce((a,p)=>a+p.valor,0))
              }
            </td>
            <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textMuted }}>
              {criterio === 'ingresos'
                ? num(top.reduce((a,p)=>a+(p.frecuencia||0),0))
                : cop(top.reduce((a,p)=>a+(p.ingresos||0),0))
              }
            </td>
            <td/>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function CatSection({ cat, prods, t }) {
  const max = prods[0]?.valor || 1
  return (
    <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 14, overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 4, height: 18, borderRadius: 99, background: t.accent, flexShrink: 0 }}/>
        <span style={{ fontWeight: 700, fontSize: 13, color: t.text }}>{cat.replace(/^\d+\s*/, '')}</span>
        <span style={{ fontSize: 10, color: t.textMuted, background: t.tableAlt, border: `1px solid ${t.border}`, borderRadius: 99, padding: '2px 8px' }}>
          {prods.length} productos
        </span>
      </div>
      <div style={{ padding: '6px 18px 14px' }}>
        {prods.map((item, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '9px 0',
            borderBottom: i < prods.length - 1 ? `1px solid ${t.border}` : 'none',
          }}>
            <span style={{ fontSize: i < 3 ? 16 : 12, minWidth: 22, textAlign: 'center' }}>
              {i < 3 ? MEDAL[i] : `${i+1}`}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 12, color: t.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.producto}
                </span>
                <span style={{ fontSize: 12, fontWeight: 700, color: POS_COLORS[i] || t.textMuted, flexShrink: 0, marginLeft: 8, fontVariantNumeric: 'tabular-nums' }}>
                  {cop(item.valor)}
                </span>
              </div>
              <AnimBar pct={(item.valor / max) * 100} color={POS_COLORS[i] || t.textMuted} delay={i * 80} />
            </div>
            <span style={{ fontSize: 10, color: t.textMuted, minWidth: 28, textAlign: 'right' }}>
              {num(item.frecuencia)}×
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

const CRITERIOS = [
  { id: 'ingresos',   icon: '💰', label: 'Por Ingresos',   desc: 'Dinero generado por producto' },
  { id: 'frecuencia', icon: '🔁', label: 'Por Frecuencia', desc: 'Veces vendido' },
  { id: 'categoria',  icon: '📂', label: 'Por Categoría',  desc: 'Top 5 por categoría' },
]

export default function TabTopProductos({ refreshKey }) {
  const t = useTheme()
  const [periodo,  setPeriodo]  = useState('semana')
  const [criterio, setCriterio] = useState('ingresos')
  const [vista,    setVista]    = useState('visual')

  const { data, loading, error } = useFetch(
    `/ventas/top2?periodo=${periodo}&criterio=${criterio}`,
    [periodo, criterio, refreshKey]
  )

  const top    = data?.top || []
  const porCat = data?.por_categoria || {}
  const esCat  = criterio === 'categoria'
  const cats   = Object.entries(porCat)

  const top3          = top.slice(0, 3)
  const rest          = top.slice(3)
  const total         = top.reduce((a, p) => a + p.valor, 0)
  const max           = top[0]?.valor || 1
  const totalRegistros= top.reduce((a, p) => a + (p.frecuencia || 1), 0)
  const ticketProm    = totalRegistros > 0 ? total / totalRegistros : 0
  const periodoLabel  = periodo === 'semana' ? 'Esta semana' : 'Este mes'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <style>{`@keyframes fadeSlideIn { from { opacity:0; transform:translateY(6px) } to { opacity:1; transform:translateY(0) } }`}</style>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 800, color: t.text, margin: 0, letterSpacing: '-.02em' }}>Top Productos</h2>
          <p style={{ fontSize: 11, color: t.textMuted, margin: '4px 0 0' }}>
            {CRITERIOS.find(c => c.id === criterio)?.desc} · {periodoLabel.toLowerCase()}
          </p>
        </div>
        <div style={{ display: 'flex', background: t.tableAlt, border: `1px solid ${t.border}`, borderRadius: 10, padding: 3, gap: 2 }}>
          {[['semana','Esta Semana'],['mes','Este Mes']].map(([v, lbl]) => (
            <button key={v} onClick={() => setPeriodo(v)} style={{
              padding: '6px 14px', borderRadius: 8, border: 'none',
              background: periodo === v ? t.accent : 'transparent',
              color: periodo === v ? '#fff' : t.textMuted,
              fontSize: 11, fontWeight: periodo === v ? 700 : 500,
              cursor: 'pointer', transition: 'all .15s', fontFamily: 'inherit',
            }}>{lbl}</button>
          ))}
        </div>
      </div>

      {/* Criterios */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {CRITERIOS.map(c => {
          const active = criterio === c.id
          return (
            <button key={c.id} onClick={() => { setCriterio(c.id); setVista('visual') }} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 99,
              background: active ? t.accent : t.card,
              border: `1.5px solid ${active ? t.accent : t.border}`,
              color: active ? '#fff' : t.textSub,
              fontSize: 12, fontWeight: active ? 700 : 400,
              cursor: 'pointer', transition: 'all .15s', fontFamily: 'inherit',
              boxShadow: active ? `0 2px 8px ${t.accent}40` : 'none',
            }}>
              <span style={{ fontSize: 13 }}>{c.icon}</span>{c.label}
            </button>
          )
        })}
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {!loading && !error && !esCat && top.length > 0 && (
        <>
          {/* KPIs */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <KpiCard
              label="Total generado" accent={t.accent} t={t}
              value={<AnimNum target={total} format={v => cop(v)} />}
              sub={`${top.length} productos · ${periodoLabel.toLowerCase()}`}
            />
            {criterio === 'ingresos' && (
              <KpiCard
                label="Ticket promedio" accent={t.blue} t={t}
                value={<AnimNum target={Math.round(ticketProm)} format={v => cop(v)} />}
                sub="por transacción registrada"
              />
            )}
            <KpiCard
              label="Producto líder" accent={t.green} t={t}
              value={top[0]?.producto?.split(' ').slice(0, 2).join(' ') || '—'}
              sub={criterio === 'frecuencia'
                ? `${num(top[0]?.valor || 0)} veces vendido`
                : cop(top[0]?.valor || 0) + ' generados'}
            />
          </div>

          {/* Toggle vista */}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <div style={{ display: 'flex', background: t.tableAlt, border: `1px solid ${t.border}`, borderRadius: 8, padding: 2, gap: 2 }}>
              {[['visual','📊 Visual'],['tabla','📋 Tabla']].map(([v, lbl]) => (
                <button key={v} onClick={() => setVista(v)} style={{
                  padding: '5px 12px', borderRadius: 6, border: 'none',
                  background: vista === v ? t.card : 'transparent',
                  color: vista === v ? t.text : t.textMuted,
                  fontSize: 11, fontWeight: vista === v ? 600 : 400,
                  cursor: 'pointer', transition: 'all .12s', fontFamily: 'inherit',
                  boxShadow: vista === v ? '0 1px 3px rgba(0,0,0,.1)' : 'none',
                }}>{lbl}</button>
              ))}
            </div>
          </div>

          {vista === 'visual' && (
            <>
              {/* Podio top 3 */}
              {top3.length > 0 && (
                <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 16, padding: '24px 20px 0' }}>
                  <div style={{ fontSize: 9, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 20, textAlign: 'center' }}>
                    Podio — {criterio === 'frecuencia' ? 'más vendidos' : 'mayor ingreso'}
                  </div>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end' }}>
                    {[top3[1], top3[0], top3[2]].filter(Boolean).map(item => (
                      <PodioCard key={item.posicion} item={item} t={t} criterio={criterio} />
                    ))}
                  </div>
                </div>
              )}

              {/* Lista 4-10 */}
              {rest.length > 0 && (
                <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 16, padding: '16px 20px' }}>
                  <div style={{ fontSize: 9, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 4 }}>
                    Posiciones 4 – {3 + rest.length}
                  </div>
                  {rest.map((item, i) => (
                    <ListRow key={item.posicion} item={item} max={max} t={t} criterio={criterio} delay={i * 60} />
                  ))}
                </div>
              )}
            </>
          )}

          {vista === 'tabla' && (
            <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: t.text }}>Detalle completo</span>
              </div>
              <TablaDetalle top={top} criterio={criterio} t={t} />
            </div>
          )}
        </>
      )}

      {/* Por categoría */}
      {!loading && !error && esCat && (
        cats.length === 0
          ? <EmptyState />
          : <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {cats.map(([cat, prods]) => (
                <CatSection key={cat} cat={cat} prods={prods} t={t} />
              ))}
            </div>
      )}

      {!loading && !error && !esCat && top.length === 0 && <EmptyState />}
    </div>
  )
}
