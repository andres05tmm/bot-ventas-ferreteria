/**
 * TabHistoricoVentas.jsx
 * Historial de ventas diarias — integrado con auto-sync del bot
 */
import { useState, useEffect, useCallback } from 'react'
import {
  API_BASE, cop, useTheme, Card, GlassCard, KpiCard,
  SectionTitle, Spinner, useIsMobile,
} from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'

const MESES = [
  'Enero','Febrero','Marzo','Abril','Mayo','Junio',
  'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'
]

const DIAS_SEMANA = ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom']

function diasEnMes(mes, año) { return new Date(año, mes, 0).getDate() }

function formatFecha(año, mes, dia) {
  return `${año}-${String(mes).padStart(2,'0')}-${String(dia).padStart(2,'0')}`
}

/* ── Intensidad para heatmap (0 → sin color, 1 → máximo) ──────────────── */
function intensidad(valor, max) {
  if (!max || !valor) return 0
  return Math.min(valor / max, 1)
}

export default function TabHistoricoVentas() {
  const t       = useTheme()
  const mobile  = useIsMobile()
  const hoy     = new Date()
  const { authFetch } = useAuth()

  const [año, setAño]   = useState(hoy.getFullYear())
  const [mes, setMes]   = useState(hoy.getMonth() + 1)
  const [celdas, setCeldas]       = useState({})
  const [diario, setDiario]       = useState({})
  const [guardando, setGuardando] = useState(false)
  const [syncing, setSyncing]     = useState(false)
  const [msg, setMsg]             = useState(null)
  const [loading, setLoading]     = useState(false)
  const [editMode, setEditMode]   = useState(false)

  /* ── Cargar datos ──────────────────────────────────────────────────────── */
  const cargar = useCallback(() => {
    setLoading(true)
    Promise.all([
      authFetch(`${API_BASE}/historico/ventas?año=${año}&mes=${mes}`).then(r => r.ok ? r.json() : {}),
      authFetch(`${API_BASE}/historico/diario?año=${año}&mes=${mes}`).then(r => r.ok ? r.json() : {}),
    ])
      .then(([ventas, diar]) => {
        const str = {}
        Object.entries(ventas).forEach(([k, v]) => {
          if (v && v > 0) str[k] = String(v)
        })
        setCeldas(str)
        setDiario(diar || {})
      })
      .catch(() => { setCeldas({}); setDiario({}) })
      .finally(() => setLoading(false))
  }, [año, mes])

  useEffect(() => { cargar() }, [cargar])

  /* ── KPIs ──────────────────────────────────────────────────────────────── */
  const valores    = Object.values(celdas).map(v => parseInt(v) || 0)
  const totalMes   = valores.reduce((a, b) => a + b, 0)
  const diasVenta  = valores.filter(v => v > 0).length
  const promedio   = diasVenta ? Math.round(totalMes / diasVenta) : 0
  const maxDia     = Math.max(...valores, 1)
  const mejorDia   = valores.length ? Math.max(...valores) : 0

  // Totales de métodos de pago desde historico_diario
  const totalEfectivo     = Object.values(diario).reduce((a, d) => a + (d.efectivo || 0), 0)
  const totalTransferencia = Object.values(diario).reduce((a, d) => a + (d.transferencia || 0), 0)
  const totalDatafono     = Object.values(diario).reduce((a, d) => a + (d.datafono || 0), 0)
  const hayDesglose       = totalEfectivo > 0 || totalTransferencia > 0 || totalDatafono > 0

  // Filas de la tabla ordenadas por fecha descendente
  const filasTabla = Object.entries(diario)
    .filter(([, d]) => d.ventas > 0)
    .sort(([a], [b]) => b.localeCompare(a))

  /* ── Calendario ────────────────────────────────────────────────────────── */
  const numDias   = diasEnMes(mes, año)
  const primerDia = new Date(año, mes - 1, 1).getDay()
  const offset    = primerDia === 0 ? 6 : primerDia - 1

  const hoyStr = formatFecha(hoy.getFullYear(), hoy.getMonth() + 1, hoy.getDate())
  const esMesActual = año === hoy.getFullYear() && mes === (hoy.getMonth() + 1)

  /* ── Handlers ──────────────────────────────────────────────────────────── */
  function cambiar(fecha, valor) {
    const solo = valor.replace(/[^0-9]/g, '')
    setCeldas(prev => ({ ...prev, [fecha]: solo }))
  }

  function mostrarMsg(tipo, texto) {
    setMsg({ tipo, texto })
    setTimeout(() => setMsg(null), 4000)
  }

  async function guardar() {
    setGuardando(true)
    const datos = {}
    Object.entries(celdas).forEach(([k, v]) => {
      const n = parseInt(v)
      if (n > 0) datos[k] = n
    })
    try {
      const res = await authFetch(`${API_BASE}/historico/ventas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ año, mes, datos })
      })
      const json = await res.json()
      if (json.ok) {
        mostrarMsg('ok', `${json.registros} días guardados en Drive`)
        setEditMode(false)
      } else {
        mostrarMsg('err', json.error || 'Error al guardar')
      }
    } catch {
      mostrarMsg('err', 'No se pudo conectar con el servidor')
    } finally {
      setGuardando(false)
    }
  }

  async function syncRango() {
    setSyncing(true)
    try {
      const res  = await authFetch(`${API_BASE}/historico/sync-rango?dias=60`, { method: 'POST' })
      const json = await res.json()
      if (json.ok) {
        mostrarMsg('ok', `${json.nuevos} días nuevos, ${json.actualizados} actualizados`)
        cargar()
      } else {
        mostrarMsg('err', json.detail || 'Error al sincronizar')
      }
    } catch {
      mostrarMsg('err', 'No se pudo conectar con el servidor')
    } finally {
      setSyncing(false)
    }
  }

  async function sincronizarDesdeExcel() {
    setSyncing(true)
    try {
      const res  = await authFetch(`${API_BASE}/historico/sincronizar-excel`, { method: 'POST' })
      const json = await res.json()
      if (json.ok) {
        mostrarMsg('ok', `${json.registros} días importados desde Excel de Drive`)
        cargar()
      } else {
        mostrarMsg('err', json.error || 'Error al sincronizar')
      }
    } catch {
      mostrarMsg('err', 'No se pudo conectar con el servidor')
    } finally {
      setSyncing(false)
    }
  }

  /* ── Navegar mes ───────────────────────────────────────────────────────── */
  function mesAnterior() {
    if (mes === 1) { setMes(12); setAño(a => a - 1) }
    else setMes(m => m - 1)
  }
  function mesSiguiente() {
    if (mes === 12) { setMes(1); setAño(a => a + 1) }
    else setMes(m => m + 1)
  }

  /* ── Color del heatmap según intensidad ────────────────────────────────── */
  function heatColor(val) {
    const i = intensidad(val, maxDia)
    if (i === 0) return 'transparent'
    // Mezclar con el accent del tema
    const alpha = Math.round((0.08 + i * 0.22) * 255)  // FIX: faltaba × 255; antes siempre era 0 → transparente
    return `${t.accent}${alpha.toString(16).padStart(2, '0')}`
  }

  /* ── Render ────────────────────────────────────────────────────────────── */
  return (
    <div style={{ padding: mobile ? '12px 8px' : '16px 0', maxWidth: 760, margin: '0 auto' }}>

      {/* ── Header + Nav ───────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 20, flexWrap: 'wrap', gap: 10,
      }}>
        <SectionTitle>
          <span style={{ marginRight: 8 }}>📊</span>
          Histórico de Ventas
        </SectionTitle>

        {/* Navegación de mes */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <NavBtn t={t} onClick={mesAnterior}>‹</NavBtn>
          <div style={{
            display: 'flex', gap: 6, alignItems: 'center',
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 8, padding: '6px 12px',
          }}>
            <select value={mes} onChange={e => setMes(Number(e.target.value))} style={selStyle(t)}>
              {MESES.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
            </select>
            <select value={año} onChange={e => setAño(Number(e.target.value))} style={selStyle(t)}>
              {[2024,2025,2026,2027].map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <NavBtn t={t} onClick={mesSiguiente}>›</NavBtn>

          {esMesActual && (
            <span style={{
              fontSize: 9, color: t.accent, fontWeight: 600,
              background: t.accentSub, padding: '3px 8px',
              borderRadius: 99, letterSpacing: '.03em', marginLeft: 4,
            }}>
              MES ACTUAL
            </span>
          )}
        </div>
      </div>

      {/* ── KPIs ───────────────────────────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(4, 1fr)',
        gap: 10, marginBottom: 20,
      }}>
        <KpiCard label="Total del mes"   value={cop(totalMes)}  icon="💰" color={t.accent} />
        <KpiCard label="Días con venta"  value={diasVenta}      icon="📅" color={t.yellow} />
        <KpiCard label="Promedio / día"  value={cop(promedio)}  icon="📈" color={t.green}  />
        <KpiCard label="Mejor día"       value={cop(mejorDia)}  icon="🏆" color={t.blue}   />
      </div>

      {/* ── Calendario ─────────────────────────────────────────────────── */}
      <GlassCard style={{ padding: mobile ? 10 : 16, marginBottom: 16 }}>
        {loading ? <Spinner /> : (
          <>
            {/* Header días */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
              gap: 4, marginBottom: 8,
            }}>
              {DIAS_SEMANA.map(d => (
                <div key={d} style={{
                  textAlign: 'center', fontSize: 10, fontWeight: 600,
                  color: t.textMuted, padding: '4px 0',
                  letterSpacing: '.04em', textTransform: 'uppercase',
                }}>
                  {d}
                </div>
              ))}
            </div>

            {/* Grid de días */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
              gap: 4,
            }}>
              {/* Offset vacío */}
              {Array.from({ length: offset }).map((_, i) => <div key={`e${i}`} />)}

              {/* Días del mes */}
              {Array.from({ length: numDias }, (_, i) => i + 1).map(dia => {
                const fecha    = formatFecha(año, mes, dia)
                const valor    = celdas[fecha] ?? ''
                const valNum   = parseInt(valor) || 0
                const tieneVal = valNum > 0
                const esHoy    = fecha === hoyStr
                const esFuturo = new Date(año, mes - 1, dia) > hoy

                return (
                  <DiaCell
                    key={dia}
                    t={t}
                    dia={dia}
                    valor={valor}
                    tieneVal={tieneVal}
                    esHoy={esHoy}
                    esFuturo={esFuturo}
                    editMode={editMode}
                    heatBg={heatColor(valNum)}
                    onChange={v => cambiar(fecha, v)}
                    mobile={mobile}
                  />
                )
              })}
            </div>

            {/* Leyenda heatmap */}
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
              gap: 6, marginTop: 12, paddingTop: 10,
              borderTop: `1px solid ${t.borderSoft}`,
            }}>
              <span style={{ fontSize: 9, color: t.textMuted }}>Menos</span>
              {[0, 0.2, 0.4, 0.7, 1].map((lv, i) => (
                <div key={i} style={{
                  width: 12, height: 12, borderRadius: 3,
                  background: lv === 0
                    ? t.card
                    : `${t.accent}${Math.round((0.08 + lv * 0.22) * 255).toString(16).padStart(2, '0')}`,
                  border: `1px solid ${t.borderSoft}`,
                }} />
              ))}
              <span style={{ fontSize: 9, color: t.textMuted }}>Más</span>
            </div>
          </>
        )}
      </GlassCard>

      {/* ── Toast ──────────────────────────────────────────────────────── */}
      {msg && (
        <div style={{
          padding: '10px 16px', borderRadius: 8, marginBottom: 12,
          background: msg.tipo === 'ok' ? `${t.green}14` : `${t.accent}14`,
          border: `1px solid ${msg.tipo === 'ok' ? t.green : t.accent}44`,
          color: msg.tipo === 'ok' ? t.green : t.accent,
          fontSize: 12, fontWeight: 500,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span>{msg.tipo === 'ok' ? '✓' : '✕'}</span>
          {msg.texto}
        </div>
      )}

      {/* ── Métodos de pago (KPIs) ─────────────────────────────────────── */}
      {hayDesglose && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(3, 1fr)',
          gap: 10, marginBottom: 16,
        }}>
          <KpiCard label="Efectivo"      value={cop(totalEfectivo)}      icon="💵" color={t.green}  />
          <KpiCard label="Transferencia" value={cop(totalTransferencia)} icon="📲" color={t.blue}   />
          <KpiCard label="Datáfono"      value={cop(totalDatafono)}      icon="💳" color={t.yellow} />
        </div>
      )}

      {/* ── Tabla de desglose por día ──────────────────────────────────── */}
      {filasTabla.length > 0 && (
        <GlassCard style={{ padding: 0, marginBottom: 16, overflow: 'hidden' }}>
          <div style={{
            padding: '10px 14px', borderBottom: `1px solid ${t.border}`,
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: t.text }}>📋 Desglose por día</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: t.cardHover }}>
                  {['Fecha','Ventas','Efectivo','Transf.','Datáfono','Gastos','Caja Neta'].map(h => (
                    <th key={h} style={{
                      padding: '8px 10px', textAlign: 'right', fontWeight: 600,
                      color: t.textMuted, letterSpacing: '.03em', fontSize: 10,
                      whiteSpace: 'nowrap',
                      ...(h === 'Fecha' ? { textAlign: 'left' } : {}),
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filasTabla.map(([fecha, d], idx) => {
                  const cajaNeta = (d.ventas || 0) - (d.gastos || 0) - (d.abonos_proveedores || 0)
                  const bg = idx % 2 === 1 ? t.cardHover : 'transparent'
                  return (
                    <tr key={fecha} style={{ background: bg }}>
                      <td style={{ padding: '7px 10px', color: t.textSub, fontWeight: 500 }}>
                        {fecha.slice(5).replace('-', '/')}
                      </td>
                      <Td t={t} val={d.ventas}                color={t.text}   />
                      <Td t={t} val={d.efectivo}              color={t.green}  />
                      <Td t={t} val={d.transferencia}         color={t.blue}   />
                      <Td t={t} val={d.datafono}              color={t.yellow} />
                      <Td t={t} val={d.gastos}                color={d.gastos > 0 ? t.accent : t.textMuted} />
                      <Td t={t} val={cajaNeta} bold           color={cajaNeta >= 0 ? t.green : t.accent} />
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr style={{ borderTop: `2px solid ${t.border}`, background: t.cardHover }}>
                  <td style={{ padding: '8px 10px', fontWeight: 700, color: t.text, fontSize: 11 }}>TOTAL</td>
                  <Td t={t} val={totalMes}          bold color={t.text}   />
                  <Td t={t} val={totalEfectivo}     bold color={t.green}  />
                  <Td t={t} val={totalTransferencia} bold color={t.blue}  />
                  <Td t={t} val={totalDatafono}     bold color={t.yellow} />
                  <Td t={t} val={Object.values(diario).reduce((a, d) => a + (d.gastos || 0), 0)} bold color={t.accent} />
                  <Td t={t} val={Object.values(diario).reduce((a, d) => a + (d.ventas || 0) - (d.gastos || 0) - (d.abonos_proveedores || 0), 0)} bold color={t.green} />
                </tr>
              </tfoot>
            </table>
          </div>
        </GlassCard>
      )}

      {/* ── Acciones ───────────────────────────────────────────────────── */}
      <GlassCard style={{ padding: 14 }}>
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 8,
          alignItems: 'center',
        }}>
          {/* Toggle edición manual */}
          <ActionBtn
            t={t}
            primary={editMode}
            onClick={() => setEditMode(!editMode)}
            icon={editMode ? '✕' : '✏️'}
            label={editMode ? 'Cancelar edición' : 'Editar manualmente'}
          />

          {editMode && (
            <ActionBtn
              t={t} primary disabled={guardando}
              onClick={guardar}
              icon="💾" label={guardando ? 'Guardando…' : `Guardar ${MESES[mes-1]}`}
            />
          )}

          <div style={{ flex: 1 }} />

          {/* Sync desde ventas reales */}
          <ActionBtn
            t={t} disabled={syncing}
            onClick={syncRango}
            icon="🔄" label={syncing ? 'Sincronizando…' : 'Sync desde ventas'}
            title="Importa totales de los últimos 60 días desde el registro de ventas"
          />

          {/* Sync desde Excel Drive */}
          <ActionBtn
            t={t} disabled={syncing}
            onClick={sincronizarDesdeExcel}
            icon="📥" label="Desde Excel"
            title="Importar desde historico_ventas.xlsx en Drive"
          />
        </div>

        <p style={{
          fontSize: 10, color: t.textMuted, margin: '10px 0 0',
          textAlign: 'center', lineHeight: 1.5,
        }}>
          El total de hoy se actualiza en vivo desde Google Sheets
          · Al ejecutar <code style={{ color: t.accent }}>/cerrar</code> queda guardado en el histórico automáticamente
        </p>
      </GlassCard>
    </div>
  )
}


/* ═══════════════════════════════════════════════════════════════════════════
   SUB-COMPONENTES
   ═══════════════════════════════════════════════════════════════════════════ */

function DiaCell({ t, dia, valor, tieneVal, esHoy, esFuturo, editMode, heatBg, onChange, mobile }) {
  const [hov, setHov] = useState(false)

  const borderColor = esHoy
    ? t.accent
    : hov && tieneVal
      ? t.green + '88'
      : t.borderSoft

  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: esHoy
          ? `${t.accent}18`
          : heatBg || t.card,
        border: `1px solid ${borderColor}`,
        borderRadius: 8,
        padding: mobile ? '5px 2px 4px' : '6px 4px 5px',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 2,
        minHeight: mobile ? 48 : 56,
        opacity: esFuturo ? 0.35 : 1,
        transition: 'border-color .15s, background .15s, transform .1s',
        transform: hov && !esFuturo ? 'scale(1.04)' : 'scale(1)',
        cursor: editMode ? 'text' : 'default',
      }}
    >
      {/* Número del día */}
      <span style={{
        fontSize: 10, fontWeight: 700,
        color: esHoy ? t.accent : t.textMuted,
        userSelect: 'none', lineHeight: 1,
      }}>
        {dia}
      </span>

      {/* Valor o input */}
      {editMode && !esFuturo ? (
        <input
          type="text"
          inputMode="numeric"
          value={valor}
          onChange={e => onChange(e.target.value)}
          placeholder="—"
          style={{
            width: '92%', background: 'transparent',
            border: 'none',
            borderBottom: `1px solid ${tieneVal ? t.green + '55' : t.borderSoft}`,
            outline: 'none', textAlign: 'center',
            fontSize: mobile ? 9 : 10,
            color: tieneVal ? t.green : t.textMuted,
            fontWeight: tieneVal ? 700 : 400,
            padding: '2px 0', fontFamily: 'inherit',
          }}
        />
      ) : (
        <span style={{
          fontSize: mobile ? 11 : 13,
          fontWeight: tieneVal ? 600 : 400,
          color: tieneVal ? t.green : t.textMuted,
          fontVariantNumeric: 'tabular-nums',
          lineHeight: 1.3,
          opacity: tieneVal ? 1 : 0.5,
        }}>
          {tieneVal ? formatK(parseInt(valor)) : '—'}
        </span>
      )}

      {/* Indicador hoy */}
      {esHoy && (
        <div style={{
          width: 4, height: 4, borderRadius: '50%',
          background: t.accent, marginTop: 1,
        }} />
      )}
    </div>
  )
}

function Td({ t, val, color, bold }) {
  const n = parseFloat(val) || 0
  return (
    <td style={{
      padding: '7px 10px', textAlign: 'right',
      color: n === 0 ? t.textMuted : (color || t.text),
      fontWeight: bold ? 700 : 400,
      fontVariantNumeric: 'tabular-nums',
      opacity: n === 0 ? 0.4 : 1,
      whiteSpace: 'nowrap',
    }}>
      {n === 0 ? '—' : cop(n)}
    </td>
  )
}

function NavBtn({ t, onClick, children }) {
  const [hov, setHov] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        width: 32, height: 32, borderRadius: 8,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: hov ? t.accentSub : t.card,
        border: `1px solid ${hov ? t.accent + '44' : t.border}`,
        color: hov ? t.accent : t.textSub,
        fontSize: 16, fontWeight: 700,
        cursor: 'pointer', fontFamily: 'inherit',
        transition: 'all .15s',
      }}
    >
      {children}
    </button>
  )
}

function ActionBtn({ t, onClick, icon, label, primary, disabled, title }) {
  const [hov, setHov] = useState(false)
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '7px 14px', borderRadius: 8,
        fontSize: 11, fontWeight: 500, fontFamily: 'inherit',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        transition: 'all .15s',
        background: primary
          ? (hov ? t.accentHov : t.accent)
          : (hov ? t.cardHover : t.card),
        color: primary ? '#fff' : t.textSub,
        border: `1px solid ${primary ? 'transparent' : (hov ? t.accent + '44' : t.border)}`,
      }}
    >
      <span style={{ fontSize: 13 }}>{icon}</span>
      {label}
    </button>
  )
}

/* ── Helpers ───────────────────────────────────────────────────────────────── */

function formatK(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2).replace('.', ',')}M`
  if (n >= 100_000) return `${Math.round(n / 1_000)}k`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace('.', ',')}k`
  return String(n)
}

function selStyle(t) {
  return {
    background: 'transparent', border: 'none',
    color: t.text, fontSize: 13, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
    outline: 'none', padding: '2px 4px',
  }
}
