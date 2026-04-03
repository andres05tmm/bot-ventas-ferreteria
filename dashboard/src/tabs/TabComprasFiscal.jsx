/**
 * TabComprasFiscal.jsx — Compras Fiscales (Contabilidad / Libro IVA)
 *
 * - Registro contable: NO modifica inventario ni kárdex
 * - Campos extra: número de factura, notas fiscales
 * - Botón ✏️ Editar por fila (PUT /compras-fiscal/{id})
 * - Botón 📦 → Compras por fila (POST /compras-fiscal/{id}/to-compras)
 *   Si ya tiene compra vinculada el botón se muestra en verde bloqueado.
 * - Es la fuente de datos del Libro IVA
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

// ── Modal Editar Fiscal ───────────────────────────────────────────────────────
function ModalEditarFiscal({ compra, onClose, onSaved, authFetch, t }) {
  const [producto,       setProducto]       = useState(compra.producto)
  const [cantidad,       setCantidad]       = useState(String(compra.cantidad))
  const [costoUnit,      setCostoUnit]      = useState(String(compra.costo_unitario))
  const [proveedor,      setProveedor]      = useState(compra.proveedor === 'Sin proveedor' ? '' : compra.proveedor)
  const [incluyeIva,     setIncluyeIva]     = useState(compra.incluye_iva)
  const [tarifaIva,      setTarifaIva]      = useState(compra.tarifa_iva || 19)
  const [numeroFactura,  setNumeroFactura]  = useState(compra.numero_factura || '')
  const [notasFiscales,  setNotasFiscales]  = useState(compra.notas_fiscales || '')
  const [guardando,      setGuardando]      = useState(false)
  const [err,            setErr]            = useState(null)

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
  const textareaStyle = {
    ...inpStyle,
    resize: 'vertical', minHeight: 64,
  }

  const guardar = async () => {
    if (!producto.trim())           { setErr('El producto es obligatorio'); return }
    if (parseFloat(cantidad) <= 0)  { setErr('Cantidad inválida'); return }
    if (parseFloat(costoUnit) <= 0) { setErr('Costo inválido'); return }
    setGuardando(true); setErr(null)
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal/${compra.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto:       producto.trim(),
          cantidad:       parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor:      proveedor.trim(),
          incluye_iva:    incluyeIva,
          tarifa_iva:     incluyeIva ? tarifaIva : 0,
          numero_factura: numeroFactura.trim(),
          notas_fiscales: notasFiscales.trim(),
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
        borderRadius: 14, padding: 24, width: '100%', maxWidth: 480,
        boxShadow: '0 20px 60px rgba(0,0,0,.4)',
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        {/* Cabecera */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
          <div>
            <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Editar Compra Fiscal</span>
            <div style={{ fontSize: 10, color: t.textMuted, marginTop: 2 }}>
              Solo contabilidad · no modifica inventario
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: t.textMuted, fontSize: 18, cursor: 'pointer' }}>✕</button>
        </div>

        {err && (
          <div style={{
            padding: '8px 12px', borderRadius: 7, marginBottom: 12,
            background: `${t.accent}14`, border: `1px solid ${t.accent}44`,
            color: t.accent, fontSize: 12,
          }}>✕ {err}</div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {/* Producto */}
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>Producto *</label>
            <ProductoSearchInput value={producto} onChange={setProducto} style={inpStyle}/>
          </div>
          {/* Cantidad */}
          <div>
            <label style={lblStyle}>Cantidad *</label>
            <input type="number" min="0" step="0.01" value={cantidad}
              onChange={e => setCantidad(e.target.value)} style={inpStyle}/>
          </div>
          {/* Costo unitario */}
          <div>
            <label style={lblStyle}>Costo unitario *</label>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: t.textMuted, fontSize: 11 }}>$</span>
              <input type="number" min="0" value={costoUnit}
                onChange={e => setCostoUnit(e.target.value)}
                style={{ ...inpStyle, paddingLeft: 22 }}/>
            </div>
          </div>
          {/* Proveedor */}
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>Proveedor</label>
            <input value={proveedor} onChange={e => setProveedor(e.target.value)} style={inpStyle}/>
          </div>
          {/* Número de factura */}
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>Número de Factura</label>
            <input value={numeroFactura} onChange={e => setNumeroFactura(e.target.value)}
              placeholder="Ej: FV-2024-001234" style={inpStyle}/>
          </div>
          {/* IVA */}
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
          {/* Notas fiscales */}
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>Notas Fiscales</label>
            <textarea value={notasFiscales} onChange={e => setNotasFiscales(e.target.value)}
              placeholder="Observaciones para el Libro IVA..." style={textareaStyle}/>
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
export default function TabComprasFiscal({ refreshKey }) {
  const t = useTheme()
  const { authFetch } = useAuth()
  const { selectedVendor } = useVendorFilter()
  const [dias, setDias] = useState(30)
  const [localRefresh, setLocalRefresh] = useState(0)
  const vendorParam = selectedVendor ? '&vendor_id=' + selectedVendor : ''
  const { data, loading, error } = useFetch(
    `/compras-fiscal?dias=${dias}${vendorParam}`,
    [dias, refreshKey, localRefresh, selectedVendor]
  )

  // Form nueva compra fiscal
  const [formOpen,      setFormOpen]      = useState(false)
  const [producto,      setProducto]      = useState('')
  const [cantidad,      setCantidad]      = useState('')
  const [costoUnit,     setCostoUnit]     = useState('')
  const [proveedor,     setProveedor]     = useState('')
  const [incluyeIva,    setIncluyeIva]    = useState(false)
  const [tarifaIva,     setTarifaIva]     = useState(19)
  const [numFactura,    setNumFactura]     = useState('')
  const [notasFiscales, setNotasFiscales] = useState('')
  const [guardando,     setGuardando]     = useState(false)
  const [msg,           setMsg]           = useState(null)

  // Editar fila
  const [editando, setEditando] = useState(null)

  // Enviando a compras normales por id
  const [enviandoCompra, setEnviandoCompra] = useState({})

  const mostrarMsg = (tipo, texto) => {
    setMsg({ tipo, texto })
    setTimeout(() => setMsg(null), 4000)
  }

  const totalBruto = cantidad && costoUnit
    ? parseFloat(cantidad) * parseFloat(costoUnit) : 0
  const { base: baseCalc, iva: ivaCalc } = incluyeIva
    ? calcIVA(totalBruto, tarifaIva)
    : { base: totalBruto, iva: 0 }

  const registrarCompraFiscal = async () => {
    if (!producto.trim())                         { mostrarMsg('err', 'El producto es obligatorio'); return }
    if (!cantidad || parseFloat(cantidad) <= 0)   { mostrarMsg('err', 'La cantidad debe ser mayor a 0'); return }
    if (!costoUnit || parseFloat(costoUnit) <= 0) { mostrarMsg('err', 'El costo unitario debe ser mayor a 0'); return }
    setGuardando(true)
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          producto:       producto.trim(),
          cantidad:       parseFloat(cantidad),
          costo_unitario: parseFloat(costoUnit),
          proveedor:      proveedor.trim(),
          incluye_iva:    incluyeIva,
          tarifa_iva:     incluyeIva ? tarifaIva : 0,
          numero_factura: numFactura.trim(),
          notas_fiscales: notasFiscales.trim(),
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      const ivaMsg = incluyeIva ? ` · IVA ${tarifaIva}%: ${cop(ivaCalc)}` : ''
      mostrarMsg('ok', `Compra fiscal registrada: ${cantidad} ${producto.trim()} — Total: ${cop(totalBruto)}${ivaMsg}`)
      setProducto(''); setCantidad(''); setCostoUnit(''); setProveedor('')
      setIncluyeIva(false); setTarifaIva(19); setNumFactura(''); setNotasFiscales('')
      setFormOpen(false)
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setGuardando(false) }
  }

  const enviarACompras = async (compra) => {
    setEnviandoCompra(prev => ({ ...prev, [compra.id]: true }))
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal/${compra.id}/to-compras`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarMsg('ok', d.ya_existia
        ? 'Esta compra fiscal ya estaba vinculada a Almacén'
        : 'Compra enviada a Almacén (Compras normales)'
      )
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setEnviandoCompra(prev => ({ ...prev, [compra.id]: false })) }
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

  // KPI IVA descontable
  const totalIvaDescontable = compras
    .filter(c => c.incluye_iva && c.tarifa_iva > 0)
    .reduce((s, c) => s + calcIVA(c.costo_total, c.tarifa_iva).iva, 0)

  const conFactura   = compras.filter(c => c.numero_factura).length
  const sinFactura   = compras.length - conFactura
  const yaEnAlmacen  = compras.filter(c => !!c.compra_origen_id).length

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
        <ModalEditarFiscal
          compra={editando}
          onClose={() => setEditando(null)}
          onSaved={() => {
            setEditando(null)
            mostrarMsg('ok', 'Compra fiscal actualizada')
            setLocalRefresh(r => r + 1)
          }}
          authFetch={authFetch}
          t={t}
        />
      )}

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
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Compras Fiscales</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            Registro contable · fuente del Libro IVA · últimos {dias} días
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
            {formOpen ? '✕ Cerrar' : '➕ Nueva compra fiscal'}
          </button>
        </div>
      </div>

      {/* Aviso contextual */}
      <div style={{
        padding: '10px 14px', borderRadius: 8,
        background: `${t.blue}0d`, border: `1px solid ${t.blue}30`,
        fontSize: 11, color: t.textMuted, display: 'flex', alignItems: 'flex-start', gap: 8,
      }}>
        <span style={{ fontSize: 14, flexShrink: 0 }}>🧾</span>
        <span>
          Las compras fiscales son el <strong style={{ color: t.text }}>registro contable oficial</strong>.
          No actualizan el inventario ni el kárdex.
          Usa el botón <strong style={{ color: t.text }}>📦 → Almacén</strong> para enviar una compra también al módulo operativo.
        </span>
      </div>

      {/* Formulario nueva compra fiscal */}
      {formOpen && (
        <GlassCard>
          <SectionTitle>Registrar Compra Fiscal</SectionTitle>
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
                  placeholder="0" style={{ ...inpStyle, paddingLeft: 22 }}/>
              </div>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>Proveedor (opcional)</label>
              <input value={proveedor} onChange={e => setProveedor(e.target.value)}
                placeholder="Ej: Ferrisariato, Distribuidora Central..." style={inpStyle}/>
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>Número de Factura</label>
              <input value={numFactura} onChange={e => setNumFactura(e.target.value)}
                placeholder="Ej: FV-2024-001234 (requerido para facturación electrónica)"
                style={inpStyle}/>
            </div>

            {/* IVA */}
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

            {/* Notas fiscales */}
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lblStyle}>Notas Fiscales (opcional)</label>
              <textarea value={notasFiscales} onChange={e => setNotasFiscales(e.target.value)}
                placeholder="Observaciones para el Libro IVA..."
                style={{ ...inpStyle, resize: 'vertical', minHeight: 60 }}/>
            </div>
          </div>

          {/* Preview de cálculo */}
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
              ✅ El IVA descontable ({cop(ivaCalc)}) quedará registrado en el Libro IVA automáticamente
            </div>
          )}

          <button onClick={registrarCompraFiscal} disabled={guardando} style={{
            background: t.blue, border: 'none', borderRadius: 8,
            color: '#fff', padding: '10px 24px', fontSize: 12,
            fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            opacity: guardando ? 0.7 : 1,
          }}>
            {guardando ? 'Guardando…' : '🧾 Registrar compra fiscal'}
          </button>
        </GlassCard>
      )}

      {/* Estado vacío */}
      {sinDatos ? (
        <GlassCard>
          <div style={{ padding: '32px 24px', textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🧾</div>
            <div style={{ color: t.text, fontWeight: 600, marginBottom: 8 }}>Sin compras fiscales registradas</div>
            <div style={{ color: t.textMuted, fontSize: 12, maxWidth: 380, margin: '0 auto', lineHeight: 1.6 }}>
              Registra compras directamente aquí, o envía una compra del módulo de Almacén
              usando el botón <strong style={{ color: t.text }}>📊 → Fiscal</strong>.
            </div>
          </div>
        </GlassCard>
      ) : (
        <>
          {/* KPIs */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <KpiCard label="Total invertido"    value={cop(total)}           sub={`Últimos ${dias} días`} icon="💰" color={t.blue}/>
            <KpiCard label="IVA descontable"    value={cop(totalIvaDescontable)} sub="Crédito fiscal"    icon="🧮" color={t.green}/>
            <KpiCard label="Compras fiscales"   value={compras.length}       sub="Registros"             icon="🧾" color={t.textSub}/>
            <KpiCard label="Con factura"        value={conFactura}
              sub={sinFactura > 0 ? `${sinFactura} sin nro.` : 'Todas tienen nro.'}
              icon="📋" color={sinFactura > 0 ? t.accent : t.green}/>
            <KpiCard label="Enviadas a almacén" value={yaEnAlmacen}          sub={`de ${compras.length}`} icon="📦" color={t.textSub}/>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {/* Gráfico por proveedor */}
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

            {/* Productos más comprados */}
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

          {/* Tabla detalle */}
          <GlassCard style={{ padding: 0 }}>
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <SectionTitle>Detalle de Compras Fiscales</SectionTitle>
              {sinFactura > 0 && (
                <span style={{
                  fontSize: 10, background: `${t.accent}15`,
                  border: `1px solid ${t.accent}40`, color: t.accent,
                  borderRadius: 20, padding: '3px 10px', fontWeight: 600,
                }}>
                  ⚠ {sinFactura} sin nro. de factura
                </span>
              )}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: t.tableAlt }}>
                    {['Fecha','Producto','Cant.','Costo Unit.','Total','IVA','N° Factura','Proveedor','Acciones'].map((h, i) => (
                      <th key={i} style={{
                        padding: '9px 12px',
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
                    const { iva }      = c.incluye_iva && c.tarifa_iva ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                    const yaEnAlmacen  = !!c.compra_origen_id
                    const cargando     = !!enviandoCompra[c.id]
                    const tieneNroFact = !!c.numero_factura

                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${t.border}` }}
                        onMouseEnter={e => { e.currentTarget.style.background = t.cardHover }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>
                        <td style={{ padding: '8px 12px', color: t.textMuted, whiteSpace: 'nowrap' }}>
                          {String(c.fecha||'').slice(0,10)}
                        </td>
                        <td style={{ padding: '8px 12px', color: t.text }}>
                          <div>{c.producto||'—'}</div>
                          {c.notas_fiscales && (
                            <div style={{ fontSize: 10, color: t.textMuted, marginTop: 2 }}
                              title={c.notas_fiscales}>
                              📝 {c.notas_fiscales.length > 40 ? c.notas_fiscales.slice(0,40)+'…' : c.notas_fiscales}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: t.textSub }}>{num(c.cantidad)}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: t.textMuted }}>{cop(c.costo_unitario)}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: t.blue, fontWeight: 600 }}>{cop(c.costo_total)}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                          {c.incluye_iva && c.tarifa_iva > 0
                            ? <span style={{ color: t.green, fontWeight: 600, fontSize: 11 }}>
                                {cop(iva)}<span style={{ fontSize: 9, marginLeft: 4, color: t.textMuted }}>{c.tarifa_iva}%</span>
                              </span>
                            : <span style={{ color: t.textMuted, fontSize: 11 }}>—</span>
                          }
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          {tieneNroFact
                            ? <span style={{ fontSize: 11, color: t.textSub, fontFamily: 'monospace' }}>
                                {c.numero_factura}
                              </span>
                            : <span style={{ fontSize: 10, color: t.accent, opacity: 0.7 }}>sin nro.</span>
                          }
                        </td>
                        <td style={{ padding: '8px 12px', color: t.textMuted, fontSize: 11 }}>{c.proveedor||'—'}</td>
                        <td style={{ padding: '8px 12px', whiteSpace: 'nowrap' }}>
                          <div style={{ display: 'flex', gap: 5, justifyContent: 'flex-end' }}>
                            {/* Editar */}
                            <button
                              onClick={() => setEditando(c)}
                              title="Editar compra fiscal"
                              style={{
                                background: `${t.blue}15`, border: `1px solid ${t.blue}40`,
                                borderRadius: 6, color: t.blue, padding: '4px 10px',
                                fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600,
                              }}>
                              ✏️ Editar
                            </button>
                            {/* → Almacén */}
                            <button
                              onClick={() => !yaEnAlmacen && !cargando && enviarACompras(c)}
                              title={yaEnAlmacen ? 'Ya vinculada a una compra de Almacén' : 'Enviar a Almacén (Compras normales)'}
                              style={{
                                background: yaEnAlmacen ? `${t.green}15` : `${t.accent}15`,
                                border: `1px solid ${yaEnAlmacen ? t.green : t.accent}40`,
                                borderRadius: 6, color: yaEnAlmacen ? t.green : t.accent,
                                padding: '4px 10px', fontSize: 11,
                                cursor: yaEnAlmacen ? 'default' : 'pointer',
                                fontFamily: 'inherit', fontWeight: 600,
                                opacity: cargando ? 0.6 : 1,
                              }}>
                              {cargando ? '…' : yaEnAlmacen ? '✓ Almacén' : '📦 → Almacén'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                    <td colSpan={4} style={{ padding: '10px 12px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>TOTAL FISCAL</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: t.blue, fontWeight: 700, fontSize: 14 }}>{cop(total)}</td>
                    <td style={{ padding: '10px 12px', textAlign: 'right', color: t.green, fontWeight: 700, fontSize: 12 }}>
                      {cop(totalIvaDescontable)}
                    </td>
                    <td colSpan={3}/>
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
