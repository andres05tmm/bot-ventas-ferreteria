import { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import {
  useTheme, GlassCard, SectionTitle, Spinner, ErrorMsg,
  StyledInput, EmptyState, API_BASE,
  useIsMobile,
} from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'

// ── Constantes ────────────────────────────────────────────────────────────────
const TIPOS_ID      = ['CC', 'NIT', 'CE', 'PAS', 'TI', 'RC']
const TIPOS_PERSONA = ['Natural', 'Jurídica']
const LIMIT         = 25

// ── Helpers visuales ──────────────────────────────────────────────────────────
function tipoIdColor(tipo, t) {
  const m = {
    'CC':  { bg: t.accentSub,  color: t.accent },
    'NIT': { bg: t.blueSub,    color: t.blue },
    'CE':  { bg: t.yellowSub,  color: '#92400e' },
    'PAS': { bg: t.greenSub,   color: t.green },
  }
  return m[tipo] || { bg: t.card, color: t.textMuted }
}

function Badge({ children, style }) {
  return (
    <span style={{
      display: 'inline-block', fontSize: 10, fontWeight: 700,
      padding: '2px 7px', borderRadius: 5, whiteSpace: 'nowrap',
      ...style,
    }}>
      {children}
    </span>
  )
}

function initials(nombre) {
  if (!nombre) return '?'
  const words = nombre.trim().split(/\s+/)
  return words.length === 1
    ? words[0].slice(0, 2).toUpperCase()
    : (words[0][0] + words[1][0]).toUpperCase()
}

function Avatar({ nombre, size = 36, t }) {
  const colors = [t.accent, t.blue, t.green, '#8b5cf6', '#f59e0b']
  const idx    = nombre ? nombre.charCodeAt(0) % colors.length : 0
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0,
      background: colors[idx] + '22', border: `1.5px solid ${colors[idx]}44`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.35, fontWeight: 700, color: colors[idx],
    }}>
      {initials(nombre)}
    </div>
  )
}

// ── Modal crear / editar cliente ──────────────────────────────────────────────
function ModalCliente({ cliente, onClose, onGuardado, authFetch }) {
  const t      = useTheme()
  const esEdit = !!cliente
  const [form, setForm] = useState({
    nombre:         cliente?.['Nombre tercero'] || '',
    tipo_id:        cliente?.['Tipo ID']        || 'CC',
    identificacion: cliente?.['Identificacion'] || '',
    tipo_persona:   cliente?.['Tipo persona']   || 'Natural',
    correo:         cliente?.['Correo']         || '',
    telefono:       cliente?.['Telefono']       || '',
    direccion:      cliente?.['Direccion']      || '',
  })
  const [estado, setEstado] = useState('idle') // idle | saving | ok | err
  const [errMsg, setErrMsg] = useState('')

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const guardar = async () => {
    if (!form.nombre.trim()) { setErrMsg('El nombre es obligatorio'); return }
    setEstado('saving'); setErrMsg('')
    try {
      const url    = esEdit
        ? `${API_BASE}/clientes/${cliente.id}`
        : `${API_BASE}/clientes`
      const method = esEdit ? 'PATCH' : 'POST'
      const r      = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error guardando')
      setEstado('ok')
      setTimeout(() => { onGuardado(d.cliente); onClose() }, 500)
    } catch (e) {
      setErrMsg(e.message)
      setEstado('err')
    }
  }

  const lbl = { fontSize: 11, color: t.textMuted, fontWeight: 600, marginBottom: 4, display: 'block' }
  const inp = {
    width: '100%', padding: '8px 10px', borderRadius: 7, border: `1px solid ${t.border}`,
    background: t.bg, color: t.text, fontSize: 12, fontFamily: 'inherit',
    outline: 'none', boxSizing: 'border-box',
  }
  const sel = { ...inp, cursor: 'pointer' }

  return createPortal(
    <div
      onMouseDown={e => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: t.bg, border: `1px solid ${t.border}`, borderRadius: 14,
        width: '100%', maxWidth: 460, padding: 24, boxShadow: '0 24px 64px rgba(0,0,0,.4)',
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>
            {esEdit ? '✏️ Editar cliente' : '➕ Nuevo cliente'}
          </div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer', color: t.textMuted, fontSize: 18, lineHeight: 1,
          }}>×</button>
        </div>

        {/* Campos */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Nombre */}
          <div>
            <label style={lbl}>Nombre completo *</label>
            <input
              style={inp} value={form.nombre} autoFocus
              placeholder="Ej: JUAN CARLOS PÉREZ"
              onChange={e => set('nombre', e.target.value)}
              onKeyDown={e => e.key === 'Enter' && guardar()}
            />
          </div>

          {/* Tipo ID + Identificación en fila */}
          <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 10 }}>
            <div>
              <label style={lbl}>Tipo ID</label>
              <select style={sel} value={form.tipo_id} onChange={e => set('tipo_id', e.target.value)}>
                {TIPOS_ID.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label style={lbl}>Número de identificación</label>
              <input style={inp} value={form.identificacion}
                placeholder="Ej: 1234567890"
                onChange={e => set('identificacion', e.target.value)}
              />
            </div>
          </div>

          {/* Tipo persona */}
          <div>
            <label style={lbl}>Tipo de persona</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {TIPOS_PERSONA.map(tp => (
                <button key={tp} onClick={() => set('tipo_persona', tp)} style={{
                  flex: 1, padding: '8px 0', borderRadius: 7, fontSize: 12, fontWeight: 600,
                  fontFamily: 'inherit', cursor: 'pointer',
                  border: form.tipo_persona === tp ? `1.5px solid ${t.accent}` : `1px solid ${t.border}`,
                  background: form.tipo_persona === tp ? t.accentSub : 'transparent',
                  color: form.tipo_persona === tp ? t.accent : t.textMuted,
                }}>{tp}</button>
              ))}
            </div>
          </div>

          {/* Teléfono + Correo */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={lbl}>Teléfono</label>
              <input style={inp} value={form.telefono} placeholder="300 123 4567"
                onChange={e => set('telefono', e.target.value)}
              />
            </div>
            <div>
              <label style={lbl}>Correo</label>
              <input style={inp} value={form.correo} placeholder="cliente@email.com" type="email"
                onChange={e => set('correo', e.target.value)}
              />
            </div>
          </div>

          {/* Dirección */}
          <div>
            <label style={lbl}>Dirección</label>
            <input style={inp} value={form.direccion} placeholder="Calle 10 # 5-20"
              onChange={e => set('direccion', e.target.value)}
            />
          </div>
        </div>

        {/* Error */}
        {errMsg && (
          <div style={{
            marginTop: 12, padding: '8px 12px', background: '#fef2f2',
            border: '1px solid #fca5a5', borderRadius: 7, fontSize: 11, color: '#dc2626',
          }}>
            ✗ {errMsg}
          </div>
        )}

        {/* Botones */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 20 }}>
          <button onClick={onClose} style={{
            background: 'transparent', border: `1px solid ${t.border}`,
            borderRadius: 8, color: t.textMuted, padding: '9px 18px',
            cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
          }}>Cancelar</button>
          <button
            onClick={guardar}
            disabled={estado === 'saving' || estado === 'ok'}
            style={{
              background: estado === 'ok' ? t.green : t.accent,
              border: 'none', borderRadius: 8, color: '#fff',
              padding: '9px 22px', cursor: 'pointer',
              fontFamily: 'inherit', fontSize: 12, fontWeight: 700,
              opacity: (estado === 'saving' || estado === 'ok') ? 0.7 : 1,
            }}
          >
            {estado === 'saving' ? 'Guardando…' : estado === 'ok' ? '✓ Guardado' : esEdit ? 'Guardar cambios' : 'Crear cliente'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Modal confirmar eliminación ───────────────────────────────────────────────
function ModalEliminarCliente({ cliente, onClose, onEliminado, authFetch }) {
  const t = useTheme()
  const [estado, setEstado] = useState('idle')
  const [errMsg, setErrMsg] = useState('')

  const eliminar = async () => {
    setEstado('saving'); setErrMsg('')
    try {
      const r = await authFetch(`${API_BASE}/clientes/${cliente.id}`, { method: 'DELETE' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error eliminando')
      setEstado('ok')
      setTimeout(() => { onEliminado(cliente.id); onClose() }, 600)
    } catch (e) {
      setErrMsg(e.message); setEstado('err')
    }
  }

  return createPortal(
    <div
      onMouseDown={e => e.target === e.currentTarget && onClose()}
      style={{
        position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div style={{
        background: t.bg, border: `1px solid ${t.border}`, borderRadius: 14,
        width: '100%', maxWidth: 360, padding: 24, boxShadow: '0 24px 64px rgba(0,0,0,.4)',
      }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: t.text, marginBottom: 8 }}>🗑 Eliminar cliente</div>
        <div style={{ fontSize: 13, color: t.text, marginBottom: 4, fontWeight: 500 }}>{cliente['Nombre tercero']}</div>
        <div style={{ fontSize: 11, color: t.textMuted, marginBottom: 16 }}>
          {cliente['Tipo ID']} {cliente['Identificacion']}
        </div>
        <div style={{
          padding: '10px 12px', background: '#fef2f2', border: '1px solid #fca5a5',
          borderRadius: 8, fontSize: 11, color: '#dc2626', marginBottom: 16,
        }}>
          ⚠ Si el cliente tiene ventas previas, no podrá eliminarse.
        </div>
        {errMsg && (
          <div style={{
            padding: '8px 12px', background: '#fef2f2', border: '1px solid #fca5a5',
            borderRadius: 7, fontSize: 11, color: '#dc2626', marginBottom: 12,
          }}>✗ {errMsg}</div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            background: 'transparent', border: `1px solid ${t.border}`,
            borderRadius: 8, color: t.textMuted, padding: '8px 16px',
            cursor: 'pointer', fontFamily: 'inherit', fontSize: 12,
          }}>{estado === 'ok' ? 'Cerrar' : 'Cancelar'}</button>
          {estado !== 'ok' && (
            <button onClick={eliminar} disabled={estado === 'saving'} style={{
              background: '#dc2626', border: 'none', borderRadius: 8, color: '#fff',
              padding: '8px 18px', cursor: 'pointer', fontFamily: 'inherit',
              fontSize: 12, fontWeight: 700, opacity: estado === 'saving' ? 0.7 : 1,
            }}>
              {estado === 'saving' ? 'Eliminando…' : 'Sí, eliminar'}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Fila de cliente ───────────────────────────────────────────────────────────
function FilaCliente({ cliente, onEdit, onDelete, t, isMobile }) {
  const [hover, setHover] = useState(false)
  const idColor = tipoIdColor(cliente['Tipo ID'], t)

  if (isMobile) {
    return (
      <div style={{
        padding: '12px 14px', borderBottom: `1px solid ${t.border}`,
        background: hover ? t.accentSub : 'transparent',
        transition: 'background .15s',
      }}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
      >
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <Avatar nombre={cliente['Nombre tercero']} t={t} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: t.text, marginBottom: 3 }}>
              {cliente['Nombre tercero']}
            </div>
            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 4 }}>
              <Badge style={{ background: idColor.bg, color: idColor.color }}>
                {cliente['Tipo ID']}
              </Badge>
              {cliente['Identificacion'] && (
                <span style={{ fontSize: 11, color: t.textMuted }}>{cliente['Identificacion']}</span>
              )}
            </div>
            {cliente['Telefono'] && (
              <div style={{ fontSize: 11, color: t.textMuted }}>📞 {cliente['Telefono']}</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={onEdit} style={btnStyle(t, t.blue, t.blueSub)} title="Editar">✏️</button>
            <button onClick={onDelete} style={btnStyle(t, '#dc2626', '#fef2f2')} title="Eliminar">🗑</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <tr
      style={{ background: hover ? t.accentSub : 'transparent', transition: 'background .15s', cursor: 'default' }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <td style={{ padding: '10px 14px' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <Avatar nombre={cliente['Nombre tercero']} t={t} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: t.text }}>
              {cliente['Nombre tercero']}
            </div>
            {cliente['Direccion'] && (
              <div style={{ fontSize: 10, color: t.textMuted, marginTop: 1 }}>
                📍 {cliente['Direccion']}
              </div>
            )}
          </div>
        </div>
      </td>
      <td style={{ padding: '10px 14px' }}>
        <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
          <Badge style={{ background: idColor.bg, color: idColor.color }}>
            {cliente['Tipo ID']}
          </Badge>
          <span style={{ fontSize: 12, color: t.textMuted }}>{cliente['Identificacion'] || '—'}</span>
        </div>
      </td>
      <td style={{ padding: '10px 14px', fontSize: 12, color: t.textMuted }}>
        {cliente['Tipo persona'] || '—'}
      </td>
      <td style={{ padding: '10px 14px', fontSize: 12, color: t.text }}>
        {cliente['Telefono'] || <span style={{ color: t.textMuted }}>—</span>}
      </td>
      <td style={{ padding: '10px 14px', fontSize: 12, color: t.text, maxWidth: 180 }}>
        <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {cliente['Correo'] || <span style={{ color: t.textMuted }}>—</span>}
        </span>
      </td>
      <td style={{ padding: '10px 14px' }}>
        <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
          <button onClick={onEdit} style={btnStyle(t, t.blue, t.blueSub)} title="Editar">✏️</button>
          <button onClick={onDelete} style={btnStyle(t, '#dc2626', '#fef2f2')} title="Eliminar">🗑</button>
        </div>
      </td>
    </tr>
  )
}

function btnStyle(t, color, bg) {
  return {
    background: bg, border: `1px solid ${color}33`, borderRadius: 6,
    color: color, fontSize: 13, padding: '4px 8px',
    cursor: 'pointer', fontFamily: 'inherit', lineHeight: 1,
  }
}

// ── Tab principal ─────────────────────────────────────────────────────────────
export default function TabClientes({ refreshKey }) {
  const t       = useTheme()
  const isMobile = useIsMobile()
  const { authFetch } = useAuth()

  const [clientes,    setClientes]    = useState([])
  const [total,       setTotal]       = useState(0)
  const [offset,      setOffset]      = useState(0)
  const [busqueda,    setBusqueda]    = useState('')
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState('')
  const [creando,     setCreando]     = useState(false)
  const [editando,    setEditando]    = useState(null)  // cliente | null
  const [eliminando,  setEliminando]  = useState(null)  // cliente | null

  const searchTimer = useRef(null)

  const cargar = useCallback(async (q, off) => {
    setLoading(true); setError('')
    try {
      const params = new URLSearchParams({ q: q || '', offset: off, limit: LIMIT })
      const r = await authFetch(`${API_BASE}/clientes?${params}`)
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || `Error ${r.status}`) }
      const d = await r.json()
      setClientes(d.clientes || [])
      setTotal(d.total || 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  // Carga inicial y cuando cambia refreshKey
  useEffect(() => { cargar(busqueda, offset) }, [refreshKey])

  // Búsqueda con debounce
  const handleBusqueda = (val) => {
    setBusqueda(val)
    setOffset(0)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => cargar(val, 0), 300)
  }

  const irPagina = (nuevoOffset) => {
    setOffset(nuevoOffset)
    cargar(busqueda, nuevoOffset)
  }

  // Callbacks de modales
  const onClienteCreado = (c) => {
    setClientes(prev => {
      const existe = prev.find(x => x.id === c.id)
      return existe ? prev : [c, ...prev]
    })
    setTotal(t => t + 1)
  }

  const onClienteEditado = (c) => {
    setClientes(prev => prev.map(x => x.id === c.id ? c : x))
  }

  const onClienteEliminado = (id) => {
    setClientes(prev => prev.filter(x => x.id !== id))
    setTotal(t => Math.max(0, t - 1))
  }

  // ── Paginación ────────────────────────────────────────────────────────────
  const paginas = Math.ceil(total / LIMIT)
  const paginaActual = Math.floor(offset / LIMIT) + 1

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ padding: isMobile ? '12px' : '0 2px 24px' }}>

      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        flexWrap: 'wrap', gap: 10, marginBottom: 16,
      }}>
        <div>
          <SectionTitle style={{ marginBottom: 2 }}>
            👥 Clientes
          </SectionTitle>
          <div style={{ fontSize: 11, color: t.textMuted }}>
            {loading ? 'Cargando…' : `${total} clientes registrados`}
          </div>
        </div>
        <button
          onClick={() => setCreando(true)}
          style={{
            background: t.accent, border: 'none', borderRadius: 8, color: '#fff',
            padding: '9px 16px', cursor: 'pointer', fontFamily: 'inherit',
            fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          + Nuevo cliente
        </button>
      </div>

      {/* Buscador */}
      <div style={{ marginBottom: 14 }}>
        <StyledInput
          value={busqueda}
          onChange={e => handleBusqueda(e.target.value)}
          placeholder="🔍  Buscar por nombre o número de identificación…"
          style={{ width: '100%', maxWidth: 480 }}
        />
      </div>

      {/* Contenido */}
      <GlassCard style={{ padding: 0, overflow: 'hidden' }}>
        {loading && (
          <div style={{ padding: 40, display: 'flex', justifyContent: 'center' }}>
            <Spinner />
          </div>
        )}

        {!loading && error && (
          <div style={{ padding: 24 }}>
            <ErrorMsg msg={error} />
          </div>
        )}

        {!loading && !error && clientes.length === 0 && (
          <EmptyState msg={busqueda ? 'Sin resultados para esa búsqueda.' : 'No hay clientes registrados aún.'} />
        )}

        {!loading && !error && clientes.length > 0 && (
          <>
            {isMobile ? (
              /* Vista móvil — cards */
              <div>
                {clientes.map(c => (
                  <FilaCliente
                    key={c.id} cliente={c} t={t} isMobile
                    onEdit={() => setEditando(c)}
                    onDelete={() => setEliminando(c)}
                  />
                ))}
              </div>
            ) : (
              /* Vista escritorio — tabla */
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: t.tableAlt, borderBottom: `1px solid ${t.border}` }}>
                    {['Cliente', 'Identificación', 'Tipo persona', 'Teléfono', 'Correo', ''].map(h => (
                      <th key={h} style={{
                        padding: '10px 14px', textAlign: 'left',
                        fontSize: 11, fontWeight: 700, color: t.textMuted,
                        textTransform: 'uppercase', letterSpacing: '.5px',
                        borderBottom: `1px solid ${t.border}`,
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {clientes.map(c => (
                    <FilaCliente
                      key={c.id} cliente={c} t={t} isMobile={false}
                      onEdit={() => setEditando(c)}
                      onDelete={() => setEliminando(c)}
                    />
                  ))}
                </tbody>
              </table>
            )}

            {/* Paginación */}
            {paginas > 1 && (
              <div style={{
                display: 'flex', justifyContent: 'center', alignItems: 'center',
                gap: 8, padding: '12px 16px', borderTop: `1px solid ${t.border}`,
              }}>
                <button
                  disabled={paginaActual === 1}
                  onClick={() => irPagina(offset - LIMIT)}
                  style={paginaBtn(t, paginaActual === 1)}
                >← Anterior</button>
                <span style={{ fontSize: 12, color: t.textMuted }}>
                  Página {paginaActual} de {paginas}
                </span>
                <button
                  disabled={paginaActual === paginas}
                  onClick={() => irPagina(offset + LIMIT)}
                  style={paginaBtn(t, paginaActual === paginas)}
                >Siguiente →</button>
              </div>
            )}
          </>
        )}
      </GlassCard>

      {/* Modales */}
      {creando && (
        <ModalCliente
          cliente={null}
          onClose={() => setCreando(false)}
          onGuardado={onClienteCreado}
          authFetch={authFetch}
        />
      )}
      {editando && (
        <ModalCliente
          cliente={editando}
          onClose={() => setEditando(null)}
          onGuardado={onClienteEditado}
          authFetch={authFetch}
        />
      )}
      {eliminando && (
        <ModalEliminarCliente
          cliente={eliminando}
          onClose={() => setEliminando(null)}
          onEliminado={onClienteEliminado}
          authFetch={authFetch}
        />
      )}
    </div>
  )
}

function paginaBtn(t, disabled) {
  return {
    background: disabled ? 'transparent' : t.accentSub,
    border: `1px solid ${disabled ? t.border : t.accent + '55'}`,
    borderRadius: 6, color: disabled ? t.textMuted : t.accent,
    padding: '6px 12px', fontSize: 11, fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontFamily: 'inherit', opacity: disabled ? 0.5 : 1,
  }
}
