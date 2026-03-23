import { useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import {
  useTheme, useFetch, Card, SectionTitle, KpiCard, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop, num, API_BASE,
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
  const [localRefresh, setLocalRefresh] = useState(0)
  const { data, loading, error } = useFetch(`/compras?dias=${dias}`, [dias, refreshKey, localRefresh])

  // Form nueva compra
  const [formOpen, setFormOpen] = useState(false)
  const [producto, setProducto] = useState('')
  const [cantidad, setCantidad] = useState('')
  const [costoUnit, setCostoUnit] = useState('')
  const [proveedor, setProveedor] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [msg, setMsg] = useState(null)

  const mostrarMsg = (tipo, texto) => { setMsg({ tipo, texto }); setTimeout(() => setMsg(null), 4000) }

  const registrarCompra = async () => {
    if (!producto.trim()) { mostrarMsg('err', 'El producto es obligatorio'); return }
    if (!cantidad || parseFloat(cantidad) <= 0) { mostrarMsg('err', 'La cantidad debe ser mayor a 0'); return }
    if (!costoUnit || parseFloat(costoUnit) <= 0) { mostrarMsg('err', 'El costo unitario debe ser mayor a 0'); return }
    setGuardando(true)
    try {
      const r = await fetch(`${API_BASE}/compras`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto: producto.trim(),
          cantidad: parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor: proveedor.trim(),
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarMsg('ok', `Compra registrada: ${cantidad} ${producto.trim()} a $${parseInt(costoUnit).toLocaleString('es-CO')} c/u`)
      setProducto(''); setCantidad(''); setCostoUnit(''); setProveedor('')
      setFormOpen(false)
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setGuardando(false) }
  }

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

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Compras a Proveedores</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            Historial de mercancía comprada · últimos {dias} días
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {DIAS_OPTIONS.map(o => (
            <PeriodBtn key={o.value} active={dias === o.value} onClick={() => setDias(o.value)}>
              {o.label}
            </PeriodBtn>
          ))}
          <button onClick={() => setFormOpen(f => !f)} style={{
            background: formOpen ? t.blue : `${t.blue}18`,
            border: `1px solid ${t.blue}55`, borderRadius: 8,
            color: formOpen ? '#fff' : t.blue,
            padding: '6px 14px', fontSize: 11, fontWeight: 700,
            cursor: 'pointer', fontFamily: 'inherit',
          }}>
            {formOpen ? '✕ Cerrar' : '➕ Nueva compra'}
          </button>
        </div>
      </div>

      {/* Formulario nueva compra */}
      {formOpen && (
        <Card>
          <SectionTitle>Registrar Compra</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Producto *</label>
              <input value={producto} onChange={e => setProducto(e.target.value)}
                placeholder="Ej: Brocha 2 pulgadas, Vinilo T1 Blanco..."
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
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Cantidad *</label>
              <input type="number" min="0" step="0.01" value={cantidad} onChange={e => setCantidad(e.target.value)}
                placeholder="0"
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
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Costo unitario *</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: t.textMuted, fontSize: 11 }}>$</span>
                <input type="number" min="0" value={costoUnit} onChange={e => setCostoUnit(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && registrarCompra()}
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
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>Proveedor (opcional)</label>
              <input value={proveedor} onChange={e => setProveedor(e.target.value)}
                placeholder="Ej: Ferrisariato, Distribuidora Central..."
                style={{
                  width: '100%', boxSizing: 'border-box',
                  background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                  border: `1px solid ${t.border}`, borderRadius: 7,
                  color: t.text, fontSize: 12, padding: '8px 10px',
                  outline: 'none', fontFamily: 'inherit',
                }}
              />
            </div>
          </div>
          {cantidad && costoUnit && (
            <div style={{ fontSize: 12, color: t.textSub, marginBottom: 10 }}>
              Total: <strong style={{ color: t.blue }}>{cop(parseFloat(cantidad) * parseFloat(costoUnit))}</strong>
            </div>
          )}
          <button onClick={registrarCompra} disabled={guardando} style={{
            background: t.blue, border: 'none', borderRadius: 8,
            color: '#fff', padding: '10px 24px', fontSize: 12,
            fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
          }}>
            {guardando ? 'Guardando…' : '📦 Registrar compra'}
          </button>
        </Card>
      )}

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
                      onMouseEnter={e => { e.currentTarget.style.background = t.cardHover; e.currentTarget.style.transform = 'translateX(2px)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.transform = 'translateX(0)' }}>
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
