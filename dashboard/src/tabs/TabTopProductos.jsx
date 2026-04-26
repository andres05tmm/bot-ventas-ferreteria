import { useState, useEffect, useRef, useCallback } from 'react'
import {
  useTheme, useFetch, GlassCard, Spinner, ErrorMsg, EmptyState, cop, num,
} from '../components/shared.jsx'

// ── Paleta ────────────────────────────────────────────────────────────────────
const POS_COLORS = [
  '#D42010','#E85A10','#F59E0B',
  '#64748B','#64748B','#64748B','#64748B','#64748B','#64748B','#64748B',
]
const MEDAL = ['🥇','🥈','🥉']

// ── Helpers ───────────────────────────────────────────────────────────────────
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

function shortVal(v, criterio) {
  if (criterio === 'frecuencia') return `${num(v)}×`
  if (v >= 1e6) return `$${(v/1e6).toFixed(1)}M`
  if (v >= 1e3) return `$${(v/1e3).toFixed(0)}k`
  return `$${num(v)}`
}

// ── Tooltip flotante ──────────────────────────────────────────────────────────
function Tooltip({ item, criterio, t, visible, x, y }) {
  if (!visible || !item) return null
  return (
    <div style={{
      position: 'fixed', left: x + 14, top: y - 10,
      background: t.id === 'caramelo' ? '#1C1410' : t.card,
      border: `1px solid ${t.border}`,
      borderRadius: 10, padding: '9px 13px',
      pointerEvents: 'none', zIndex: 9000,
      boxShadow: '0 8px 24px rgba(0,0,0,.25)',
      minWidth: 180, maxWidth: 240,
      animation: 'ttFade .12s ease both',
    }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: t.id === 'caramelo' ? '#F5F0E8' : t.text, marginBottom: 6, lineHeight: 1.3 }}>
        {item.producto}
      </div>
      {item.categoria && (
        <div style={{ fontSize: 10, color: '#9C8E82', marginBottom: 7 }}>{item.categoria}</div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <div>
          <div style={{ fontSize: 9, color: '#9C8E82', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 2 }}>
            {criterio === 'frecuencia' ? 'Veces vendido' : 'Ingresos'}
          </div>
          <div style={{ fontSize: 14, fontWeight: 800, color: POS_COLORS[item.posicion - 1] || '#64748B', fontVariantNumeric: 'tabular-nums' }}>
            {criterio === 'frecuencia' ? `${num(item.valor)}×` : cop(item.valor)}
          </div>
        </div>
        {criterio === 'ingresos' && item.frecuencia != null && (
          <div>
            <div style={{ fontSize: 9, color: '#9C8E82', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 2 }}>Registros</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: t.id === 'caramelo' ? '#F5F0E8' : t.text }}>{num(item.frecuencia)}</div>
          </div>
        )}
        {criterio === 'frecuencia' && item.ingresos != null && (
          <div>
            <div style={{ fontSize: 9, color: '#9C8E82', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 2 }}>Total $</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#34D060' }}>{cop(item.ingresos)}</div>
          </div>
        )}
      </div>
      <div style={{ marginTop: 7, display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ flex: 1, height: 3, borderRadius: 99, background: 'rgba(128,128,128,.2)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${item._pct || 0}%`, background: POS_COLORS[item.posicion - 1] || '#64748B', borderRadius: 99 }}/>
        </div>
        <span style={{ fontSize: 10, color: '#9C8E82' }}>{(item._pct || 0).toFixed(1)}%</span>
      </div>
    </div>
  )
}

// ── Gráfico de barras horizontal custom ───────────────────────────────────────
const BAR_H   = 36   // altura de cada barra
const BAR_GAP = 14   // espacio entre barras
const LABEL_W = 170  // ancho columna de nombres
const VAL_W   = 80   // ancho columna de valores
const RADIUS  = 5    // border-radius barra

function HBarChart({ top, criterio, t }) {
  const [widths,  setWidths]  = useState([])
  const [ttItem,  setTtItem]  = useState(null)
  const [ttPos,   setTtPos]   = useState({ x: 0, y: 0 })
  const [ttVis,   setTtVis]   = useState(false)

  const max   = top[0]?.valor || 1
  const total = top.reduce((a, p) => a + p.valor, 0)

  // Animación de entrada de barras
  useEffect(() => {
    setWidths(new Array(top.length).fill(0))
    const t = setTimeout(() => {
      setWidths(top.map(p => p.valor / max))
    }, 60)
    return () => clearTimeout(t)
  }, [top])

  // Número de ticks del eje X
  const tickCount = 5
  const ticks = Array.from({ length: tickCount }, (_, i) => (i / (tickCount - 1)) * max)

  const svgH = top.length * (BAR_H + BAR_GAP) + 30 // +30 para eje X

  const onMouseMove = useCallback((e, item, pct) => {
    setTtItem({ ...item, _pct: pct })
    setTtPos({ x: e.clientX, y: e.clientY })
    setTtVis(true)
  }, [])
  const onMouseLeave = useCallback(() => setTtVis(false), [])

  return (
    <div style={{ position: 'relative', userSelect: 'none' }}>
      <Tooltip item={ttItem} criterio={criterio} t={t} visible={ttVis} x={ttPos.x} y={ttPos.y} />

      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        {/* Columna de nombres */}
        <div style={{ width: LABEL_W, flexShrink: 0, paddingBottom: 30 }}>
          {top.map((item, i) => (
            <div key={i} style={{
              height: BAR_H, marginBottom: BAR_GAP,
              display: 'flex', alignItems: 'center',
              paddingRight: 12,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
                {/* Posición / medalla */}
                {i < 3
                  ? <span style={{ fontSize: 15, flexShrink: 0 }}>{MEDAL[i]}</span>
                  : <span style={{
                      width: 20, height: 20, borderRadius: 5,
                      background: `${POS_COLORS[i]}18`,
                      border: `1px solid ${POS_COLORS[i]}33`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 9, fontWeight: 700, color: POS_COLORS[i], flexShrink: 0,
                    }}>{i + 1}</span>
                }
                <span style={{
                  fontSize: 11, color: t.text, fontWeight: i === 0 ? 700 : 500,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  lineHeight: 1.2,
                }}>{item.producto}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Zona del gráfico — flex 1 */}
        <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
          <svg
            width="100%" height={svgH}
            style={{ overflow: 'visible', display: 'block' }}
            viewBox={`0 0 100 ${svgH}`}
            preserveAspectRatio="none"
          >
            {/* Grid lines verticales */}
            {ticks.map((tick, ti) => {
              const xPct = (tick / max) * 100
              return (
                <line key={ti}
                  x1={`${xPct}%`} y1={0}
                  x2={`${xPct}%`} y2={svgH - 30}
                  stroke={t.border} strokeWidth="0.5"
                  strokeDasharray={ti === 0 ? 'none' : '3 3'}
                />
              )
            })}
          </svg>

          {/* Barras absolutas sobre el SVG */}
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0 }}>
            {top.map((item, i) => {
              const pct    = total > 0 ? (item.valor / total) * 100 : 0
              const color  = POS_COLORS[i]
              const wFrac  = widths[i] || 0

              return (
                <div key={i} style={{
                  height: BAR_H, marginBottom: BAR_GAP,
                  display: 'flex', alignItems: 'center', cursor: 'pointer',
                }}
                  onMouseMove={e => onMouseMove(e, item, pct)}
                  onMouseLeave={onMouseLeave}
                >
                  {/* Track (fondo) */}
                  <div style={{
                    flex: 1, height: BAR_H - 12, borderRadius: RADIUS,
                    background: `${color}14`,
                    position: 'relative', overflow: 'hidden',
                  }}>
                    {/* Barra animada */}
                    <div style={{
                      position: 'absolute', top: 0, left: 0, bottom: 0,
                      width: `${wFrac * 100}%`,
                      borderRadius: RADIUS,
                      background: i === 0
                        ? `linear-gradient(90deg, ${color}dd 0%, ${color} 60%, ${color}ee 100%)`
                        : i === 1
                        ? `linear-gradient(90deg, ${color}cc 0%, ${color} 100%)`
                        : `linear-gradient(90deg, ${color}99 0%, ${color}cc 100%)`,
                      transition: 'width .8s cubic-bezier(.22,1,.36,1)',
                      transitionDelay: `${i * 55}ms`,
                      boxShadow: i < 3 ? `inset 0 1px 0 rgba(255,255,255,.15)` : 'none',
                    }}>
                      {/* Shine overlay para top 3 */}
                      {i < 3 && (
                        <div style={{
                          position: 'absolute', inset: 0,
                          background: 'linear-gradient(180deg, rgba(255,255,255,.12) 0%, transparent 60%)',
                          borderRadius: RADIUS,
                        }}/>
                      )}
                    </div>

                    {/* Valor inline (aparece cuando la barra es suficientemente larga) */}
                    {wFrac > 0.22 && (
                      <div style={{
                        position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                        fontSize: 10, fontWeight: 700, color: '#fff',
                        opacity: wFrac > 0.35 ? 0.9 : 0,
                        transition: 'opacity .4s',
                        transitionDelay: `${i * 55 + 400}ms`,
                        fontVariantNumeric: 'tabular-nums',
                        textShadow: '0 1px 2px rgba(0,0,0,.3)',
                        pointerEvents: 'none',
                      }}>
                        {shortVal(item.valor, criterio)}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Eje X — etiquetas */}
          <div style={{
            height: 30, display: 'flex', alignItems: 'flex-end', paddingBottom: 4,
            position: 'relative',
          }}>
            {ticks.map((tick, ti) => (
              <div key={ti} style={{
                position: 'absolute',
                left: `${(tick / max) * 100}%`,
                transform: 'translateX(-50%)',
                fontSize: 9, color: t.textMuted,
                fontVariantNumeric: 'tabular-nums',
                whiteSpace: 'nowrap',
              }}>
                {shortVal(tick, criterio)}
              </div>
            ))}
          </div>
        </div>

        {/* Columna de valores — siempre visible */}
        <div style={{ width: VAL_W, flexShrink: 0, paddingBottom: 30, paddingLeft: 10 }}>
          {top.map((item, i) => (
            <div key={i} style={{
              height: BAR_H, marginBottom: BAR_GAP,
              display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
            }}>
              <div style={{ textAlign: 'right' }}>
                <div style={{
                  fontSize: 11, fontWeight: 700, color: POS_COLORS[i],
                  fontVariantNumeric: 'tabular-nums',
                  transition: 'color .3s',
                }}>
                  {criterio === 'frecuencia' ? `${num(item.valor)}×` : cop(item.valor)}
                </div>
                {criterio === 'ingresos' && (
                  <div style={{ fontSize: 9, color: t.textMuted, marginTop: 1 }}>
                    {num(item.frecuencia)}×
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── KPI card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, accent, t }) {
  const isCaramelo = t.id === 'caramelo'
  return (
    <div style={{
      background: isCaramelo ? 'rgba(255,255,255,0.72)' : t.card,
      backdropFilter: isCaramelo ? 'blur(12px)' : undefined,
      WebkitBackdropFilter: isCaramelo ? 'blur(12px)' : undefined,
      border: isCaramelo ? '0.5px solid rgba(200,32,14,0.12)' : `1px solid ${t.border}`,
      borderRadius: 16,
      boxShadow: isCaramelo ? '0 2px 12px rgba(0,0,0,0.06), 0 0 0 0.5px rgba(200,32,14,0.08)' : t.shadowCard,
      padding: '16px 20px', flex: 1, minWidth: 0, position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position: 'absolute', top: -18, right: -18, width: 72, height: 72, borderRadius: '50%', background: `${accent}10`, pointerEvents: 'none' }}/>
      <div style={{ fontSize: 9, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: accent, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: 10, color: t.textMuted, marginTop: 5 }}>{sub}</div>}
    </div>
  )
}

// ── Tabla detalle ─────────────────────────────────────────────────────────────
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
                    <span style={{ fontSize: 10, color: t.textMuted, minWidth: 30, textAlign: 'right' }}>{pct.toFixed(1)}%</span>
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
                : cop(top.reduce((a,p)=>a+p.valor,0))}
            </td>
            <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textMuted }}>
              {criterio === 'ingresos'
                ? num(top.reduce((a,p)=>a+(p.frecuencia||0),0))
                : cop(top.reduce((a,p)=>a+(p.ingresos||0),0))}
            </td>
            <td/>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

// ── Vista por categoría ───────────────────────────────────────────────────────
function AnimBar({ pct, color, delay = 0 }) {
  const [w, setW] = useState(0)
  useEffect(() => {
    const t = setTimeout(() => setW(pct), delay + 80)
    return () => clearTimeout(t)
  }, [pct, delay])
  return (
    <div style={{ height: 5, borderRadius: 99, overflow: 'hidden', background: `${color}18`, flex: 1 }}>
      <div style={{
        height: '100%', borderRadius: 99,
        background: `linear-gradient(90deg, ${color}bb, ${color})`,
        width: `${w}%`, transition: 'width .7s cubic-bezier(.22,1,.36,1)',
      }}/>
    </div>
  )
}

function CatSection({ cat, prods, t }) {
  const max = prods[0]?.valor || 1
  return (
    <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 14, overflow: 'hidden' }}>
      <div style={{ padding: '13px 18px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 3, height: 18, borderRadius: 99, background: t.accent, flexShrink: 0 }}/>
        <span style={{ fontWeight: 700, fontSize: 13, color: t.text }}>{cat.replace(/^\d+\s*/, '')}</span>
        <span style={{ fontSize: 10, color: t.textMuted, background: t.tableAlt, border: `1px solid ${t.border}`, borderRadius: 99, padding: '2px 8px' }}>
          {prods.length} productos
        </span>
      </div>
      <div style={{ padding: '6px 18px 14px' }}>
        {prods.map((item, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
            borderBottom: i < prods.length - 1 ? `1px solid ${t.border}` : 'none',
          }}>
            <span style={{ fontSize: i < 3 ? 15 : 11, minWidth: 22, textAlign: 'center', flexShrink: 0 }}>
              {i < 3 ? MEDAL[i] : `${i+1}`}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: t.text, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {item.producto}
                </span>
                <span style={{ fontSize: 11, fontWeight: 700, color: POS_COLORS[i] || t.textMuted, flexShrink: 0, marginLeft: 8, fontVariantNumeric: 'tabular-nums' }}>
                  {cop(item.valor)}
                </span>
              </div>
              <AnimBar pct={(item.valor / max) * 100} color={POS_COLORS[i] || t.textMuted} delay={i * 70} />
            </div>
            <span style={{ fontSize: 10, color: t.textMuted, minWidth: 24, textAlign: 'right', flexShrink: 0 }}>
              {num(item.frecuencia)}×
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Criterio + período selectors ──────────────────────────────────────────────
const CRITERIOS = [
  { id: 'ingresos',   icon: '💰', label: 'Por Ingresos',   desc: 'Dinero generado por producto' },
  { id: 'frecuencia', icon: '🔁', label: 'Por Frecuencia', desc: 'Veces vendido' },
  { id: 'categoria',  icon: '📂', label: 'Por Categoría',  desc: 'Top 5 por categoría' },
]

// ── Tab principal ─────────────────────────────────────────────────────────────
export default function TabTopProductos({ refreshKey }) {
  const t = useTheme()
  const [periodo,  setPeriodo]  = useState('semana')
  const [criterio, setCriterio] = useState('ingresos')
  const [vista,    setVista]    = useState('grafico') // 'grafico' | 'tabla'

  const { data, loading, error } = useFetch(
    `/ventas/top2?periodo=${periodo}&criterio=${criterio}`,
    [periodo, criterio, refreshKey]
  )

  const top    = data?.top || []
  const porCat = data?.por_categoria || {}
  const esCat  = criterio === 'categoria'
  const cats   = Object.entries(porCat)

  const total          = top.reduce((a, p) => a + p.valor, 0)
  const totalRegistros = top.reduce((a, p) => a + (p.frecuencia || 1), 0)
  const ticketProm     = totalRegistros > 0 ? total / totalRegistros : 0
  const periodoLabel   = periodo === 'semana' ? 'Esta semana' : 'Este mes'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <style>{`@keyframes ttFade { from { opacity:0; transform:translateY(4px) } to { opacity:1; transform:translateY(0) } }`}</style>

      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 17, fontWeight: 800, color: t.text, margin: 0, letterSpacing: '-.02em' }}>Top Productos</h2>
          <p style={{ fontSize: 11, color: t.textMuted, margin: '3px 0 0' }}>
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

      {/* ── Criterios ── */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {CRITERIOS.map(c => {
          const active = criterio === c.id
          return (
            <button key={c.id} onClick={() => setCriterio(c.id)} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '7px 14px', borderRadius: 99,
              background: active ? t.accent : t.card,
              border: `1.5px solid ${active ? t.accent : t.border}`,
              color: active ? '#fff' : t.textSub,
              fontSize: 12, fontWeight: active ? 700 : 400,
              cursor: 'pointer', transition: 'all .15s', fontFamily: 'inherit',
              boxShadow: active ? `0 2px 8px ${t.accent}40` : 'none',
            }}>
              <span>{c.icon}</span>{c.label}
            </button>
          )
        })}
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {/* ── Vista ingresos / frecuencia ── */}
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

          {/* Toggle gráfico / tabla */}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <div style={{ display: 'flex', background: t.tableAlt, border: `1px solid ${t.border}`, borderRadius: 8, padding: 2, gap: 2 }}>
              {[['grafico','📊 Gráfico'],['tabla','📋 Tabla']].map(([v, lbl]) => (
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

          {/* Gráfico */}
          {vista === 'grafico' && (
            <GlassCard style={{ padding: '22px 24px 10px' }}>
              <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 18 }}>
                Top 10 — {criterio === 'frecuencia' ? 'Veces vendido' : 'Ingresos generados'}
              </div>
              <HBarChart top={top} criterio={criterio} t={t} />
            </GlassCard>
          )}

          {/* Tabla */}
          {vista === 'tabla' && (
            <GlassCard style={{ padding: 0, overflow: 'hidden' }}>
              <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: t.text }}>Detalle completo</span>
              </div>
              <TablaDetalle top={top} criterio={criterio} t={t} />
            </GlassCard>
          )}
        </>
      )}

      {/* ── Por categoría ── */}
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
