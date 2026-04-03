/**
 * TabCompras.jsx — Compras a Proveedores
 * Agrega campo de IVA al formulario de nueva compra:
 *   - Toggle "incluye IVA"
 *   - Selector de tarifa (5% / 19%)
 *   - Preview de base + IVA en tiempo real
 * El IVA se guarda en compras.incluye_iva y compras.tarifa_iva
 * para ser usado en el Libro IVA como crédito descontable.
 */
import { useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import {
  useTheme, useFetch, Card, GlassCard, SectionTitle, KpiCard, Spinner, ErrorMsg,
  PeriodBtn, EmptyState, cop, num, API_BASE,
} from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'
import { useVendorFilter } from '../hooks/useVendorFilter.jsx'

const DIAS_OPTIONS = [
  { label: '7 días',  value: 7  },
  { label: '15 días', value: 15 },
  { label: '30 días', value: 30 },
  { label: '90 días', value: 90 },
]
const PROV_COLORS = ['#60a5fa','#4ade80','#fbbf24','#f87171','#a78bfa','#fb923c','#94a3b8']
const TARIFAS_IVA = [5, 19]

function calcIVA(total, tarifa) {
  if (!total || !tarifa) return { base: total || 0, iva: 0 }
  const t = parseFloat(total) * parseFloat(tarifa)
  const base = Math.round(parseFloat(total) * 100 / (100 + parseFloat(tarifa)))
  const iva  = Math.round(parseFloat(total) - base)
  return { base, iva }
}

export default function TabCompras({ refreshKey }) {
  const t = useTheme()
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()
  const [dias, setDias] = useState(30)
  const [localRefresh, setLocalRefresh] = useState(0)
  const vendorParam = selectedVendor ? '&vendor_id=' + selectedVendor : ''
  const { data, loading, error } = useFetch(
    `/compras?dias=${dias}${vendorParam}`,
    [dias, refreshKey, localRefresh, selectedVendor]
  )

  // Form
  const [formOpen,    setFormOpen]    = useState(false)
  const [producto,    setProducto]    = useState('')
  const [cantidad,    setCantidad]    = useState('')
  const [costoUnit,   setCostoUnit]   = useState('')
  const [proveedor,   setProveedor]   = useState('')
  const [incluyeIva,  setIncluyeIva]  = useState(false)
  const [tarifaIva,   setTarifaIva]   = useState(19)
  const [guardando,   setGuardando]   = useState(false)
  const [msg,         setMsg]         = useState(null)

  const mostrarMsg = (tipo, texto) => {
    setMsg({ tipo, texto })
    setTimeout(() => setMsg(null), 4000)
  }

  const totalBruto = cantidad && costoUnit
    ? parseFloat(cantidad) * parseFloat(costoUnit)
    : 0
  const { base: baseCalc, iva: ivaCalc } = incluyeIva
    ? calcIVA(totalBruto, tarifaIva)
    : { base: totalBruto, iva: 0 }

  const registrarCompra = async () => {
    if (!producto.trim())                { mostrarMsg('err', 'El producto es obligatorio'); return }
    if (!cantidad || parseFloat(cantidad) <= 0)   { mostrarMsg('err', 'La cantidad debe ser mayor a 0'); return }
    if (!costoUnit || parseFloat(costoUnit) <= 0) { mostrarMsg('err', 'El costo unitario debe ser mayor a 0'); return }
    setGuardando(true)
    try {
      const r = await authFetch(`${API_BASE}/compras`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto:       producto.trim(),
          cantidad:       parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor:      proveedor.trim(),
          incluye_iva:    incluyeIva,
          tarifa_iva:     incluyeIva ? tarifaIva : 0,
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      const ivaMsg = incluyeIva ? ` · IVA ${tarifaIva}%: ${cop(ivaCalc)}` : ''
      mostrarMsg('ok', `Compra registrada: ${cantidad} ${producto.trim()} — Total: ${cop(totalBruto)}${ivaMsg}`)
      setProducto(''); setCantidad(''); setCostoUnit(''); setProveedor('')
      setIncluyeIva(false); setTarifaIva(19)
      setFormOpen(false)
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setGuardando(false) }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  const d       = data || {}
  const compras = d.compras || []
  const porProv = Object.entries(d.por_proveedor || {}).sort((a, b) => b[1] - a[1])
  const porProd = Object.entries(d.por_producto  || {}).slice(0, 10)
  const total   = d.total_invertido || 0
  const pieData = porProv.map(([name, value]) => ({ name, value }))
  const sinDatos = compras.length === 0

  const inpStyle = {
    width: '100%', boxSizing: 'border-box',
    background: t.id === 'caramelo' ? '#f8fafc' : '#111',
    border: `1px solid ${t.border}`, borderRadius: 7,
    color: t.text, fontSize: 12, padding: '8px 10px',
    outline: 'none', fontFamily: 'inherit',
  }
  const lblStyle = {
    fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
    letterSpacing: '.06em', display: 'block', marginBottom: 4,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

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
        <GlassCard>
          <SectionTitle>Registrar Compra</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 12 }}>

            {/* Producto */}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>Producto *</label>
              <input value={producto} onChange={e => setProducto(e.target.value)}
                placeholder="Ej: Brocha 2 pulgadas, Vinilo T1 Blanco..."
                style={inpStyle}/>
            </div>

            {/* Cantidad */}
            <div>
              <label style={lblStyle}>Cantidad *</label>
              <input type="number" min="0" step="0.01" value={cantidad}
                onChange={e => setCantidad(e.target.value)}
                placeholder="0" style={inpStyle}/>
            </div>

            {/* Costo unitario */}
            <div>
              <label style={lblStyle}>Costo unitario *</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: t.textMuted, fontSize: 11 }}>$</span>
                <input type="number" min="0" value={costoUnit}
                  onChange={e => setCostoUnit(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && registrarCompra()}
                  placeholder="0"
                  style={{ ...inpStyle, paddingLeft: 22 }}/>
              </div>
            </div>

            {/* Proveedor */}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>Proveedor (opcional)</label>
              <input value={proveedor} onChange={e => setProveedor(e.target.value)}
                placeholder="Ej: Ferrisariato, Distribuidora Central..."
                style={inpStyle}/>
            </div>

            {/* Toggle IVA */}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>IVA en esta compra</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                {/* Toggle */}
                <button
                  onClick={() => setIncluyeIva(v => !v)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    background: incluyeIva ? `${t.green}18` : t.tableAlt,
                    border: `1px solid ${incluyeIva ? t.green : t.border}`,
                    borderRadius: 8, padding: '7px 14px',
                    cursor: 'pointer', fontFamily: 'inherit',
                    fontSize: 11, fontWeight: 600,
                    color: incluyeIva ? t.green : t.textMuted,
                    transition: 'all .15s',
                  }}>
                  <span style={{
                    width: 28, height: 16, borderRadius: 99,
                    background: incluyeIva ? t.green : t.border,
                    position: 'relative', transition: 'background .15s', flexShrink: 0,
                  }}>
                    <span style={{
                      position: 'absolute', top: 2,
                      left: incluyeIva ? 14 : 2,
                      width: 12, height: 12, borderRadius: '50%',
                      background: '#fff', transition: 'left .15s',
                    }}/>
                  </span>
                  {incluyeIva ? 'Precio incluye IVA' : 'Sin IVA'}
                </button>

                {/* Selector tarifa */}
                {incluyeIva && (
                  <div style={{ display: 'flex', gap: 6 }}>
                    {TARIFAS_IVA.map(t_ => (
                      <button key={t_} onClick={() => setTarifaIva(t_)} style={{
                        background: tarifaIva === t_ ? t.accent : t.accentSub,
                        border: `1px solid ${tarifaIva === t_ ? t.accent : t.border}`,
                        color: tarifaIva === t_ ? '#fff' : t.textMuted,
                        borderRadius: 7, padding: '6px 14px',
                        cursor: 'pointer', fontFamily: 'inherit',
                        fontSize: 11, fontWeight: 700, transition: 'all .15s',
                      }}>{t_}%</button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Preview totales */}
          {cantidad && costoUnit && (
            <div style={{
              display: 'flex', gap: 16, flexWrap: 'wrap',
              padding: '10px 14px', borderRadius: 8,
              background: t.tableAlt, border: `1px solid ${t.border}`,
              marginBottom: 12, fontSize: 12,
            }}>
              <span style={{ color: t.textMuted }}>
                Total bruto: <strong style={{ color: t.blue }}>{cop(totalBruto)}</strong>
              </span>
              {incluyeIva && (
                <>
                  <span style={{ color: t.textMuted }}>
                    Base (sin IVA): <strong style={{ color: t.text }}>{cop(baseCalc)}</strong>
                  </span>
                  <span style={{ color: t.textMuted }}>
                    IVA {tarifaIva}% descontable: <strong style={{ color: t.green }}>{cop(ivaCalc)}</strong>
                  </span>
                </>
              )}
            </div>
          )}

          {incluyeIva && (
            <div style={{
              padding: '8px 12px', borderRadius: 7, marginBottom: 12,
              background: `${t.green}10`, border: `1px solid ${t.green}33`,
              fontSize: 11, color: t.green,
            }}>
              ✅ Este IVA ({cop(ivaCalc)}) se contabilizará como IVA descontable en el Libro IVA
              y reducirá el IVA a pagar bimestralmente.
            </div>
          )}

          <button onClick={registrarCompra} disabled={guardando} style={{
            background: t.blue, border: 'none', borderRadius: 8,
            color: '#fff', padding: '10px 24px', fontSize: 12,
            fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            opacity: guardando ? 0.7 : 1,
          }}>
            {guardando ? 'Guardando…' : '📦 Registrar compra'}
          </button>
        </GlassCard>
      )}

      {sinDatos ? (
        <GlassCard>
          <div style={{ padding: '32px 24px', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>📦</div>
            <div style={{ color: t.text, fontWeight: 600, marginBottom: 8 }}>Sin compras registradas</div>
            <div style={{ color: t.textMuted, fontSize: 12, maxWidth: 340, margin: '0 auto' }}>
              Las compras también se pueden registrar en Telegram:
            </div>
            <code style={{
              display: 'inline-block', marginTop: 10,
              background: t.tableAlt, color: t.accent,
              border: `1px solid ${t.border}`,
              padding: '6px 14px', borderRadius: 7, fontSize: 12,
            }}>
              /compra 20 brocha 2" a 2500
            </code>
          </div>
        </GlassCard>
      ) : (
        <>
          {/* KPIs */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <KpiCard label="Total invertido"  value={cop(total)}       sub={`Últimos ${dias} días`} icon="💰" color={t.blue}/>
            <KpiCard label="Compras"          value={compras.length}   sub="Registros"              icon="📦" color={t.textSub}/>
            <KpiCard label="Proveedores"      value={porProv.length}   sub="Distintos"              icon="🏭" color={t.textSub}/>
            <KpiCard label="Productos"        value={Object.keys(d.por_producto||{}).length} sub="Artículos comprados" icon="🔢" color={t.textSub}/>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <GlassCard>
              <SectionTitle>Por Proveedor</SectionTitle>
              {porProv.length === 0 ? <EmptyState/> : (
                <>
                  <ResponsiveContainer width="100%" height={120}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2}>
                        {pieData.map((_, i) => <Cell key={i} fill={PROV_COLORS[i % PROV_COLORS.length]}/>)}
                      </Pie>
                      <Tooltip
                        contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
                        formatter={v => [cop(v)]}/>
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                    {porProv.map(([prov, val], i) => (
                      <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <span style={{ width: 8, height: 8, borderRadius: '50%', background: PROV_COLORS[i % PROV_COLORS.length], flexShrink: 0, display: 'inline-block' }}/>
                          <span style={{ fontSize: 11, color: t.textSub }}>{prov}</span>
                        </div>
                        <span style={{ fontSize: 11, fontWeight: 600, color: t.text }}>{cop(val)}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </GlassCard>

            <GlassCard>
              <SectionTitle>Productos más Comprados</SectionTitle>
              {porProd.length === 0 ? <EmptyState/> : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {porProd.map(([prod, val], i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ color: t.textMuted, fontSize: 11, minWidth: 18, textAlign: 'right' }}>#{i+1}</span>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 11, color: t.text, marginBottom: 3 }}>{prod}</div>
                        <div style={{ height: 3, background: t.border, borderRadius: 2 }}>
                          <div style={{ height: '100%', width: `${(val / (porProd[0]?.[1] || 1)) * 100}%`, background: t.blue, borderRadius: 2 }}/>
                        </div>
                      </div>
                      <span style={{ fontSize: 11, color: t.blue, fontWeight: 600, whiteSpace: 'nowrap' }}>{cop(val)}</span>
                    </div>
                  ))}
                </div>
              )}
            </GlassCard>
          </div>

          {/* Tabla */}
          <GlassCard style={{ padding: 0 }}>
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
              <SectionTitle>Detalle de Compras</SectionTitle>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: t.tableAlt }}>
                    {['Fecha','Producto','Cantidad','Costo Unit.','Total','IVA','Proveedor'].map((h, i) => (
                      <th key={i} style={{
                        padding: '9px 14px',
                        textAlign: [2,3,4,5].includes(i) ? 'right' : 'left',
                        fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
                        letterSpacing: '.08em', fontWeight: 500,
                        borderBottom: `1px solid ${t.border}`, whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {compras.map((c, i) => {
                    const { iva } = c.incluye_iva && c.tarifa_iva
                      ? calcIVA(c.costo_total, c.tarifa_iva)
                      : { iva: 0 }
                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${t.border}` }}
                        onMouseEnter={e => { e.currentTarget.style.background = t.cardHover }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                        <td style={{ padding: '9px 14px', color: t.textMuted, whiteSpace: 'nowrap' }}>{String(c.fecha||'').slice(0,10)}</td>
                        <td style={{ padding: '9px 14px', color: t.text }}>{c.producto||'—'}</td>
                        <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textSub }}>{num(c.cantidad)}</td>
                        <td style={{ padding: '9px 14px', textAlign: 'right', color: t.textMuted }}>{cop(c.costo_unitario)}</td>
                        <td style={{ padding: '9px 14px', textAlign: 'right', color: t.blue, fontWeight: 600 }}>{cop(c.costo_total)}</td>
                        <td style={{ padding: '9px 14px', textAlign: 'right' }}>
                          {c.incluye_iva && c.tarifa_iva > 0
                            ? <span style={{ color: t.green, fontWeight: 600, fontSize: 11 }}>
                                {cop(iva)}
                                <span style={{ fontSize: 9, marginLeft: 4, color: t.textMuted }}>{c.tarifa_iva}%</span>
                              </span>
                            : <span style={{ color: t.textMuted, fontSize: 11 }}>—</span>
                          }
                        </td>
                        <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{c.proveedor||'—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                    <td colSpan={4} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>TOTAL INVERTIDO</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', color: t.blue, fontWeight: 700, fontSize: 14 }}>{cop(total)}</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', color: t.green, fontWeight: 700, fontSize: 12 }}>
                      {cop(compras.filter(c => c.incluye_iva && c.tarifa_iva > 0).reduce((s, c) => {
                        const { iva } = calcIVA(c.costo_total, c.tarifa_iva)
                        return s + iva
                      }, 0))}
                    </td>
                    <td/>
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
