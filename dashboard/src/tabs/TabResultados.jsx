import { useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'
import {
  useTheme, useFetch, Card, SectionTitle, KpiCard,
  Spinner, ErrorMsg, PeriodBtn, EmptyState, cop, num,
} from '../components/shared.jsx'

function fmtDia(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

// ── Estado de Resultados ───────────────────────────────────────────────────
function EstadoResultados({ d, periodo, t }) {
  const [detalle, setDetalle] = useState(false)
  const filas = [
    { label: '(+) Ventas totales',            valor: d.total_ventas,   color: t.green,  bold: true },
    { label: '(−) Costo mercancía vendida',    valor: -d.cmv,           color: '#f87171', negativo: true },
    { label: '= Utilidad Bruta',               valor: d.utilidad_bruta, color: d.utilidad_bruta >= 0 ? t.accent : '#f87171', bold: true, separador: true },
    { label: `(−) Gastos operativos`,          valor: -d.total_gastos,  color: '#f87171', negativo: true },
    { label: '= Utilidad Neta',                valor: d.utilidad_neta,  color: d.utilidad_neta >= 0 ? t.green : '#ef4444', bold: true, grande: true, separador: true },
  ]

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <SectionTitle>Estado de Resultados · {periodo === 'semana' ? 'Esta Semana' : 'Este Mes'}</SectionTitle>
        {!d.tiene_cmv && (
          <span style={{
            fontSize: 10, color: t.yellow, background: t.id === 'light' ? '#fef9c3' : '#422006',
            border: `1px solid ${t.yellow}44`, padding: '3px 10px', borderRadius: 99,
          }}>
            ⚠️ CMV en $0 — registra compras con /compra
          </span>
        )}
      </div>

      {/* Tabla P&L */}
      <div style={{ borderRadius: 8, overflow: 'hidden', border: `1px solid ${t.border}` }}>
        {filas.map((f, i) => (
          <div key={i} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: f.grande ? '14px 18px' : '11px 18px',
            background: f.grande ? (t.id === 'light' ? '#f0fdf4' : '#052e1640') : (f.separador ? t.tableAlt : 'transparent'),
            borderTop: f.separador ? `2px solid ${t.border}` : (i > 0 ? `1px solid ${t.border}` : 'none'),
          }}>
            <span style={{ color: f.bold ? t.text : t.textSub, fontWeight: f.bold ? 600 : 400, fontSize: f.grande ? 14 : 13 }}>
              {f.label}
            </span>
            <span style={{ color: f.color, fontWeight: f.bold ? 700 : 500, fontSize: f.grande ? 16 : 13 }}>
              {f.negativo && f.valor < 0 ? `−${cop(Math.abs(f.valor))}` : cop(f.valor)}
            </span>
          </div>
        ))}
        {/* Márgenes */}
        <div style={{
          display: 'flex', gap: 0,
          borderTop: `1px solid ${t.border}`, background: t.tableFoot,
        }}>
          {[
            { label: 'Margen bruto', valor: d.margen_bruto_pct },
            { label: 'Margen neto',  valor: d.margen_neto_pct  },
            { label: 'Cobertura CMV', valor: d.cobertura_cmv_pct, suffix: '% productos' },
          ].map((m, i) => (
            <div key={i} style={{
              flex: 1, padding: '10px 18px', textAlign: 'center',
              borderLeft: i > 0 ? `1px solid ${t.border}` : 'none',
            }}>
              <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 3 }}>{m.label}</div>
              <div style={{
                fontSize: 15, fontWeight: 700,
                color: (m.valor || 0) >= 0 ? t.accent : '#ef4444',
              }}>
                {m.valor != null ? `${m.valor}${m.suffix || '%'}` : '—'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Detalle CMV */}
      {d.cmv_detalle?.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <button
            onClick={() => setDetalle(p => !p)}
            style={{
              background: 'none', border: `1px solid ${t.border}`,
              color: t.textMuted, borderRadius: 7, padding: '5px 12px',
              fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {detalle ? '▲ Ocultar' : '▼ Ver'} detalle CMV por producto ({d.cmv_detalle.length})
          </button>

          {detalle && (
            <div style={{ overflowX: 'auto', marginTop: 10 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                <thead>
                  <tr style={{ background: t.tableAlt }}>
                    {['Producto', 'Cant.', 'Ingresos', 'CMV', 'Margen %'].map((h, i) => (
                      <th key={i} style={{
                        padding: '7px 12px', textAlign: i > 0 ? 'right' : 'left',
                        fontSize: 9, color: t.textMuted, textTransform: 'uppercase',
                        fontWeight: 500, letterSpacing: '.07em',
                        borderBottom: `1px solid ${t.border}`,
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.cmv_detalle.map((row, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${t.border}` }}
                      onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                      <td style={{ padding: '7px 12px', color: t.text }}>{row.producto}</td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', color: t.textMuted }}>{num(row.cantidad)}</td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', color: t.green }}>{cop(row.ingresos)}</td>
                      <td style={{ padding: '7px 12px', textAlign: 'right', color: '#f87171' }}>{cop(row.cmv)}</td>
                      <td style={{ padding: '7px 12px', textAlign: 'right' }}>
                        <span style={{
                          color: row.margen_pct >= 30 ? t.green : row.margen_pct >= 15 ? t.yellow : '#f87171',
                          fontWeight: 600,
                        }}>{row.margen_pct}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Productos sin costo */}
      {d.sin_costo?.length > 0 && (
        <div style={{
          marginTop: 12, padding: '10px 14px',
          background: t.id === 'light' ? '#fef9c3' : '#422006',
          border: `1px solid ${t.yellow}44`, borderRadius: 8,
          fontSize: 11, color: t.yellow,
        }}>
          <strong>{d.sin_costo.length} productos sin costo registrado</strong> — su CMV aparece como $0.
          Registra sus precios de compra con <code style={{ background: t.card, padding: '1px 5px', borderRadius: 3 }}>/compra</code> en Telegram.
          {d.sin_costo.length <= 5 && (
            <div style={{ marginTop: 6, color: t.textMuted }}>
              {d.sin_costo.join(' · ')}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ── Proyección de Caja ─────────────────────────────────────────────────────
function ProyeccionCaja({ pd, t }) {
  const positivo = pd.proy_caja_fin_mes >= 0
  const serie    = pd.serie_diaria || []
  const hoy      = pd.dia_del_mes

  return (
    <Card>
      <SectionTitle>Proyección de Caja — Cierre del Mes</SectionTitle>

      {!pd.tiene_datos ? (
        <EmptyState msg="Sin suficientes ventas recientes para proyectar. Se necesita al menos un día con ventas." />
      ) : (
        <>
          {/* KPIs proyección */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 14 }}>
            {[
              { label: 'Caja hoy',           valor: cop(pd.efectivo_actual),   color: t.text },
              { label: 'Ingreso prom/día',   valor: cop(pd.prom_ventas_dia),   color: t.green },
              { label: 'Gasto prom/día',     valor: cop(pd.prom_gastos_dia),   color: '#f87171' },
              { label: 'Neto prom/día',      valor: cop(pd.prom_neto_dia),     color: pd.prom_neto_dia >= 0 ? t.accent : '#f87171' },
              { label: `Días restantes`,     valor: pd.dias_restantes,         color: t.textSub },
              { label: 'Caja proyectada',    valor: cop(pd.proy_caja_fin_mes), color: positivo ? t.green : '#ef4444' },
            ].map((k, i) => (
              <div key={i} style={{
                background: t.tableAlt, borderRadius: 8, padding: '10px 14px',
                border: i === 5 ? `1px solid ${(positivo ? t.green : '#ef4444')}44` : `1px solid ${t.border}`,
              }}>
                <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 4 }}>{k.label}</div>
                <div style={{ fontSize: i === 5 ? 16 : 14, fontWeight: i === 5 ? 800 : 600, color: k.color }}>
                  {k.valor}
                </div>
              </div>
            ))}
          </div>

          {/* Gráfica área */}
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={serie} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="gradReal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={t.accent} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={t.accent} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradProy" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={t.blue} stopOpacity={0.15} />
                  <stop offset="95%" stopColor={t.blue} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={t.border} />
              <XAxis dataKey="dia" tick={{ fill: t.textMuted, fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: t.textMuted, fontSize: 9 }} axisLine={false} tickLine={false}
                tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
              />
              <Tooltip
                contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, fontSize: 11 }}
                formatter={(v, n) => [cop(v), n === 'valor' ? 'Caja' : n]}
                labelFormatter={d => `Día ${d}`}
              />
              <ReferenceLine x={hoy} stroke={t.accent} strokeDasharray="4 4" label={{ value: 'Hoy', fill: t.accent, fontSize: 9 }} />
              <Area
                type="monotone" dataKey="valor"
                data={serie.filter(s => s.real)}
                stroke={t.accent} fill="url(#gradReal)" strokeWidth={2}
                dot={false} name="Real"
              />
              <Area
                type="monotone" dataKey="valor"
                data={serie.filter(s => !s.real)}
                stroke={t.blue} fill="url(#gradProy)" strokeWidth={2}
                strokeDasharray="5 3" dot={false} name="Proyectado"
              />
            </AreaChart>
          </ResponsiveContainer>

          {/* Resumen mes */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 12 }}>
            {[
              { label: 'Ventas acumuladas',    real: pd.ventas_mes_actual,  proy: pd.proy_ventas_mes,  color: t.green },
              { label: 'Gastos acumulados',    real: pd.gastos_mes_actual,  proy: pd.proy_gastos_mes,  color: '#f87171' },
            ].map((row, i) => (
              <div key={i} style={{ background: t.tableAlt, borderRadius: 8, padding: '10px 14px', border: `1px solid ${t.border}` }}>
                <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 6 }}>{row.label}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <div>
                    <div style={{ fontSize: 9, color: t.textMuted }}>Actual</div>
                    <div style={{ fontWeight: 600, color: row.color }}>{cop(row.real)}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 9, color: t.textMuted }}>Proyectado fin de mes</div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: row.color }}>{cop(row.proy)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 10, fontSize: 10, color: t.textMuted, fontStyle: 'italic' }}>
            * Proyección basada en promedio de los últimos 14 días con ventas. La línea punteada indica el escenario proyectado.
          </div>
        </>
      )}
    </Card>
  )
}

// ── Gráfica histórica ventas vs gastos ─────────────────────────────────────
function GraficaHistorica({ historico, t }) {
  if (!historico?.length) return null
  const data = historico.map(h => ({ dia: fmtDia(h.fecha), ventas: h.ventas, gastos: h.gastos, neto: h.ventas - h.gastos }))
  return (
    <Card>
      <SectionTitle>Ventas vs Gastos por Día</SectionTitle>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={t.border} />
          <XAxis dataKey="dia" tick={{ fill: t.textMuted, fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: t.textMuted, fontSize: 9 }} axisLine={false} tickLine={false}
            tickFormatter={v => v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v} />
          <Tooltip
            contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, fontSize: 11 }}
            formatter={v => [cop(v)]}
          />
          <Bar dataKey="ventas" name="Ventas" fill={t.green}   radius={[3,3,0,0]} maxBarSize={22} />
          <Bar dataKey="gastos" name="Gastos" fill="#f87171"   radius={[3,3,0,0]} maxBarSize={22} />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  )
}

// ── Tab principal ───────────────────────────────────────────────────────────
export default function TabResultados({ refreshKey }) {
  const t = useTheme()
  const [periodo, setPeriodo] = useState('mes')

  const { data: rd, loading: rl, error: re } = useFetch(`/resultados?periodo=${periodo}`, [periodo, refreshKey])
  const { data: pd, loading: pl, error: pe } = useFetch('/proyeccion', [refreshKey])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Resultados Financieros</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            Estado de resultados · Proyección de caja
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <PeriodBtn active={periodo === 'semana'} onClick={() => setPeriodo('semana')}>Esta Semana</PeriodBtn>
          <PeriodBtn active={periodo === 'mes'}    onClick={() => setPeriodo('mes')}>Este Mes</PeriodBtn>
        </div>
      </div>

      {/* KPIs rápidos */}
      {rd && !rl && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <KpiCard label="Ventas"         value={cop(rd.total_ventas)}   sub="Ingresos del período"   icon="💰" color={t.green} />
          <KpiCard label="CMV"            value={cop(rd.cmv)}            sub="Costo de lo vendido"    icon="📦" color="#f87171" />
          <KpiCard label="Utilidad Bruta" value={cop(rd.utilidad_bruta)} sub={`Margen ${rd.margen_bruto_pct}%`} icon="📊" color={t.accent} />
          <KpiCard label="Utilidad Neta"  value={cop(rd.utilidad_neta)}  sub={`Después de gastos`}    icon="✅" color={rd.utilidad_neta >= 0 ? t.green : '#ef4444'} />
        </div>
      )}

      {rl && <Spinner />}
      {re && <ErrorMsg msg={`Error resultados: ${re}`} />}
      {rd && !rl && <EstadoResultados d={rd} periodo={periodo} t={t} />}
      {rd && !rl && <GraficaHistorica historico={rd.historico} t={t} />}

      {pl && <Spinner />}
      {pe && <ErrorMsg msg={`Error proyección: ${pe}`} />}
      {pd && !pl && <ProyeccionCaja pd={pd} t={t} />}
    </div>
  )
}
