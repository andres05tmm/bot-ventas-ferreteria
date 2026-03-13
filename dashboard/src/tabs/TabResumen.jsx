import { useState, useEffect, useCallback } from 'react'

function useIsMobile() {
  const [v, setV] = useState(() => window.innerWidth < 768)
  useEffect(() => {
    const fn = () => setV(window.innerWidth < 768)
    window.addEventListener('resize', fn)
    return () => window.removeEventListener('resize', fn)
  }, [])
  return v
}
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import {
  useTheme, useFetch, Card, KpiCard, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop, num,
} from '../components/shared.jsx'
import { API_BASE } from '../App.jsx'

function fmtFecha(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

// Agrupa ventas por método de pago
function agruparMetodos(ventas) {
  const acc = {}
  ;(ventas || []).forEach(v => {
    const raw = String(v.metodo || '').trim().toLowerCase()
    const key =
      raw.includes('efect') ? 'Efectivo' :
      raw.includes('nequi') ? 'Nequi' :
      raw.includes('billet') ? 'Billetera' :
      raw.includes('transf') ? 'Transferencia' :
      raw.includes('tarjet') ? 'Tarjeta' :
      raw === '' || raw === '—' ? 'Sin registrar' : 'Otro'
    acc[key] = (acc[key] || 0) + (parseFloat(v.total) || 0)
  })
  return Object.entries(acc).map(([name, value]) => ({ name, value }))
}

// Agrupa ventas por vendedor
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

const METODO_COLORS = ['#dc2626', '#2563eb', '#16a34a', '#d97706', '#7c3aed', '#888']

export default function TabResumen({ refreshKey }) {
  const t = useTheme()
  const isMobile = useIsMobile()
  const [periodo, setPeriodo] = useState('semana')

  const { data: resumen, loading: lRes, error: eRes } = useFetch('/ventas/resumen', [refreshKey])
  const { data: alertasData } = useFetch('/inventario/bajo', [refreshKey])
  const { data: ventasHoy }   = useFetch('/ventas/hoy',     [refreshKey])

  const [top5, setTop5] = useState(null)
  useEffect(() => {
    fetch(`${API_BASE}/ventas/top?periodo=semana`)
      .then(r => r.json())
      .then(d => setTop5(d.top?.slice(0, 5) || []))
      .catch(() => setTop5([]))
  }, [refreshKey])

  if (lRes) return <Spinner />
  if (eRes) return <ErrorMsg msg={`Error cargando resumen: ${eRes}`} />

  const r = resumen || {}
  const rawHist = periodo === 'semana' ? (r.historico_7d || []) : (r.historico_mes || [])
  const chartData = rawHist.map(d => ({ dia: fmtFecha(d.fecha), ventas: d.total || 0 }))
  const totalChart = chartData.reduce((a, d) => a + d.ventas, 0)
  const maxTop5 = top5?.[0]?.unidades || 1

  const metodosData   = agruparMetodos(ventasHoy?.ventas)
  const vendedoresData = agruparVendedores(ventasHoy?.ventas)

  const RC = [t.accent, '#ef4444', '#f97316', '#fb923c', '#fbbf24']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard label="Ventas hoy"      value={cop(r.total_hoy)}          sub="Acumulado del día"         icon="💰" color={t.green} />
        <KpiCard label="Pedidos hoy"     value={r.pedidos_hoy ?? 0}        sub="Transacciones"             icon="📦" color={t.yellow} />
        <KpiCard label="Stock con alerta" value={alertasData?.total ?? '—'} sub="Sin precio o agotados"    icon="⚠️" color={t.accent} />
        <KpiCard label="Ticket promedio"  value={cop(r.ticket_prom)}        sub="Promedio últimos 7 días"  icon="🧾" color={t.blue} />
        <KpiCard label="Total semana"     value={cop(r.total_semana)}       sub="Últimos 7 días"            icon="📅" color={t.textSub} />
        <KpiCard label="Total mes"        value={cop(r.total_mes)}          sub="Mes en curso"              icon="🗓️" color={t.textSub} />
      </div>

      {/* Gráfica de ventas + selector */}
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <SectionTitle>Ventas — {periodo === 'semana' ? 'Últimos 7 días' : 'Este mes'}</SectionTitle>
          <div style={{ display: 'flex', gap: 6 }}>
            <PeriodBtn active={periodo === 'semana'} onClick={() => setPeriodo('semana')}>Semanal</PeriodBtn>
            <PeriodBtn active={periodo === 'mes'}    onClick={() => setPeriodo('mes')}>Mensual</PeriodBtn>
          </div>
        </div>
        <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 6 }}>
          TOTAL · <span style={{ color: t.accent, fontWeight: 700, fontSize: 15 }}>{cop(totalChart)}</span>
        </div>
        <ResponsiveContainer width="100%" height={190}>
          <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="gradArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={t.accent} stopOpacity={.3} />
                <stop offset="95%" stopColor={t.accent} stopOpacity={0}  />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={t.border} />
            <XAxis dataKey="dia" tick={{ fill: t.textMuted, fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fill: t.textMuted, fontSize: 9 }} axisLine={false} tickLine={false}
              tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
            />
            <Tooltip
              contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
              formatter={v => [cop(v), 'Ventas']}
            />
            <Area type="monotone" dataKey="ventas" stroke={t.accent} strokeWidth={2} fill="url(#gradArea)"
              dot={{ fill: t.accent, r: 3 }} activeDot={{ r: 5 }} />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      {/* Fila: Top 5 + Métodos de pago */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>

        {/* Mini Top 5 */}
        <Card>
          <SectionTitle>Top 5 Productos — Esta Semana</SectionTitle>
          {!top5 ? <Spinner /> : top5.length === 0 ? <EmptyState msg="Sin ventas esta semana." /> : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {top5.map((p, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '22px 1fr 60px 88px', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 11, color: RC[i], textAlign: 'right' }}>#{i+1}</span>
                  <div>
                    <div style={{ fontSize: 11, color: t.text, marginBottom: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.producto}</div>
                    <div style={{ height: 3, background: t.border, borderRadius: 2, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${(p.unidades / maxTop5) * 100}%`, background: RC[i], borderRadius: 2 }} />
                    </div>
                  </div>
                  <span style={{ fontSize: 10, color: t.textMuted, textAlign: 'right' }}>{num(p.unidades)} uds</span>
                  <span style={{ fontSize: 10, color: t.textSub,   textAlign: 'right' }}>{cop(p.ingresos)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Métodos de pago */}
        <Card>
          <SectionTitle>Métodos de Pago — Hoy</SectionTitle>
          {!ventasHoy ? <Spinner /> : metodosData.length === 0 ? <EmptyState msg="Sin ventas hoy." /> : (
            <>
              <ResponsiveContainer width="100%" height={150}>
                <PieChart>
                  <Pie data={metodosData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={40} outerRadius={65} paddingAngle={3}>
                    {metodosData.map((_, i) => <Cell key={i} fill={METODO_COLORS[i % METODO_COLORS.length]} />)}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
                    formatter={v => [cop(v)]}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 4 }}>
                {metodosData.map((m, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                      <span style={{ width: 8, height: 8, borderRadius: '50%', background: METODO_COLORS[i % METODO_COLORS.length], flexShrink: 0, display: 'inline-block' }} />
                      <span style={{ fontSize: 11, color: t.textSub }}>{m.name}</span>
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 600, color: t.text }}>{cop(m.value)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Vendedores del día */}
      {vendedoresData.length > 0 && (
        <Card>
          <SectionTitle>Vendedores — Hoy</SectionTitle>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {vendedoresData.map((v, i) => (
              <div key={i} style={{
                background: i === 0 ? t.accentSub : t.cardHover,
                border: `1px solid ${i === 0 ? t.accent + '55' : t.border}`,
                borderRadius: 8, padding: '10px 16px', flex: 1, minWidth: 140,
              }}>
                <div style={{ fontSize: 11, color: t.textSub, marginBottom: 4 }}>
                  {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i+1}`} {v.nombre}
                </div>
                <div style={{ fontSize: 18, fontWeight: 700, color: i === 0 ? t.accent : t.text }}>{cop(v.total)}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
