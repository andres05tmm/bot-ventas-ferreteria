import { useState, useEffect } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  useTheme, useFetch, Card, GlassCard, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop, num, API_BASE,
  useIsMobile, useCountUp,
} from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'

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

// ── KPI hover: glow borde agresivo + número que crece ────────────────────────
function KpiBig({ label, value, sub, color, icon, pill }) {
  const t          = useTheme()
  const c          = color || t.accent
  const isCaramelo = t.id === 'caramelo'

  // Count-up: parse numeric from formatted string or raw number
  const rawNum = (() => {
    if (typeof value === 'number') return value
    if (typeof value !== 'string') return null
    const cleaned = value.replace(/\$/g, '').replace(/\./g, '').replace(/,.*$/, '').trim()
    const n = parseInt(cleaned, 10)
    return isNaN(n) ? null : n
  })()
  const animated   = useCountUp(rawNum ?? 0, 800)
  const displayVal = rawNum !== null
    ? (typeof value === 'string' && value.startsWith('$')
        ? '$' + Math.round(animated).toLocaleString('es-CO')
        : Math.round(animated).toLocaleString('es-CO'))
    : value

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      style={{
        background: isCaramelo ? 'rgba(255,255,255,0.72)' : t.card,
        backdropFilter:       isCaramelo ? 'blur(12px)' : undefined,
        WebkitBackdropFilter: isCaramelo ? 'blur(12px)' : undefined,
        border: isCaramelo
          ? `0.5px solid rgba(200,32,14,0.14)`
          : `1px solid ${t.border}`,
        borderRadius: 16,
        padding: '18px 20px',
        flex: 1, minWidth: 150,
        cursor: 'default',
        transition: 'border-color .2s ease, box-shadow .2s ease',
        boxShadow: isCaramelo
          ? '0 2px 12px rgba(0,0,0,0.07), 0 0 0 0.5px rgba(200,32,14,0.08)'
          : t.shadowCard,
      }}
    >
      {/* Header: label + ícono */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <span style={{ fontSize: 10, color: t.textMuted, fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase' }}>
          {label}
        </span>
        <span style={{ fontSize: 18, opacity: .55, display: 'inline-block' }}>{icon}</span>
      </div>

      {/* Valor con count-up */}
      <div style={{
        fontSize: 24,
        fontWeight: 700,
        color: t.text,
        letterSpacing: '-0.03em', lineHeight: 1,
        fontVariantNumeric: 'tabular-nums',
        marginBottom: 10,
      }}>
        {displayVal}
      </div>

      {/* Sub */}
      {sub && <div style={{ fontSize: 11, color: t.textMuted }}>{sub}</div>}

      {/* Pill */}
      {pill && (
        <div style={{
          display: 'inline-block', marginTop: 8,
          fontSize: 10, padding: '3px 9px', borderRadius: 99,
          background: c + '1a', color: c,
          border: `1px solid ${c}44`,
          fontWeight: 600,
        }}>
          {pill}
        </div>
      )}
    </motion.div>
  )
}

function MetodoCard({ m, total, color, t }) {
  const pct = total > 0 ? Math.round((m.value / total) * 100) : 0
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '10px 0',
      borderBottom: `1px solid ${t.border}`,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 10, flexShrink: 0,
        background: color + '22',
        border: `1px solid ${color}44`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 16,
      }}>
        {METODO_ICONS[m.name] || '💸'}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: t.text, fontWeight: 500 }}>{m.name}</span>
          <span style={{ fontSize: 12, color: t.text, fontWeight: 700 }}>{cop(m.value)}</span>
        </div>
        <div style={{ height: 4, background: t.border, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2, transition: 'width .5s' }} />
        </div>
      </div>
      <span style={{ fontSize: 10, color: t.textMuted, minWidth: 28, textAlign: 'right' }}>{pct}%</span>
    </div>
  )
}

function VendedorRow({ v, i, maxTotal, t }) {
  const pct = maxTotal > 0 ? Math.round((v.total / maxTotal) * 100) : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderBottom: `1px solid ${t.border}` }}>
      <span style={{ fontSize: 18, minWidth: 24, textAlign: 'center' }}>
        {i < 3 ? MEDALLAS[i] : <span style={{ fontSize: 11, color: t.textMuted }}>#{i+1}</span>}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: t.text, fontWeight: 500 }}>{v.nombre}</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: i === 0 ? t.accent : t.text }}>{cop(v.total)}</span>
        </div>
        <div style={{ height: 4, background: t.border, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: i === 0 ? t.accent : t.textMuted, borderRadius: 2 }} />
        </div>
      </div>
      <span style={{ fontSize: 10, color: t.textMuted, minWidth: 28, textAlign: 'right' }}>{pct}%</span>
    </div>
  )
}

// Formatea cantidad + unidad de forma inteligente:
// gramos → muestra en kg si ≥1000, si no en g
// resto   → muestra con la etiqueta correcta (galón, mts, kg, uds…)
function formatCantidadTop(unidades, unidad_medida) {
  const u = (unidad_medida || 'Unidad').toLowerCase().replace('ó', 'o')
  const esGramos = u === 'gramos' || u === 'grm' || u === 'g'
  const esKg     = u === 'kg'
  const esMts    = u === 'mts' || u === 'cms'
  const esGalon  = u === 'galón' || u === 'galon' || u === 'lt' || u === 'lts'

  if (esGramos) {
    if (unidades >= 1000) return `${(unidades / 1000).toFixed(1).replace(/\.0$/, '')} kg`
    return `${num(unidades)} g`
  }
  if (esKg)    return `${num(unidades)} kg`
  if (esMts)   return `${num(unidades)} ${u}`
  if (esGalon) return `${num(unidades)} gal`
  return `${num(unidades)} uds`
}

function TopRow({ p, i, max, t }) {
  const pct = max > 0 ? Math.round((p.ingresos / max) * 100) : 0
  const color = TOP_COLORS[i] || t.textMuted
  const cantLabel = formatCantidadTop(p.unidades, p.unidad_medida)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderBottom: `1px solid ${t.border}` }}>
      <div style={{
        width: 24, height: 24, borderRadius: 6, background: color + '22',
        border: `1px solid ${color}44`, display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontSize: 10, fontWeight: 800, color, flexShrink: 0,
      }}>
        {i + 1}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
          <span style={{ fontSize: 11, color: t.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '65%' }}>
            {p.producto}
          </span>
          <span style={{ fontSize: 11, color, fontWeight: 700 }}>{cop(p.ingresos)}</span>
        </div>
        <div style={{ height: 3, background: t.border, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2 }} />
        </div>
      </div>
      <span style={{ fontSize: 10, color: t.textMuted, minWidth: 40, textAlign: 'right' }}>
        {cantLabel}
      </span>
    </div>
  )
}

const kpiVariants = {
  hidden:  { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: 'easeOut' } },
}

export default function TabResumen({ refreshKey }) {
  const t = useTheme()
  const isMobile = useIsMobile()
  const prefersReducedMotion = useReducedMotion()
  const [periodo, setPeriodo] = useState('semana')
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()

  const vendorParam = selectedVendor ? `?vendor_id=${selectedVendor}` : ''
  const { data: resumen, loading: lRes, error: eRes } = useFetch(`/ventas/resumen${vendorParam}`, [refreshKey, selectedVendor])
  const { data: alertasData } = useFetch('/inventario/bajo', [refreshKey])
  const { data: ventasHoy }   = useFetch(`/ventas/hoy${vendorParam}`,     [refreshKey, selectedVendor])

  const [top5, setTop5] = useState(null)
  useEffect(() => {
    const url = `${API_BASE}/ventas/top?periodo=semana${selectedVendor ? `&vendor_id=${selectedVendor}` : ''}`
    authFetch(url)
      .then(r => r.json())
      .then(d => setTop5(d.top?.slice(0, 5) || []))
      .catch(() => setTop5([]))
  }, [refreshKey, authFetch, selectedVendor])

  if (lRes) return <Spinner />
  if (eRes) return <ErrorMsg msg={`Error cargando resumen: ${eRes}`} />

  const r          = resumen || {}
  const rawHist    = periodo === 'semana' ? (r.historico_7d || []) : (r.historico_mes || [])
  const chartData  = rawHist.map(d => ({ dia: fmtFecha(d.fecha), ventas: d.total || 0 }))
  const totalChart = chartData.reduce((a, d) => a + d.ventas, 0)
  const maxTop5Ing = top5?.[0]?.ingresos || 1

  const metodosData    = agruparMetodos(ventasHoy?.ventas)
  const vendedoresData = agruparVendedores(ventasHoy?.ventas)
  const totalMetodos   = metodosData.reduce((a, m) => a + m.value, 0)
  const maxVendedor    = vendedoresData[0]?.total || 1

  const promAntes = chartData.length > 1
    ? chartData.slice(0, -1).reduce((a, d) => a + d.ventas, 0) / (chartData.length - 1)
    : 0
  const tendencia = promAntes > 0
    ? Math.round(((r.total_hoy - promAntes) / promAntes) * 100)
    : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* KPIs */}
      <motion.div
        style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : 'repeat(auto-fill, minmax(170px, 1fr))', gap: 10 }}
        initial={prefersReducedMotion ? false : 'hidden'}
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.08 } } }}
      >
        <motion.div variants={kpiVariants}><KpiBig
          label="Ventas hoy"
          value={cop(r.total_hoy)}
          sub="Acumulado del día"
          pill={tendencia != null
            ? (tendencia >= 0 ? `▲ ${tendencia}% vs promedio` : `▼ ${Math.abs(tendencia)}% vs promedio`)
            : 'Sin comparativa aún'}
          icon="💰"
          color={t.green}
        /></motion.div>
        <motion.div variants={kpiVariants}><KpiBig
          label="Pedidos hoy"
          value={r.pedidos_hoy ?? 0}
          sub="Transacciones"
          pill={r.pedidos_hoy > 0 ? `Ticket prom: ${cop(r.ticket_prom)}` : 'Sin ventas aún'}
          icon="🧾"
          color={t.accent}
        /></motion.div>
        <motion.div variants={kpiVariants}><KpiBig
          label="Stock con alerta"
          value={alertasData?.total ?? '—'}
          sub={alertasData?.total > 0 ? 'Sin precio o agotados' : 'Sin alertas'}
          pill={alertasData?.total > 0 ? 'Ver en Inventario' : 'Todo en orden'}
          icon="⚠️"
          color={alertasData?.total > 0 ? t.yellow : t.green}
        /></motion.div>
        <motion.div variants={kpiVariants}><KpiBig
          label="Ticket promedio"
          value={cop(r.ticket_prom)}
          sub="Últimos 7 días"
          pill="Promedio por venta"
          icon="🧮"
          color={t.textSub}
        /></motion.div>
        <motion.div variants={kpiVariants}><KpiBig
          label="Total semana"
          value={cop(r.total_semana)}
          sub="Últimos 7 días"
          pill="Ver gráfica abajo"
          icon="📅"
          color={t.blue}
        /></motion.div>
        <motion.div variants={kpiVariants}><KpiBig
          label="Total mes"
          value={cop(r.total_mes)}
          sub="Mes en curso"
          pill="Acumulado mensual"
          icon="🗓️"
          color={t.textSub}
        /></motion.div>
      </motion.div>

      {/* Gráfica */}
      <GlassCard>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: t.text }}>
              Evolución de Ventas
            </div>
            <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>
              Total del período:{' '}
              <span style={{ color: t.accent, fontWeight: 700, fontSize: 14 }}>{cop(totalChart)}</span>
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
            <ResponsiveContainer width="100%" height={isMobile ? 160 : 200}>
              <AreaChart data={chartData} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={t.accent} stopOpacity={.25} />
                    <stop offset="95%" stopColor={t.accent} stopOpacity={0}   />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={t.border} vertical={false} />
                <XAxis dataKey="dia" tick={{ fill: t.textMuted, fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis
                  tick={{ fill: t.textMuted, fontSize: 9 }} axisLine={false} tickLine={false}
                  tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
                />
                <Tooltip
                  contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
                  formatter={v => [cop(v), 'Ventas']}
                  cursor={{ stroke: t.accent, strokeWidth: 1, strokeDasharray: '4 4' }}
                />
                <Area
                  type="monotone" dataKey="ventas" stroke={t.accent} strokeWidth={2.5}
                  fill="url(#gradArea)" dot={{ fill: t.accent, r: 3, strokeWidth: 0 }}
                  activeDot={{ r: 5, fill: t.accent }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
      </GlassCard>

      {/* Métodos + Top 5 */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>
        <GlassCard>
          <SectionTitle>Métodos de Pago · Hoy</SectionTitle>
          {!ventasHoy
            ? <Spinner />
            : metodosData.length === 0
            ? <EmptyState msg="Sin ventas hoy." />
            : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14 }}>
                  <ResponsiveContainer width={90} height={90}>
                    <PieChart>
                      <Pie data={metodosData} dataKey="value" cx="50%" cy="50%" innerRadius={26} outerRadius={42} paddingAngle={2} startAngle={90} endAngle={-270}>
                        {metodosData.map((_, i) => <Cell key={i} fill={METODO_COLORS[i % METODO_COLORS.length]} />)}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: t.text }}>{cop(totalMetodos)}</div>
                    <div style={{ fontSize: 10, color: t.textMuted, marginTop: 2 }}>Total del día</div>
                    <div style={{ fontSize: 11, color: t.textSub, marginTop: 4 }}>
                      {metodosData.length} método{metodosData.length > 1 ? 's' : ''}
                    </div>
                  </div>
                </div>
                {metodosData.map((m, i) => (
                  <MetodoCard key={i} m={m} total={totalMetodos} color={METODO_COLORS[i % METODO_COLORS.length]} t={t} />
                ))}
              </>
            )
          }
        </GlassCard>

        <GlassCard>
          <SectionTitle>Top 5 Productos · Esta Semana</SectionTitle>
          {!top5
            ? <Spinner />
            : top5.length === 0
            ? <EmptyState msg="Sin ventas esta semana." />
            : (
              <>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  marginBottom: 12, padding: '8px 12px',
                  background: t.tableAlt, borderRadius: 8,
                }}>
                  <span style={{ fontSize: 11, color: t.textMuted }}>Ingresos top 5</span>
                  <span style={{ fontSize: 14, fontWeight: 800, color: t.accent }}>
                    {cop(top5.reduce((a, p) => a + (p.ingresos || 0), 0))}
                  </span>
                </div>
                {top5.map((p, i) => (
                  <TopRow key={i} p={p} i={i} max={maxTop5Ing} t={t} />
                ))}
              </>
            )
          }
        </GlassCard>
      </div>

      {/* Vendedores */}
      {vendedoresData.length > 0 && (
        <GlassCard>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, paddingBottom: 10, borderBottom: `1px solid ${t.border}` }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: t.text }}>Vendedores · Hoy</span>
            <span style={{ fontSize: 11, color: t.textMuted }}>
              {vendedoresData.length} vendedor{vendedoresData.length > 1 ? 'es' : ''}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {vendedoresData.map((v, i) => (
              <VendedorRow key={i} v={v} i={i} maxTotal={maxVendedor} t={t} />
            ))}
          </div>
        </GlassCard>
      )}

    </div>
  )
}
