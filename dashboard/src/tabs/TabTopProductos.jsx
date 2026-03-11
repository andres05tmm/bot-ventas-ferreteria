import { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, Th, cop, num,
} from '../components/shared.jsx'

const BAR_TOOLTIP = ({ active, payload, t }) => {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{ background: '#1e1e1e', border: '1px solid #2a2a2a', borderRadius: 6, padding: '8px 12px', maxWidth: 220 }}>
      <div style={{ color: '#f5f5f5', fontSize: 12, marginBottom: 4 }}>{d.producto}</div>
      <div style={{ color: '#dc2626', fontWeight: 700 }}>{num(d.unidades)} unidades</div>
      <div style={{ color: '#888', fontSize: 11, marginTop: 2 }}>{cop(d.ingresos)}</div>
    </div>
  )
}

export default function TabTopProductos({ refreshKey }) {
  const t = useTheme()
  const [periodo, setPeriodo] = useState('semana')
  const { data, loading, error } = useFetch(`/ventas/top?periodo=${periodo}`, [periodo, refreshKey])

  const top = data?.top || []
  const totalUnidades = top.reduce((a, p) => a + p.unidades, 0)
  const totalIngresos = top.reduce((a, p) => a + p.ingresos, 0)

  const barColors = top.map((_, i) => {
    if (i === 0) return t.accent
    if (i === 1) return '#ef4444'
    if (i === 2) return '#f97316'
    if (i < 5)   return '#fb923c'
    return t.border
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Header + selector */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Top 10 Productos</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            Ranking por unidades vendidas · {periodo === 'semana' ? 'esta semana' : 'este mes'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <PeriodBtn active={periodo === 'semana'} onClick={() => setPeriodo('semana')}>Esta Semana</PeriodBtn>
          <PeriodBtn active={periodo === 'mes'}    onClick={() => setPeriodo('mes')}>Este Mes</PeriodBtn>
        </div>
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {!loading && !error && (
        <>
          {/* Totales rápidos */}
          {top.length > 0 && (
            <div style={{ display: 'flex', gap: 10 }}>
              {[
                { label: 'Productos en ranking', value: top.length },
                { label: 'Total unidades',       value: num(totalUnidades), color: t.accent },
                { label: 'Total ingresos',       value: cop(totalIngresos), color: t.green },
              ].map(item => (
                <div key={item.label} style={{
                  background: t.card, border: `1px solid ${t.border}`,
                  borderRadius: 8, padding: '10px 16px', flex: 1,
                }}>
                  <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 5 }}>{item.label}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: item.color || t.text }}>{item.value}</div>
                </div>
              ))}
            </div>
          )}

          {/* Gráfica horizontal */}
          <Card>
            <SectionTitle>Top 10 por Unidades Vendidas</SectionTitle>
            {top.length === 0 ? <EmptyState /> : (
              <ResponsiveContainer width="100%" height={Math.max(260, top.length * 34)}>
                <BarChart data={top} layout="vertical" margin={{ top: 0, right: 32, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={t.border} horizontal={false} />
                  <XAxis type="number" tick={{ fill: t.textMuted, fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => num(v)} />
                  <YAxis type="category" dataKey="producto" width={160} tick={{ fill: t.textSub, fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<BAR_TOOLTIP />} />
                  <Bar dataKey="unidades" radius={[0, 6, 6, 0]} maxBarSize={26}>
                    {top.map((_, i) => <Cell key={i} fill={barColors[i]} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>

          {/* Tabla detalle */}
          <Card style={{ padding: 0 }}>
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${t.border}` }}>
              <SectionTitle>Detalle Top 10</SectionTitle>
            </div>
            {top.length === 0 ? <EmptyState /> : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: t.tableAlt }}>
                      <Th center>#</Th>
                      <Th>Producto</Th>
                      <Th center>Unidades</Th>
                      <Th center>Ingresos</Th>
                      <Th center>% Unidades</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {top.map(row => (
                      <tr key={row.posicion}
                        style={{ borderBottom: `1px solid ${t.border}` }}
                        onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            width: 24, height: 24, borderRadius: '50%',
                            background: row.posicion <= 3 ? t.accent : t.border,
                            color: row.posicion <= 3 ? '#fff' : t.textSub,
                            fontSize: 11, fontWeight: 700,
                          }}>
                            {row.posicion}
                          </span>
                        </td>
                        <td style={{ padding: '10px 14px', color: t.text }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{ width: 3, height: 20, borderRadius: 2, background: barColors[row.posicion - 1], flexShrink: 0 }} />
                            {row.producto}
                            {row.posicion === 1 && (
                              <span style={{ background: t.accentSub, color: t.accent, border: `1px solid ${t.accent}33`, fontSize: 9, padding: '1px 7px', borderRadius: 99 }}>
                                🏆 #1
                              </span>
                            )}
                          </div>
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'center', color: t.accent, fontWeight: 600 }}>
                          {num(row.unidades)}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'center', color: t.green, fontWeight: 600 }}>
                          {cop(row.ingresos)}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 7, justifyContent: 'center' }}>
                            <div style={{ width: 50, height: 3, background: t.border, borderRadius: 2, overflow: 'hidden' }}>
                              <div style={{ height: '100%', width: `${(row.unidades / (top[0]?.unidades || 1)) * 100}%`, background: barColors[row.posicion - 1] }} />
                            </div>
                            <span style={{ fontSize: 10, color: t.textMuted }}>
                              {totalUnidades ? ((row.unidades / totalUnidades) * 100).toFixed(1) : 0}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ borderTop: `1px solid ${t.border}`, background: t.tableFoot }}>
                      <td colSpan={2} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600 }}>
                        TOTAL ({top.length} productos)
                      </td>
                      <td style={{ padding: '10px 14px', textAlign: 'center', color: t.accent, fontWeight: 700 }}>{num(totalUnidades)}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'center', color: t.green,  fontWeight: 700 }}>{cop(totalIngresos)}</td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
