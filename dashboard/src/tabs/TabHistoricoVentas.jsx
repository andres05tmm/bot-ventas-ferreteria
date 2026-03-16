/**
 * TabHistoricoVentas.jsx
 * Registro manual de ventas diarias históricas
 * (días en que el bot no estaba disponible)
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
  const hoy    = new Date()
  const [año,  setAño]  = useState(hoy.getFullYear())
  const [mes,  setMes]  = useState(hoy.getMonth() + 1)
  const [datos, setDatos] = useState({})       // { "2026-03-01": 850000, ... }
  const [editando, setEditando] = useState({}) // { "2026-03-01": "850000" }
  const [guardando, setGuardando] = useState(false)
  const [msg, setMsg] = useState(null)
  const [loading, setLoading] = useState(false)

  // Cargar datos del servidor
  const cargar = useCallback(() => {
    setLoading(true)
    fetch(`${API_BASE}/historico/ventas?año=${año}&mes=${mes}`)
      .then(r => r.ok ? r.json() : {})
      .then(d => { setDatos(d); setEditando({}) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [año, mes])

  useEffect(() => { cargar() }, [cargar])

  const totalMes = Object.values(datos).reduce((a, b) => a + (b || 0), 0)
  const diasConVenta = Object.values(datos).filter(v => v > 0).length
  const promediodia = diasConVenta ? Math.round(totalMes / diasConVenta) : 0

  function handleChange(fecha, valor) {
    const solo = valor.replace(/[^0-9]/g, '')
    setEditando(prev => ({ ...prev, [fecha]: solo }))
  }

  function handleBlur(fecha) {
    const raw = editando[fecha]
    if (raw === undefined) return
    const num = raw === '' ? 0 : parseInt(raw, 10)
    setDatos(prev => ({ ...prev, [fecha]: num }))
  }

  async function guardar() {
    setGuardando(true)
    setMsg(null)
    try {
      const res = await fetch(`${API_BASE}/historico/ventas`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ año, mes, datos })
      })
      const json = await res.json()
      if (json.ok) {
        setMsg({ tipo: 'ok', texto: '✅ Guardado correctamente en Excel y Drive' })
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
  const dias    = Array.from({ length: numDias }, (_, i) => i + 1)

  // Agrupar en filas de 7 (semanas)
  const semanas = []
  for (let i = 0; i < dias.length; i += 7) {
    semanas.push(dias.slice(i, i + 7))
  }

  return (
    <div style={{ padding: '16px', maxWidth: 680, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:20 }}>
        <span style={{ fontSize:22 }}>📅</span>
        <div>
          <h2 style={{ margin:0, fontSize:18, color:'#fff', fontWeight:700 }}>
            Historial de Ventas
          </h2>
          <p style={{ margin:0, fontSize:12, color:'#888' }}>
            Registro manual de días sin bot
          </p>
        </div>
      </div>

      {/* Selector mes/año */}
      <div style={{ display:'flex', gap:10, marginBottom:20, flexWrap:'wrap' }}>
        <select
          value={mes}
          onChange={e => setMes(Number(e.target.value))}
          style={estiloSelect}
        >
          {MESES.map((m, i) => (
            <option key={i+1} value={i+1}>{m}</option>
          ))}
        </select>
        <select
          value={año}
          onChange={e => setAño(Number(e.target.value))}
          style={estiloSelect}
        >
          {[2024, 2025, 2026, 2027].map(a => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
      </div>

      {/* KPIs del mes */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:20 }}>
        <KPI label="Total del mes"    valor={cop(totalMes)}   color="#e74c3c" />
        <KPI label="Días con venta"   valor={diasConVenta}    color="#f39c12" />
        <KPI label="Promedio/día"     valor={cop(promediodia)}color="#2ecc71" />
      </div>

      {/* Grilla de días */}
      {loading ? (
        <div style={{ color:'#888', textAlign:'center', padding:40 }}>Cargando...</div>
      ) : (
        <div style={{ background:'#1a1a1a', borderRadius:12, padding:16, marginBottom:16 }}>
          {/* Encabezado días semana */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:4, marginBottom:8 }}>
            {['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'].map(d => (
              <div key={d} style={{ textAlign:'center', fontSize:11, color:'#666', fontWeight:600 }}>
                {d}
              </div>
            ))}
          </div>

          {/* Semanas */}
          {semanas.map((semana, si) => (
            <div key={si} style={{ display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:4, marginBottom:4 }}>
              {semana.map(dia => {
                const fecha  = formatFecha(año, mes, dia)
                const valor  = editando[fecha] !== undefined ? editando[fecha] : (datos[fecha] || '')
                const tieneValor = datos[fecha] > 0
                const esHoy  = fecha === formatFecha(hoy.getFullYear(), hoy.getMonth()+1, hoy.getDate())
                return (
                  <div key={dia} style={{
                    background: esHoy ? '#2d1a1a' : tieneValor ? '#1a2d1a' : '#242424',
                    border: `1px solid ${esHoy ? '#e74c3c44' : tieneValor ? '#2ecc7144' : '#333'}`,
                    borderRadius: 8,
                    padding: '6px 4px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 3,
                  }}>
                    <span style={{ fontSize:10, color: esHoy ? '#e74c3c' : '#555', fontWeight:600 }}>
                      {dia}
                    </span>
                    <input
                      type="text"
                      inputMode="numeric"
                      value={valor}
                      onChange={e => handleChange(fecha, e.target.value)}
                      onBlur={() => handleBlur(fecha)}
                      placeholder="0"
                      style={{
                        width: '100%',
                        background: 'transparent',
                        border: 'none',
                        outline: 'none',
                        textAlign: 'center',
                        fontSize: 10,
                        color: tieneValor ? '#2ecc71' : '#444',
                        fontWeight: tieneValor ? 700 : 400,
                        cursor: 'text',
                      }}
                    />
                  </div>
                )
              })}
              {/* Rellenar última semana si no tiene 7 días */}
              {semana.length < 7 && Array.from({ length: 7 - semana.length }).map((_, i) => (
                <div key={`vacio-${i}`} />
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Mensaje de estado */}
      {msg && (
        <div style={{
          padding: '10px 16px',
          borderRadius: 8,
          background: msg.tipo === 'ok' ? '#1a2d1a' : '#2d1a1a',
          border: `1px solid ${msg.tipo === 'ok' ? '#2ecc7155' : '#e74c3c55'}`,
          color: msg.tipo === 'ok' ? '#2ecc71' : '#e74c3c',
          fontSize: 13,
          marginBottom: 12,
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
          padding: '12px',
          background: guardando ? '#333' : '#e74c3c',
          color: '#fff',
          border: 'none',
          borderRadius: 10,
          fontSize: 14,
          fontWeight: 700,
          cursor: guardando ? 'not-allowed' : 'pointer',
          transition: 'background 0.2s',
        }}
      >
        {guardando ? 'Guardando...' : `💾 Guardar ${MESES[mes-1]} ${año}`}
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
      background: '#1a1a1a',
      borderRadius: 10,
      padding: '12px 10px',
      textAlign: 'center',
      border: `1px solid ${color}22`,
    }}>
      <div style={{ fontSize: 16, fontWeight: 700, color }}>{valor}</div>
      <div style={{ fontSize: 11, color: '#666', marginTop: 3 }}>{label}</div>
    </div>
  )
}

const estiloSelect = {
  background: '#1a1a1a',
  border: '1px solid #333',
  borderRadius: 8,
  color: '#fff',
  padding: '8px 14px',
  fontSize: 14,
  cursor: 'pointer',
  flex: 1,
  minWidth: 120,
}
