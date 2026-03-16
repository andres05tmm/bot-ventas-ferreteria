/**
 * TabHistoricoVentas.jsx
 * Registro manual de ventas diarias históricas
 */
import { useState, useEffect, useCallback } from 'react'
import { API_BASE, cop } from '../components/shared.jsx'

const MESES = [
  'Enero','Febrero','Marzo','Abril','Mayo','Junio',
  'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'
]

function diasEnMes(mes, año) {
  return new Date(año, mes, 0).getDate()
}

function formatFecha(año, mes, dia) {
  return `${año}-${String(mes).padStart(2,'0')}-${String(dia).padStart(2,'0')}`
}

export default function TabHistoricoVentas() {
  const hoy   = new Date()
  const [año, setAño]   = useState(2025)
  const [mes, setMes]   = useState(11)
  // Un solo estado: { "2026-03-01": "850000" } — siempre strings para el input
  const [celdas, setCeldas]       = useState({})
  const [guardando, setGuardando] = useState(false)
  const [msg, setMsg]             = useState(null)
  const [loading, setLoading]     = useState(false)

  // Cargar datos del servidor al cambiar mes/año
  const cargar = useCallback(() => {
    setLoading(true)
    fetch(`${API_BASE}/historico/ventas?año=${año}&mes=${mes}`)
      .then(r => r.ok ? r.json() : {})
      .then(d => {
        // Convertir { "2026-03-01": 850000 } → { "2026-03-01": "850000" }
        const str = {}
        Object.entries(d).forEach(([k, v]) => {
          if (v && v > 0) str[k] = String(v)
        })
        setCeldas(str)
      })
      .catch(() => setCeldas({}))
      .finally(() => setLoading(false))
  }, [año, mes])

  useEffect(() => { cargar() }, [cargar])

  // KPIs
  const totalMes = Object.values(celdas)
    .reduce((a, b) => a + (parseInt(b) || 0), 0)
  const diasConVenta = Object.values(celdas)
    .filter(v => parseInt(v) > 0).length
  const promedio = diasConVenta ? Math.round(totalMes / diasConVenta) : 0

  function cambiar(fecha, valor) {
    const solo = valor.replace(/[^0-9]/g, '')
    setCeldas(prev => ({ ...prev, [fecha]: solo }))
  }

  async function sincronizarDesdeExcel() {
    setGuardando(true)
    setMsg(null)
    try {
      const res  = await fetch(`${API_BASE}/historico/sincronizar-excel`, { method: 'POST' })
      const json = await res.json()
      if (json.ok) {
        setMsg({ tipo: 'ok', texto: `✅ Sincronizado desde Excel — ${json.registros} días importados` })
        cargar()  // recargar datos del mes actual
      } else {
        setMsg({ tipo: 'err', texto: `❌ ${json.error || 'Error al sincronizar'}` })
      }
    } catch {
      setMsg({ tipo: 'err', texto: '❌ No se pudo conectar con el servidor' })
    } finally {
      setGuardando(false)
      setTimeout(() => setMsg(null), 5000)
    }
  }
    setGuardando(true)
    setMsg(null)
    // Convertir strings a números
    const datos = {}
    Object.entries(celdas).forEach(([k, v]) => {
      const n = parseInt(v)
      if (n > 0) datos[k] = n
    })
    try {
      const res = await fetch(`${API_BASE}/historico/ventas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ año, mes, datos })
      })
      const json = await res.json()
      if (json.ok) {
        setMsg({ tipo: 'ok', texto: `✅ ${json.registros} días guardados en Drive` })
      } else {
        setMsg({ tipo: 'err', texto: `❌ ${json.error || 'Error al guardar'}` })
      }
    } catch {
      setMsg({ tipo: 'err', texto: '❌ No se pudo conectar con el servidor' })
    } finally {
      setGuardando(false)
      setTimeout(() => setMsg(null), 4000)
    }
  }

  const numDias = diasEnMes(mes, año)
  // Día de la semana en que empieza el mes (0=Dom, ajustar a Lun=0)
  const primerDia = new Date(año, mes - 1, 1).getDay()
  const offset    = primerDia === 0 ? 6 : primerDia - 1  // Lun=0 ... Dom=6

  return (
    <div style={{ padding:'16px', maxWidth:700, margin:'0 auto' }}>

      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:20 }}>
        <span style={{ fontSize:22 }}>📅</span>
        <div>
          <h2 style={{ margin:0, fontSize:18, fontWeight:700 }}>Historial de Ventas</h2>
          <p style={{ margin:0, fontSize:12, color:'#888' }}>Registro manual de días sin bot</p>
        </div>
      </div>

      {/* Selectores */}
      <div style={{ display:'flex', gap:10, marginBottom:20 }}>
        <select value={mes} onChange={e => setMes(Number(e.target.value))} style={estiloSelect}>
          {MESES.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
        </select>
        <select value={año} onChange={e => setAño(Number(e.target.value))} style={estiloSelect}>
          {[2024,2025,2026,2027].map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>

      {/* KPIs */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:20 }}>
        <KPI label="Total del mes"  valor={cop(totalMes)}   color="#e74c3c" />
        <KPI label="Días con venta" valor={diasConVenta}    color="#f39c12" />
        <KPI label="Promedio/día"   valor={cop(promedio)}   color="#27ae60" />
      </div>

      {/* Grilla */}
      {loading ? (
        <div style={{ textAlign:'center', padding:40, color:'#888' }}>Cargando...</div>
      ) : (
        <div style={{ background:'#111', borderRadius:12, padding:14, marginBottom:16 }}>
          {/* Encabezado días */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:3, marginBottom:6 }}>
            {['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'].map(d => (
              <div key={d} style={{ textAlign:'center', fontSize:11, color:'#555', fontWeight:600, padding:'4px 0' }}>
                {d}
              </div>
            ))}
          </div>

          {/* Días del mes con offset */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:3 }}>
            {/* Celdas vacías al inicio */}
            {Array.from({ length: offset }).map((_, i) => (
              <div key={`e${i}`} />
            ))}

            {/* Días reales */}
            {Array.from({ length: numDias }, (_, i) => i + 1).map(dia => {
              const fecha    = formatFecha(año, mes, dia)
              const valor    = celdas[fecha] ?? ''
              const tieneVal = parseInt(valor) > 0
              const esHoy    = fecha === formatFecha(
                hoy.getFullYear(), hoy.getMonth() + 1, hoy.getDate()
              )

              return (
                <div key={dia} style={{
                  background: esHoy ? '#2a1010' : tieneVal ? '#0d1f0d' : '#1a1a1a',
                  border: `1px solid ${esHoy ? '#c0392b44' : tieneVal ? '#27ae6044' : '#2a2a2a'}`,
                  borderRadius: 8,
                  padding: '6px 4px 4px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: 2,
                  minHeight: 52,
                }}>
                  <span style={{
                    fontSize: 10,
                    color: esHoy ? '#e74c3c' : '#444',
                    fontWeight: 700,
                    userSelect: 'none',
                  }}>
                    {dia}
                  </span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={valor}
                    onChange={e => cambiar(fecha, e.target.value)}
                    placeholder="—"
                    style={{
                      width: '90%',
                      background: 'transparent',
                      border: 'none',
                      borderBottom: `1px solid ${tieneVal ? '#27ae6066' : '#2a2a2a'}`,
                      outline: 'none',
                      textAlign: 'center',
                      fontSize: 10,
                      color: tieneVal ? '#27ae60' : '#555',
                      fontWeight: tieneVal ? 700 : 400,
                      padding: '2px 0',
                      cursor: 'text',
                    }}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Mensaje */}
      {msg && (
        <div style={{
          padding: '10px 16px',
          borderRadius: 8,
          marginBottom: 12,
          background: msg.tipo === 'ok' ? '#0d1f0d' : '#2a1010',
          border: `1px solid ${msg.tipo === 'ok' ? '#27ae6055' : '#c0392b55'}`,
          color: msg.tipo === 'ok' ? '#27ae60' : '#e74c3c',
          fontSize: 13,
        }}>
          {msg.texto}
        </div>
      )}

      {/* Botón guardar */}
      <button
        onClick={guardar}
        disabled={guardando}
        style={{
          width: '100%',
          padding: 14,
          background: guardando ? '#333' : '#e74c3c',
          color: '#fff',
          border: 'none',
          borderRadius: 10,
          fontSize: 14,
          fontWeight: 700,
          cursor: guardando ? 'not-allowed' : 'pointer',
          marginBottom: 8,
        }}
      >
        {guardando ? 'Guardando...' : `💾 Guardar ${MESES[mes-1]} ${año}`}
      </button>

      {/* Botón sincronizar desde Excel */}
      <button
        onClick={sincronizarDesdeExcel}
        disabled={guardando}
        style={{
          width: '100%',
          padding: 12,
          background: 'transparent',
          color: '#888',
          border: '1px solid #333',
          borderRadius: 10,
          fontSize: 13,
          cursor: guardando ? 'not-allowed' : 'pointer',
        }}
      >
        🔄 Importar cambios desde Excel de Drive
      </button>

      <p style={{ textAlign:'center', fontSize:11, color:'#555', marginTop:10 }}>
        Se guarda en <code>historico_ventas.xlsx</code> en Google Drive
      </p>
    </div>
  )
}

function KPI({ label, valor, color }) {
  return (
    <div style={{
      background: '#111',
      borderRadius: 10,
      padding: '12px 10px',
      textAlign: 'center',
      border: `1px solid ${color}22`,
    }}>
      <div style={{ fontSize:16, fontWeight:700, color }}>{valor}</div>
      <div style={{ fontSize:11, color:'#666', marginTop:3 }}>{label}</div>
    </div>
  )
}

const estiloSelect = {
  background: '#111',
  border: '1px solid #333',
  borderRadius: 8,
  color: '#fff',
  padding: '8px 14px',
  fontSize: 14,
  cursor: 'pointer',
  flex: 1,
}
