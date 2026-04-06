/**
 * TabCompras.jsx — Compras a Proveedores (Almacén)
 * - Registro operativo: actualiza inventario + kárdex
 * - Botón ✏️ Editar por fila
 * - Botón 📊 Fiscal por fila (duplica a compras_fiscal para el Libro IVA)
 *   Si la compra ya tiene entrada fiscal el botón se muestra en verde bloqueado.
 */
import { useState, useRef, useEffect } from 'react'
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
  const base = Math.round(parseFloat(total) * 100 / (100 + parseFloat(tarifa)))
  const iva  = Math.round(parseFloat(total) - base)
  return { base, iva }
}

// ── Buscador de productos del catálogo ─────────────────────────────────────────
function ProductoSearchInput({ value, onChange, style, placeholder }) {
  const t = useTheme()
  const { authFetch } = useAuth()
  const [todos, setTodos] = useState([])
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const cargar = async () => {
    if (todos.length > 0) return
    try {
      const r = await authFetch(`${API_BASE}/productos`)
      const d = await r.json()
      const nombres = (d.productos || []).map(p => p.nombre).sort((a,b) => a.localeCompare(b))
      setTodos(nombres)
    } catch {}
  }

  const filtrados = value.trim().length >= 1
    ? todos.filter(n => n.toLowerCase().includes(value.toLowerCase()))
    : todos.slice(0, 30)

  useEffect(() => {
    const handler = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const dropdownBg = t.id === 'caramelo' ? '#fff' : '#1a1a1a'

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <input
        value={value}
        onChange={e => { onChange(e.target.value); setOpen(true) }}
        onFocus={() => { cargar(); setOpen(true) }}
        style={style}
        placeholder={placeholder || 'Buscar producto del catálogo…'}
        autoComplete="off"
      />
      {open && filtrados.length > 0 && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 3px)', left: 0, right: 0,
          zIndex: 9999, maxHeight: 220, overflowY: 'auto',
          background: dropdownBg, border: `1px solid ${t.border}`,
          borderRadius: 8, boxShadow: '0 6px 24px rgba(0,0,0,.28)',
        }}>
          {filtrados.map(n => (
            <div
              key={n}
              onMouseDown={e => { e.preventDefault(); onChange(n); setOpen(false) }}
              style={{
                padding: '7px 12px', cursor: 'pointer', fontSize: 12,
                color: n.toLowerCase() === value.toLowerCase() ? t.blue : t.text,
                fontWeight: n.toLowerCase() === value.toLowerCase() ? 700 : 400,
                borderBottom: `1px solid ${t.border}20`,
                transition: 'background .1s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = `${t.blue}18` }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
            >
              {n}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Modal Editar ──────────────────────────────────────────────────────────────
function ModalEditar({ compra, onClose, onSaved, authFetch, t }) {
  const [producto,   setProducto]   = useState(compra.producto)
  const [cantidad,   setCantidad]   = useState(String(compra.cantidad))
  const [costoUnit,  setCostoUnit]  = useState(String(compra.costo_unitario))
  const [proveedor,  setProveedor]  = useState(compra.proveedor === 'Sin proveedor' ? '' : compra.proveedor)
  const [incluyeIva, setIncluyeIva] = useState(compra.incluye_iva)
  const [tarifaIva,  setTarifaIva]  = useState(compra.tarifa_iva || 19)
  const [guardando,  setGuardando]  = useState(false)
  const [err,        setErr]        = useState(null)

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

  const guardar = async () => {
    if (!producto.trim())              { setErr('El producto es obligatorio'); return }
    if (parseFloat(cantidad) <= 0)     { setErr('Cantidad inválida'); return }
    if (parseFloat(costoUnit) <= 0)    { setErr('Costo inválido'); return }
    setGuardando(true); setErr(null)
    try {
      const r = await authFetch(`${API_BASE}/compras/${compra.id}`, {
        method: 'PUT',
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
      onSaved()
    } catch (e) { setErr(e.message) }
    finally { setGuardando(false) }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,.55)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', padding: 16,
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: t.card, border: `1px solid ${t.border}`,
        borderRadius: 14, padding: 24, width: '100%', maxWidth: 440,
        boxShadow: '0 20px 60px rgba(0,0,0,.4)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Editar Compra</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: t.textMuted, fontSize: 18, cursor: 'pointer' }}>✕</button>
        </div>

        {err && (
          <div style={{ padding: '8px 12px', borderRadius: 7, marginBottom: 12,
            background: `${t.accent}14`, border: `1px solid ${t.accent}44`,
            color: t.accent, fontSize: 12 }}>✕ {err}</div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>Producto *</label>
            <ProductoSearchInput value={producto} onChange={setProducto} style={inpStyle}/>
          </div>
          <div>
            <label style={lblStyle}>Cantidad *</label>
            <input type="number" min="0" step="0.01" value={cantidad}
              onChange={e => setCantidad(e.target.value)} style={inpStyle}/>
          </div>
          <div>
            <label style={lblStyle}>Costo unitario *</label>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: t.textMuted, fontSize: 11 }}>$</span>
              <input type="number" min="0" value={costoUnit}
                onChange={e => setCostoUnit(e.target.value)}
                style={{ ...inpStyle, paddingLeft: 22 }}/>
            </div>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>Proveedor</label>
            <input value={proveedor} onChange={e => setProveedor(e.target.value)} style={inpStyle}/>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>IVA</label>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <button onClick={() => setIncluyeIva(v => !v)} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                background: incluyeIva ? `${t.green}18` : t.tableAlt,
                border: `1px solid ${incluyeIva ? t.green : t.border}`,
                borderRadius: 8, padding: '7px 14px', cursor: 'pointer',
                fontFamily: 'inherit', fontSize: 11, fontWeight: 600,
                color: incluyeIva ? t.green : t.textMuted,
              }}>
                <span style={{ width: 28, height: 16, borderRadius: 99,
                  background: incluyeIva ? t.green : t.border,
                  position: 'relative', flexShrink: 0 }}>
                  <span style={{ position: 'absolute', top: 2,
                    left: incluyeIva ? 14 : 2, width: 12, height: 12,
                    borderRadius: '50%', background: '#fff', transition: 'left .15s' }}/>
                </span>
                {incluyeIva ? 'Incluye IVA' : 'Sin IVA'}
              </button>
              {incluyeIva && TARIFAS_IVA.map(tv => (
                <button key={tv} onClick={() => setTarifaIva(tv)} style={{
                  background: tarifaIva === tv ? t.accent : t.accentSub,
                  border: `1px solid ${tarifaIva === tv ? t.accent : t.border}`,
                  color: tarifaIva === tv ? '#fff' : t.textMuted,
                  borderRadius: 7, padding: '6px 14px', cursor: 'pointer',
                  fontFamily: 'inherit', fontSize: 11, fontWeight: 700,
                }}>{tv}%</button>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 18, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            background: t.tableAlt, border: `1px solid ${t.border}`,
            borderRadius: 8, color: t.textMuted, padding: '9px 20px',
            fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
          }}>Cancelar</button>
          <button onClick={guardar} disabled={guardando} style={{
            background: t.blue, border: 'none', borderRadius: 8,
            color: '#fff', padding: '9px 20px', fontSize: 12,
            fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            opacity: guardando ? 0.7 : 1,
          }}>{guardando ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </div>
    </div>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────
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

  // Form nueva compra
  const [formOpen,   setFormOpen]   = useState(false)
  const [producto,   setProducto]   = useState('')
  const [cantidad,   setCantidad]   = useState('')
  const [costoUnit,  setCostoUnit]  = useState('')
  const [proveedor,  setProveedor]  = useState('')
  const [incluyeIva, setIncluyeIva] = useState(true)
  const [tarifaIva,  setTarifaIva]  = useState(19)
  const [guardando,  setGuardando]  = useState(false)
  const [msg,        setMsg]        = useState(null)

  // Editar
  const [editando, setEditando] = useState(null)

  // Enviando a fiscal por id de compra
  const [enviandoFiscal, setEnviandoFiscal] = useState({})

  const mostrarMsg = (tipo, texto) => {
    setMsg({ tipo, texto })
    setTimeout(() => setMsg(null), 4000)
  }

  const totalBruto = cantidad && costoUnit
    ? parseFloat(cantidad) * parseFloat(costoUnit) : 0
  const { base: baseCalc, iva: ivaCalc } = incluyeIva
    ? calcIVA(totalBruto, tarifaIva)
    : { base: totalBruto, iva: 0 }

  const registrarCompra = async () => {
    if (!producto.trim())                         { mostrarMsg('err', 'El producto es obligatorio'); return }
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
      setIncluyeIva(false); setTarifaIva(19); setFormOpen(false)
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setGuardando(false) }
  }

  const enviarAFiscal = async (compra) => {
    setEnviandoFiscal(prev => ({ ...prev, [compra.id]: true }))
    try {
      const r = await authFetch(`${API_BASE}/compras/${compra.id}/to-fiscal`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarMsg('ok', d.ya_existia
        ? 'Esta compra ya estaba en Compras Fiscal'
        : 'Compra enviada a Contabilidad Fiscal'
      )
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setEnviandoFiscal(prev => ({ ...prev, [compra.id]: false })) }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  const d        = data || {}
  const compras  = d.compras || []
  const porProv  = Object.entries(d.por_proveedor || {}).sort((a, b) => b[1] - a[1])
  const porProd  = Object.entries(d.por_producto  || {}).slice(0, 10)
  const total    = d.total_invertido || 0
  const pieData  = porProv.map(([name, value]) => ({ name, value }))
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

      {/* Modal editar */}
      {editando && (
        <ModalEditar
          compra={editando}
          onClose={() => setEditando(null)}
          onSaved={() => {
            setEditando(null)
            mostrarMsg('ok', 'Compra actualizada')
            setLocalRefresh(r => r + 1)
          }}
          authFetch={authFetch}
          t={t}
        />
      )}

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
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
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
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>Producto *</label>
              <ProductoSearchInput value={producto} onChange={setProducto}
                style={inpStyle} placeholder="Buscar o escribir nombre del producto…"/>
            </div>
            <div>
              <label style={lblStyle}>Cantidad *</label>
              <input type="number" min="0" step="0.01" value={cantidad}
                onChange={e => setCantidad(e.target.value)} placeholder="0" style={inpStyle}/>
            </div>
            <div>
              <label style={lblStyle}>Costo unitario *</label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: t.textMuted, fontSize: 11 }}>$</span>
                <input type="number" min="0" value={costoUnit}
                  onChange={e => setCostoUnit(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && registrarCompra()}
                  placeholder="0" style={{ ...inpStyle, paddingLeft: 22 }}/>
              </div>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>Proveedor (opcional)</label>
              <input value={proveedor} onChange={e => setProveedor(e.target.value)}
                placeholder="Ej: Ferrisariato, Distribuidora Central..." style={inpStyle}/>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>IVA en esta compra</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <button onClick={() => setIncluyeIva(v => !v)} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  background: incluyeIva ? `${t.green}18` : t.tableAlt,
                  border: `1px solid ${incluyeIva ? t.green : t.border}`,
                  borderRadius: 8, padding: '7px 14px', cursor: 'pointer',
                  fontFamily: 'inherit', fontSize: 11, fontWeight: 600,
                  color: incluyeIva ? t.green : t.textMuted, transition: 'all .15s',
                }}>
                  <span style={{ width: 28, height: 16, borderRadius: 99,
                    background: incluyeIva ? t.green : t.border,
                    position: 'relative', transition: 'background .15s', flexShrink: 0 }}>
                    <span style={{ position: 'absolute', top: 2,
                      left: incluyeIva ? 14 : 2, width: 12, height: 12,
                      borderRadius: '50%', background: '#fff', transition: 'left .15s' }}/>
                  </span>
                  {incluyeIva ? 'Precio incluye IVA' : 'Sin IVA'}
                </button>
                {incluyeIva && (
                  <div style={{ display: 'flex', gap: 6 }}>
                    {TARIFAS_IVA.map(tv => (
                      <button key={tv} onClick={() => setTarifaIva(tv)} style={{
                        background: tarifaIva === tv ? t.accent : t.accentSub,
                        border: `1px solid ${tarifaIva === tv ? t.accent : t.border}`,
                        color: tarifaIva === tv ? '#fff' : t.textMuted,
                        borderRadius: 7, padding: '6px 14px', cursor: 'pointer',
                        fontFamily: 'inherit', fontSize: 11, fontWeight: 700, transition: 'all .15s',
                      }}>{tv}%</button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

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
                    IVA {tarifaIva}%: <strong style={{ color: t.green }}>{cop(ivaCalc)}</strong>
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
              ✅ Al enviar esta compra a Compras Fiscal, el IVA ({cop(ivaCalc)}) se registrará como crédito descontable en el Libro IVA
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
            <KpiCard label="Total invertido"  value={cop(total)}     sub={`Últimos ${dias} días`}  icon="💰" color={t.blue}/>
            <KpiCard label="Compras"          value={compras.length} sub="Registros"               icon="📦" color={t.textSub}/>
            <KpiCard label="Proveedores"      value={porProv.length} sub="Distintos"               icon="🏭" color={t.textSub}/>
            <KpiCard label="Productos"        value={Object.keys(d.por_producto||{}).length} sub="Artículos" icon="🔢" color={t.textSub}/>
          </div>

          {/* Gráficas — columna única para móvil */}
          <GlassCard>
            <SectionTitle>Por Proveedor</SectionTitle>
            {porProv.length === 0 ? <EmptyState/> : (
              <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <ResponsiveContainer width={120} height={120}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={55} paddingAngle={2}>
                      {pieData.map((_, i) => <Cell key={i} fill={PROV_COLORS[i % PROV_COLORS.length]}/>)}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: t.card, border: `1px solid ${t.border}`, borderRadius: 8, color: t.text, fontSize: 11 }}
                      formatter={v => [cop(v)]}/>
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ flex: 1, minWidth: 140, display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {porProv.map(([prov, val], i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 0 }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: PROV_COLORS[i % PROV_COLORS.length], flexShrink: 0, display: 'inline-block' }}/>
                        <span style={{ fontSize: 11, color: t.textSub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{prov}</span>
                      </div>
                      <span style={{ fontSize: 11, fontWeight: 700, color: t.text, flexShrink: 0 }}>{cop(val)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </GlassCard>

          <GlassCard>
            <SectionTitle>Productos más Comprados</SectionTitle>
            {porProd.length === 0 ? <EmptyState/> : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {porProd.map(([prod, val], i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={{ color: t.textMuted, fontSize: 11, minWidth: 22, textAlign: 'right', fontWeight: 700 }}>#{i+1}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 11, color: t.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{prod}</span>
                        <span style={{ fontSize: 12, color: t.blue, fontWeight: 700, flexShrink: 0 }}>{cop(val)}</span>
                      </div>
                      <div style={{ height: 3, background: t.border, borderRadius: 2 }}>
                        <div style={{ height: '100%', width: `${(val / (porProd[0]?.[1] || 1)) * 100}%`, background: t.blue, borderRadius: 2 }}/>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          {/* Detalle — cards en lugar de tabla para móvil */}
          <GlassCard style={{ padding: 0 }}>
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <SectionTitle>Detalle de Compras</SectionTitle>
              <span style={{ fontSize: 11, color: t.textMuted }}>{compras.length} registros</span>
            </div>

            {/* Totales compactos */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 18px', background: t.tableAlt,
              borderBottom: `1px solid ${t.border}`,
            }}>
              <span style={{ fontSize: 11, color: t.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em' }}>Total Invertido</span>
              <span style={{ fontSize: 13, color: t.blue, fontWeight: 700 }}>{cop(total)}</span>
            </div>

            {/* Cards */}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {compras.map((c, i) => {
                const { iva }    = c.incluye_iva && c.tarifa_iva ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                const yaEnFiscal = !!c.compra_fiscal_id
                const cargando  = !!enviandoFiscal[c.id]

                return (
                  <div key={i} style={{
                    padding: '12px 18px',
                    borderBottom: i < compras.length - 1 ? `1px solid ${t.border}` : 'none',
                  }}>
                    {/* Fila 1: fecha + proveedor */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                      <span style={{ fontSize: 11, color: t.textMuted }}>{String(c.fecha||'').slice(0,10)}</span>
                      <span style={{ fontSize: 11, color: t.textMuted, fontStyle: 'italic' }}>{c.proveedor||'Sin proveedor'}</span>
                    </div>

                    {/* Fila 2: producto */}
                    <div style={{ fontSize: 13, fontWeight: 600, color: t.text, marginBottom: 8, lineHeight: 1.35 }}>
                      {c.producto||'—'}
                    </div>

                    {/* Fila 3: cantidades */}
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                      <span style={{
                        fontSize: 11, color: t.textMuted, background: t.tableAlt,
                        borderRadius: 5, padding: '2px 8px', border: `1px solid ${t.border}`,
                      }}>{num(c.cantidad)} uds × {cop(c.costo_unitario)}</span>
                      <span style={{ fontSize: 12, color: t.blue, fontWeight: 700 }}>{cop(c.costo_total)}</span>
                      {c.incluye_iva && c.tarifa_iva > 0 && (
                        <span style={{
                          fontSize: 11, color: t.green, fontWeight: 600,
                          background: `${t.green}12`, borderRadius: 5, padding: '2px 8px',
                          border: `1px solid ${t.green}30`,
                        }}>IVA {cop(iva)} ({c.tarifa_iva}%)</span>
                      )}
                    </div>

                    {/* Acciones */}
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => setEditando(c)}
                        style={{
                          flex: 1, background: `${t.blue}14`, border: `1px solid ${t.blue}40`,
                          borderRadius: 7, color: t.blue, padding: '7px 0',
                          fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600,
                        }}>✏️ Editar</button>
                      <button
                        onClick={() => !yaEnFiscal && !cargando && enviarAFiscal(c)}
                        style={{
                          flex: 1,
                          background: yaEnFiscal ? `${t.green}14` : `${t.accent}14`,
                          border: `1px solid ${yaEnFiscal ? t.green : t.accent}40`,
                          borderRadius: 7, color: yaEnFiscal ? t.green : t.accent,
                          padding: '7px 0', fontSize: 12,
                          cursor: yaEnFiscal ? 'default' : 'pointer',
                          fontFamily: 'inherit', fontWeight: 600,
                          opacity: cargando ? 0.6 : 1,
                        }}>
                        {cargando ? '…' : yaEnFiscal ? '✓ En Fiscal' : '📊 → Fiscal'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </GlassCard>
        </>
      )}
    </div>
  )
}
