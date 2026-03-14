import { useState, useEffect } from 'react'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop, num, API_BASE,
} from '../components/shared.jsx'

function fmtFecha(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

function agruparMetodos(ventas) {
  const acc = {}
  ;(ventas || []).forEach(v => {
    const raw = String(v.metodo || '').trim().toLowerCase()
    const key =
      raw.includes('efect')  ? 'Efectivo' :
      raw.includes('nequi')  ? 'Nequi' :
      raw.includes('billet') ? 'Billetera' :
      raw.includes('transf') ? 'Transferencia' :
      raw.includes('tarjet') ? 'Tarjeta' :
      raw === '' || raw === '—' ? 'Sin registrar' : 'Otro'
    acc[key] = (acc[key] || 0) + (parseFloat(v.total) || 0)
  })
  return Object.entries(acc).map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
}

function agruparVendedores(ventas) {
  const acc = {}
  ;(ventas || []).forEach(v => {
    const key = String(v.vendedor || '').trim() || 'Sin asignar'
    acc[key] = (acc[key] || 0) + (parseFloat(v.total) || 0)
  })
  return Object.entries(acc)
    .map(([nombre, total]) => ({ nombre, total }))
    .sort((a, b) => b.total - a.total)
}

const METODO_COLORS = ['#dc2626','#2563eb','#16a34a','#d97706','#7c3aed','#6b7280']
const METODO_ICONS  = { Efectivo:'💵', Nequi:'📲', Billetera:'👛', Transferencia:'🏦', Tarjeta:'💳', 'Sin registrar':'❓', Otro:'💸' }
const TOP_COLORS    = ['#dc2626','#ef4444','#f97316','#fb923c','#fbbf24']
const MEDALLAS      = ['🥇','🥈','🥉']

// ─────────────────────────────────────────────────────────────────────────────
// KPI HERO — tarjeta grande con número prominente
// ─────────────────────────────────────────────────────────────────────────────
function KpiHero({ label, value, sub, color, icon, badge }) {
  const t = useTheme()
  return (
    <div style={{
      background: t.card,
      border: `1px solid ${t.border}`,
      borderRadius: 14,
      padding: '20px 22px',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      position: 'relative',
      overflow: 'hidden',
      flex: 1,
      minWidth: 140,
    }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 4, background: color, borderRadius: '14px 14px 0 0' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.12em' }}>
          {label}
        </span>
        <span style={{ fontSize: 18 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 30, fontWeight: 800, color: t.text, letterSpacing: '-0.04em', lineHeight: 1, marginTop: 4 }}>
        {value}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
        {badge && (
          <span style={{
            fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 99,
            background: badge.bg, color: badge.color,
          }}>
            {badge.text}
          </span>
        )}
        {sub && <span style={{ fontSize: 11, color: color, fontWeight: 500 }}>{sub}</span>}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// KPI SECUNDARIO — fila compacta para métricas de apoyo
// ─────────────────────────────────────────────────────────────────────────────
function KpiSecRow({ items, t }) {
  return (
    <div style={{ display: 'flex', gap: 10 }}>
      {items.map((k, i) => (
        <div key={i} style={{
          flex: 1, background: t.tableAlt,
          border: `1px solid ${t.border}`,
          borderRadius: 10, padding: '13px 16px',
        }}>
          <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.1em', marginBottom: 6 }}>
            {k.label}
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: k.color || t.text, letterSpacing: '-0.02em' }}>
            {k.value}
          </div>
          {k.sub && <div style={{ fontSize: 10, color: t.textMuted, marginTop: 4 }}>{k.sub}</div>}
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// BARRA DE MÉTODO con icono y barra de progreso
// ─────────────────────────────────────────────────────────────────────────────
function MetodoBarra({ m, total, color, t }) {
  const pct = total > 0 ? Math.round((m.value / total) * 100) : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 0', borderBottom: `1px solid ${t.border}` }}>
      <div style={{
        width: 38, height: 38, borderRadius: 10, flexShrink: 0,
        background: color + '18', border: `1px solid ${color}33`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
      }}>
        {METODO_ICONS[m.name] || '💸'}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
          <span style={{ fontSize: 13, color: t.text, fontWeight: 500 }}>{m.name}</span>
          <span style={{ fontSize: 14, color: t.text, fontWeight: 700 }}>{cop(m.value)}</span>
        </div>
        <div style={{ height: 5, background: t.border, borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width .6s' }} />
        </div>
      </div>
      <span style={{
        fontSize: 12, fontWeight: 700, minWidth: 34, textAlign: 'right',
        color: color,
      }}>{pct}%</span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// FILA DE VENDEDOR
// ─────────────────────────────────────────────────────────────────────────────
function VendedorFila({ v, i, max, t }) {
  const pct = max > 0 ? Math.round((v.total / max) * 100) : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 0', borderBottom: `1px solid ${t.border}` }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10, flexShrink: 0,
        background: i === 0 ? t.accent + '20' : t.tableAlt,
        border: `1px solid ${i === 0 ? t.accent + '44' : t.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16,
      }}>
        {i < 3 ? MEDALLAS[i] : <span style={{ fontSize: 12, color: t.textMuted, fontWeight: 700 }}>#{i+1}</span>}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
          <span style={{ fontSize: 13, color: t.text, fontWeight: i === 0 ? 600 : 400 }}>{v.nombre}</span>
          <span style={{ fontSize: 14, fontWeight: 700, color: i === 0 ? t.accent : t.text }}>{cop(v.total)}</span>
        </div>
        <div style={{ height: 5, background: t.border, borderRadius: 3, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: i === 0 ? t.accent : t.textMuted, borderRadius: 3 }} />
        </div>
      </div>
      <span style={{ fontSize: 11, color: t.textMuted, minWidth: 30, textAlign: 'right' }}>{pct}%</span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// FILA TOP 5
// ─────────────────────────────────────────────────────────────────────────────
function Top5Fila({ p, i, max, t }) {
  const pct   = max > 0 ? Math.round((p.ingresos / max) * 100) : 0
  const color = TOP_COLORS[i] || t.textMuted
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: `1px solid ${t.border}` }}>
      <div style={{
        width: 28, height: 28, borderRadius: 8, background: color + '20',
        border: `1px solid ${color}44`, display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontSize: 11, fontWeight: 800, color, flexShrink: 0,
      }}>
        {i + 1}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 5 }}>
          <span style={{ fontSize: 12, color: t.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '62%' }}>
            {p.producto}
          </span>
          <span style={{ fontSize: 13, color, fontWeight: 700 }}>{cop(p.ingresos)}</span>
        </div>
        <div style={{ height: 4, background: t.border, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2 }} />
        </div>
      </div>
      <span style={{ fontSize: 10, color: t.textMuted, minWidth: 40, textAlign: 'right', whiteSpace: 'nowrap' }}>
        {num(p.frecuencia || p.unidades)} ×
      </span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TOOLTIP PERSONALIZADO
// ─────────────────────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, t }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: t.card, border: `1px solid ${t.border}`,
      borderRadius: 8, padding: '8px 12px',
    }}>
      <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 2 }}>{payload[0].payload.dia}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: t.accent }}>{cop(payload[0].value)}</div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB PRINCIPAL
// ─────────────────────────────────────────────────────────────────────────────
export default function TabResumen({ refreshKey }) {
  const t = useTheme()
  const [periodo, setPeriodo] = useState('semana')

  const { data: resumen, loading: lRes, error: eRes } = useFetch('/ventas/resumen', [refreshKey])
  const { data: alertasData } = useFetch('/inventario/bajo', [refreshKey])
  const { data: ventasHoy   } = useFetch('/ventas/hoy',     [refreshKey])

  const [top5, setTop5] = useState(null)
  useEffect(() => {
    fetch(`${API_BASE}/ventas/top?periodo=semana`)
      .then(r => r.json())
      .then(d => setTop5(d.top?.slice(0, 5) || []))
      .catch(() => setTop5([]))
  }, [refreshKey])

  if (lRes) return <Spinner />
  if (eRes) return <ErrorMsg msg={`Error cargando resumen: ${eRes}`} />

  const r            = resumen || {}
  const rawHist      = periodo === 'semana' ? (r.historico_7d || []) : (r.historico_mes || [])
  const chartData    = rawHist.map(d => ({ dia: fmtFecha(d.fecha), ventas: d.total || 0 }))
  const totalChart   = chartData.reduce((a, d) => a + d.ventas, 0)
  const maxTop5Ing   = top5?.[0]?.ingresos || 1
  const metodosData  = agruparMetodos(ventasHoy?.ventas)
  const vendData     = agruparVendedores(ventasHoy?.ventas)
  const totalMet     = metodosData.reduce((a, m) => a + m.value, 0)
  const maxVend      = vendData[0]?.total || 1
  const numConsecutivos = [...new Set((ventasHoy?.ventas || []).map(v => v.num))].length

  const promAntes = chartData.length > 1
    ? chartData.slice(0, -1).reduce((a, d) => a + d.ventas, 0) / (chartData.length - 1)
    : 0
  const tendencia = promAntes > 0
    ? Math.round(((r.total_hoy - promAntes) / promAntes) * 100)
    : null
  const tendBadge = tendencia != null ? {
    text: tendencia >= 0 ? `▲ ${tendencia}%` : `▼ ${Math.abs(tendencia)}%`,
    color: tendencia >= 0 ? t.green : '#f87171',
    bg:    tendencia >= 0 ? t.green + '22' : '#f8717122',
  } : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* ── FILA 1: 4 KPIs heroes ─────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <KpiHero
          label="Ventas hoy"
          value={cop(r.total_hoy)}
          sub="Acumulado del día"
          icon="💰"
          color={t.green}
          badge={tendBadge}
        />
        <KpiHero
          label="Esta semana"
          value={cop(r.total_semana)}
          sub="Últimos 7 días"
          icon="📅"
          color={t.blue}
        />
        <KpiHero
          label="Este mes"
          value={cop(r.total_mes)}
          sub="Mes en curso"
          icon="🗓️"
          color={t.accent}
        />
        <KpiHero
          label="Alertas stock"
          value={alertasData?.total ?? '—'}
          sub={alertasData?.total > 0 ? 'Revisar inventario' : 'Todo en orden'}
          icon={alertasData?.total > 0 ? '⚠️' : '✅'}
          color={alertasData?.total > 0 ? t.yellow : t.green}
        />
      </div>

      {/* ── FILA 2: Métricas de apoyo ──────────────────────────────────── */}
      <KpiSecRow t={t} items={[
        {
          label: 'Transacciones hoy',
          value: numConsecutivos,
          color: t.text,
          sub: r.pedidos_hoy > 0 ? `${r.pedidos_hoy} líneas de venta` : 'Sin ventas hoy',
        },
        {
          label: 'Ticket promedio',
          value: cop(r.ticket_prom),
          color: t.accent,
          sub: 'Promedio últimos 7 días',
        },
        {
          label: 'Productos vendidos hoy',
          value: (ventasHoy?.ventas || []).length,
          color: t.text,
          sub: 'Líneas registradas',
        },
      ]} />

      {/* ── FILA 3: Gráfica de evolución ───────────────────────────────── */}
      <Card>
        <div style={{
          display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', marginBottom: 16,
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: t.text }}>
              Evolución de ventas
            </div>
            <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
              Total del período: {' '}
              <span style={{ color: t.accent, fontWeight: 700, fontSize: 15 }}>{cop(totalChart)}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <PeriodBtn active={periodo === 'semana'} onClick={() => setPeriodo('semana')}>7 días</PeriodBtn>
            <PeriodBtn active={periodo === 'mes'}    onClick={() => setPeriodo('mes')}>Mes</PeriodBtn>
          </div>
        </div>

        {chartData.length === 0
          ? <EmptyState msg="Sin datos para este período." />
          : (
            <ResponsiveContainer width="100%" height={210}>
              <AreaChart data={chartData} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={t.accent} stopOpacity={.22} />
                    <stop offset="95%" stopColor={t.accent} stopOpacity={0}   />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={t.border} vertical={false} />
                <XAxis
                  dataKey="dia"
                  tick={{ fill: t.textMuted, fontSize: 10 }}
                  axisLine={false} tickLine={false}
                />
                <YAxis
                  tick={{ fill: t.textMuted, fontSize: 9 }}
                  axisLine={false} tickLine={false}
                  tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
                />
                <Tooltip content={<ChartTooltip t={t} />} cursor={{ stroke: t.accent, strokeWidth: 1, strokeDasharray: '4 4' }} />
                <Area
                  type="monotone" dataKey="ventas" stroke={t.accent} strokeWidth={2.5}
                  fill="url(#gArea)"
                  dot={{ fill: t.accent, r: 3.5, strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: t.accent, strokeWidth: 0 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )
        }
      </Card>

      {/* ── FILA 4: Métodos de pago + Top 5 ──────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>

        {/* Métodos de pago */}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <SectionTitle>Métodos de pago · Hoy</SectionTitle>
            {totalMet > 0 && (
              <span style={{ fontSize: 16, fontWeight: 800, color: t.text }}>{cop(totalMet)}</span>
            )}
          </div>
          {!ventasHoy
            ? <Spinner />
            : metodosData.length === 0
            ? <EmptyState msg="Sin ventas hoy." />
            : (
              <>
                {/* Donut pequeño + resumen */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12, padding: '10px 14px', background: t.tableAlt, borderRadius: 10 }}>
                  <div style={{ flexShrink: 0 }}>
                    <ResponsiveContainer width={72} height={72}>
                      <PieChart>
                        <Pie
                          data={metodosData} dataKey="value"
                          cx="50%" cy="50%"
                          innerRadius={22} outerRadius={34}
                          paddingAngle={3} startAngle={90} endAngle={-270}
                        >
                          {metodosData.map((_, i) => <Cell key={i} fill={METODO_COLORS[i % METODO_COLORS.length]} />)}
                        </Pie>
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
                    {metodosData.slice(0, 2).map((m, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: METODO_COLORS[i], flexShrink: 0, display: 'inline-block' }} />
                        <span style={{ fontSize: 11, color: t.textSub, flex: 1 }}>{m.name}</span>
                        <span style={{ fontSize: 11, fontWeight: 600, color: t.text }}>
                          {totalMet > 0 ? `${Math.round((m.value/totalMet)*100)}%` : '—'}
                        </span>
                      </div>
                    ))}
                    {metodosData.length > 2 && (
                      <div style={{ fontSize: 10, color: t.textMuted }}>+{metodosData.length - 2} más</div>
                    )}
                  </div>
                </div>
                {/* Barras */}
                {metodosData.map((m, i) => (
                  <MetodoBarra key={i} m={m} total={totalMet} color={METODO_COLORS[i % METODO_COLORS.length]} t={t} />
                ))}
              </>
            )
          }
        </Card>

        {/* Top 5 productos */}
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <SectionTitle>Top 5 productos · Semana</SectionTitle>
            {top5?.length > 0 && (
              <span style={{ fontSize: 16, fontWeight: 800, color: t.accent }}>
                {cop(top5.reduce((a, p) => a + (p.ingresos || 0), 0))}
              </span>
            )}
          </div>
          {!top5
            ? <Spinner />
            : top5.length === 0
            ? <EmptyState msg="Sin ventas esta semana." />
            : top5.map((p, i) => (
                <Top5Fila key={i} p={p} i={i} max={maxTop5Ing} t={t} />
              ))
          }
        </Card>
      </div>

      {/* ── FILA 5: Vendedores (solo si hay datos) ────────────────────── */}
      {vendData.length > 0 && (
        <Card>
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            alignItems: 'center', marginBottom: 14,
            paddingBottom: 12, borderBottom: `1px solid ${t.border}`,
          }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Vendedores · Hoy</span>
            <span style={{ fontSize: 11, color: t.textMuted }}>
              {vendData.length} vendedor{vendData.length > 1 ? 'es' : ''}
            </span>
          </div>
          {/* Grid de 2 columnas cuando hay más de 2 vendedores */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: vendData.length > 2 ? '1fr 1fr' : '1fr',
            gap: '0 24px',
          }}>
            {vendData.map((v, i) => (
              <VendedorFila key={i} v={v} i={i} max={maxVend} t={t} />
            ))}
          </div>
        </Card>
      )}

    </div>
  )
}
