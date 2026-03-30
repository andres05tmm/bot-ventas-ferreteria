import { useState } from 'react'
import {
  BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  useTheme, useFetch, Card, GlassCard, SectionTitle, KpiCard, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop, API_BASE,
  useIsMobile,
} from '../components/shared.jsx'

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
  const [localRefresh, setLocalRefresh] = useState(0)
  const { data, loading, error } = useFetch(`/gastos?dias=${dias}`, [dias, refreshKey, localRefresh])

  // Form nuevo gasto
  const [formOpen, setFormOpen] = useState(false)
  const [concepto, setConcepto] = useState('')
  const [monto, setMonto] = useState('')
  const [categoria, setCategoria] = useState('General')
  const [origen, setOrigen] = useState('caja')
  const [guardando, setGuardando] = useState(false)
  const [msg, setMsg] = useState(null)

  const mostrarMsg = (tipo, texto) => { setMsg({ tipo, texto }); setTimeout(() => setMsg(null), 4000) }

  const registrarGasto = async () => {
    if (!concepto.trim()) { mostrarMsg('err', 'El concepto es obligatorio'); return }
    if (!monto || parseInt(monto) <= 0) { mostrarMsg('err', 'El monto debe ser mayor a 0'); return }
    setGuardando(true)
    try {
      const r = await fetch(`${API_BASE}/gastos`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concepto: concepto.trim(), monto: parseInt(monto), categoria, origen }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarMsg('ok', d.mensaje)
      setConcepto(''); setMonto(''); setCategoria('General')
      setFormOpen(false)
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setGuardando(false) }
  }

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

      {/* Toast */}
      {msg && (
        <div style={{
          padding: '10px 16px', borderRadius: 8,
          background: msg.tipo === 'ok' ? `${t.green}14` : `${t.accent}14`,
          border: `1px solid ${msg.tipo === 'ok' ? t.green : t.accent}44`,
          color: msg.tipo === 'ok' ? t.green : t.accent,
          fontSize: 12, fontWeight: 500,
        }}>{msg.tipo === 'ok' ? '✓' : '✕'} {msg.texto}</div>
      )}

      {/* Selector período + botón nuevo */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Gastos</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            {gastos.length} registros · últimos {dias} {dias === 1 ? 'día' : 'días'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {DIAS_OPTIONS.map(o => (
            <PeriodBtn key={o.value} active={dias === o.value} onClick={() => setDias(o.value)}>
              {o.label}
            </PeriodBtn>
          ))}
          <button onClick={() => setFormOpen(f => !f)} style={{
            background: formOpen ? t.accent : t.accentSub,
            border: `1px solid ${t.accent}55`, borderRadius: 8,
            color: formOpen ? '#fff' : t.accent,
            padding: '6px 14px', fontSize: 11, fontWeight: 700,
            cursor: 'pointer', fontFamily: 'inherit',
          }}>
            {formOpen ? '✕ Cerrar' : '➕ Nuevo gasto'}
          </button>
        </div>
      </div>

      {/* Formulario nuevo gasto */}
      {formOpen && (
        <GlassCard>
          <SectionTitle>Registrar Gasto</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <div>
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Concepto *</label>
              <input value={concepto} onChange={e => setConcepto(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && registrarGasto()}
                placeholder="Ej: Almuerzo, transporte, material..."
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                  border: `1px solid ${t.border}`, borderRadius: 7,
                  color: t.text, fontSize: 12, padding: '8px 10px',
                  outline: 'none', fontFamily: 'inherit',
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Monto *</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: t.textMuted, fontSize: 11 }}>$</span>
                <input type="number" min="0" value={monto} onChange={e => setMonto(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && registrarGasto()}
                  placeholder="0"
                  style={{
                    width: '100%', boxSizing: 'border-box', paddingLeft: 22,
                    background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                    border: `1px solid ${t.border}`, borderRadius: 7,
                    color: t.text, fontSize: 12, padding: '8px 10px 8px 22px',
                    outline: 'none', fontFamily: 'inherit',
                  }}
                />
              </div>
            </div>
            <div>
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Categoría</label>
              <select value={categoria} onChange={e => setCategoria(e.target.value)}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                  border: `1px solid ${t.border}`, borderRadius: 7,
                  color: t.text, fontSize: 12, padding: '8px 10px',
                  outline: 'none', fontFamily: 'inherit', cursor: 'pointer',
                }}>
                {['General','Transporte','Alimentación','Servicios','Materiales','Arriendo','Otro'].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Origen</label>
              <div style={{ display: 'flex', gap: 6 }}>
                {[{k:'caja',l:'💵 De caja'},{k:'externo',l:'🏦 Externo'}].map(o => (
                  <button key={o.k} onClick={() => setOrigen(o.k)} style={{
                    flex: 1, padding: '8px 10px', borderRadius: 7, fontSize: 11,
                    fontFamily: 'inherit', cursor: 'pointer',
                    background: origen === o.k ? t.accentSub : (t.id === 'caramelo' ? '#f8fafc' : '#111'),
                    border: `1px solid ${origen === o.k ? t.accent : t.border}`,
                    color: origen === o.k ? t.accent : t.textMuted,
                    fontWeight: origen === o.k ? 600 : 400,
                  }}>{o.l}</button>
                ))}
              </div>
            </div>
          </div>
          <button onClick={registrarGasto} disabled={guardando} style={{
            background: t.accent, border: 'none', borderRadius: 8,
            color: '#fff', padding: '10px 24px', fontSize: 12,
            fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
          }}>
            {guardando ? 'Guardando…' : '💸 Registrar gasto'}
          </button>
        </GlassCard>
      )}

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard label="Total gastos"     value={cop(total)}      sub={`Últimos ${dias} días`}  icon="💸" color="#f87171" />
        <KpiCard label="Promedio diario"  value={cop(promDiario)} sub="Gasto diario promedio"    icon="📊" color={t.yellow} />
        <KpiCard label="Categorías"       value={porCat.length}   sub="Tipos de gasto"           icon="📂" color={t.textSub} />
        <KpiCard label="Registros"        value={gastos.length}   sub="Egresos registrados"      icon="📋" color={t.textSub} />
      </div>

      {gastos.length === 0 ? (
        <GlassCard>
          <EmptyState msg="Sin gastos registrados en este período." />
        </GlassCard>
      ) : (
        <>
          {/* Gráficas */}
          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>
            {/* Histórico diario */}
            {dias > 1 && (
              <GlassCard>
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
              </GlassCard>
            )}

            {/* Por categoría */}
            <GlassCard>
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
            </GlassCard>
          </div>

          {/* Tabla detalle */}
          <GlassCard style={{ padding: 0 }}>
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
          </GlassCard>
        </>
      )}
    </div>
  )
}
