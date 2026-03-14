import { useState, useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, Th, cop, num,
} from '../components/shared.jsx'

const CRITERIOS = [
  { id: 'ingresos',   label: '💰 Por Ingresos',   desc: 'Dinero generado por producto' },
  { id: 'frecuencia', label: '🔁 Por Frecuencia',  desc: 'Veces que se registró la venta' },
  { id: 'categoria',  label: '📂 Por Categoría',   desc: 'Top 5 dentro de cada categoría' },
]

function barColor(t, i) {
  const cols = [t.accent, '#ef4444', '#f97316', '#fb923c', '#fbbf24', '#a3a3a3', '#a3a3a3', '#a3a3a3', '#a3a3a3', '#a3a3a3']
  return cols[i] || t.border
}

function TooltipContent({ active, payload, criterio, t }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 7, padding: '9px 13px', maxWidth: 230 }}>
      <div style={{ color: t.text, fontSize: 12, marginBottom: 4, fontWeight: 600 }}>{d.producto}</div>
      {d.categoria && <div style={{ color: t.textMuted, fontSize: 10, marginBottom: 6 }}>{d.categoria}</div>}
      <div style={{ color: t.accent, fontWeight: 700 }}>
        {criterio === 'frecuencia' ? `${num(d.valor)} ventas` : cop(d.valor)}
      </div>
      {criterio === 'ingresos' && d.frecuencia != null &&
        <div style={{ color: t.textMuted, fontSize: 11, marginTop: 3 }}>{num(d.frecuencia)} registros</div>}
      {criterio === 'frecuencia' && d.ingresos != null &&
        <div style={{ color: t.green, fontSize: 11, marginTop: 3 }}>{cop(d.ingresos)} total</div>}
    </div>
  )
}

function TopChart({ top, criterio, t }) {
  if (!top?.length) return <EmptyState />
  const max = top[0]?.valor || 1
  return (
    <ResponsiveContainer width="100%" height={Math.max(260, top.length * 34)}>
      <BarChart data={top} layout="vertical" margin={{ top: 0, right: 32, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={t.border} horizontal={false} />
        <XAxis
          type="number" tick={{ fill: t.textMuted, fontSize: 10 }} axisLine={false} tickLine={false}
          tickFormatter={v => criterio === 'frecuencia' ? num(v) : (v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v)}
        />
        <YAxis type="category" dataKey="producto" width={165} tick={{ fill: t.textSub, fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip content={<TooltipContent criterio={criterio} t={t} />} />
        <Bar dataKey="valor" radius={[0, 6, 6, 0]} maxBarSize={26}>
          {top.map((_, i) => <Cell key={i} fill={barColor(t, i)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function TablaDetalle({ top, criterio, t }) {
  const totalValor    = top.reduce((a, p) => a + p.valor, 0)
  const totalIngresos = top.reduce((a, p) => a + (p.ingresos || p.valor || 0), 0)
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: t.tableAlt }}>
            <Th center>#</Th>
            <Th>Producto</Th>
            <Th>Categoría</Th>
            <Th right>{criterio === 'frecuencia' ? 'Ventas' : 'Ingresos'}</Th>
            {criterio === 'ingresos'   && <Th right>Registros</Th>}
            {criterio === 'frecuencia' && <Th right>Total $</Th>}
            <Th right>% del total</Th>
          </tr>
        </thead>
        <tbody>
          {top.map((row) => (
            <tr key={row.posicion}
              style={{ borderBottom: `1px solid ${t.border}` }}
              onMouseEnter={e => { e.currentTarget.style.background = t.cardHover; e.currentTarget.style.transform = 'translateX(2px)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.transform = 'translateX(0)' }}>
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
                  <div style={{ width: 3, height: 20, borderRadius: 2, background: barColor(t, row.posicion - 1), flexShrink: 0 }} />
                  {row.producto}
                  {row.posicion === 1 && (
                    <span style={{ background: t.accentSub, color: t.accent, border: `1px solid ${t.accent}33`, fontSize: 9, padding: '1px 7px', borderRadius: 99 }}>🏆 #1</span>
                  )}
                </div>
              </td>
              <td style={{ padding: '10px 14px', color: t.textMuted, fontSize: 11 }}>{row.categoria || '—'}</td>
              <td style={{ padding: '10px 14px', textAlign: 'right', color: t.accent, fontWeight: 600 }}>
                {criterio === 'frecuencia' ? `${num(row.valor)}×` : cop(row.valor)}
              </td>
              {criterio === 'ingresos' && (
                <td style={{ padding: '10px 14px', textAlign: 'right', color: t.textMuted }}>{num(row.frecuencia)}</td>
              )}
              {criterio === 'frecuencia' && (
                <td style={{ padding: '10px 14px', textAlign: 'right', color: t.green }}>{cop(row.ingresos)}</td>
              )}
              <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                  <div style={{ width: 44, height: 3, background: t.border, borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(row.valor / (totalValor || 1)) * 100}%`, background: barColor(t, row.posicion - 1) }} />
                  </div>
                  <span style={{ fontSize: 10, color: t.textMuted }}>
                    {totalValor ? ((row.valor / totalValor) * 100).toFixed(1) : 0}%
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ borderTop: `1px solid ${t.border}`, background: t.tableFoot }}>
            <td colSpan={3} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600 }}>
              TOTAL ({top.length} productos)
            </td>
            <td style={{ padding: '10px 14px', textAlign: 'right', color: t.accent, fontWeight: 700 }}>
              {criterio === 'frecuencia' ? `${num(totalValor)}×` : cop(totalValor)}
            </td>
            {criterio === 'ingresos'   && <td style={{ padding: '10px 14px', textAlign: 'right', color: t.textMuted }}>{num(top.reduce((a,p)=>a+p.frecuencia,0))}</td>}
            {criterio === 'frecuencia' && <td style={{ padding: '10px 14px', textAlign: 'right', color: t.green }}>{cop(totalIngresos)}</td>}
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

export default function TabTopProductos({ refreshKey }) {
  const t = useTheme()
  const [periodo,  setPeriodo]  = useState('semana')
  const [criterio, setCriterio] = useState('ingresos')

  const { data, loading, error } = useFetch(
    `/ventas/top2?periodo=${periodo}&criterio=${criterio}`,
    [periodo, criterio, refreshKey]
  )

  const top        = data?.top || []
  const porCat     = data?.por_categoria || {}
  const esCat      = criterio === 'categoria'
  const cats       = Object.entries(porCat)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Controles */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Top Productos</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            {CRITERIOS.find(c => c.id === criterio)?.desc} · {periodo === 'semana' ? 'esta semana' : 'este mes'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <PeriodBtn active={periodo === 'semana'} onClick={() => setPeriodo('semana')}>Esta Semana</PeriodBtn>
          <PeriodBtn active={periodo === 'mes'}    onClick={() => setPeriodo('mes')}>Este Mes</PeriodBtn>
        </div>
      </div>

      {/* Selector de criterio */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {CRITERIOS.map(c => (
          <button key={c.id} onClick={() => setCriterio(c.id)} style={{
            background: criterio === c.id ? t.accentSub : t.card,
            border: `1px solid ${criterio === c.id ? t.accent : t.border}`,
            color: criterio === c.id ? t.accent : t.textSub,
            borderRadius: 8, padding: '7px 14px', fontSize: 12,
            fontFamily: 'inherit', cursor: 'pointer', transition: 'all .15s',
            fontWeight: criterio === c.id ? 600 : 400,
          }}>
            {c.label}
          </button>
        ))}
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {!loading && !error && (
        <>
          {/* Vista global (ingresos / frecuencia) */}
          {!esCat && (
            <>
              <Card>
                <SectionTitle>Top 10 — {criterio === 'ingresos' ? 'Ingresos generados' : 'Veces vendido'}</SectionTitle>
                {top.length === 0 ? <EmptyState /> : <TopChart top={top} criterio={criterio} t={t} />}
              </Card>
              {top.length > 0 && (
                <Card style={{ padding: 0 }}>
                  <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
                    <SectionTitle>Detalle</SectionTitle>
                  </div>
                  <TablaDetalle top={top} criterio={criterio} t={t} />
                </Card>
              )}
            </>
          )}

          {/* Vista por categoría */}
          {esCat && (
            <>
              {cats.length === 0 ? <EmptyState /> : cats.map(([cat, prods]) => (
                <Card key={cat}>
                  <SectionTitle>{cat.replace(/^\d+\s*/, '')}</SectionTitle>
                  {prods.length === 0 ? <EmptyState msg="Sin ventas en este período." /> : (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ background: t.tableAlt }}>
                            <Th center>#</Th>
                            <Th>Producto</Th>
                            <Th right>Ingresos</Th>
                            <Th right>Registros</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {prods.map((row, i) => (
                            <tr key={i} style={{ borderBottom: `1px solid ${t.border}` }}
                              onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                              <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                                <span style={{
                                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                  width: 22, height: 22, borderRadius: '50%',
                                  background: i < 3 ? t.accent : t.border,
                                  color: i < 3 ? '#fff' : t.textSub, fontSize: 10, fontWeight: 700,
                                }}>{i + 1}</span>
                              </td>
                              <td style={{ padding: '9px 14px', color: t.text }}>{row.producto}</td>
                              <td style={{ padding: '9px 14px', textAlign: 'right', color: t.green, fontWeight: 600 }}>{cop(row.valor)}</td>
                              <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textMuted }}>{num(row.frecuencia)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              ))}
            </>
          )}
        </>
      )}
    </div>
  )
}
