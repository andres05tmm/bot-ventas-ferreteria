import { useState } from 'react'
import { useTheme, useFetch, Card, GlassCard, SectionTitle, KpiCard, Spinner, ErrorMsg, cop, useIsMobile, API_BASE } from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'

function MetodoRow({ label, valor, icon, t }) {
  if (!valor) return null
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderBottom: `1px solid ${t.border}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <span style={{ color: t.textSub, fontSize: 13 }}>{label}</span>
      </div>
      <span style={{ color: t.text, fontWeight: 600, fontSize: 14 }}>{cop(valor)}</span>
    </div>
  )
}

function GastoRow({ g, t }) {
  return (
    <tr style={{ borderBottom: `1px solid ${t.border}` }}
      onMouseEnter={e => { e.currentTarget.style.background = t.cardHover; e.currentTarget.style.transform = 'translateX(2px)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.transform = 'translateX(0)' }}>
      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{g.hora || '—'}</td>
      <td style={{ padding: '9px 14px', color: t.text }}>{g.concepto || '—'}</td>
      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>
        <span style={{
          background: t.accentSub, color: t.accent,
          border: `1px solid ${t.accent}33`,
          padding: '2px 8px', borderRadius: 99, fontSize: 10,
        }}>
          {g.categoria || 'Gasto'}
        </span>
      </td>
      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{g.origen || '—'}</td>
      <td style={{ padding: '9px 14px', textAlign: 'right', color: '#f87171', fontWeight: 600 }}>
        -{cop(g.monto)}
      </td>
    </tr>
  )
}

export default function TabCaja({ refreshKey }) {
  const t = useTheme()
  const isMobile = useIsMobile()
  const { authFetch } = useAuth()
  const [localRefresh, setLocalRefresh] = useState(0)
  const { data, loading, error } = useFetch('/caja', [refreshKey, localRefresh])

  // Estado para abrir caja
  const [montoApertura, setMontoApertura] = useState('')
  const [abriendo, setAbriendo] = useState(false)
  const [cerrando, setCerrando] = useState(false)
  const [msg, setMsg] = useState(null)

  // Estado Venta Varia
  const [variaOpen,   setVariaOpen]   = useState(false)
  const [variaMonto,  setVariaMonto]  = useState('')
  const [variaMetodo, setVariaMetodo] = useState('efectivo')
  const [variaDesc,   setVariaDesc]   = useState('')
  const [variando,    setVariando]    = useState(false)

  const mostrarMsg = (tipo, texto) => { setMsg({ tipo, texto }); setTimeout(() => setMsg(null), 4000) }

  const abrirCaja = async () => {
    setAbriendo(true)
    try {
      const r = await authFetch(`${API_BASE}/caja/abrir`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monto_apertura: parseInt(montoApertura) || 0 }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarMsg('ok', d.mensaje)
      setMontoApertura('')
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setAbriendo(false) }
  }

  const cerrarCaja = async () => {
    if (!confirm('¿Cerrar la caja del día?')) return
    setCerrando(true)
    try {
      const r = await authFetch(`${API_BASE}/caja/cerrar`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarMsg('ok', 'Caja cerrada')
      setLocalRefresh(r => r + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setCerrando(false) }
  }

  const registrarVentaVaria = async () => {
    const monto = parseFloat(variaMonto.replace(/[^0-9.]/g, ''))
    if (!monto || monto <= 0) return mostrarMsg('err', 'Ingresa un monto válido')
    setVariando(true)
    try {
      const r = await authFetch(`${API_BASE}/ventas/varia`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          monto,
          metodo_pago: variaMetodo,
          descripcion: variaDesc.trim() || 'Venta Varia',
          vendedor: 'Dashboard',
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      mostrarMsg('ok', `✓ Venta varia de $${monto.toLocaleString('es-CO')} registrada (${variaMetodo})`)
      setVariaMonto(''); setVariaDesc(''); setVariaOpen(false)
      setLocalRefresh(x => x + 1)
    } catch (e) { mostrarMsg('err', e.message) }
    finally { setVariando(false) }
  }

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error cargando caja: ${error}`} />

  const d = data || {}
  const abierta = d.abierta
  const gastos  = d.gastos || []

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
        }}>
          {msg.tipo === 'ok' ? '✓' : '✕'} {msg.texto}
        </div>
      )}

      {/* Estado + Acciones */}
      <GlassCard style={{ padding: '14px 18px' }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 18 }}>{abierta ? '🟢' : '⚫'}</span>
            <div>
              <span style={{ fontWeight: 600, color: abierta ? t.green : t.textMuted, fontSize: 13 }}>
                Caja {abierta ? 'abierta' : 'cerrada'}
              </span>
              {d.fecha && (
                <span style={{ color: t.textMuted, fontSize: 11, marginLeft: 10 }}>
                  {d.fecha}
                </span>
              )}
            </div>
          </div>

          {/* Botón cerrar si está abierta */}
          {abierta && (
            <button onClick={cerrarCaja} disabled={cerrando} style={{
              background: 'transparent', border: `1px solid ${t.accent}44`,
              borderRadius: 8, color: t.accent, padding: '7px 16px',
              fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
            }}>
              {cerrando ? 'Cerrando…' : '🔒 Cerrar caja'}
            </button>
          )}
        </div>

        {/* Formulario abrir caja si está cerrada */}
        {!abierta && (
          <div style={{
            marginTop: 14, paddingTop: 14, borderTop: `1px solid ${t.border}`,
            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
          }}>
            <span style={{ fontSize: 12, color: t.textSub }}>Monto apertura:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ color: t.textMuted, fontSize: 12 }}>$</span>
              <input
                type="number" min="0" value={montoApertura}
                onChange={e => setMontoApertura(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && abrirCaja()}
                placeholder="0"
                style={{
                  width: 120, background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                  border: `1px solid ${t.border}`, borderRadius: 7,
                  color: t.text, fontSize: 14, padding: '8px 10px',
                  outline: 'none', fontFamily: 'monospace',
                }}
              />
            </div>
            <button onClick={abrirCaja} disabled={abriendo} style={{
              background: t.green, border: 'none', borderRadius: 8,
              color: '#fff', padding: '8px 20px', fontSize: 12,
              fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
            }}>
              {abriendo ? 'Abriendo…' : '🔓 Abrir caja'}
            </button>
          </div>
        )}
      </GlassCard>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4,1fr)', gap: 10 }}>
        <KpiCard label="Monto apertura"   value={cop(d.monto_apertura)}  sub="Base inicial"          icon="🏦" color={t.textSub} />
        <KpiCard label="Total ventas hoy" value={cop(d.total_ventas)}    sub="Efectivo + transf. + datafono" icon="💰" color={t.green} />
        <KpiCard label="Total gastos"     value={cop(d.total_gastos)}    sub="Todos los egresos"      icon="💸" color="#f87171" />
        <KpiCard label="Efectivo esperado" value={cop(d.efectivo_esperado)} sub="Caja - gastos en efectivo" icon="🧮" color={t.accent} />
      </div>

      {/* Venta Varia */}
      <GlassCard style={{ padding: '14px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13, color: t.text }}>
              🧾 Venta Varia
            </div>
            <div style={{ fontSize: 11, color: t.textMuted, marginTop: 2 }}>
              Para cuadrar ventas que no se alcanzaron a anotar
            </div>
          </div>
          <button
            onClick={() => setVariaOpen(v => !v)}
            style={{
              background: variaOpen ? t.accentSub : t.accent,
              border: 'none', borderRadius: 8,
              color: variaOpen ? t.accent : '#fff',
              padding: '7px 16px', fontSize: 12, fontWeight: 600,
              cursor: 'pointer', fontFamily: 'inherit',
              transition: 'all .15s',
            }}>
            {variaOpen ? '✕ Cancelar' : '+ Registrar'}
          </button>
        </div>

        {variaOpen && (
          <div style={{
            marginTop: 16, paddingTop: 16,
            borderTop: `1px solid ${t.border}`,
            display: 'flex', flexDirection: 'column', gap: 12,
          }}>
            {/* Monto */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: t.textSub, minWidth: 70 }}>Monto:</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, flex: 1 }}>
                <span style={{ color: t.textMuted, fontSize: 14, fontWeight: 600 }}>$</span>
                <input
                  type="number" min="0" value={variaMonto}
                  onChange={e => setVariaMonto(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && registrarVentaVaria()}
                  placeholder="0"
                  style={{
                    flex: 1, maxWidth: 160,
                    background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                    border: `1px solid ${t.border}`, borderRadius: 7,
                    color: t.text, fontSize: 14, padding: '8px 10px',
                    outline: 'none', fontFamily: 'monospace',
                  }}
                />
              </div>
            </div>

            {/* Descripción opcional */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12, color: t.textSub, minWidth: 70 }}>Descripción:</span>
              <input
                type="text" value={variaDesc}
                onChange={e => setVariaDesc(e.target.value)}
                placeholder="Ej: Sobrante cierre, ventas no anotadas…"
                style={{
                  flex: 1,
                  background: t.id === 'caramelo' ? '#f8fafc' : '#111',
                  border: `1px solid ${t.border}`, borderRadius: 7,
                  color: t.text, fontSize: 12, padding: '8px 10px',
                  outline: 'none', fontFamily: 'inherit',
                }}
              />
            </div>

            {/* Método de pago */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12, color: t.textSub, minWidth: 70 }}>Método:</span>
              <div style={{ display: 'flex', gap: 6 }}>
                {[
                  { val: 'efectivo',      label: '💵 Efectivo',      color: '#22c55e' },
                  { val: 'transferencia', label: '📲 Transferencia', color: '#3b82f6' },
                  { val: 'datafono',      label: '💳 Datafono',      color: '#a855f7' },
                ].map(op => (
                  <button
                    key={op.val}
                    onClick={() => setVariaMetodo(op.val)}
                    style={{
                      fontFamily: 'inherit', fontSize: 11.5, fontWeight: 600,
                      padding: '6px 13px', borderRadius: 20, cursor: 'pointer',
                      transition: 'all .15s',
                      background: variaMetodo === op.val ? op.color + '20' : 'transparent',
                      border: `2px solid ${variaMetodo === op.val ? op.color : t.border}`,
                      color: variaMetodo === op.val ? op.color : t.textMuted,
                    }}>
                    {op.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Botón registrar */}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={registrarVentaVaria}
                disabled={variando || !variaMonto}
                style={{
                  background: (!variaMonto || variando) ? t.border : t.accent,
                  border: 'none', borderRadius: 8,
                  color: (!variaMonto || variando) ? t.textMuted : '#fff',
                  padding: '9px 24px', fontSize: 13, fontWeight: 700,
                  cursor: (!variaMonto || variando) ? 'default' : 'pointer',
                  fontFamily: 'inherit', transition: 'all .15s',
                }}>
                {variando ? 'Registrando…' : '✓ Registrar venta varia'}
              </button>
            </div>
          </div>
        )}
      </GlassCard>

      {/* Desglose por método */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>
        <GlassCard>
          <SectionTitle>Ingresos por Método</SectionTitle>
          <MetodoRow label="Efectivo"      valor={d.efectivo}       icon="💵" t={t} />
          <MetodoRow label="Transferencia" valor={d.transferencias} icon="📲" t={t} />
          <MetodoRow label="Datáfono"      valor={d.datafono}       icon="💳" t={t} />
          {!d.efectivo && !d.transferencias && !d.datafono && (
            <div style={{ color: t.textMuted, fontSize: 12, padding: '12px 0' }}>Sin ventas registradas hoy.</div>
          )}
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            paddingTop: 12, marginTop: 4,
          }}>
            <span style={{ color: t.textMuted, fontSize: 12, fontWeight: 600 }}>TOTAL</span>
            <span style={{ color: t.green, fontSize: 16, fontWeight: 700 }}>{cop(d.total_ventas)}</span>
          </div>
        </GlassCard>

        <GlassCard>
          <SectionTitle>Resumen Efectivo</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { label: 'Apertura',         valor: d.monto_apertura,   color: t.textSub },
              { label: '+ Ventas efectivo', valor: d.efectivo,         color: t.green },
              { label: '— Gastos de caja', valor: -d.total_gastos_caja, color: '#f87171' },
            ].map((row, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${t.border}` }}>
                <span style={{ color: t.textSub, fontSize: 12 }}>{row.label}</span>
                <span style={{ color: row.color, fontWeight: 600 }}>
                  {row.valor < 0 ? `-${cop(Math.abs(row.valor))}` : cop(row.valor)}
                </span>
              </div>
            ))}
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 6 }}>
              <span style={{ color: t.text, fontWeight: 700 }}>= Efectivo en caja</span>
              <span style={{ color: t.accent, fontSize: 16, fontWeight: 700 }}>{cop(d.efectivo_esperado)}</span>
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Gastos del día */}
      <GlassCard style={{ padding: 0 }}>
        <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
          <SectionTitle>Gastos del Día ({gastos.length})</SectionTitle>
        </div>
        {gastos.length === 0 ? (
          <div style={{ padding: '24px', color: t.textMuted, fontSize: 12, textAlign: 'center' }}>
            Sin gastos registrados hoy.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: t.tableAlt }}>
                  {['Hora', 'Concepto', 'Categoría', 'Origen', 'Monto'].map((h, i) => (
                    <th key={i} style={{
                      padding: '9px 14px', textAlign: i === 4 ? 'right' : 'left',
                      fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
                      letterSpacing: '.08em', fontWeight: 500,
                      borderBottom: `1px solid ${t.border}`,
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gastos.map((g, i) => <GastoRow key={i} g={g} t={t} />)}
              </tbody>
              <tfoot>
                <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                  <td colSpan={4} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>
                    TOTAL GASTOS
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#f87171', fontWeight: 700, fontSize: 14 }}>
                    -{cop(d.total_gastos)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  )
}
