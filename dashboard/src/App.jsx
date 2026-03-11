import { useState, useEffect, useMemo } from 'react'
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

// ── Config ────────────────────────────────────────────────────────────────────
export const API_BASE = import.meta.env.VITE_API_URL || '/api'

// ── Helpers ───────────────────────────────────────────────────────────────────
const COP = v => '$' + Math.round(v || 0).toLocaleString('es-CO')
const RC  = ['#dc2626','#ef4444','#f97316','#fb923c','#fbbf24','#a3a3a3','#a3a3a3','#a3a3a3','#a3a3a3','#a3a3a3']
const TABS = ['Resumen', 'Top 10', 'Inventario', 'Historial']

function fmtFecha(s) {
  if (!s) return ''
  const [, m, d] = s.split('-')
  return `${d}/${m}`
}

// ── useFetch ──────────────────────────────────────────────────────────────────
function useFetch(url) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}${url}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url])

  return { data, loading, error }
}

// ── Componentes base ──────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon, color = '#dc2626' }) {
  return (
    <div
      style={{ background: '#141414', border: '1px solid #222', borderRadius: 10, padding: '16px 18px', transition: 'border-color .2s', cursor: 'default' }}
      onMouseEnter={e => e.currentTarget.style.borderColor = '#dc262644'}
      onMouseLeave={e => e.currentTarget.style.borderColor = '#222'}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 9, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>{label}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#f0e6d8', letterSpacing: '-0.02em' }}>{value}</div>
          <div style={{ fontSize: 10, color, marginTop: 5 }}>{sub}</div>
        </div>
        <span style={{ fontSize: 20, opacity: .7 }}>{icon}</span>
      </div>
    </div>
  )
}

function Badge({ children, type }) {
  const s = {
    pagado:    { background: '#14532d22', color: '#4ade80', border: '1px solid #4ade8033' },
    pendiente: { background: '#78350f22', color: '#fbbf24', border: '1px solid #fbbf2433' },
    bajo:      { background: '#7f1d1d22', color: '#f87171', border: '1px solid #f8717133' },
    ok:        { background: '#14532d22', color: '#4ade80', border: '1px solid #4ade8033' },
    agotado:   { background: '#18181b',   color: '#52525b', border: '1px solid #3f3f46'   },
    sinprecio: { background: '#78350f22', color: '#fbbf24', border: '1px solid #fbbf2433' },
  }
  return (
    <span style={{ display: 'inline-block', padding: '2px 9px', borderRadius: 99, fontSize: 10, ...(s[type] || s.ok) }}>
      {children}
    </span>
  )
}

const Spinner = () => (
  <div style={{ padding: 48, textAlign: 'center', color: '#444', fontSize: 12 }}>Cargando...</div>
)
const ErrMsg = ({ msg }) => (
  <div style={{ padding: 16, color: '#f87171', fontSize: 12, background: '#1a0808', borderRadius: 8, border: '1px solid #7f1d1d' }}>{msg}</div>
)

// ── Pestaña Resumen ───────────────────────────────────────────────────────────
function TabResumen() {
  const [periodo, setPeriodo] = useState('semana')
  const { data: resumen, loading, error } = useFetch('/ventas/resumen')
  const { data: alertasData }             = useFetch('/inventario/bajo')
  const [top5, setTop5]                   = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/ventas/top?periodo=semana`)
      .then(r => r.json())
      .then(d => setTop5(d.top?.slice(0, 5) || []))
      .catch(() => setTop5([]))
  }, [])

  if (loading) return <Spinner />
  if (error)   return <ErrMsg msg={`Error cargando resumen: ${error}`} />

  const r         = resumen || {}
  const rawHist   = periodo === 'semana' ? (r.historico_7d || []) : (r.historico_mes || [])
  const chartData = rawHist.map(d => ({ dia: fmtFecha(d.fecha), ventas: d.total || 0 }))
  const totalChart = chartData.reduce((a, d) => a + d.ventas, 0)
  const maxTop5   = top5?.[0]?.unidades || 1

  return (
    <>
      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 14 }}>
        <KpiCard label="Ventas hoy"      value={COP(r.total_hoy)}   sub="Acumulado del día"     icon="💰" color="#4ade80" />
        <KpiCard label="Pedidos hoy"     value={r.pedidos_hoy ?? 0} sub="Transacciones"          icon="📦" color="#4ade80" />
        <KpiCard label="Stock bajo"      value={alertasData?.total ?? '—'} sub="Requieren atención" icon="⚠️" color="#dc2626" />
        <KpiCard label="Ticket promedio" value={COP(r.ticket_prom)} sub="Promedio últimos 7 días" icon="🧾" color="#fbbf24" />
      </div>

      {/* Gráfica con selector */}
      <div style={{ background: '#141414', border: '1px solid #222', borderRadius: 10, padding: 16, marginBottom: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#ccc' }}>
            Ventas — {periodo === 'semana' ? 'últimos 7 días' : 'este mes'}
          </div>
          <div style={{ display: 'flex', gap: 5 }}>
            {['semana', 'mes'].map(p => (
              <button key={p} onClick={() => setPeriodo(p)} style={{
                background: periodo === p ? '#dc2626' : 'none',
                border: '1px solid ' + (periodo === p ? '#dc2626' : '#2a2a2a'),
                color: periodo === p ? '#fff' : '#555',
                fontSize: 10, padding: '4px 12px', borderRadius: 6, cursor: 'pointer',
              }}>
                {p === 'semana' ? 'Semanal' : 'Mensual'}
              </button>
            ))}
          </div>
        </div>
        <div style={{ fontSize: 9, color: '#444', marginBottom: 4 }}>
          TOTAL · <span style={{ color: '#dc2626', fontWeight: 700, fontSize: 14 }}>{COP(totalChart)}</span>
        </div>
        <ResponsiveContainer width="100%" height={185}>
          <AreaChart data={chartData}>
            <defs>
              <linearGradient id="gr" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#dc2626" stopOpacity={.3} />
                <stop offset="95%" stopColor="#dc2626" stopOpacity={0}  />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" />
            <XAxis dataKey="dia" tick={{ fill: '#444', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fill: '#444', fontSize: 9 }} axisLine={false} tickLine={false}
              tickFormatter={v => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}k` : v}
            />
            <Tooltip
              contentStyle={{ background: '#141414', border: '1px solid #222', borderRadius: 8, color: '#e2d9ce', fontSize: 11 }}
              formatter={v => [COP(v), 'Ventas']}
            />
            <Area type="monotone" dataKey="ventas" stroke="#dc2626" strokeWidth={2} fill="url(#gr)"
              dot={{ fill: '#dc2626', r: 3 }} activeDot={{ r: 5 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Mini top 5 */}
      <div style={{ background: '#141414', border: '1px solid #222', borderRadius: 10, padding: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#ccc', marginBottom: 14 }}>Top 5 productos esta semana</div>
        {!top5 ? <Spinner /> : top5.length === 0 ? (
          <p style={{ color: '#666', fontSize: 12 }}>Sin ventas registradas esta semana.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {top5.map((p, i) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '26px 1fr 64px 90px', alignItems: 'center', gap: 10 }}>
                <span style={{ fontWeight: 700, fontSize: 11, color: RC[i], textAlign: 'right' }}>#{i + 1}</span>
                <div>
                  <div style={{ fontSize: 11, marginBottom: 4, color: '#ddd' }}>{p.producto}</div>
                  <div style={{ height: 3, background: '#1e1e1e', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${(p.unidades / maxTop5) * 100}%`, background: RC[i], borderRadius: 2 }} />
                  </div>
                </div>
                <span style={{ fontSize: 10, color: '#555', textAlign: 'right' }}>{p.unidades} uds</span>
                <span style={{ fontSize: 10, color: '#444', textAlign: 'right' }}>{COP(p.ingresos)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}

// ── Pestaña Top 10 ────────────────────────────────────────────────────────────
function TabTop10() {
  const [per, setPer] = useState('semana')
  const { data, loading, error } = useFetch(`/ventas/top?periodo=${per}`)

  const top = useMemo(
    () => (data?.top || []).map(p => ({ nombre: p.producto, vendidos: p.unidades, ingresos: p.ingresos })),
    [data],
  )
  const totalUnits = top.reduce((a, p) => a + p.vendidos, 0)

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#f0e6d8' }}>Top 10 Productos</div>
          <div style={{ fontSize: 10, color: '#444', marginTop: 2 }}>
            Ranking por unidades vendidas · {per === 'semana' ? 'esta semana' : 'este mes'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 5 }}>
          {['semana', 'mes'].map(p => (
            <button key={p} onClick={() => setPer(p)} style={{
              background: per === p ? '#dc2626' : 'none',
              border: '1px solid ' + (per === p ? '#dc2626' : '#2a2a2a'),
              color: per === p ? '#fff' : '#555',
              fontSize: 11, padding: '5px 14px', borderRadius: 6, cursor: 'pointer',
            }}>
              {p === 'semana' ? 'Esta semana' : 'Este mes'}
            </button>
          ))}
        </div>
      </div>

      {loading && <Spinner />}
      {error   && <ErrMsg msg={`Error: ${error}`} />}

      {!loading && !error && top.length === 0 && (
        <div style={{ background: '#141414', border: '1px solid #222', borderRadius: 10, padding: 32, textAlign: 'center', color: '#555', fontSize: 12 }}>
          Sin datos para este período.
        </div>
      )}

      {!loading && !error && top.length > 0 && (
        <>
          {/* Gráfica horizontal */}
          <div style={{ background: '#141414', border: '1px solid #222', borderRadius: 10, padding: 16, marginBottom: 10 }}>
            <ResponsiveContainer width="100%" height={Math.max(240, top.length * 28)}>
              <BarChart data={top} layout="vertical" barSize={11} margin={{ left: 130, right: 24, top: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a1a1a" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#444', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="nombre" tick={{ fill: '#888', fontSize: 10 }} axisLine={false} tickLine={false} width={125} />
                <Tooltip
                  contentStyle={{ background: '#141414', border: '1px solid #222', borderRadius: 8, color: '#e2d9ce', fontSize: 11 }}
                  formatter={v => [`${v} uds`, 'Vendidos']}
                />
                <Bar dataKey="vendidos" radius={[0, 3, 3, 0]}>
                  {top.map((_, i) => <Cell key={i} fill={i < 5 ? RC[i] : '#242424'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Tabla */}
          <div style={{ background: '#141414', border: '1px solid #222', borderRadius: 10, overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #1e1e1e' }}>
                  {['#', 'Producto', 'Unidades', 'Ingresos', '%'].map((h, i) => (
                    <th key={i} style={{ padding: '10px 14px', textAlign: i === 0 ? 'center' : 'left', fontSize: 9, color: '#444', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 400 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {top.map((p, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #161616' }}
                    onMouseEnter={e => e.currentTarget.style.background = '#1a1a1a'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                    <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                      <span style={{ fontWeight: 700, fontSize: 12, color: RC[i] }}>#{i + 1}</span>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 3, height: 22, borderRadius: 2, background: RC[i], flexShrink: 0 }} />
                        <span style={{ color: '#ddd' }}>{p.nombre}</span>
                        {i === 0 && (
                          <span style={{ background: '#dc262612', color: '#dc2626', border: '1px solid #dc262628', fontSize: 9, padding: '1px 7px', borderRadius: 99 }}>
                            🏆 #1
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ width: 50, height: 3, background: '#1e1e1e', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${(p.vendidos / (top[0].vendidos || 1)) * 100}%`, background: RC[i] }} />
                        </div>
                        <span style={{ color: '#666' }}>{p.vendidos}</span>
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px', color: i < 3 ? '#f0e6d8' : '#555', fontWeight: i < 3 ? 600 : 400 }}>
                      {COP(p.ingresos)}
                    </td>
                    <td style={{ padding: '10px 14px', color: '#555', fontSize: 10 }}>
                      {totalUnits ? ((p.vendidos / totalUnits) * 100).toFixed(1) : 0}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  )
}

// ── Pestaña Inventario ────────────────────────────────────────────────────────
function catIcon(cat) {
  const c = cat.toLowerCase()
  if (c.includes('pint') || c.includes('vinilo') || c.includes('color'))              return '🎨'
  if (c.includes('thinner') || c.includes('varsol') || c.includes('solvente'))       return '🧪'
  if (c.includes('lija') || c.includes('esmeril') || c.includes('abras'))            return '🪚'
  if (c.includes('tornill') || c.includes('clav') || c.includes('perno'))            return '🔩'
  if (c.includes('adhesiv') || c.includes('pega') || c.includes('silicon'))          return '🧲'
  if (c.includes('ferret') || c.includes('herram') || c.includes('artículo') || c.includes('brocha') || c.includes('rodillo')) return '🔧'
  if (c.includes('granel'))                                                           return '⚖️'
  return '📦'
}

function TabInventario() {
  const { data, loading, error } = useFetch('/productos')
  const { data: alertasData }    = useFetch('/inventario/bajo')
  const [abierta, setAbierta]    = useState(null)
  const [busqueda, setBusqueda]  = useState('')

  const alertaMap = useMemo(() => {
    const m = {}
    ;(alertasData?.alertas || []).forEach(a => { m[a.key] = a })
    return m
  }, [alertasData])

  // Agrupar por categoría, ordenar por prefijo numérico
  const categorias = useMemo(() => {
    const grupos = {}
    ;(data?.productos || []).forEach(p => {
      const cat = p.categoria || 'Sin categoría'
      if (!grupos[cat]) grupos[cat] = []
      grupos[cat].push(p)
    })
    return Object.entries(grupos).sort(([a], [b]) => (parseInt(a) || 999) - (parseInt(b) || 999))
  }, [data])

  const stockBadge = (p) => {
    const a = alertaMap[p.key]
    if (!a)                                        return <Badge type="ok">OK</Badge>
    if (a.motivo === 'sin_precio')                 return <Badge type="sinprecio">Sin precio</Badge>
    if (a.stock === 0 || a.stock === '0')          return <Badge type="agotado">Agotado</Badge>
    return <Badge type="bajo">Stock bajo</Badge>
  }

  if (loading) return <Spinner />
  if (error)   return <ErrMsg msg={`Error: ${error}`} />

  const filtrar = prods => {
    if (!busqueda) return prods
    const q = busqueda.toLowerCase()
    return prods.filter(p => p.nombre.toLowerCase().includes(q) || p.codigo.toLowerCase().includes(q))
  }

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ fontSize: 10, color: '#555' }}>
          {data?.total ?? 0} productos · <span style={{ color: '#dc2626' }}>⚠️ {alertasData?.total ?? 0} con alertas</span>
        </div>
        <input
          value={busqueda} onChange={e => setBusqueda(e.target.value)}
          placeholder="Buscar producto o código..."
          style={{ background: '#141414', border: '1px solid #2a2a2a', color: '#ccc', padding: '6px 12px', borderRadius: 7, fontSize: 11, outline: 'none', width: 220 }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {categorias.map(([cat, prods]) => {
          const label  = cat.replace(/^\d+\s*/, '')
          const filtrados = filtrar(prods)
          if (busqueda && filtrados.length === 0) return null
          const alertasCat = prods.filter(p => alertaMap[p.key]).length
          const expandida  = busqueda ? true : abierta === cat

          return (
            <div key={cat} style={{
              background: '#141414',
              border: '1px solid ' + (expandida ? '#dc262633' : '#222'),
              borderRadius: 10, overflow: 'hidden', transition: 'border-color .2s',
            }}>
              {/* Header categoría */}
              <div
                onClick={() => !busqueda && setAbierta(p => p === cat ? null : cat)}
                style={{ padding: '13px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: busqueda ? 'default' : 'pointer', userSelect: 'none' }}
                onMouseEnter={e => { if (!busqueda) e.currentTarget.style.background = '#1a1a1a' }}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 16 }}>{catIcon(label)}</span>
                  <span style={{ fontWeight: 600, fontSize: 13, color: '#e2d9ce' }}>{label}</span>
                  <span style={{ fontSize: 10, color: '#444' }}>{prods.length} productos</span>
                  {alertasCat > 0 && <span style={{ fontSize: 10, color: '#dc2626' }}>⚠️ {alertasCat}</span>}
                </div>
                {!busqueda && (
                  <span style={{ color: '#444', fontSize: 12, transition: 'transform .2s', transform: expandida ? 'rotate(90deg)' : 'rotate(0deg)', display: 'inline-block' }}>▶</span>
                )}
              </div>

              {/* Tabla de productos */}
              {expandida && (
                <div style={{ borderTop: '1px solid #1a1a1a' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr>
                        {['Producto', 'Código', 'Precio', 'Estado'].map((h, i) => (
                          <th key={i} style={{ padding: '7px 14px', textAlign: 'left', fontSize: 9, color: '#333', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 400, borderBottom: '1px solid #1a1a1a' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filtrados.map(p => {
                        const alerta   = alertaMap[p.key]
                        const stockNum = alerta?.stock
                        const pulsing  = stockNum !== null && stockNum !== undefined && Number(stockNum) > 0 && Number(stockNum) <= 3
                        return (
                          <tr key={p.key} style={{ borderTop: '1px solid #161616' }}
                            onMouseEnter={e => e.currentTarget.style.background = '#1a1a1a'}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                            <td style={{ padding: '10px 14px', color: stockNum === 0 ? '#444' : '#ddd' }}>
                              {pulsing && (
                                <span style={{ width: 6, height: 6, background: '#dc2626', borderRadius: '50%', display: 'inline-block', marginRight: 6, animation: 'pu 1.5s infinite' }} />
                              )}
                              {p.nombre}
                            </td>
                            <td style={{ padding: '10px 14px', color: '#3a3a3a', fontFamily: 'monospace', fontSize: 11 }}>{p.codigo || '—'}</td>
                            <td style={{ padding: '10px 14px', color: p.precio ? '#22c55e' : '#666', fontWeight: p.precio ? 600 : 400 }}>
                              {p.precio ? COP(p.precio) : '—'}
                            </td>
                            <td style={{ padding: '10px 14px' }}>{stockBadge(p)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </>
  )
}

// ── Pestaña Historial ─────────────────────────────────────────────────────────
function TabHistorial() {
  const { data, loading, error } = useFetch('/ventas/hoy')
  const [filtro, setFiltro]      = useState('todos')

  // Derivar estado desde el campo metodo
  const todasVentas = useMemo(() => (data?.ventas || []).map(v => ({
    ...v,
    estado: (v.metodo && v.metodo.trim() && v.metodo !== '—') ? 'pagado' : 'pendiente',
  })), [data])

  const ventas    = filtro === 'todos' ? todasVentas : todasVentas.filter(v => v.estado === filtro)
  const total     = ventas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const totalTodo = todasVentas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)

  if (loading) return <Spinner />
  if (error)   return <ErrMsg msg={`Error: ${error}`} />

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
        <div style={{ fontSize: 10, color: '#555' }}>
          Hoy · {todasVentas.length} registros · Total:{' '}
          <span style={{ color: '#dc2626', fontWeight: 600 }}>{COP(totalTodo)}</span>
        </div>
        <div style={{ display: 'flex', gap: 5 }}>
          {['todos', 'pagado', 'pendiente'].map(f => (
            <button key={f} onClick={() => setFiltro(f)} style={{
              background: filtro === f ? '#dc2626' : 'none',
              border: '1px solid ' + (filtro === f ? '#dc2626' : '#2a2a2a'),
              color: filtro === f ? '#fff' : '#555',
              fontSize: 10, padding: '4px 12px', borderRadius: 6, cursor: 'pointer', textTransform: 'capitalize',
            }}>
              {f}
            </button>
          ))}
        </div>
      </div>

      <div style={{ background: '#141414', border: '1px solid #222', borderRadius: 10, overflow: 'hidden' }}>
        {ventas.length === 0 ? (
          <div style={{ padding: '32px 24px', textAlign: 'center', color: '#555', fontSize: 12 }}>
            {filtro === 'todos' ? 'No hay ventas registradas hoy.' : `Sin registros con estado "${filtro}".`}
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #1e1e1e' }}>
                {['#', 'Hora', 'Producto', 'Cliente', 'Cant.', 'Total', 'Método', 'Estado'].map((h, i) => (
                  <th key={i} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 9, color: '#444', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 400 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ventas.map((v, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #161616' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#1a1a1a'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <td style={{ padding: '11px 14px', color: '#dc2626', fontWeight: 700 }}>{v.num}</td>
                  <td style={{ padding: '11px 14px', color: '#444', fontStyle: 'italic', fontSize: 11 }}>{v.hora}</td>
                  <td style={{ padding: '11px 14px', color: '#ddd' }}>{v.producto}</td>
                  <td style={{ padding: '11px 14px', color: '#555', fontSize: 11 }}>{v.cliente || 'Consumidor Final'}</td>
                  <td style={{ padding: '11px 14px', color: '#666' }}>{v.cantidad}</td>
                  <td style={{ padding: '11px 14px', color: '#dc2626', fontWeight: 600 }}>{COP(v.total)}</td>
                  <td style={{ padding: '11px 14px', color: '#555', fontSize: 11 }}>{v.metodo || '—'}</td>
                  <td style={{ padding: '11px 14px' }}><Badge type={v.estado}>{v.estado}</Badge></td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: '1px solid #222', background: '#111' }}>
                <td colSpan={5} style={{ padding: '10px 14px', fontSize: 10, color: '#444', textAlign: 'right' }}>
                  SUBTOTAL ({ventas.length} registros)
                </td>
                <td style={{ padding: '10px 14px', color: '#dc2626', fontWeight: 700 }}>{COP(total)}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    </>
  )
}

// ── App principal ─────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState('Resumen')

  return (
    <div style={{ fontFamily: 'system-ui,sans-serif', background: '#0a0a0a', minHeight: '100vh', color: '#e2d9ce', fontSize: 13 }}>
      <style>{`
        *{box-sizing:border-box;margin:0;padding:0}
        button{font-family:inherit;transition:all .15s}
        button:focus{outline:none}
        input:focus{outline:none;border-color:#dc262666 !important}
        @keyframes pu{0%,100%{opacity:1}50%{opacity:.3}}
        ::-webkit-scrollbar{width:4px}
        ::-webkit-scrollbar-thumb{background:#dc2626;border-radius:2px}
      `}</style>

      {/* Header */}
      <div style={{ borderBottom: '1px solid #1a1a1a', padding: '0 22px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 52, background: '#0d0d0d', position: 'sticky', top: 0, zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ width: 28, height: 28, background: '#dc2626', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14 }}>🔩</div>
          <div>
            <span style={{ fontWeight: 700, fontSize: 14, color: '#fff' }}>FERRETERÍA</span>
            <span style={{ fontWeight: 700, fontSize: 14, color: '#dc2626' }}> PUNTO ROJO</span>
          </div>
          <div style={{ width: 1, height: 18, background: '#222' }} />
          <span style={{ fontSize: 10, color: '#333', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Dashboard</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ fontSize: 10, color: '#333' }}><span style={{ color: '#4ade80' }}>●</span> Bot activo</div>
          <div style={{ fontSize: 10, color: '#2a2a2a' }}>
            {new Date().toLocaleDateString('es-CO', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ padding: '10px 22px 0', display: 'flex', gap: 3, borderBottom: '1px solid #141414', background: '#0d0d0d', position: 'sticky', top: 52, zIndex: 9 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: tab === t ? '#dc2626' : 'none',
            border: 'none',
            color: tab === t ? '#fff' : '#555',
            fontSize: 12, padding: '7px 15px', cursor: 'pointer',
            borderRadius: '7px 7px 0 0',
            borderBottom: tab === t ? '2px solid #dc2626' : '2px solid transparent',
          }}>
            {t}
          </button>
        ))}
      </div>

      {/* Contenido */}
      <div style={{ padding: '18px 22px', maxWidth: 1200, margin: '0 auto' }} key={tab}>
        {tab === 'Resumen'    && <TabResumen />}
        {tab === 'Top 10'     && <TabTop10 />}
        {tab === 'Inventario' && <TabInventario />}
        {tab === 'Historial'  && <TabHistorial />}
      </div>

      <div style={{ borderTop: '1px solid #111', padding: '10px 22px', display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 10, color: '#1a1a1a' }}>Ferretería Punto Rojo · Dashboard v2</span>
        <span style={{ fontSize: 10, color: '#1a1a1a' }}>Google Sheets · memoria.json</span>
      </div>
    </div>
  )
}
