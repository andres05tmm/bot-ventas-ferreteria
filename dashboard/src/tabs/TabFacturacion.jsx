/**
 * TabFacturacion.jsx
 * Facturación Electrónica DIAN — integración con MATIAS API
 *
 * Secciones:
 *   1. KPIs  — emitidas hoy, $ facturado total, pendientes hoy
 *   2. Panel emitir — lista de ventas sin FE del día seleccionado + botón emitir por fila
 *   3. Historial  — tabla de facturas_electronicas con descarga de PDF
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import {
  useTheme, GlassCard, Card, SectionTitle,
  Spinner, ErrorMsg, EmptyState, Th,
  cop, API_BASE, useIsMobile,
} from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtFecha(str) {
  if (!str) return '—'
  const d = new Date(str)
  if (isNaN(d)) return str
  return d.toLocaleDateString('es-CO', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function fmtFechaSolo(str) {
  if (!str) return '—'
  const d = new Date(str + 'T12:00:00')
  if (isNaN(d)) return str
  return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
}

function cufeCorto(cufe) {
  if (!cufe || cufe.length < 16) return cufe || '—'
  return cufe.slice(0, 16) + '…' + cufe.slice(-8)
}

function copiarCufe(cufe) {
  if (!cufe) return
  navigator.clipboard.writeText(cufe).catch(() => {})
}

function EstadoBadge({ estado, t }) {
  const cfg = {
    emitida:     { bg: t.greenSub,  color: t.green,  label: '✅ Emitida'     },
    error:       { bg: '#fef2f244', color: '#dc2626', label: '❌ Error'       },
    sin_factura: { bg: t.yellowSub, color: t.yellow,  label: '⏳ Pendiente'  },
  }[estado] || { bg: t.accentSub, color: t.accent, label: estado }

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: '3px 10px', borderRadius: 99,
      background: cfg.bg, color: cfg.color,
      fontSize: 10, fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  )
}

function MetodoBadge({ metodo, t }) {
  const raw   = (metodo || '').toLowerCase()
  const light = t.id === 'caramelo'
  let color, bg
  if (raw.includes('efect'))  { color = light ? '#166534' : '#4ade80'; bg = light ? '#dcfce7' : '#052e16' }
  else if (raw.includes('nequi'))  { color = light ? '#1d4ed8' : '#93c5fd'; bg = light ? '#dbeafe' : '#172554' }
  else if (raw.includes('transf')) { color = light ? '#a16207' : '#d4d4aa'; bg = light ? '#fef9c3' : '#1c1917' }
  else if (raw.includes('tarjet') || raw.includes('dataf')) { color = light ? '#4338ca' : '#a5b4fc'; bg = light ? '#e0e7ff' : '#1e1b4b' }
  else                         { color = t.textMuted; bg = t.tableAlt }

  return (
    <span style={{
      display: 'inline-block', padding: '2px 9px', borderRadius: 99,
      background: bg, color, fontSize: 10, fontWeight: 500, whiteSpace: 'nowrap',
    }}>
      {metodo || '—'}
    </span>
  )
}

// ── KPI card mini ─────────────────────────────────────────────────────────────

function KpiMini({ label, value, color, icon }) {
  const t = useTheme()
  const [hov, setHov] = useState(false)
  const c = color || t.accent
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flex: 1, minWidth: 140,
        background: t.cardGrad,
        border: `1px solid ${hov ? c + '55' : t.border}`,
        borderRadius: 14, padding: '14px 18px',
        transition: 'border-color .2s, box-shadow .2s',
        boxShadow: hov ? `0 0 0 3px ${c}22` : t.shadowCard,
        position: 'relative', overflow: 'hidden',
      }}
    >
      <div style={{
        position: 'absolute', left: 0, top: '20%', bottom: '20%',
        width: 3,
        background: `linear-gradient(180deg, ${c}00, ${c}, ${c}00)`,
        borderRadius: 99, opacity: hov ? 1 : 0.5,
        transition: 'opacity .2s',
      }}/>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{
            fontSize: 10, fontWeight: 600, color: t.textMuted,
            letterSpacing: '.06em', textTransform: 'uppercase', marginBottom: 8,
          }}>
            {label}
          </div>
          <div style={{
            fontSize: 22, fontWeight: 700, color: t.text,
            letterSpacing: '-0.03em', fontVariantNumeric: 'tabular-nums',
          }}>
            {value}
          </div>
        </div>
        {icon && (
          <div style={{
            width: 32, height: 32, borderRadius: 9,
            background: `${c}15`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, flexShrink: 0,
          }}>{icon}</div>
        )}
      </div>
    </div>
  )
}

// ── Modal confirmación emisión ────────────────────────────────────────────────

function ModalEmitir({ venta, onClose, onEmitida }) {
  const t = useTheme()
  const { authFetch } = useAuth()
  const [estado, setEstado] = useState('idle') // idle | loading | ok | error
  const [error,  setError]  = useState('')
  const [result, setResult] = useState(null)

  const esConsumidorFinal = !venta.cliente_nombre || venta.cliente_nombre === 'Consumidor Final'

  const emitir = async () => {
    setEstado('loading')
    setError('')
    try {
      const r = await authFetch(`${API_BASE}/facturacion/emitir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ venta_id: venta.id }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || JSON.stringify(d))
      setResult(d)
      setEstado('ok')
      setTimeout(() => { onEmitida(); onClose() }, 2200)
    } catch (e) {
      setError(e.message)
      setEstado('error')
    }
  }

  const inp = {
    background: t.id === 'caramelo' ? '#F0EBE3' : t.card,
    border: `1px solid ${t.border}`,
    borderRadius: 8,
    padding: '8px 12px',
    color: t.text,
    fontSize: 12,
  }

  return createPortal(
    <div
      onMouseDown={e => e.target === e.currentTarget && estado !== 'loading' && onClose()}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        background: 'rgba(0,0,0,.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: t.bg, border: `1px solid ${t.border}`,
        borderRadius: 16, width: '100%', maxWidth: 460,
        boxShadow: '0 24px 64px rgba(0,0,0,.5)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 22px 16px',
          borderBottom: `1px solid ${t.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: t.text }}>
              📄 Emitir Factura Electrónica
            </div>
            <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
              Consecutivo #{venta.consecutivo} — {fmtFechaSolo(venta.fecha)}
            </div>
          </div>
          {estado !== 'loading' && (
            <button
              onClick={onClose}
              style={{
                background: 'transparent', border: `1px solid ${t.border}`,
                borderRadius: 7, color: t.textMuted, width: 28, height: 28,
                cursor: 'pointer', fontSize: 14,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >✕</button>
          )}
        </div>

        <div style={{ padding: '18px 22px 22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Datos de la venta */}
          <div style={{
            background: t.tableAlt, borderRadius: 10,
            border: `1px solid ${t.border}`, overflow: 'hidden',
          }}>
            {[
              ['Cliente',  venta.cliente_nombre || 'Consumidor Final'],
              ['Total',    cop(venta.total)],
              ['Método',   venta.metodo_pago || 'efectivo'],
              ['Vendedor', venta.vendedor || '—'],
            ].map(([k, v]) => (
              <div key={k} style={{
                display: 'flex', justifyContent: 'space-between',
                padding: '9px 14px',
                borderBottom: `1px solid ${t.border}`,
              }}>
                <span style={{ fontSize: 11, color: t.textMuted }}>{k}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: t.text }}>{v}</span>
              </div>
            ))}
          </div>

          {/* Advertencia consumidor final */}
          {esConsumidorFinal && estado === 'idle' && (
            <div style={{
              padding: '10px 14px', borderRadius: 9,
              background: t.yellowSub, border: `1px solid ${t.yellow}44`,
              fontSize: 12, color: t.yellow, lineHeight: 1.5,
            }}>
              ⚠️ <strong>Sin datos fiscales del cliente.</strong> La factura se emitirá como
              "Consumidor Final" con NIT genérico 222222222222. Válido para ventas ordinarias.
            </div>
          )}

          {/* Resultado OK */}
          {estado === 'ok' && result && (
            <div style={{
              padding: '14px 16px', borderRadius: 10,
              background: t.greenSub, border: `1px solid ${t.green}44`,
              display: 'flex', flexDirection: 'column', gap: 6,
            }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: t.green }}>
                ✅ Factura {result.numero} emitida ante la DIAN
              </div>
              <div style={{ fontSize: 11, color: t.green, opacity: 0.85 }}>
                CUFE: {cufeCorto(result.cufe)}
              </div>
              <div style={{ fontSize: 11, color: t.green, opacity: 0.7 }}>
                {result.pdf_telegram
                  ? '📲 Sin correo registrado — PDF enviado al grupo de Telegram.'
                  : '📧 PDF enviado al correo del cliente automáticamente.'}
              </div>
            </div>
          )}

          {/* Error */}
          {estado === 'error' && (
            <div style={{
              padding: '10px 14px', borderRadius: 9,
              background: '#fef2f244', border: '1px solid #dc262644',
              fontSize: 12, color: '#dc2626',
            }}>
              <strong>❌ Error DIAN:</strong> {error}
            </div>
          )}

          {/* Botones */}
          {estado !== 'ok' && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 2 }}>
              <button
                onClick={onClose}
                disabled={estado === 'loading'}
                style={{
                  background: 'transparent', border: `1px solid ${t.border}`,
                  borderRadius: 9, color: t.textMuted, padding: '9px 18px',
                  cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
                  opacity: estado === 'loading' ? 0.5 : 1,
                }}
              >
                Cancelar
              </button>
              <button
                onClick={emitir}
                disabled={estado === 'loading' || estado === 'ok'}
                style={{
                  background: estado === 'error' ? '#dc2626' : t.accent,
                  border: 'none', borderRadius: 9, color: '#fff',
                  padding: '9px 22px', cursor: 'pointer',
                  fontFamily: 'inherit', fontSize: 12, fontWeight: 700,
                  opacity: estado === 'loading' ? 0.75 : 1,
                  display: 'flex', alignItems: 'center', gap: 8,
                  transition: 'background .2s',
                }}
              >
                {estado === 'loading' && (
                  <div style={{
                    width: 13, height: 13,
                    border: '2px solid rgba(255,255,255,.35)',
                    borderTopColor: '#fff',
                    borderRadius: '50%',
                    animation: 'spin .65s linear infinite',
                  }}/>
                )}
                {estado === 'loading' ? 'Enviando a DIAN…' :
                 estado === 'error'   ? 'Reintentar' :
                 'Emitir Factura DIAN'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Sección: Ventas pendientes de FE ─────────────────────────────────────────

function PanelEmitir({ onEmitida }) {
  const t       = useTheme()
  const isMob   = useIsMobile()
  const { authFetch } = useAuth()

  const [fecha,     setFecha]     = useState(() => new Date().toISOString().slice(0, 10))
  const [ventas,    setVentas]    = useState([])
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState(null)
  const [emitiendo, setEmitiendo] = useState(null) // venta seleccionada para modal

  // BUGFIX: authFetch se recrea en cada render (useAuth no usa contexto/useCallback),
  // lo que causaba un loop infinito: authFetch nueva → cargar nueva → useEffect re-corre → setLoading → loop.
  // Solución: guardar authFetch en un ref estable para que useCallback no dependa de ella.
  const authFetchRef = useRef(authFetch)
  authFetchRef.current = authFetch

  const cargar = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await authFetchRef.current(`${API_BASE}/facturacion/ventas-pendientes?fecha=${fecha}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setVentas(await r.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [fecha]) // authFetch NO va aquí — se accede via ref estable

  useEffect(() => { cargar() }, [cargar])

  const lbl = {
    fontSize: 10, fontWeight: 600, color: t.textMuted,
    textTransform: 'uppercase', letterSpacing: '.06em',
    marginBottom: 4, display: 'block',
  }
  const inpBase = {
    background: t.id === 'caramelo' ? '#F0EBE3' : t.card,
    border: `1px solid ${t.border}`,
    borderRadius: 8, color: t.text,
    fontSize: 12, padding: '7px 11px',
    fontFamily: 'inherit', outline: 'none',
  }

  return (
    <GlassCard style={{ padding: 0 }}>
      {/* Header */}
      <div style={{
        padding: '14px 20px', borderBottom: `1px solid ${t.border}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10,
      }}>
        <SectionTitle>📋 Ventas sin Factura Electrónica</SectionTitle>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div>
            <label style={lbl}>Fecha</label>
            <input
              type="date"
              value={fecha}
              onChange={e => setFecha(e.target.value)}
              style={inpBase}
            />
          </div>
          <button
            onClick={cargar}
            style={{
              background: t.accentSub, border: `1px solid ${t.accent}55`,
              color: t.accent, borderRadius: 8, padding: '7px 14px',
              cursor: 'pointer', fontFamily: 'inherit', fontSize: 11, fontWeight: 600,
              marginTop: 14,
            }}
          >
            🔄 Actualizar
          </button>
        </div>
      </div>

      {/* Contenido */}
      {loading && <Spinner />}
      {!loading && error && <div style={{ padding: 16 }}><ErrorMsg msg={error} /></div>}
      {!loading && !error && ventas.length === 0 && (
        <EmptyState msg={`✅ Todas las ventas del ${fmtFechaSolo(fecha)} tienen factura emitida.`} />
      )}
      {!loading && !error && ventas.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: t.tableAlt }}>
                <Th>#</Th>
                <Th>Hora</Th>
                <Th>Cliente</Th>
                <Th>Vendedor</Th>
                <Th center>Método</Th>
                <Th right>Total</Th>
                <Th center>Acción</Th>
              </tr>
            </thead>
            <tbody>
              {ventas.map(v => (
                <tr
                  key={v.id}
                  style={{ borderBottom: `1px solid ${t.border}`, transition: 'background .15s' }}
                  onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '9px 14px', color: t.accent, fontWeight: 700 }}>
                    {v.consecutivo}
                  </td>
                  <td style={{ padding: '9px 14px', color: t.textMuted, fontStyle: 'italic', whiteSpace: 'nowrap' }}>
                    {v.hora ? String(v.hora).slice(0, 5) : '—'}
                  </td>
                  <td style={{ padding: '9px 14px', color: t.text, maxWidth: 180 }}>
                    {v.cliente_nombre || 'Consumidor Final'}
                    {(!v.cliente_nombre || v.cliente_nombre === 'Consumidor Final') && (
                      <span style={{
                        fontSize: 9, marginLeft: 6, padding: '1px 5px',
                        borderRadius: 4, background: t.yellowSub, color: t.yellow,
                        fontWeight: 700,
                      }}>CF</span>
                    )}
                  </td>
                  <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>
                    {v.vendedor || '—'}
                  </td>
                  <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                    <MetodoBadge metodo={v.metodo_pago} t={t} />
                  </td>
                  <td style={{ padding: '9px 14px', textAlign: 'right', color: t.green, fontWeight: 700 }}>
                    {cop(v.total)}
                  </td>
                  <td style={{ padding: '9px 10px', textAlign: 'center' }}>
                    <button
                      onClick={() => setEmitiendo(v)}
                      style={{
                        background: t.accent, border: 'none',
                        borderRadius: 7, color: '#fff',
                        padding: isMob ? '6px 10px' : '6px 14px',
                        cursor: 'pointer', fontFamily: 'inherit',
                        fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap',
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                      }}
                    >
                      📄 {isMob ? 'FE' : 'Emitir FE'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                <td colSpan={5} style={{ padding: '9px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>
                  {ventas.length} venta{ventas.length !== 1 ? 's' : ''} pendiente{ventas.length !== 1 ? 's' : ''}
                </td>
                <td style={{ padding: '9px 14px', textAlign: 'right', color: t.accent, fontWeight: 700, fontSize: 13 }}>
                  {cop(ventas.reduce((a, v) => a + (Number(v.total) || 0), 0))}
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Modal emisión */}
      {emitiendo && (
        <ModalEmitir
          venta={emitiendo}
          onClose={() => setEmitiendo(null)}
          onEmitida={() => { setEmitiendo(null); cargar(); onEmitida() }}
        />
      )}
    </GlassCard>
  )
}

// ── Sección: Historial de facturas emitidas ───────────────────────────────────

function Historial({ refreshKey }) {
  const t     = useTheme()
  const isMob = useIsMobile()
  const { authFetch } = useAuth()

  const [facturas, setFacturas] = useState([])
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)
  const [filtro,   setFiltro]   = useState('todas') // todas | emitida | error
  const [pdfLoading, setPdfLoading] = useState(null) // cufe en descarga

  // BUGFIX: mismo problema que PanelEmitir — authFetch nueva en cada render causaba loop infinito.
  const authFetchRef = useRef(authFetch)
  authFetchRef.current = authFetch

  const cargar = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await authFetchRef.current(`${API_BASE}/facturacion/lista?limite=100`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setFacturas(await r.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, []) // authFetch NO va aquí — se accede via ref estable

  useEffect(() => { cargar() }, [cargar, refreshKey])

  const descargarPDF = async (cufe, numero) => {
    if (!cufe || cufe === '—') return
    setPdfLoading(cufe)
    try {
      const r = await authFetchRef.current(`${API_BASE}/facturacion/pdf/${cufe}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const blob = await r.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `${numero || 'factura'}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      alert(`Error descargando PDF: ${e.message}`)
    } finally {
      setPdfLoading(null)
    }
  }

  const filtradas = facturas.filter(f =>
    filtro === 'todas' ? true : f.estado === filtro
  )

  const totalEmitidas = facturas.filter(f => f.estado === 'emitida').length
  const totalMonto    = facturas.filter(f => f.estado === 'emitida').reduce((a, f) => a + (Number(f.total) || 0), 0)
  const totalErrores  = facturas.filter(f => f.estado === 'error').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <KpiMini label="Facturas emitidas"  value={totalEmitidas}  color={t.green}  icon="✅" />
        <KpiMini label="$ Total facturado"  value={cop(totalMonto)} color={t.accent} icon="💰" />
        <KpiMini label="Con errores"        value={totalErrores}   color={totalErrores > 0 ? '#dc2626' : t.textMuted} icon="❌" />
      </div>

      {/* Tabla historial */}
      <GlassCard style={{ padding: 0 }}>
        <div style={{
          padding: '14px 20px', borderBottom: `1px solid ${t.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10,
        }}>
          <SectionTitle>📑 Historial de Facturas Electrónicas</SectionTitle>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {['todas', 'emitida', 'error'].map(f => (
              <button
                key={f}
                onClick={() => setFiltro(f)}
                style={{
                  background: filtro === f ? t.accent : t.accentSub,
                  border: `1px solid ${filtro === f ? t.accent : t.border}`,
                  color: filtro === f ? '#fff' : t.textMuted,
                  borderRadius: 8, padding: '5px 13px',
                  cursor: 'pointer', fontFamily: 'inherit',
                  fontSize: 11, fontWeight: filtro === f ? 700 : 500,
                  transition: 'all .15s',
                }}
              >
                {f === 'todas' ? 'Todas' : f === 'emitida' ? '✅ Emitidas' : '❌ Errores'}
              </button>
            ))}
            <button
              onClick={cargar}
              style={{
                background: 'transparent', border: `1px solid ${t.border}`,
                color: t.textMuted, borderRadius: 8, padding: '5px 11px',
                cursor: 'pointer', fontFamily: 'inherit', fontSize: 11,
              }}
            >
              🔄
            </button>
          </div>
        </div>

        {loading && <Spinner />}
        {!loading && error && <div style={{ padding: 16 }}><ErrorMsg msg={error} /></div>}
        {!loading && !error && filtradas.length === 0 && (
          <EmptyState msg="No hay facturas electrónicas registradas." />
        )}
        {!loading && !error && filtradas.length > 0 && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: t.tableAlt }}>
                  <Th>Número</Th>
                  <Th>Fecha emisión</Th>
                  <Th>Venta #</Th>
                  <Th>Cliente</Th>
                  <Th right>Total</Th>
                  <Th center>Estado</Th>
                  {!isMob && <Th>CUFE</Th>}
                  <Th center>PDF</Th>
                </tr>
              </thead>
              <tbody>
                {filtradas.map(f => (
                  <tr
                    key={f.id}
                    style={{ borderBottom: `1px solid ${t.border}`, transition: 'background .15s' }}
                    onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: '9px 14px', color: t.accent, fontWeight: 700, whiteSpace: 'nowrap' }}>
                      {f.numero || '—'}
                    </td>
                    <td style={{ padding: '9px 14px', color: t.textMuted, whiteSpace: 'nowrap', fontSize: 11 }}>
                      {fmtFecha(f.fecha_emision)}
                    </td>
                    <td style={{ padding: '9px 14px', color: t.textSub, textAlign: 'center' }}>
                      {f.venta_consecutivo != null ? `#${f.venta_consecutivo}` : '—'}
                    </td>
                    <td style={{ padding: '9px 14px', color: t.text, maxWidth: 180 }}>
                      {f.cliente_nombre || 'Consumidor Final'}
                    </td>
                    <td style={{ padding: '9px 14px', textAlign: 'right', color: t.green, fontWeight: 600 }}>
                      {cop(f.total)}
                    </td>
                    <td style={{ padding: '9px 14px', textAlign: 'center' }}>
                      <EstadoBadge estado={f.estado} t={t} />
                    </td>
                    {!isMob && (
                      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 10, fontFamily: 'monospace' }}>
                        {f.estado === 'error'
                          ? <span style={{ color: '#dc2626', fontSize: 11 }}>{f.error_msg?.slice(0, 60) || '—'}</span>
                          : (
                            <span
                              title={f.cufe}
                              onClick={() => copiarCufe(f.cufe)}
                              style={{ cursor: 'copy', fontFamily: 'monospace', fontSize: 11 }}
                            >
                              {cufeCorto(f.cufe)}
                            </span>
                          )
                        }
                      </td>
                    )}
                    <td style={{ padding: '9px 10px', textAlign: 'center' }}>
                      {f.cufe && f.estado === 'emitida' ? (
                        <button
                          onClick={() => descargarPDF(f.cufe, f.numero)}
                          disabled={pdfLoading === f.cufe}
                          title="Descargar PDF"
                          style={{
                            background: t.blueSub, border: `1px solid ${t.blue}44`,
                            color: t.blue, borderRadius: 7,
                            width: 32, height: 32, cursor: 'pointer',
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: pdfLoading === f.cufe ? 9 : 14,
                            opacity: pdfLoading === f.cufe ? 0.6 : 1,
                            transition: 'opacity .15s',
                          }}
                        >
                          {pdfLoading === f.cufe ? '…' : '⬇'}
                        </button>
                      ) : (
                        <span style={{ color: t.textMuted, fontSize: 11 }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                  <td colSpan={isMob ? 3 : 4} style={{
                    padding: '9px 14px', fontSize: 10,
                    color: t.textMuted, fontWeight: 600, textAlign: 'right',
                  }}>
                    {filtradas.length} factura{filtradas.length !== 1 ? 's' : ''}
                  </td>
                  <td style={{ padding: '9px 14px', textAlign: 'right', color: t.accent, fontWeight: 700, fontSize: 13 }}>
                    {cop(filtradas.filter(f => f.estado === 'emitida').reduce((a, f) => a + (Number(f.total) || 0), 0))}
                  </td>
                  <td colSpan={isMob ? 2 : 3} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function TabFacturacion({ refreshKey }) {
  const t = useTheme()
  const [histRefresh, setHistRefresh] = useState(0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Banner DIAN */}
      <div style={{
        padding: '12px 18px', borderRadius: 12,
        background: t.blueSub, border: `1px solid ${t.blue}33`,
        display: 'flex', alignItems: 'center', gap: 10,
        fontSize: 12, color: t.blue,
      }}>
        <span style={{ fontSize: 20 }}>🏛️</span>
        <div>
          <strong>Facturación Electrónica DIAN</strong> vía MATIAS API · UBL 2.1
          <span style={{ marginLeft: 10, opacity: 0.7, fontSize: 11 }}>
            Las facturas se envían al correo del cliente automáticamente.
          </span>
        </div>
      </div>

      {/* Panel de ventas pendientes */}
      <PanelEmitir onEmitida={() => setHistRefresh(r => r + 1)} />

      {/* Historial con KPIs */}
      <Historial refreshKey={`${refreshKey}-${histRefresh}`} />

    </div>
  )
}
