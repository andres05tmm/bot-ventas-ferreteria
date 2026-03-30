/**
 * TabProveedores.jsx
 * Gestión de cuentas por pagar, facturas y abonos a proveedores.
 */
import { useState, useCallback, useRef } from 'react'
import {
  useTheme, useFetch, Card, GlassCard, SectionTitle, KpiCard,
  Spinner, ErrorMsg, cop, useIsMobile, API_BASE, StyledInput,
} from '../components/shared.jsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function estadoColor(estado, t) {
  if (estado === 'pagada')   return { bg: '#16a34a18', border: '#16a34a44', text: '#16a34a' }
  if (estado === 'parcial')  return { bg: '#f59e0b18', border: '#f59e0b44', text: '#f59e0b' }
  return                            { bg: `${t.accent}14`, border: `${t.accent}44`, text: t.accent }
}

function estadoLabel(estado) {
  if (estado === 'pagada')  return 'PAGADA'
  if (estado === 'parcial') return 'PARCIAL'
  return 'PENDIENTE'
}

function diasDesde(fecha) {
  if (!fecha) return null
  const diff = Math.floor((Date.now() - new Date(fecha)) / 86400000)
  return diff
}

function semaforo(dias) {
  if (dias === null) return null
  if (dias <= 7)  return '🟢'
  if (dias <= 30) return '🟡'
  return '🔴'
}

// ── Sub-componentes ───────────────────────────────────────────────────────────

function BarraDeuda({ pagado, total, t }) {
  const pct = total > 0 ? Math.min((pagado / total) * 100, 100) : 0
  return (
    <div style={{
      width: '100%', height: 6, borderRadius: 99,
      background: t.borderSoft, overflow: 'hidden',
    }}>
      <div style={{
        width: `${pct}%`, height: '100%',
        background: pct >= 100 ? '#16a34a' : pct > 50 ? '#f59e0b' : t.accent,
        borderRadius: 99, transition: 'width .4s',
      }} />
    </div>
  )
}

function FacturaCard({ fac, t, mobile, onAbonar }) {
  const [open, setOpen] = useState(false)
  const ec = estadoColor(fac.estado, t)
  const dias = diasDesde(fac.fecha)

  return (
    <div style={{
      border: `1px solid ${t.border}`,
      borderRadius: 12, overflow: 'hidden',
      marginBottom: 10,
      transition: 'box-shadow .2s',
    }}
      onMouseEnter={e => e.currentTarget.style.boxShadow = `0 2px 12px ${t.accent}18`}
      onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
    >
      {/* Cabecera */}
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: mobile ? '12px' : '14px 16px',
          background: t.card, cursor: 'pointer',
        }}
      >
        {/* Semáforo + ID */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, minWidth: 44 }}>
          <span style={{ fontSize: 14 }}>{semaforo(dias)}</span>
          <span style={{ fontSize: 10, color: t.textMuted, fontWeight: 700, letterSpacing: '.03em' }}>
            {fac.id}
          </span>
        </div>

        {/* Info principal */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontWeight: 600, fontSize: mobile ? 13 : 14,
            color: t.text, whiteSpace: 'nowrap',
            overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {fac.proveedor}
          </div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>
            {fac.descripcion} · {fac.fecha}
          </div>
          <BarraDeuda pagado={fac.pagado} total={fac.total} t={t} />
        </div>

        {/* Monto + estado */}
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: t.text }}>{cop(fac.total)}</div>
          <div style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '.04em',
            padding: '2px 7px', borderRadius: 99, marginTop: 4,
            background: ec.bg, border: `1px solid ${ec.border}`, color: ec.text,
            display: 'inline-block',
          }}>
            {estadoLabel(fac.estado)}
          </div>
        </div>

        {/* Chevron */}
        <span style={{
          fontSize: 12, color: t.textMuted, marginLeft: 4,
          transform: open ? 'rotate(180deg)' : 'rotate(0)',
          transition: 'transform .2s',
        }}>▾</span>
      </div>

      {/* Detalle expandido */}
      {open && (
        <div style={{
          background: t.bg, borderTop: `1px solid ${t.borderSoft}`,
          padding: mobile ? '12px' : '14px 16px',
        }}>
          {/* KPIs de la factura */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 12 }}>
            {[
              { label: 'Total factura', value: cop(fac.total),     color: t.text     },
              { label: 'Pagado',        value: cop(fac.pagado),    color: '#16a34a'  },
              { label: 'Pendiente',     value: cop(fac.pendiente), color: t.accent   },
            ].map(({ label, value, color }) => (
              <div key={label} style={{
                background: t.card, border: `1px solid ${t.borderSoft}`,
                borderRadius: 8, padding: '8px 10px', textAlign: 'center',
              }}>
                <div style={{ fontSize: 10, color: t.textMuted, marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: 13, fontWeight: 700, color }}>{value}</div>
              </div>
            ))}
          </div>

          {/* Historial de abonos */}
          {fac.abonos?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: t.textMuted, marginBottom: 6 }}>
                ABONOS
              </div>
              {fac.abonos.map((ab, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '6px 0', borderBottom: `1px solid ${t.borderSoft}`,
                  fontSize: 12,
                }}>
                  <span style={{ color: t.textMuted }}>{ab.fecha}</span>
                  <span style={{ color: '#16a34a', fontWeight: 600 }}>+{cop(ab.monto)}</span>
                  {ab.foto_url && (
                    <a
                      href={ab.foto_url} target="_blank" rel="noreferrer"
                      style={{ color: t.accent, fontSize: 11, textDecoration: 'none' }}
                    >
                      📎 comprobante
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Foto de factura */}
          {fac.foto_url && (
            <a
              href={fac.foto_url} target="_blank" rel="noreferrer"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                fontSize: 11, color: t.accent, textDecoration: 'none',
                padding: '5px 10px', borderRadius: 6,
                border: `1px solid ${t.accent}44`,
                background: `${t.accent}0a`,
                marginBottom: 10,
              }}
            >
              📄 Ver factura original
            </a>
          )}

          {/* Botón abonar */}
          {fac.estado !== 'pagada' && (
            <button
              onClick={() => onAbonar(fac)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '7px 14px', borderRadius: 8,
                fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                cursor: 'pointer', border: 'none',
                background: t.accent, color: '#fff',
                transition: 'opacity .15s',
              }}
              onMouseEnter={e => e.currentTarget.style.opacity = '.85'}
              onMouseLeave={e => e.currentTarget.style.opacity = '1'}
            >
              💸 Registrar abono
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function SelectorFoto({ t, label, onChange, preview, onClear }) {
  const ref = useRef(null)
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={labelStyle(t)}>{label}</label>
      {preview ? (
        <div style={{ position: 'relative', display: 'inline-block' }}>
          <img src={preview} alt="preview"
            style={{ width: '100%', maxHeight: 140, objectFit: 'cover',
                     borderRadius: 8, border: `1px solid ${t.border}` }} />
          <button onClick={onClear} style={{
            position: 'absolute', top: 4, right: 4,
            background: '#000a', color: '#fff', border: 'none',
            borderRadius: '50%', width: 22, height: 22, cursor: 'pointer',
            fontSize: 12, lineHeight: 1,
          }}>✕</button>
        </div>
      ) : (
        <div
          onClick={() => ref.current?.click()}
          style={{
            border: `2px dashed ${t.border}`, borderRadius: 8,
            padding: '16px 12px', textAlign: 'center', cursor: 'pointer',
            color: t.textMuted, fontSize: 12,
            transition: 'border-color .15s, background .15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = t.accent; e.currentTarget.style.background = `${t.accent}08` }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.background = 'transparent' }}
        >
          📷 Toca para adjuntar foto o PDF
          <div style={{ fontSize: 10, marginTop: 4, color: t.textMuted }}>
            JPG · PNG · PDF — máx 10 MB
          </div>
        </div>
      )}
      <input ref={ref} type="file" accept="image/*,application/pdf"
        style={{ display: 'none' }} onChange={onChange} />
    </div>
  )
}

function ModalNuevaFactura({ onClose, onCreada, t }) {
  const [form, setForm] = useState({ proveedor: '', total: '', descripcion: '', fecha: '' })
  const [foto, setFoto]         = useState(null)   // File object
  const [preview, setPreview]   = useState(null)   // URL.createObjectURL
  const [paso, setPaso]         = useState(1)       // 1=datos, 2=foto+confirmación
  const [estado, setEstado]     = useState('idle')  // idle|saving|uploading|ok|err
  const [facCreada, setFacCreada] = useState(null)
  const [err, setErr]           = useState('')
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const seleccionarFoto = e => {
    const file = e.target.files[0]
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { setErr('La foto no puede superar 10 MB'); return }
    setFoto(file)
    if (file.type.startsWith('image/'))
      setPreview(URL.createObjectURL(file))
    else
      setPreview(null)  // PDF: sin preview visual
    setErr('')
  }

  const limpiarFoto = () => { setFoto(null); setPreview(null) }

  // Paso 1: guardar datos de la factura
  const guardarDatos = async () => {
    if (!form.proveedor.trim()) { setErr('El proveedor es obligatorio'); return }
    if (!form.total || isNaN(Number(form.total))) { setErr('El total debe ser un número'); return }
    setErr(''); setEstado('saving')
    try {
      const r = await fetch(`${API_BASE}/proveedores/facturas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          proveedor:   form.proveedor.trim(),
          total:       Number(form.total),
          descripcion: form.descripcion.trim() || 'Sin descripción',
          fecha:       form.fecha || undefined,
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setFacCreada(d.factura)
      setEstado('idle')
      setPaso(2)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  // Paso 2: subir foto (opcional) y cerrar
  const finalizarConFoto = async () => {
    if (!foto) { onCreada(facCreada); onClose(); return }
    setEstado('uploading')
    try {
      const fd = new FormData()
      fd.append('foto', foto)
      const r = await fetch(`${API_BASE}/proveedores/facturas/${facCreada.id}/foto`, {
        method: 'POST', body: fd,
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error subiendo foto')
      setEstado('ok')
      setTimeout(() => { onCreada({ ...facCreada, foto_url: d.url }); onClose() }, 600)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  return (
    <Overlay onClose={onClose} t={t}>
      {/* Header con indicador de paso */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: t.text, flex: 1 }}>
          {paso === 1 ? '📄 Nueva Factura' : `✅ ${facCreada?.id} creada`}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[1, 2].map(n => (
            <div key={n} style={{
              width: 8, height: 8, borderRadius: '50%',
              background: paso >= n ? t.accent : t.borderSoft,
              transition: 'background .2s',
            }} />
          ))}
        </div>
      </div>

      {paso === 1 && (
        <>
          <label style={labelStyle(t)}>Proveedor *</label>
          <StyledInput value={form.proveedor} onChange={e => set('proveedor', e.target.value)}
            placeholder="Ej: Pinturas Davinci" style={{ marginBottom: 10 }} />

          <label style={labelStyle(t)}>Total de la factura *</label>
          <StyledInput value={form.total} onChange={e => set('total', e.target.value)}
            placeholder="350000" type="number" style={{ marginBottom: 10 }} />

          <label style={labelStyle(t)}>Descripción (opcional)</label>
          <StyledInput value={form.descripcion} onChange={e => set('descripcion', e.target.value)}
            placeholder="Ej: surtido brochas y rodillos" style={{ marginBottom: 10 }} />

          <label style={labelStyle(t)}>Fecha (por defecto hoy)</label>
          <StyledInput value={form.fecha} onChange={e => set('fecha', e.target.value)}
            type="date" style={{ marginBottom: 14 }} />

          {err && <div style={{ color: t.accent, fontSize: 12, marginBottom: 10 }}>{err}</div>}
          <BtnPrimario t={t} onClick={guardarDatos} disabled={estado === 'saving'}>
            {estado === 'saving' ? 'Guardando…' : 'Siguiente → Foto'}
          </BtnPrimario>
        </>
      )}

      {paso === 2 && (
        <>
          <div style={{
            background: t.accentSub, border: `1px solid ${t.accent}33`,
            borderRadius: 8, padding: '10px 12px', marginBottom: 14, fontSize: 12,
          }}>
            <div style={{ color: t.text, fontWeight: 600 }}>{facCreada?.proveedor}</div>
            <div style={{ color: t.textMuted, marginTop: 2 }}>
              {facCreada?.descripcion} · {cop(facCreada?.total)}
            </div>
          </div>

          <SelectorFoto
            t={t}
            label="Foto de la factura (opcional)"
            onChange={seleccionarFoto}
            preview={preview}
            onClear={limpiarFoto}
          />
          {foto && !preview && (
            <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 8, marginTop: -8 }}>
              📎 {foto.name}
            </div>
          )}

          {err && <div style={{ color: t.accent, fontSize: 12, marginBottom: 10 }}>{err}</div>}

          <BtnPrimario t={t} onClick={finalizarConFoto}
            disabled={estado === 'uploading' || estado === 'ok'}>
            {estado === 'uploading' ? '⬆️ Subiendo a Drive…'
              : estado === 'ok' ? '✓ Listo'
              : foto ? '💾 Guardar con foto' : 'Guardar sin foto'}
          </BtnPrimario>

          {!foto && estado === 'idle' && (
            <button onClick={() => { onCreada(facCreada); onClose() }} style={{
              width: '100%', marginTop: 8, padding: '8px',
              background: 'transparent', border: 'none',
              color: t.textMuted, fontSize: 12, cursor: 'pointer',
            }}>
              Omitir foto por ahora
            </button>
          )}
        </>
      )}
    </Overlay>
  )
}

function ModalAbono({ factura, onClose, onAbonado, t }) {
  const [monto, setMonto]       = useState('')
  const [foto, setFoto]         = useState(null)
  const [preview, setPreview]   = useState(null)
  const [paso, setPaso]         = useState(1)    // 1=monto, 2=foto
  const [estado, setEstado]     = useState('idle')
  const [err, setErr]           = useState('')

  const seleccionarFoto = e => {
    const file = e.target.files[0]
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { setErr('La foto no puede superar 10 MB'); return }
    setFoto(file)
    if (file.type.startsWith('image/')) setPreview(URL.createObjectURL(file))
    setErr('')
  }

  // Paso 1: registrar el monto del abono
  const registrarAbono = async () => {
    const montoNum = Number(monto)
    if (!monto || isNaN(montoNum) || montoNum <= 0) {
      setErr('El monto debe ser mayor a 0'); return
    }
    // FIX: validar que el abono no supere el saldo pendiente
    if (montoNum > factura.pendiente) {
      setErr(`El abono ($${montoNum.toLocaleString('es-CO')}) supera el pendiente ($${factura.pendiente.toLocaleString('es-CO')}). Máximo permitido: ${cop(factura.pendiente)}`)
      return
    }
    setErr(''); setEstado('saving')
    try {
      const r = await fetch(`${API_BASE}/proveedores/abonos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fac_id: factura.id, monto: Number(monto) }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('idle')
      setPaso(2)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  // Paso 2: subir comprobante (opcional) y cerrar
  const finalizarConFoto = async () => {
    if (!foto) { onAbonado(); onClose(); return }
    setEstado('uploading')
    try {
      const fd = new FormData()
      fd.append('foto', foto)
      const r = await fetch(`${API_BASE}/proveedores/abonos/${factura.id}/foto`, {
        method: 'POST', body: fd,
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error subiendo comprobante')
      setEstado('ok')
      setTimeout(() => { onAbonado(); onClose() }, 600)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  return (
    <Overlay onClose={onClose} t={t}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: t.text, flex: 1 }}>
          {paso === 1 ? '💸 Registrar Abono' : '✅ Abono registrado'}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {[1, 2].map(n => (
            <div key={n} style={{
              width: 8, height: 8, borderRadius: '50%',
              background: paso >= n ? t.accent : t.borderSoft,
            }} />
          ))}
        </div>
      </div>
      <div style={{ fontSize: 12, color: t.textMuted, marginBottom: 16 }}>
        {factura.id} · {factura.proveedor}
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8,
        marginBottom: 14,
      }}>
        {[
          { label: 'Total factura', value: cop(factura.total),    color: t.text    },
          { label: 'Pendiente',     value: cop(factura.pendiente), color: t.accent  },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background: t.bg, border: `1px solid ${t.borderSoft}`,
            borderRadius: 8, padding: '8px 10px', textAlign: 'center',
          }}>
            <div style={{ fontSize: 10, color: t.textMuted }}>{label}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color }}>{value}</div>
          </div>
        ))}
      </div>
      {paso === 1 && (
        <>
          <label style={labelStyle(t)}>Monto del abono</label>
          <StyledInput
            value={monto} onChange={e => setMonto(e.target.value)}
            placeholder={`Máx. ${cop(factura.pendiente)}`}
            type="number" style={{ marginBottom: 14 }}
          />
          {err && <div style={{ color: t.accent, fontSize: 12, marginBottom: 10 }}>{err}</div>}
          <BtnPrimario t={t} onClick={registrarAbono} disabled={estado === 'saving'}>
            {estado === 'saving' ? 'Registrando…' : 'Siguiente → Comprobante'}
          </BtnPrimario>
        </>
      )}

      {paso === 2 && (
        <>
          <SelectorFoto
            t={t}
            label="Foto del comprobante de pago (opcional)"
            onChange={seleccionarFoto}
            preview={preview}
            onClear={() => { setFoto(null); setPreview(null) }}
          />
          {foto && !preview && (
            <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 8, marginTop: -8 }}>
              📎 {foto.name}
            </div>
          )}

          {err && <div style={{ color: t.accent, fontSize: 12, marginBottom: 10 }}>{err}</div>}

          <BtnPrimario t={t} onClick={finalizarConFoto}
            disabled={estado === 'uploading' || estado === 'ok'}>
            {estado === 'uploading' ? '⬆️ Subiendo a Drive…'
              : estado === 'ok' ? '✓ Listo'
              : foto ? '💾 Guardar con comprobante' : 'Guardar sin foto'}
          </BtnPrimario>

          {!foto && estado === 'idle' && (
            <button onClick={() => { onAbonado(); onClose() }} style={{
              width: '100%', marginTop: 8, padding: '8px',
              background: 'transparent', border: 'none',
              color: t.textMuted, fontSize: 12, cursor: 'pointer',
            }}>
              Omitir comprobante por ahora
            </button>
          )}
        </>
      )}
    </Overlay>
  )
}

function ResumenProveedores({ data, t, mobile }) {
  if (!data?.por_proveedor) return null
  const provs = Object.entries(data.por_proveedor)
    .filter(([, v]) => v.deuda > 0)
    .sort(([, a], [, b]) => b.deuda - a.deuda)

  if (!provs.length) return null

  return (
    <GlassCard style={{ padding: 14, marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: t.textMuted, marginBottom: 10,
                    letterSpacing: '.05em' }}>
        DEUDA POR PROVEEDOR
      </div>
      {provs.map(([nombre, v]) => {
        const pct = (v.deuda / (v.deuda + v.pagado || 1)) * 100
        return (
          <div key={nombre} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: t.text, fontWeight: 500 }}>{nombre}</span>
              <span style={{ fontSize: 12, color: t.accent, fontWeight: 700 }}>{cop(v.deuda)}</span>
            </div>
            <div style={{
              height: 4, borderRadius: 99,
              background: t.borderSoft, overflow: 'hidden',
            }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: pct > 70 ? t.accent : pct > 40 ? '#f59e0b' : '#16a34a',
                borderRadius: 99,
              }} />
            </div>
          </div>
        )
      })}
    </GlassCard>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function TabProveedores({ refreshKey }) {
  const t       = useTheme()
  const mobile  = useIsMobile()

  const [localRefresh, setLocalRefresh] = useState(0)
  const [filtro, setFiltro]             = useState('pendientes') // 'todas' | 'pendientes'
  const [modalFactura, setModalFactura] = useState(false)
  const [modalAbono,   setModalAbono]   = useState(null)  // factura seleccionada

  const reload = () => setLocalRefresh(r => r + 1)

  const { data, loading, error } = useFetch(
    `/proveedores/facturas?solo_pendientes=${filtro === 'pendientes'}`,
    [refreshKey, localRefresh, filtro]
  )
  const { data: resumen } = useFetch('/proveedores/resumen', [refreshKey, localRefresh])

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error cargando facturas: ${error}`} />

  const facturas    = data?.facturas || []
  const totalDeuda  = data?.total_deuda  || 0
  const totalPagado = data?.total_pagado || 0
  const nPend       = data?.n_pendientes || 0
  const nParc       = data?.n_parciales  || 0

  return (
    <div style={{ padding: mobile ? '12px 8px' : '16px 0', maxWidth: 760, margin: '0 auto' }}>

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 20, flexWrap: 'wrap', gap: 10,
      }}>
        <SectionTitle>
          <span style={{ marginRight: 8 }}>🏦</span>
          Proveedores
        </SectionTitle>
        <button
          onClick={() => setModalFactura(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 16px', borderRadius: 8,
            fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            cursor: 'pointer', border: 'none',
            background: t.accent, color: '#fff',
          }}
        >
          + Nueva Factura
        </button>
      </div>

      {/* ── KPIs ───────────────────────────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(4,1fr)',
        gap: 10, marginBottom: 20,
      }}>
        <KpiCard label="Deuda total"    value={cop(totalDeuda)}  icon="💳" color={t.accent} />
        <KpiCard label="Total pagado"   value={cop(totalPagado)} icon="✅" color="#16a34a"  />
        <KpiCard label="Pendientes"     value={nPend}            icon="🔴" color={t.accent} />
        <KpiCard label="En proceso"     value={nParc}            icon="🟡" color="#f59e0b"  />
      </div>

      {/* ── Resumen por proveedor ───────────────────────────────────────── */}
      <ResumenProveedores data={resumen} t={t} mobile={mobile} />

      {/* ── Filtros ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
        {[['pendientes','⏳ Pendientes'],['todas','📋 Todas']].map(([key, label]) => (
          <button key={key} onClick={() => setFiltro(key)} style={{
            padding: '6px 14px', borderRadius: 99,
            fontSize: 11, fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer',
            background: filtro === key ? t.accent      : t.card,
            color:      filtro === key ? '#fff'        : t.textSub,
            border:     `1px solid ${filtro === key ? 'transparent' : t.border}`,
            transition: 'all .15s',
          }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── Lista de facturas ───────────────────────────────────────────── */}
      {facturas.length === 0 ? (
        <GlassCard style={{ padding: 32, textAlign: 'center' }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>📄</div>
          <div style={{ color: t.textMuted, fontSize: 14 }}>
            {filtro === 'pendientes'
              ? 'No hay facturas pendientes'
              : 'No hay facturas registradas'}
          </div>
          <div style={{ color: t.textMuted, fontSize: 12, marginTop: 6 }}>
            Usa "/factura Proveedor Total" en Telegram o el botón "Nueva Factura"
          </div>
        </GlassCard>
      ) : (
        facturas.map(fac => (
          <FacturaCard
            key={fac.id} fac={fac} t={t} mobile={mobile}
            onAbonar={f => setModalAbono(f)}
          />
        ))
      )}

      {/* ── Nota informativa ────────────────────────────────────────────── */}
      <div style={{
        marginTop: 16, padding: '10px 14px',
        borderRadius: 8, background: t.accentSub,
        border: `1px solid ${t.accent}22`,
        fontSize: 11, color: t.textMuted, lineHeight: 1.6,
      }}>
        💡 Las fotos de facturas y comprobantes se guardan en Drive →{' '}
        <code style={{ color: t.accent }}>Facturas_Proveedores / Proveedor</code>
        {' '}· Los abonos se registran automáticamente en el histórico diario.
      </div>

      {/* ── Modales ─────────────────────────────────────────────────────── */}
      {modalFactura && (
        <ModalNuevaFactura
          t={t}
          onClose={() => setModalFactura(false)}
          onCreada={() => reload()}
        />
      )}
      {modalAbono && (
        <ModalAbono
          t={t}
          factura={modalAbono}
          onClose={() => setModalAbono(null)}
          onAbonado={() => reload()}
        />
      )}
    </div>
  )
}

// ── Utilidades de UI ──────────────────────────────────────────────────────────

function Overlay({ onClose, t, children }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,.45)', backdropFilter: 'blur(3px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: t.card, borderRadius: 14,
          padding: 20, width: '100%', maxWidth: 420,
          border: `1px solid ${t.border}`,
          boxShadow: `0 20px 60px rgba(0,0,0,.35)`,
        }}
      >
        {children}
      </div>
    </div>
  )
}

function BtnPrimario({ t, onClick, disabled, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        width: '100%', padding: '10px', borderRadius: 8,
        fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? .6 : 1,
        background: t.accent, color: '#fff', border: 'none',
        transition: 'opacity .15s',
      }}
    >
      {children}
    </button>
  )
}

function labelStyle(t) {
  return { fontSize: 11, fontWeight: 600, color: t.textMuted,
           display: 'block', marginBottom: 4, letterSpacing: '.04em' }
}
