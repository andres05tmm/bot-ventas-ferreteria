import { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { Card, SectionTitle, Spinner, ErrorMsg, useFetch, cop, num } from '../components/shared.jsx'

const BAR_TOOLTIP = ({ active, payload }) => {
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

export default function TabTopProductos() {
  const [periodo, setPeriodo] = useState('semana')
  const { data, loading, error } = useFetch(`/ventas/top?periodo=${periodo}`, [periodo])

  const top = data?.top || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* Selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ color: '#888', fontSize: 13 }}>Período:</span>
        {['semana', 'mes'].map(p => (
          <button
            key={p}
            onClick={() => setPeriodo(p)}
            style={{
              padding: '6px 16px',
              borderRadius: 6,
              border: '1px solid',
              borderColor: periodo === p ? '#dc2626' : '#2a2a2a',
              background: periodo === p ? '#dc262622' : 'transparent',
              color: periodo === p ? '#dc2626' : '#888',
              fontSize: 13,
              fontWeight: periodo === p ? 600 : 400,
              textTransform: 'capitalize',
            }}
          >
            {p === 'semana' ? 'Esta Semana' : 'Este Mes'}
          </button>
        ))}
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {!loading && !error && (
        <>
          {/* Gráfica horizontal */}
          <Card>
            <SectionTitle>Top 10 por Unidades Vendidas</SectionTitle>
            {top.length === 0 ? (
              <p style={{ color: '#666', fontSize: 13 }}>Sin datos para este período.</p>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(260, top.length * 36)}>
                <BarChart data={top} layout="vertical" margin={{ top: 0, right: 32, left: 0, bottom: 0 }}>
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
                    width={160}
                    tick={{ fill: '#ccc', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<BAR_TOOLTIP />} />
                  <Bar dataKey="unidades" fill="#dc2626" radius={[0, 6, 6, 0]} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>

          {/* Tabla */}
          <Card>
            <SectionTitle>Detalle Top 10</SectionTitle>
            {top.length === 0 ? (
              <p style={{ color: '#666', fontSize: 13 }}>Sin datos.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr>
                      {['#', 'Producto', 'Unidades', 'Ingresos'].map(h => (
                        <th key={h} style={{
                          textAlign: h === '#' || h === 'Unidades' || h === 'Ingresos' ? 'center' : 'left',
                          padding: '8px 12px',
                          color: '#888',
                          fontWeight: 600,
                          borderBottom: '1px solid #2a2a2a',
                          whiteSpace: 'nowrap',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {top.map((row) => (
                      <tr key={row.posicion} style={{ borderBottom: '1px solid #1e1e1e' }}>
                        <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            width: 24, height: 24, borderRadius: '50%',
                            background: row.posicion <= 3 ? '#dc2626' : '#2a2a2a',
                            color: row.posicion <= 3 ? '#fff' : '#888',
                            fontSize: 11, fontWeight: 700,
                          }}>
                            {row.posicion}
                          </span>
                        </td>
                        <td style={{ padding: '10px 12px', color: '#f5f5f5', maxWidth: 260 }}>
                          {row.producto}
                        </td>
                        <td style={{ padding: '10px 12px', textAlign: 'center', color: '#dc2626', fontWeight: 600 }}>
                          {num(row.unidades)}
                        </td>
                        <td style={{ padding: '10px 12px', textAlign: 'center', color: '#22c55e', fontWeight: 600 }}>
                          {cop(row.ingresos)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}
