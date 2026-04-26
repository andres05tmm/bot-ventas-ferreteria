/**
 * FacturasElectronicasRecibidas.jsx
 * Sección para agregar dentro de TabProveedores.jsx.
 *
 * INTEGRACIÓN:
 *   import FacturasElectronicasRecibidas from './FacturasElectronicasRecibidas'
 *   // Al final del return de TabProveedores:
 *   <FacturasElectronicasRecibidas />
 */
import { useState } from 'react'
import { useTheme, useFetch, cop, API_BASE, Spinner } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'

function BadgeEvento({ fecha, label }) {
  const activo = Boolean(fecha)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10,
                  color: activo ? '#16a34a' : '#9ca3af' }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                     background: activo ? '#16a34a' : '#d1d5db' }} />
      {label}
    </div>
  )
}

function ModalReclamo({ cufe, id, onClose, onEnviado }) {
  const t = useTheme()
  const { authFetch } = useAuth()
  const [motivo,   setMotivo]   = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error,    setError]    = useState('')

  const enviar = async () => {
    if (!motivo.trim()) { setError('El motivo es obligatorio'); return }
    setEnviando(true); setError('')
    try {
      const r = await authFetch(`${API_BASE}/proveedores/reclamar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cufe, compra_fiscal_id: id, motivo: motivo.trim() }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      onEnviado(); onClose()
    } catch (e) {
      setError(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div onClick={e => e.target === e.currentTarget && onClose()} style={{
      position: 'fixed', inset: 0, background: '#000000bb',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      zIndex: 9999, padding: 16,
    }}>
      <div style={{ background: t.card, border: `1px solid ${t.border}`,
                    borderRadius: 14, padding: 24, width: '100%', maxWidth: 420 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: t.text, marginBottom: 4 }}>
          ⚠️ Reclamar factura
        </div>
        <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 16 }}>
          Se enviará el evento 031 a la DIAN con el motivo del reclamo.
        </div>
        <textarea
          autoFocus value={motivo} onChange={e => setMotivo(e.target.value)}
          placeholder="Describe el motivo (ej: mercancía no recibida, diferencia en cantidades...)"
          rows={4}
          style={{ width: '100%', boxSizing: 'border-box',
                   background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                   border: `1px solid ${t.accent}66`, borderRadius: 8,
                   color: t.text, fontSize: 12, padding: '10px 12px',
                   fontFamily: 'inherit', outline: 'none', resize: 'vertical', marginBottom: 12 }}
        />
        {error && (
          <div style={{ padding: '7px 10px', background: '#fef2f2', border: '1px solid #fca5a5',
                        borderRadius: 7, fontSize: 11, color: '#dc2626', marginBottom: 12 }}>
            ⚠ {error}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={onClose} style={{
            flex: 1, padding: 10, background: 'transparent',
            border: `1px solid ${t.border}`, borderRadius: 8,
            color: t.textMuted, cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
          }}>Cancelar</button>
          <button onClick={enviar} disabled={enviando} style={{
            flex: 2, padding: 10, background: enviando ? t.border : '#f59e0b',
            border: 'none', borderRadius: 8, color: '#fff',
            cursor: enviando ? 'not-allowed' : 'pointer',
            fontFamily: 'inherit', fontSize: 12, fontWeight: 600,
          }}>{enviando ? 'Enviando...' : '⚠️ Enviar reclamo'}</button>
        </div>
      </div>
    </div>
  )
}

export default function FacturasElectronicasRecibidas() {
  const t = useTheme()
  const { authFetch } = useAuth()
  const [filtro,       setFiltro]       = useState('pendiente')
  const [refresh,      setRefresh]      = useState(0)
  const [aceptando,    setAceptando]    = useState(null)
  const [modalReclamo, setModalReclamo] = useState(null)
  const [toast,        setToast]        = useState(null)

  const { data, loading } = useFetch(
    `/proveedores/facturas-electronicas?estado=${filtro}&limit=30`,
    [filtro, refresh]
  )
  const facturas = data || []

  const mostrarToast = (msg, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  const aceptar = async (fac) => {
    setAceptando(fac.id)
    try {
      const r = await authFetch(`${API_BASE}/proveedores/aceptar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cufe: fac.cufe_proveedor, compra_fiscal_id: fac.id }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarToast('✅ Factura aceptada ante la DIAN (032 + 033)')
      setRefresh(x => x + 1)
    } catch (e) {
      mostrarToast(`❌ ${e.message}`, false)
    } finally {
      setAceptando(null)
    }
  }

  const FILTROS = [
    { key: 'pendiente', label: '⏳ Pendientes' },
    { key: 'aceptada',  label: '✅ Aceptadas'  },
    { key: 'reclamada', label: '⚠️ Reclamadas' },
  ]

  return (
    <div style={{ marginTop: 36 }}>
      {/* Header */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: t.text }}>
          📨 Facturas electrónicas recibidas
        </div>
        <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
          FE de proveedores recibidas por correo — requieren respuesta ante la DIAN
        </div>
      </div>

      {/* Filtros */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        {FILTROS.map(f => (
          <button key={f.key} onClick={() => setFiltro(f.key)} style={{
            padding: '5px 14px', borderRadius: 99, cursor: 'pointer',
            background: filtro === f.key ? t.accentSub : 'transparent',
            border: `1px solid ${filtro === f.key ? t.accent : t.border}`,
            color: filtro === f.key ? t.accent : t.textMuted,
            fontSize: 11, fontFamily: 'inherit', transition: 'all .15s',
          }}>{f.label}</button>
        ))}
      </div>

      {/* Lista */}
      {loading ? (
        <Spinner />
      ) : facturas.length === 0 ? (
        <div style={{ border: `1px dashed ${t.border}`, borderRadius: 10,
                      padding: '28px 16px', textAlign: 'center',
                      color: t.textMuted, fontSize: 12 }}>
          {filtro === 'pendiente'
            ? 'No hay facturas pendientes de aceptar.'
            : `No hay facturas ${filtro === 'aceptada' ? 'aceptadas' : 'reclamadas'}.`}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {facturas.map(fac => {
            const enProceso = aceptando === fac.id
            const estadoColor = fac.evento_estado === 'aceptada'  ? '#16a34a'
                              : fac.evento_estado === 'reclamada' ? '#f59e0b'
                              : '#6b7280'
            const estadoLabel = fac.evento_estado === 'aceptada'  ? '✅ Aceptada'
                              : fac.evento_estado === 'reclamada' ? '⚠️ Reclamada'
                              : '⏳ Pendiente'
            return (
              <div key={fac.id} style={{ background: t.card, border: `1px solid ${t.border}`,
                                         borderRadius: 12, overflow: 'hidden' }}>
                {/* Cabecera */}
                <div style={{ padding: '12px 16px', borderBottom: `1px solid ${t.border}`,
                              display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: t.text,
                                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {fac.proveedor || 'Proveedor desconocido'}
                    </div>
                    <div style={{ fontSize: 10, color: t.textMuted, marginTop: 2 }}>
                      {fac.numero_factura && `N° ${fac.numero_factura} · `}
                      {fac.fecha} · {fac.costo_total ? cop(fac.costo_total) : '—'}
                    </div>
                  </div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: estadoColor, whiteSpace: 'nowrap' }}>
                    {estadoLabel}
                  </div>
                </div>

                {/* Badges eventos */}
                <div style={{ padding: '10px 16px', display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <BadgeEvento fecha={fac.evento_030_at} label="030 Acuse" />
                  <BadgeEvento fecha={fac.evento_031_at} label="031 Reclamo" />
                  <BadgeEvento fecha={fac.evento_032_at} label="032 Recibo bien" />
                  <BadgeEvento fecha={fac.evento_033_at} label="033 Aceptación" />
                  {fac.evento_error && (
                    <div style={{ fontSize: 10, color: '#dc2626', background: '#fef2f2',
                                  border: '1px solid #fca5a5', borderRadius: 5,
                                  padding: '2px 8px', maxWidth: '100%',
                                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      ⚠ {fac.evento_error}
                    </div>
                  )}
                </div>

                {/* Acciones — solo si está pendiente */}
                {fac.evento_estado === 'pendiente' && (
                  <div style={{ padding: '0 16px 14px', display: 'flex', gap: 8 }}>
                    <button onClick={() => aceptar(fac)} disabled={enProceso} style={{
                      flex: 2, padding: '9px 12px',
                      background: enProceso ? t.border : '#16a34a',
                      border: 'none', borderRadius: 8,
                      color: enProceso ? t.textMuted : '#fff',
                      fontSize: 12, fontWeight: 600,
                      cursor: enProceso ? 'not-allowed' : 'pointer',
                      fontFamily: 'inherit', transition: 'all .15s',
                    }}>
                      {enProceso ? 'Enviando...' : '✅ Aceptar'}
                    </button>
                    <button
                      onClick={() => setModalReclamo({ cufe: fac.cufe_proveedor, id: fac.id })}
                      disabled={enProceso}
                      style={{
                        flex: 1, padding: '9px 12px', background: 'transparent',
                        border: `1px solid #f59e0b`, borderRadius: 8, color: '#f59e0b',
                        fontSize: 12, fontWeight: 600,
                        cursor: enProceso ? 'not-allowed' : 'pointer',
                        fontFamily: 'inherit', transition: 'all .15s',
                      }}>
                      ⚠️ Reclamar
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Modal reclamo */}
      {modalReclamo && (
        <ModalReclamo
          cufe={modalReclamo.cufe} id={modalReclamo.id}
          onClose={() => setModalReclamo(null)}
          onEnviado={() => { setRefresh(x => x + 1); mostrarToast('⚠️ Reclamo enviado a la DIAN') }}
        />
      )}

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 22, right: 22, background: t.card,
          border: `1px solid ${toast.ok ? '#16a34a' : '#dc2626'}`,
          color: toast.ok ? '#16a34a' : '#dc2626',
          padding: '10px 16px', borderRadius: 9, fontSize: 12, fontWeight: 500, zIndex: 999,
        }}>
          {toast.msg}
        </div>
      )}
    </div>
  )
}
