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
  PeriodBtn, EmptyState, cop, num, API_BASE, useIsMobile,
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

// Agrupa compras por numero_factura. Ítems sin número o con número único quedan solos.
function agruparCompras(lista) {
  const map = new Map()
  lista.forEach(c => {
    const key = c.numero_factura ? c.numero_factura : `_solo_${c.id}`
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(c)
  })
  return Array.from(map.entries()).map(([key, items]) => ({
    key,
    isGroup: items.length >= 2 && !key.startsWith('_solo_'),
    items,
  }))
}

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

// ── Modal Editar Factura (grupo completo) ─────────────────────────────────────
function ModalEditarFactura({ factura, onClose, onSaved, authFetch, t }) {
  const isMobile = useIsMobile()
  // Campos globales (se aplican a todos los ítems al guardar)
  const [proveedor,     setProveedor]     = useState(
    factura.proveedor === 'Sin proveedor' ? '' : (factura.proveedor || '')
  )
  const [numeroFactura, setNumeroFactura] = useState(factura.numero_factura || '')
  const [notasFiscales, setNotasFiscales] = useState(factura.items[0]?.notas_fiscales || '')

  // Estado por fila: { id → { producto, cantidad, costoUnit, incluyeIva, tarifaIva } }
  const [filas, setFilas] = useState(() =>
    Object.fromEntries(factura.items.map(c => [c.id, {
      producto:  c.producto,
      cantidad:  String(c.cantidad),
      costoUnit: String(c.costo_unitario),
      incluyeIva: c.incluye_iva,
      tarifaIva:  c.tarifa_iva || 19,
    }]))
  )

  const [guardando,  setGuardando]  = useState(false)
  const [err,        setErr]        = useState(null)
  const [resumen,    setResumen]    = useState(null)

  const setFila = (id, campo, valor) =>
    setFilas(prev => ({ ...prev, [id]: { ...prev[id], [campo]: valor } }))

  const totalFila = (id) => {
    const f = filas[id]
    const q = parseFloat(f.cantidad)
    const p = parseFloat(f.costoUnit)
    return isNaN(q) || isNaN(p) ? 0 : q * p
  }

  const totalGeneral  = factura.items.reduce((s, c) => s + totalFila(c.id), 0)
  const totalIvaTotal = factura.items.reduce((s, c) => {
    const f = filas[c.id]
    if (!f.incluyeIva || !f.tarifaIva) return s
    return s + calcIVA(totalFila(c.id), f.tarifaIva).iva
  }, 0)

  const guardarTodos = async () => {
    // Validar antes de lanzar
    for (const c of factura.items) {
      const f = filas[c.id]
      if (!f.producto.trim())       { setErr(`Producto vacío en fila "${c.producto}"`); return }
      if (!(parseFloat(f.cantidad)  > 0)) { setErr(`Cantidad inválida en "${f.producto}"`); return }
      if (!(parseFloat(f.costoUnit) > 0)) { setErr(`Costo inválido en "${f.producto}"`);   return }
    }
    setGuardando(true); setErr(null); setResumen(null)

    const resultados = await Promise.allSettled(
      factura.items.map(c => {
        const f = filas[c.id]
        return authFetch(`${API_BASE}/compras-fiscal/${c.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            producto:       f.producto.trim(),
            cantidad:       parseFloat(f.cantidad),
            costo_unitario: parseFloat(f.costoUnit),
            proveedor:      proveedor.trim(),
            incluye_iva:    f.incluyeIva,
            tarifa_iva:     f.incluyeIva ? f.tarifaIva : 0,
            numero_factura: numeroFactura.trim(),
            notas_fiscales: notasFiscales.trim(),
          }),
        }).then(async r => {
          const d = await r.json()
          if (!r.ok) throw new Error(d.detail || 'Error')
          return d
        })
      })
    )

    setGuardando(false)
    const ok  = resultados.filter(r => r.status === 'fulfilled').length
    const ko  = resultados.filter(r => r.status === 'rejected')
    if (ko.length > 0) {
      setErr(`${ko.length} ítem(s) fallaron: ${ko.map(r => r.reason?.message).join(', ')}`)
    }
    if (ok > 0) {
      setResumen(`${ok} de ${factura.items.length} ítems guardados`)
      onSaved(`${ok} de ${factura.items.length} ítems de la factura actualizados`)
    }
  }

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
  const cellStyle = { padding: '0 4px', boxSizing: 'border-box' }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,.55)', display: 'flex',
      alignItems: 'flex-start', justifyContent: 'center',
      padding: '24px 16px', overflowY: 'auto',
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: t.card, border: `1px solid ${t.border}`,
        borderRadius: 14, padding: 24, width: '100%', maxWidth: 780,
        boxShadow: '0 20px 60px rgba(0,0,0,.4)',
      }}>
        {/* Cabecera */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
          <div>
            <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Editar Factura</span>
            <span style={{
              marginLeft: 10, fontSize: 13, color: t.blue, fontWeight: 700, fontFamily: 'monospace',
            }}>{factura.numero_factura}</span>
            <div style={{ fontSize: 10, color: t.textMuted, marginTop: 3 }}>
              Solo contabilidad · no modifica inventario · {factura.items.length} ítems
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: t.textMuted, fontSize: 18, cursor: 'pointer',
          }}>✕</button>
        </div>

        {err && (
          <div style={{
            padding: '8px 12px', borderRadius: 7, marginBottom: 12,
            background: `${t.accent}14`, border: `1px solid ${t.accent}44`,
            color: t.accent, fontSize: 12,
          }}>✕ {err}</div>
        )}

        {/* Campos globales */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10, marginBottom: 20 }}>
          <div>
            <label style={lblStyle}>Proveedor (aplica a todos)</label>
            <input value={proveedor} onChange={e => setProveedor(e.target.value)}
              placeholder="Ej: Ferrisariato" style={inpStyle}/>
          </div>
          <div>
            <label style={lblStyle}>Número de Factura</label>
            <input value={numeroFactura} onChange={e => setNumeroFactura(e.target.value)}
              placeholder="Ej: FV-2024-001234" style={inpStyle}/>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={lblStyle}>Notas Fiscales (aplica a todos)</label>
            <textarea value={notasFiscales} onChange={e => setNotasFiscales(e.target.value)}
              placeholder="Observaciones para el Libro IVA..."
              style={{ ...inpStyle, resize: 'vertical', minHeight: 52 }}/>
          </div>
        </div>

        {/* Tabla de ítems */}
        <div style={{
          border: `1px solid ${t.border}`, borderRadius: 10, overflow: 'hidden', marginBottom: 16,
          overflowX: 'auto',
        }}>
          {/* Cabecera tabla */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '2fr 80px 110px 160px 90px',
            minWidth: 480,
            background: t.tableAlt,
            padding: '8px 12px',
            fontSize: 10, color: t.textMuted,
            fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em',
            borderBottom: `1px solid ${t.border}`,
          }}>
            <span style={cellStyle}>Producto</span>
            <span style={cellStyle}>Cantidad</span>
            <span style={cellStyle}>Costo unit.</span>
            <span style={cellStyle}>IVA</span>
            <span style={{ ...cellStyle, textAlign: 'right' }}>Total</span>
          </div>

          {/* Filas */}
          {factura.items.map((c, ri) => {
            const f   = filas[c.id]
            const tot = totalFila(c.id)
            return (
              <div key={c.id} style={{
                display: 'grid',
                gridTemplateColumns: '2fr 80px 110px 160px 90px',
                minWidth: 480,
                padding: '10px 12px', alignItems: 'center',
                borderBottom: ri < factura.items.length - 1 ? `1px solid ${t.border}` : 'none',
                gap: 6,
              }}>
                {/* Producto */}
                <div style={cellStyle}>
                  <ProductoSearchInput
                    value={f.producto}
                    onChange={v => setFila(c.id, 'producto', v)}
                    style={{ ...inpStyle, fontSize: 11, padding: '5px 8px' }}
                    placeholder="Producto…"
                  />
                </div>

                {/* Cantidad */}
                <div style={cellStyle}>
                  <input
                    type="number" min="0" step="0.01"
                    value={f.cantidad}
                    onChange={e => setFila(c.id, 'cantidad', e.target.value)}
                    style={{ ...inpStyle, fontSize: 11, padding: '5px 8px' }}
                  />
                </div>

                {/* Costo unitario */}
                <div style={{ ...cellStyle, position: 'relative' }}>
                  <span style={{
                    position: 'absolute', left: 13, top: '50%',
                    transform: 'translateY(-50%)', color: t.textMuted, fontSize: 10,
                  }}>$</span>
                  <input
                    type="number" min="0"
                    value={f.costoUnit}
                    onChange={e => setFila(c.id, 'costoUnit', e.target.value)}
                    style={{ ...inpStyle, fontSize: 11, padding: '5px 8px', paddingLeft: 20 }}
                  />
                </div>

                {/* IVA */}
                <div style={{ ...cellStyle, display: 'flex', gap: 5, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button onClick={() => setFila(c.id, 'incluyeIva', !f.incluyeIva)} style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    background: f.incluyeIva ? `${t.green}18` : t.tableAlt,
                    border: `1px solid ${f.incluyeIva ? t.green : t.border}`,
                    borderRadius: 7, padding: '4px 8px', cursor: 'pointer',
                    fontFamily: 'inherit', fontSize: 10, fontWeight: 600,
                    color: f.incluyeIva ? t.green : t.textMuted,
                  }}>
                    <span style={{
                      width: 22, height: 13, borderRadius: 99,
                      background: f.incluyeIva ? t.green : t.border,
                      position: 'relative', flexShrink: 0,
                    }}>
                      <span style={{
                        position: 'absolute', top: 1.5,
                        left: f.incluyeIva ? 11 : 1.5, width: 10, height: 10,
                        borderRadius: '50%', background: '#fff', transition: 'left .15s',
                      }}/>
                    </span>
                    {f.incluyeIva ? 'IVA' : 'Sin'}
                  </button>
                  {f.incluyeIva && TARIFAS_IVA.map(tv => (
                    <button key={tv} onClick={() => setFila(c.id, 'tarifaIva', tv)} style={{
                      background: f.tarifaIva === tv ? t.accent : t.accentSub,
                      border: `1px solid ${f.tarifaIva === tv ? t.accent : t.border}`,
                      color: f.tarifaIva === tv ? '#fff' : t.textMuted,
                      borderRadius: 6, padding: '3px 8px', cursor: 'pointer',
                      fontFamily: 'inherit', fontSize: 10, fontWeight: 700,
                    }}>{tv}%</button>
                  ))}
                </div>

                {/* Total calculado */}
                <div style={{ ...cellStyle, textAlign: 'right' }}>
                  <span style={{ fontSize: 12, color: t.blue, fontWeight: 700 }}>{cop(tot)}</span>
                  {f.incluyeIva && f.tarifaIva > 0 && tot > 0 && (
                    <div style={{ fontSize: 10, color: t.green, marginTop: 2 }}>
                      IVA {cop(calcIVA(tot, f.tarifaIva).iva)}
                    </div>
                  )}
                </div>
              </div>
            )
          })}

          {/* Pie totales */}
          <div style={{
            display: 'flex', justifyContent: 'flex-end', gap: 24,
            padding: '10px 16px', background: t.tableAlt,
            borderTop: `1px solid ${t.border}`,
            fontSize: 12,
          }}>
            {totalIvaTotal > 0 && (
              <span style={{ color: t.green, fontWeight: 600 }}>
                IVA total: {cop(totalIvaTotal)}
              </span>
            )}
            <span style={{ color: t.blue, fontWeight: 700 }}>
              Total general: {cop(totalGeneral)}
            </span>
          </div>
        </div>

        {/* Botones */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            background: t.tableAlt, border: `1px solid ${t.border}`,
            borderRadius: 8, color: t.textMuted, padding: '9px 20px',
            fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
          }}>Cancelar</button>
          <button onClick={guardarTodos} disabled={guardando} style={{
            background: t.blue, border: 'none', borderRadius: 8,
            color: '#fff', padding: '9px 20px', fontSize: 12,
            fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            opacity: guardando ? 0.7 : 1,
          }}>{guardando ? 'Guardando…' : 'Guardar todos los cambios'}</button>
        </div>
      </div>
    </div>
  )
}

// ── Modal Enviar al Almacén (grupo completo, con revisión pre-envío) ──────────
function ModalEnviarAlmacen({ factura, onClose, onSaved, authFetch, t }) {
  // Estado por fila: { [id]: { producto, cantidad, costoUnit, checked } }
  const [filas, setFilas] = useState(() =>
    Object.fromEntries(factura.items.map(c => [c.id, {
      producto:  c.producto,
      cantidad:  String(c.cantidad),
      costoUnit: String(c.costo_unitario),
      checked:   !c.compra_origen_id,   // ítems ya en almacén → pre-desmarcados
    }]))
  )
  const [enviando, setEnviando] = useState(false)
  const [err,      setErr]      = useState(null)

  const setFila = (id, campo, valor) =>
    setFilas(prev => ({ ...prev, [id]: { ...prev[id], [campo]: valor } }))

  // Ítems seleccionados (checkeados y aún no en almacén)
  const seleccionados = factura.items.filter(c => filas[c.id].checked && !c.compra_origen_id)
  const totalSel = seleccionados.reduce((s, c) => {
    const f = filas[c.id]
    return s + (parseFloat(f.cantidad) || 0) * (parseFloat(f.costoUnit) || 0)
  }, 0)

  const confirmar = async () => {
    if (seleccionados.length === 0) return
    setEnviando(true); setErr(null)
    try {
      const r = await authFetch(`${API_BASE}/compras-fiscal/bulk-to-compras`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: seleccionados.map(c => {
            const f = filas[c.id]
            return {
              id:             c.id,
              producto:       f.producto.trim(),
              cantidad:       parseFloat(f.cantidad),
              costo_unitario: parseFloat(f.costoUnit),
            }
          }),
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')

      let msg = `${d.procesados} ítem(s) enviados al Almacén`
      if (d.ya_existian > 0)     msg += ` · ${d.ya_existian} ya existían`
      if (d.errores?.length > 0) msg += ` · ${d.errores.length} error(es)`
      onSaved(msg)
    } catch (e) {
      setErr(e.message)
    } finally {
      setEnviando(false)
    }
  }

  const inpStyle = {
    width: '100%', boxSizing: 'border-box',
    background: t.id === 'caramelo' ? '#f8fafc' : '#111',
    border: `1px solid ${t.border}`, borderRadius: 7,
    color: t.text, fontSize: 11, padding: '5px 8px',
    outline: 'none', fontFamily: 'inherit',
  }
  const cellStyle = { padding: '0 4px', boxSizing: 'border-box' }
  const COLS = '28px 2fr 80px 100px 80px 90px'

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,.55)', display: 'flex',
      alignItems: 'flex-start', justifyContent: 'center',
      padding: '24px 16px', overflowY: 'auto',
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{
        background: t.card, border: `1px solid ${t.border}`,
        borderRadius: 14, padding: 24, width: '100%', maxWidth: 760,
        boxShadow: '0 20px 60px rgba(0,0,0,.4)',
      }}>
        {/* Cabecera */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <span style={{ fontSize: 14, fontWeight: 700, color: t.text }}>Enviar a Almacén</span>
            <span style={{ marginLeft: 10, fontSize: 13, color: t.blue, fontWeight: 700, fontFamily: 'monospace' }}>
              {factura.numero_factura}
            </span>
            <div style={{ fontSize: 10, color: t.textMuted, marginTop: 3 }}>
              Revisa y ajusta antes de confirmar
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: t.textMuted, fontSize: 18, cursor: 'pointer',
          }}>✕</button>
        </div>

        {/* Aviso informativo */}
        <div style={{
          padding: '10px 14px', borderRadius: 8, marginBottom: 16,
          background: `${t.blue}0d`, border: `1px solid ${t.blue}30`,
          fontSize: 11, color: t.textMuted, display: 'flex', gap: 8,
        }}>
          <span style={{ fontSize: 14, flexShrink: 0 }}>📦</span>
          <span>
            Esta acción creará registros en <strong style={{ color: t.text }}>Compras (inventario)</strong>.
            Los nombres y cantidades son editables antes de confirmar.
          </span>
        </div>

        {err && (
          <div style={{
            padding: '8px 12px', borderRadius: 7, marginBottom: 12,
            background: `${t.accent}14`, border: `1px solid ${t.accent}44`,
            color: t.accent, fontSize: 12,
          }}>✕ {err}</div>
        )}

        {/* Tabla */}
        <div style={{ border: `1px solid ${t.border}`, borderRadius: 10, overflow: 'hidden', marginBottom: 14, overflowX: 'auto' }}>
          {/* Cabecera tabla */}
          <div style={{
            display: 'grid', gridTemplateColumns: COLS,
            minWidth: 460,
            background: t.tableAlt, padding: '7px 12px',
            fontSize: 10, color: t.textMuted,
            fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em',
            borderBottom: `1px solid ${t.border}`,
            alignItems: 'center', gap: 6,
          }}>
            <span style={cellStyle}/>
            <span style={cellStyle}>Producto</span>
            <span style={cellStyle}>Cant.</span>
            <span style={cellStyle}>Costo unit.</span>
            <span style={{ ...cellStyle, textAlign: 'right' }}>Total</span>
            <span style={cellStyle}>Estado</span>
          </div>

          {/* Filas */}
          {factura.items.map((c, ri) => {
            const f       = filas[c.id]
            const yaEnAlm = !!c.compra_origen_id
            const tot     = (parseFloat(f.cantidad) || 0) * (parseFloat(f.costoUnit) || 0)
            return (
              <div key={c.id} style={{
                display: 'grid', gridTemplateColumns: COLS,
                minWidth: 460,
                padding: '9px 12px', alignItems: 'center', gap: 6,
                borderBottom: ri < factura.items.length - 1 ? `1px solid ${t.border}` : 'none',
                opacity: yaEnAlm ? 0.5 : 1,
              }}>
                {/* Checkbox */}
                <div style={{ ...cellStyle, display: 'flex', justifyContent: 'center' }}>
                  <input
                    type="checkbox"
                    checked={f.checked}
                    disabled={yaEnAlm}
                    onChange={e => setFila(c.id, 'checked', e.target.checked)}
                    style={{ width: 15, height: 15, cursor: yaEnAlm ? 'default' : 'pointer', accentColor: t.blue }}
                  />
                </div>

                {/* Producto */}
                <div style={cellStyle}>
                  <ProductoSearchInput
                    value={f.producto}
                    onChange={v => setFila(c.id, 'producto', v)}
                    style={{ ...inpStyle, opacity: yaEnAlm ? 0.5 : 1 }}
                    placeholder="Producto…"
                  />
                </div>

                {/* Cantidad */}
                <div style={cellStyle}>
                  <input
                    type="number" min="0" step="0.01"
                    value={f.cantidad}
                    disabled={yaEnAlm}
                    onChange={e => setFila(c.id, 'cantidad', e.target.value)}
                    style={inpStyle}
                  />
                </div>

                {/* Costo unitario */}
                <div style={{ ...cellStyle, position: 'relative' }}>
                  <span style={{
                    position: 'absolute', left: 13, top: '50%',
                    transform: 'translateY(-50%)', color: t.textMuted, fontSize: 10,
                  }}>$</span>
                  <input
                    type="number" min="0"
                    value={f.costoUnit}
                    disabled={yaEnAlm}
                    onChange={e => setFila(c.id, 'costoUnit', e.target.value)}
                    style={{ ...inpStyle, paddingLeft: 18 }}
                  />
                </div>

                {/* Total */}
                <div style={{ ...cellStyle, textAlign: 'right' }}>
                  <span style={{ fontSize: 12, color: t.blue, fontWeight: 700 }}>{cop(tot)}</span>
                </div>

                {/* Estado */}
                <div style={cellStyle}>
                  {yaEnAlm ? (
                    <span style={{
                      fontSize: 10, color: t.textMuted, fontWeight: 600,
                      background: t.tableAlt, borderRadius: 5,
                      padding: '2px 8px', border: `1px solid ${t.border}`,
                    }}>Ya en almacén</span>
                  ) : (
                    <span style={{
                      fontSize: 10,
                      color: f.checked ? t.green : t.textMuted,
                      fontWeight: 600,
                    }}>{f.checked ? '✓ Incluido' : '—'}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Resumen */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '10px 14px', borderRadius: 8,
          background: t.tableAlt, border: `1px solid ${t.border}`,
          fontSize: 12, marginBottom: 16,
        }}>
          <span style={{ color: t.textMuted }}>
            <strong style={{ color: t.text }}>{seleccionados.length}</strong> ítem(s) seleccionados
          </span>
          <span style={{ color: t.blue, fontWeight: 700 }}>Total: {cop(totalSel)}</span>
        </div>

        {/* Botones */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            background: t.tableAlt, border: `1px solid ${t.border}`,
            borderRadius: 8, color: t.textMuted, padding: '9px 20px',
            fontSize: 12, cursor: 'pointer', fontFamily: 'inherit',
          }}>Cancelar</button>
          <button
            onClick={confirmar}
            disabled={enviando || seleccionados.length === 0}
            style={{
              background: seleccionados.length === 0 ? t.tableAlt : t.accent,
              border: `1px solid ${seleccionados.length === 0 ? t.border : t.accent}`,
              borderRadius: 8, color: seleccionados.length === 0 ? t.textMuted : '#fff',
              padding: '9px 20px', fontSize: 12, fontWeight: 700,
              cursor: seleccionados.length === 0 ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit', opacity: enviando ? 0.7 : 1,
            }}>
            {enviando ? 'Enviando…' : `📦 Enviar ${seleccionados.length} ítem(s) al Almacén`}
          </button>
        </div>
      </div>
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
  const isMobile = useIsMobile()
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
  const [incluyeIva,    setIncluyeIva]    = useState(true)
  const [tarifaIva,     setTarifaIva]     = useState(19)
  const [numFactura,    setNumFactura]     = useState('')
  const [notasFiscales, setNotasFiscales] = useState('')
  const [guardando,     setGuardando]     = useState(false)
  const [msg,           setMsg]           = useState(null)

  // Editar ítem suelto (ModalEditarFiscal)
  const [editando, setEditando] = useState(null)

  // Editar factura agrupada completa (ModalEditarFactura)
  const [editandoFactura, setEditandoFactura] = useState(null)

  // Enviando a compras normales por id
  const [enviandoCompra, setEnviandoCompra] = useState({})

  // Estado de expansión de acordeones (key = numero_factura)
  const [expandedGroups, setExpandedGroups] = useState({})

  // Modal enviar factura agrupada → almacén
  const [modalEnviarAlmacen, setModalEnviarAlmacen] = useState(null)

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
  const agrupados = agruparCompras(compras)

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

      {/* Modal editar ítem individual */}
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

      {/* Modal editar factura completa (grupo) */}
      {editandoFactura && (
        <ModalEditarFactura
          factura={editandoFactura}
          onClose={() => setEditandoFactura(null)}
          onSaved={(resumenMsg) => {
            setEditandoFactura(null)
            mostrarMsg('ok', resumenMsg)
            setLocalRefresh(r => r + 1)
          }}
          authFetch={authFetch}
          t={t}
        />
      )}

      {/* Modal enviar factura al almacén */}
      {modalEnviarAlmacen && (
        <ModalEnviarAlmacen
          factura={modalEnviarAlmacen}
          onClose={() => setModalEnviarAlmacen(null)}
          onSaved={(resumenMsg) => {
            setModalEnviarAlmacen(null)
            mostrarMsg('ok', resumenMsg)
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
              <SectionTitle>Detalle de Compras Fiscales</SectionTitle>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {sinFactura > 0 && (
                  <span style={{
                    fontSize: 10, background: `${t.accent}15`,
                    border: `1px solid ${t.accent}40`, color: t.accent,
                    borderRadius: 20, padding: '3px 10px', fontWeight: 600,
                  }}>⚠ {sinFactura} sin nro.</span>
                )}
                <span style={{ fontSize: 11, color: t.textMuted }}>
                  {agrupados.length} entradas · {compras.length} ítems
                </span>
              </div>
            </div>

            {/* Totales compactos arriba */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 18px', background: t.tableAlt,
              borderBottom: `1px solid ${t.border}`,
            }}>
              <span style={{ fontSize: 11, color: t.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em' }}>Total Fiscal</span>
              <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: t.blue, fontWeight: 700 }}>{cop(total)}</span>
                {totalIvaDescontable > 0 && (
                  <span style={{ fontSize: 11, color: t.green, fontWeight: 600 }}>IVA {cop(totalIvaDescontable)}</span>
                )}
              </div>
            </div>

            {/* Cards */}
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {agrupados.map((grupo, gi) => {
                const isLast = gi === agrupados.length - 1

                // ── Grupo / acordeón ──────────────────────────────
                if (grupo.isGroup) {
                  const expanded       = !!expandedGroups[grupo.key]
                  const items          = grupo.items
                  const totalGrupo     = items.reduce((s, x) => s + (x.costo_total || 0), 0)
                  const tieneIva       = items.some(x => x.incluye_iva && x.tarifa_iva > 0)
                  const enAlmacenCount = items.filter(x => !!x.compra_origen_id).length
                  const todosEnAlmacen = enAlmacenCount === items.length
                  const primerItem     = items[0]
                  const toggleExpanded = () =>
                    setExpandedGroups(prev => ({ ...prev, [grupo.key]: !prev[grupo.key] }))

                  return (
                    <div key={grupo.key} style={{ borderBottom: !isLast ? `1px solid ${t.border}` : 'none' }}>
                      {/* Header del acordeón */}
                      <div
                        style={{
                          padding: '12px 18px', cursor: 'pointer', userSelect: 'none',
                          display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                        }}
                        onClick={toggleExpanded}
                      >
                        {/* Flecha toggle */}
                        <span style={{
                          fontSize: 10, color: t.textMuted, flexShrink: 0,
                          display: 'inline-block',
                          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                          transition: 'transform .15s',
                        }}>▶</span>

                        {/* Info principal */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 3 }}>
                            <span style={{ fontSize: 13, fontWeight: 700, color: t.text, fontFamily: 'monospace' }}>
                              {grupo.key}
                            </span>
                            <span style={{ fontSize: 11, color: t.textMuted, fontStyle: 'italic' }}>
                              {primerItem.proveedor || 'Sin proveedor'}
                            </span>
                            <span style={{
                              fontSize: 10, color: t.textMuted,
                              background: t.tableAlt, borderRadius: 5,
                              padding: '2px 8px', border: `1px solid ${t.border}`,
                            }}>{items.length} ítems</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 13, color: t.blue, fontWeight: 700 }}>{cop(totalGrupo)}</span>
                            {tieneIva && (
                              <span style={{
                                fontSize: 10, color: t.green, fontWeight: 600,
                                background: `${t.green}12`, borderRadius: 5,
                                padding: '2px 8px', border: `1px solid ${t.green}30`,
                              }}>IVA</span>
                            )}
                            {todosEnAlmacen ? (
                              <span style={{
                                fontSize: 10, color: t.green, fontWeight: 600,
                                background: `${t.green}12`, borderRadius: 5,
                                padding: '2px 8px', border: `1px solid ${t.green}30`,
                              }}>✓ En Almacén</span>
                            ) : enAlmacenCount > 0 ? (
                              <span style={{
                                fontSize: 10, color: t.accent, fontWeight: 600,
                                background: `${t.accent}12`, borderRadius: 5,
                                padding: '2px 8px', border: `1px solid ${t.accent}30`,
                              }}>{enAlmacenCount} de {items.length} en almacén</span>
                            ) : null}
                          </div>
                        </div>

                        {/* Botones del header (detienen la propagación del toggle) */}
                        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}
                          onClick={e => e.stopPropagation()}>
                          <button
                            onClick={() => setEditandoFactura({
                              numero_factura: grupo.key,
                              proveedor: primerItem.proveedor,
                              items,
                            })}
                            title="Editar factura"
                            style={{
                              background: `${t.blue}14`, border: `1px solid ${t.blue}40`,
                              borderRadius: 7, color: t.blue,
                              padding: isMobile ? '6px 10px' : '6px 12px',
                              fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600,
                            }}>{isMobile ? '✏️' : '✏️ Editar factura'}</button>
                          {todosEnAlmacen ? (
                            <button disabled title="Todo en almacén" style={{
                              background: `${t.green}14`, border: `1px solid ${t.green}40`,
                              borderRadius: 7, color: t.green,
                              padding: isMobile ? '6px 10px' : '6px 12px',
                              fontSize: 11, cursor: 'default', fontFamily: 'inherit',
                              fontWeight: 600,
                            }}>{isMobile ? '✓' : '✓ Todo en Almacén'}</button>
                          ) : (
                            <button
                              onClick={() => setModalEnviarAlmacen({
                                numero_factura: grupo.key,
                                proveedor:      primerItem.proveedor,
                                items,
                              })}
                              title={enAlmacenCount > 0 ? '→ Almacén (parcial)' : '→ Almacén'}
                              style={{
                                background: `${t.accent}14`, border: `1px solid ${t.accent}40`,
                                borderRadius: 7, color: t.accent,
                                padding: isMobile ? '6px 10px' : '6px 12px',
                                fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                                fontWeight: 600,
                              }}>
                              {isMobile ? '📦' : (enAlmacenCount > 0 ? '📦 → Almacén (parcial)' : '📦 → Almacén')}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Cuerpo expandible */}
                      {expanded && (
                        <div style={{ borderTop: `1px solid ${t.border}` }}>
                          {isMobile ? (
                            /* ── Móvil: cards apiladas ── */
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                              {items.map(c => {
                                const { iva } = c.incluye_iva && c.tarifa_iva
                                  ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                                const enAlmacenFila = !!c.compra_origen_id
                                return (
                                  <div key={c.id} style={{
                                    padding: '10px 16px',
                                    borderTop: `1px solid ${t.border}30`,
                                    display: 'flex', flexDirection: 'column', gap: 5,
                                  }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                                      <span style={{ fontSize: 13, fontWeight: 600, color: t.text, flex: 1, lineHeight: 1.35 }}>
                                        {c.producto}
                                      </span>
                                      <button
                                        onClick={() => setEditando(c)}
                                        title="Editar ítem"
                                        style={{
                                          background: `${t.blue}14`, border: `1px solid ${t.blue}40`,
                                          borderRadius: 6, color: t.blue, padding: '4px 8px',
                                          fontSize: 13, cursor: 'pointer', fontFamily: 'inherit',
                                          fontWeight: 600, flexShrink: 0,
                                        }}>✏️</button>
                                    </div>
                                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                                      <span style={{
                                        fontSize: 11, color: t.textMuted, background: t.tableAlt,
                                        borderRadius: 5, padding: '2px 8px', border: `1px solid ${t.border}`,
                                      }}>{num(c.cantidad)} × {cop(c.costo_unitario)}</span>
                                      <span style={{ fontSize: 12, color: t.blue, fontWeight: 700 }}>{cop(c.costo_total)}</span>
                                      {c.incluye_iva && c.tarifa_iva > 0 && (
                                        <span style={{
                                          fontSize: 11, color: t.green, fontWeight: 600,
                                          background: `${t.green}12`, borderRadius: 5,
                                          padding: '2px 8px', border: `1px solid ${t.green}30`,
                                        }}>IVA {cop(iva)} ({c.tarifa_iva}%)</span>
                                      )}
                                      {enAlmacenFila && (
                                        <span style={{
                                          fontSize: 11, color: t.green, fontWeight: 600,
                                          background: `${t.green}12`, borderRadius: 5,
                                          padding: '2px 8px', border: `1px solid ${t.green}30`,
                                        }}>✓ Almacén</span>
                                      )}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          ) : (
                            /* ── Desktop: tabla grid ── */
                            <>
                              <div style={{
                                display: 'grid',
                                gridTemplateColumns: '2fr 70px 90px 90px 60px 60px 36px',
                                gap: 4, padding: '6px 18px',
                                background: t.tableAlt,
                                fontSize: 10, color: t.textMuted,
                                fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em',
                                alignItems: 'center',
                              }}>
                                <span>Producto</span>
                                <span>Cant.</span>
                                <span>Costo unit.</span>
                                <span>Total</span>
                                <span>IVA</span>
                                <span>Almacén</span>
                                <span/>
                              </div>
                              {items.map(c => {
                                const { iva } = c.incluye_iva && c.tarifa_iva
                                  ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                                const enAlmacenFila = !!c.compra_origen_id
                                return (
                                  <div key={c.id} style={{
                                    display: 'grid',
                                    gridTemplateColumns: '2fr 70px 90px 90px 60px 60px 36px',
                                    gap: 4, padding: '8px 18px',
                                    alignItems: 'center',
                                    borderTop: `1px solid ${t.border}30`,
                                    fontSize: 12,
                                  }}>
                                    <span style={{
                                      color: t.text, fontWeight: 500,
                                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                    }}>{c.producto}</span>
                                    <span style={{ color: t.textSub }}>{num(c.cantidad)}</span>
                                    <span style={{ color: t.textMuted }}>{cop(c.costo_unitario)}</span>
                                    <span style={{ color: t.blue, fontWeight: 700 }}>{cop(c.costo_total)}</span>
                                    <span style={{ color: c.incluye_iva && c.tarifa_iva ? t.green : t.textMuted }}>
                                      {c.incluye_iva && c.tarifa_iva ? `${c.tarifa_iva}%` : '—'}
                                    </span>
                                    <span style={{ color: enAlmacenFila ? t.green : t.textMuted }}>
                                      {enAlmacenFila ? '✓' : '—'}
                                    </span>
                                    <button
                                      onClick={() => setEditando(c)}
                                      style={{
                                        background: `${t.blue}14`, border: `1px solid ${t.blue}40`,
                                        borderRadius: 6, color: t.blue, padding: '4px 6px',
                                        fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                                        fontWeight: 600, textAlign: 'center',
                                      }}>✏️</button>
                                  </div>
                                )
                              })}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  )
                }

                // ── Individual (comportamiento existente sin cambios) ──
                const c            = grupo.items[0]
                const { iva }      = c.incluye_iva && c.tarifa_iva ? calcIVA(c.costo_total, c.tarifa_iva) : { iva: 0 }
                const enAlmacenItem = !!c.compra_origen_id
                const cargando     = !!enviandoCompra[c.id]
                const tieneNroFact = !!c.numero_factura

                return (
                  <div key={c.id} style={{
                    padding: '12px 18px',
                    borderBottom: !isLast ? `1px solid ${t.border}` : 'none',
                  }}>
                    {/* Fila 1: fecha + proveedor */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                      <span style={{ fontSize: 11, color: t.textMuted }}>{String(c.fecha||'').slice(0,10)}</span>
                      <span style={{ fontSize: 11, color: t.textMuted, fontStyle: 'italic' }}>{c.proveedor||'Sin proveedor'}</span>
                    </div>

                    {/* Fila 2: producto */}
                    <div style={{ fontSize: 13, fontWeight: 600, color: t.text, marginBottom: 4, lineHeight: 1.35 }}>
                      {c.producto||'—'}
                    </div>

                    {/* Nota fiscal */}
                    {c.notas_fiscales && (
                      <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 6 }}>
                        📝 {c.notas_fiscales.length > 60 ? c.notas_fiscales.slice(0,60)+'…' : c.notas_fiscales}
                      </div>
                    )}

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
                      {tieneNroFact
                        ? <span style={{ fontSize: 10, color: t.textMuted, fontFamily: 'monospace', background: t.tableAlt, borderRadius: 5, padding: '2px 8px', border: `1px solid ${t.border}` }}>
                            {c.numero_factura}
                          </span>
                        : <span style={{ fontSize: 10, color: t.accent, background: `${t.accent}12`, borderRadius: 5, padding: '2px 8px' }}>sin nro.</span>
                      }
                    </div>

                    {/* Acciones */}
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => setEditando(c)}
                        title="Editar"
                        style={{
                          flex: isMobile ? 0 : 1,
                          background: `${t.blue}14`, border: `1px solid ${t.blue}40`,
                          borderRadius: 7, color: t.blue,
                          padding: isMobile ? '7px 14px' : '7px 0',
                          fontSize: 12, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600,
                        }}>{isMobile ? '✏️' : '✏️ Editar'}</button>
                      <button
                        onClick={() => !enAlmacenItem && !cargando && enviarACompras(c)}
                        title={enAlmacenItem ? 'En Almacén' : '→ Almacén'}
                        style={{
                          flex: 1,
                          background: enAlmacenItem ? `${t.green}14` : `${t.accent}14`,
                          border: `1px solid ${enAlmacenItem ? t.green : t.accent}40`,
                          borderRadius: 7, color: enAlmacenItem ? t.green : t.accent,
                          padding: '7px 0', fontSize: 12,
                          cursor: enAlmacenItem ? 'default' : 'pointer',
                          fontFamily: 'inherit', fontWeight: 600,
                          opacity: cargando ? 0.6 : 1,
                        }}>
                        {cargando ? '…' : isMobile
                          ? (enAlmacenItem ? '✓ Almacén' : '📦 → Almacén')
                          : (enAlmacenItem ? '✓ En Almacén' : '📦 → Almacén')}
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
