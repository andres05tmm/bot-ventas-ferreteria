import { useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import {
  useTheme, useFetch, Card, SectionTitle, KpiCard, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop, num,
} from '../components/shared.jsx'

const DIAS_OPTIONS = [
  { label: '7 días',  value: 7 },
  { label: '15 días', value: 15 },
  { label: '30 días', value: 30 },
  { label: '90 días', value: 90 },
]

const PROV_COLORS = ['#60a5fa','#4ade80','#fbbf24','#f87171','#a78bfa','#fb923c','#94a3b8']

export default function TabCompras({ refreshKey }) {
  const t = useTheme()
  const [dias, setDias] = useState(30)
  const { data, loading, error } = useFetch(`/compras?dias=${dias}`, [dias, refreshKey])

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  const d          = data || {}
  const compras    = d.compras || []
  const porProv    = Object.entries(d.por_proveedor || {}).sort((a, b) => b[1] - a[1])
  const porProd    = Object.entries(d.por_producto  || {}).slice(0, 10)
  const total      = d.total_invertido || 0
  const pieData    = porProv.map(([name, value]) => ({ name, value }))

  const sinDatos = compras.length === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Compras a Proveedores</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            Historial de mercancía comprada · últimos {dias} días
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

      {sinDatos ? (
        <Card>
          <div style={{ padding: '32px 24px', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>📦</div>
            <div style={{ color: t.text, fontWeight: 600, marginBottom: 8 }}>Sin compras registradas</div>
            <div style={{ color: t.textMuted, fontSize: 12, maxWidth: 340, margin: '0 auto' }}>
              Las compras se registran en Telegram con el comando:
            </div>
            <code style={{
              display: 'inline-block', marginTop: 10,
              background: t.tableAlt, color: t.accent,
              border: `1px solid ${t.border}`,
              padding: '6px 14px', borderRadius: 7, fontSize: 12,
            }}>
              /compra [cantidad] [producto] a [precio]
            </code>
            <div style={{ color: t.textMuted, fontSize: 11, marginTop: 8 }}>
              Ej: /compra 20 brocha 2" a 2500
            </div>
          </div>
        </Card>
      ) : (
        <>
          {/* KPIs */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <KpiCard label="Total invertido"  value={cop(total)}       sub={`Últimos ${dias} días`} icon="💰" color={t.blue} />
            <KpiCard label="Compras"          value={compras.length}   sub="Registros"               icon="📦" color={t.textSub} />
            <KpiCard label="Proveedores"      value={porProv.length}   sub="Distintos"               icon="🏭" color={t.textSub} />
            <KpiCard label="Productos"        value={Object.keys(d.por_producto||{}).length} sub="Artículos comprados" icon="🔢" color={t.textSub} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {/* Por proveedor */}
            <Card>
              <SectionTitle>Por Proveedor</SectionTitle>
              {porProv.length === 0 ? <EmptyState /> : (
                <>
                  <ResponsiveContainer width="100%" height={120}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2}>
                        {pieData.map((_, i) => <Cell key={i} fill={PROV_COLORS[i % PROV_COLORS.length]} />)}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
                        formatter={v => [cop(v)]}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                    {porProv.map(([prov, val], i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ width: 8, height: 8, borderRadius: '50%', background: PROV_COLORS[i % PROV_COLORS.length], flexShrink: 0, display: 'inline-block' }} />
                          <span style={{ fontSize: 11, color: t.textSub }}>{prov}</span>
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: t.text }}>{cop(val)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Card>

            {/* Top productos más comprados */}
            <Card>
              <SectionTitle>Productos más Comprados</SectionTitle>
              {porProd.length === 0 ? <EmptyState /> : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {porProd.map(([prod, val], i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ color: t.textMuted, fontSize: 11, minWidth: 18, textAlign: 'right' }}>#{i+1}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 11, color: t.text, marginBottom: 3 }}>{prod}</div>
                        <div style={{ height: 3, background: t.border, borderRadius: 2 }}>
                          <div style={{ height: '100%', width: `${(val / (porProd[0]?.[1] || 1)) * 100}%`, background: t.blue, borderRadius: 2 }} />
                        </div>
                      </div>
                      <span style={{ fontSize: 11, color: t.blue, fontWeight: 600, whiteSpace: 'nowrap' }}>{cop(val)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          {/* Tabla de compras */}
          <Card style={{ padding: 0 }}>
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
              <SectionTitle>Detalle de Compras</SectionTitle>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: t.tableAlt }}>
                    {['Fecha', 'Producto', 'Cantidad', 'Costo Unit.', 'Total', 'Proveedor'].map((h, i) => (
                      <th key={i} style={{
                        padding: '9px 14px',
                        textAlign: [2,3,4].includes(i) ? 'right' : 'left',
                        fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
                        letterSpacing: '.08em', fontWeight: 500,
                        borderBottom: `1px solid ${t.border}`, whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compras.map((c, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${t.border}` }}
                      onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                      <td style={{ padding: '9px 14px', color: t.textMuted, whiteSpace: 'nowrap' }}>
                        {String(c.fecha || '').slice(0, 10)}
                      </td>
                      <td style={{ padding: '9px 14px', color: t.text }}>{c.producto || '—'}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textSub }}>{num(c.cantidad)}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textMuted }}>{cop(c.costo_unitario)}</td>
                      <td style={{ padding: '9px 14px', textAlign: 'right', color: t.blue, fontWeight: 600 }}>{cop(c.costo_total)}</td>
                      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{c.proveedor || '—'}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                    <td colSpan={4} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>
                      TOTAL INVERTIDO
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', color: t.blue, fontWeight: 700, fontSize: 14 }}>
                      {cop(total)}
                    </td>
                    <td />
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
