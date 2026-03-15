import { useState } from 'react'
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  useTheme, useFetch, Card, SectionTitle, KpiCard, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop,
}, useIsMobile } from '../components/shared.jsx'

const DIAS_OPTIONS = [
  { label: 'Hoy',     value: 1 },
  { label: '7 días',  value: 7 },
  { label: '15 días', value: 15 },
  { label: '30 días', value: 30 },
]

const CAT_COLORS = ['#f87171','#fb923c','#fbbf24','#4ade80','#60a5fa','#a78bfa','#f472b6','#94a3b8']

function fmtFecha(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

export default function TabGastos({ refreshKey }) {
  const t = useTheme()
  const isMobile = useIsMobile()
  const [dias, setDias] = useState(7)
  const { data, loading, error } = useFetch(`/gastos?dias=${dias}`, [dias, refreshKey])

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error cargando gastos: ${error}`} />

  const d          = data || {}
  const gastos     = d.gastos || []
  const historico  = (d.historico || []).map(h => ({ dia: fmtFecha(h.fecha), total: h.total }))
  const porCat     = Object.entries(d.por_categoria || {}).sort((a, b) => b[1] - a[1])
  const pieData    = porCat.map(([name, value]) => ({ name, value }))
  const total      = d.total || 0
  const promDiario = dias > 0 ? total / dias : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Selector período */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Gastos</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            {gastos.length} registros · últimos {dias} {dias === 1 ? 'día' : 'días'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {DIAS_OPTIONS.map(o => (
            <PeriodBtn key={o.value} active={dias === o.value} onClick={() => setDias(o.value)}>
              {o.label}
            </PeriodBtn>
          ))}
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard label="Total gastos"     value={cop(total)}      sub={`Últimos ${dias} días`}  icon="💸" color="#f87171" />
        <KpiCard label="Promedio diario"  value={cop(promDiario)} sub="Gasto diario promedio"    icon="📊" color={t.yellow} />
        <KpiCard label="Categorías"       value={porCat.length}   sub="Tipos de gasto"           icon="📂" color={t.textSub} />
        <KpiCard label="Registros"        value={gastos.length}   sub="Egresos registrados"      icon="📋" color={t.textSub} />
      </div>

      {gastos.length === 0 ? (
        <Card>
          <EmptyState msg="Sin gastos registrados en este período." />
        </Card>
      ) : (
        <>
          {/* Gráficas */}
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>
            {/* Histórico diario */}
            {dias > 1 && (
              <Card>
                <SectionTitle>Gastos por Día</SectionTitle>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={historico} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={t.border} />
                    <XAxis dataKey="dia" tick={{ fill: t.textMuted, fontSize: 10 }} axisLine={false} tickLine={false} />
                    <YAxis
                      tick={{ fill: t.textMuted, fontSize: 9 }} axisLine={false} tickLine={false}
                      tickFormatter={v => v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
                    />
                    <Tooltip
                      contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
                      formatter={v => [cop(v), 'Gastos']}
                    />
                    <Bar dataKey="total" fill="#f87171" radius={[3, 3, 0, 0]} maxBarSize={28} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            )}

            {/* Por categoría */}
            <Card>
              <SectionTitle>Por Categoría</SectionTitle>
              {porCat.length === 0 ? <EmptyState /> : (
                <>
                  <ResponsiveContainer width="100%" height={120}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2}>
                        {pieData.map((_, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
                        formatter={v => [cop(v)]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginTop: 6 }}>
                    {porCat.slice(0, 5).map(([cat, val], i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ width: 8, height: 8, borderRadius: '50%', background: CAT_COLORS[i % CAT_COLORS.length], flexShrink: 0, display: 'inline-block' }} />
                          <span style={{ fontSize: 11, color: t.textSub }}>{cat}</span>
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: t.text }}>{cop(val)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Card>
          </div>

          {/* Tabla detalle */}
          <Card style={{ padding: 0 }}>
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
              <SectionTitle>Detalle de Gastos</SectionTitle>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: t.tableAlt }}>
                    {['Fecha', 'Hora', 'Concepto', 'Categoría', 'Origen', 'Monto'].map((h, i) => (
                      <th key={i} style={{
                        padding: '9px 14px', textAlign: i === 5 ? 'right' : 'left',
                        fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
                        letterSpacing: '.08em', fontWeight: 500,
                        borderBottom: `1px solid ${t.border}`, whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {gastos.map((g, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${t.border}` }}
                      onMouseEnter={e => { e.currentTarget.style.background = t.cardHover; e.currentTarget.style.transform = 'translateX(2px)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.transform = 'translateX(0)' }}>
                      <td style={{ padding: '9px 14px', color: t.textMuted, whiteSpace: 'nowrap' }}>{g.fecha}</td>
                      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{g.hora || '—'}</td>
                      <td style={{ padding: '9px 14px', color: t.text }}>{g.concepto || '—'}</td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{ background: t.accentSub, color: t.accent, border: `1px solid ${t.accent}33`, padding: '2px 8px', borderRadius: 99, fontSize: 10 }}>
                          {g.categoria || 'Sin categoría'}
                        </span>
                      </td>
                      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{g.origen || '—'}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: '#f87171', fontWeight: 600 }}>
                        -{cop(g.monto)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                    <td colSpan={5} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>
                      TOTAL ({gastos.length} registros)
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', color: '#f87171', fontWeight: 700, fontSize: 14 }}>
                      -{cop(total)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}
