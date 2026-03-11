import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { Card, KpiCard, SectionTitle, Spinner, ErrorMsg, useFetch, cop, num } from '../components/shared.jsx'
import { API_BASE } from '../App.jsx'
import { useState, useEffect } from 'react'

function fmt(fecha) {
  if (!fecha) return ''
  const [, mes, dia] = fecha.split('-')
  return `${dia}/${mes}`
}

const AREA_TOOLTIP = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{ background: '#1e1e1e', border: '1px solid #2a2a2a', borderRadius: 6, padding: '8px 12px' }}>
      <div style={{ color: '#888', fontSize: 11, marginBottom: 4 }}>{label}</div>
      <div style={{ color: '#dc2626', fontWeight: 700 }}>{cop(payload[0].value)}</div>
    </div>
  )
}

const BAR_TOOLTIP = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{ background: '#1e1e1e', border: '1px solid #2a2a2a', borderRadius: 6, padding: '8px 12px', maxWidth: 200 }}>
      <div style={{ color: '#f5f5f5', fontSize: 12, marginBottom: 2 }}>{d.producto}</div>
      <div style={{ color: '#888', fontSize: 11 }}>{num(d.unidades)} uds · {cop(d.ingresos)}</div>
    </div>
  )
}

export default function TabResumen() {
  const { data: resumen, loading: lRes, error: eRes } = useFetch('/ventas/resumen')
  const [top5, setTop5] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/ventas/top?periodo=semana`)
      .then(r => r.json())
      .then(d => setTop5(d.top?.slice(0, 5) || []))
      .catch(() => setTop5([]))
  }, [])

  if (lRes) return <Spinner />
  if (eRes) return <ErrorMsg msg={`Error cargando resumen: ${eRes}`} />

  const r = resumen || {}
  const historico = (r.historico_7d || []).map(d => ({ ...d, fecha: fmt(d.fecha) }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* KPIs */}
      <section>
        <SectionTitle>Indicadores del Día</SectionTitle>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          <KpiCard
            label="Ventas hoy"
            value={cop(r.total_hoy)}
            sub="Total acumulado del día"
          />
          <KpiCard
            label="Pedidos hoy"
            value={r.pedidos_hoy ?? 0}
            sub="Transacciones registradas"
            color="#f59e0b"
          />
          <KpiCard
            label="Ticket promedio"
            value={cop(r.ticket_prom)}
            sub="Promedio últimos 7 días"
            color="#22c55e"
          />
          <KpiCard
            label="Ventas semana"
            value={cop(r.total_semana)}
            sub="Últimos 7 días"
            color="#818cf8"
          />
        </div>
      </section>

      {/* Gráfica de área - últimos 7 días */}
      <Card>
        <SectionTitle>Ventas Diarias — Últimos 7 Días</SectionTitle>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={historico} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="gradRojo" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#dc2626" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#dc2626" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
            <XAxis dataKey="fecha" tick={{ fill: '#888', fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fill: '#888', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={v => v >= 1e6 ? `$${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `$${(v/1e3).toFixed(0)}K` : `$${v}`}
            />
            <Tooltip content={<AREA_TOOLTIP />} />
            <Area
              type="monotone"
              dataKey="total"
              stroke="#dc2626"
              strokeWidth={2}
              fill="url(#gradRojo)"
              dot={{ fill: '#dc2626', r: 3 }}
              activeDot={{ r: 5 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </Card>

      {/* Top 5 productos */}
      <Card>
        <SectionTitle>Top 5 Productos — Esta Semana</SectionTitle>
        {!top5 ? <Spinner /> : top5.length === 0 ? (
          <p style={{ color: '#666', fontSize: 13 }}>Sin ventas registradas esta semana.</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={top5} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: '#888', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={v => num(v)}
              />
              <YAxis
                type="category"
                dataKey="producto"
                width={140}
                tick={{ fill: '#ccc', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<BAR_TOOLTIP />} />
              <Bar dataKey="unidades" fill="#dc2626" radius={[0, 4, 4, 0]} maxBarSize={24} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>
    </div>
  )
}
