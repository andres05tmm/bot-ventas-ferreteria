/**
 * TabLibroIVA.jsx — Libro de IVA · Régimen Simple de Tributación
 *
 * Secciones:
 *   1. Selector de período (bimestral DIAN o fechas custom)
 *   2. KPIs: IVA generado, descontable, neto
 *   3. Cuadro neto: ventas FE - compras - saldo anterior = IVA a pagar
 *   4. Historial de cierres bimestrales con botón "Cerrar período"
 *   5. Libros detallados: ventas FE | compras con IVA
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import {
  useTheme, GlassCard, SectionTitle,
  Spinner, ErrorMsg, EmptyState, Th,
  cop, API_BASE,
} from '../components/shared.jsx'
import { useAuth } from '../hooks/useAuth.js'

// ── Constantes ────────────────────────────────────────────────────────────────

const BIMESTRES = [
  { n:1, label:'Ene – Feb', ini:'01-01', fin:'02-28' },
  { n:2, label:'Mar – Abr', ini:'03-01', fin:'04-30' },
  { n:3, label:'May – Jun', ini:'05-01', fin:'06-30' },
  { n:4, label:'Jul – Ago', ini:'07-01', fin:'08-31' },
  { n:5, label:'Sep – Oct', ini:'09-01', fin:'10-31' },
  { n:6, label:'Nov – Dic', ini:'11-01', fin:'12-31' },
]
const NOMBRES_BIM = ['Ene-Feb','Mar-Abr','May-Jun','Jul-Ago','Sep-Oct','Nov-Dic']

function bimDates(n) {
  const año = new Date().getFullYear()
  const b   = BIMESTRES[n - 1]
  const fin = n === 1
    ? ((año % 4 === 0 && año % 100 !== 0) || año % 400 === 0 ? '02-29' : '02-28')
    : b.fin
  return [`${año}-${b.ini}`, `${año}-${fin}`]
}

function currentBim() { return Math.ceil((new Date().getMonth() + 1) / 2) }

function fmtF(s) {
  if (!s) return '—'
  const [y,m,d] = s.split('-')
  const mn = ['','ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']
  return `${d} ${mn[+m]} ${y}`
}

// ── KPI ───────────────────────────────────────────────────────────────────────

function Kpi({ label, value, sub, color, icon }) {
  const t = useTheme(); const c = color || t.accent
  return (
    <div style={{ flex:1, minWidth:150, background:t.cardGrad, border:`1px solid ${t.border}`, borderRadius:14, padding:'14px 18px', boxShadow:t.shadowCard, position:'relative', overflow:'hidden' }}>
      <div style={{ position:'absolute', left:0, top:'20%', bottom:'20%', width:3, background:`linear-gradient(180deg,${c}00,${c},${c}00)`, borderRadius:99 }}/>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div>
          <div style={{ fontSize:10, fontWeight:600, color:t.textMuted, letterSpacing:'.06em', textTransform:'uppercase', marginBottom:6 }}>{label}</div>
          <div style={{ fontSize:21, fontWeight:700, color:t.text, fontVariantNumeric:'tabular-nums' }}>{value}</div>
          {sub && <div style={{ fontSize:11, color:t.textMuted, marginTop:3 }}>{sub}</div>}
        </div>
        {icon && <div style={{ width:32, height:32, borderRadius:9, background:`${c}15`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:15 }}>{icon}</div>}
      </div>
    </div>
  )
}

// ── Cuadro IVA neto ───────────────────────────────────────────────────────────

function CuadroNeto({ resumen }) {
  const t = useTheme()
  if (!resumen) return null
  const { ventas, compras, iva_neto } = resumen
  const aFavor = iva_neto.a_favor === 'empresa'
  return (
    <GlassCard style={{ padding:0 }}>
      <div style={{ padding:'14px 20px', borderBottom:`1px solid ${t.border}` }}>
        <SectionTitle>⚖️ Cuadro IVA neto del período</SectionTitle>
      </div>
      <div style={{ padding:'16px 20px', display:'flex', flexDirection:'column', gap:0 }}>

        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'12px 16px', background:t.tableAlt, borderRadius:'10px 10px 0 0', borderBottom:`1px solid ${t.border}` }}>
          <div>
            <div style={{ fontSize:12, fontWeight:600, color:t.text }}>🧾 IVA generado — ventas con FE emitida</div>
            <div style={{ fontSize:11, color:t.textMuted, marginTop:2 }}>
              {ventas.por_tarifa.map(r=>`Tarifa ${r.tarifa}%: ${cop(r.iva_valor)}`).join(' · ') || 'Sin facturas electrónicas emitidas'}
            </div>
          </div>
          <div style={{ fontSize:18, fontWeight:700, color:t.accent, fontVariantNumeric:'tabular-nums', minWidth:100, textAlign:'right' }}>{cop(ventas.total_iva)}</div>
        </div>

        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'12px 16px', borderBottom:`1px solid ${t.border}` }}>
          <div>
            <div style={{ fontSize:12, fontWeight:600, color:t.text }}>🛒 IVA descontable — compras a proveedores con IVA</div>
            <div style={{ fontSize:11, color:t.textMuted, marginTop:2 }}>
              {compras.por_tarifa.map(r=>`Tarifa ${r.tarifa}%: ${cop(r.iva_valor)}`).join(' · ') || 'Sin compras con IVA en el período'}
            </div>
          </div>
          <div style={{ fontSize:18, fontWeight:700, color:t.green, fontVariantNumeric:'tabular-nums', minWidth:100, textAlign:'right' }}>− {cop(compras.total_iva)}</div>
        </div>

        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'16px 16px', borderRadius:'0 0 10px 10px', background: aFavor ? t.greenSub : t.accentSub, border:`1px solid ${aFavor ? t.green : t.accent}33` }}>
          <div>
            <div style={{ fontSize:13, fontWeight:700, color: aFavor ? t.green : t.accent }}>
              {aFavor ? '✅ Saldo a tu favor este período' : '💳 IVA neto a pagar a la DIAN'}
            </div>
            <div style={{ fontSize:11, color:t.textMuted, marginTop:2 }}>
              {aFavor
                ? 'Este saldo se arrastrará automáticamente al cerrar el bimestre'
                : 'Diferencia entre IVA cobrado en facturas y el IVA pagado en compras'}
            </div>
          </div>
          <div style={{ fontSize:22, fontWeight:700, color: aFavor ? t.green : t.accent, fontVariantNumeric:'tabular-nums', minWidth:100, textAlign:'right' }}>
            {cop(Math.abs(iva_neto.valor))}
          </div>
        </div>
      </div>
    </GlassCard>
  )
}

// ── Modal Cerrar Bimestre ─────────────────────────────────────────────────────

function ModalCierre({ bimestre, año, onClose, onCerrado, authFetch }) {
  const t = useTheme()
  const [obs,   setObs]   = useState('')
  const [est,   setEst]   = useState('idle')
  const [res,   setRes]   = useState(null)
  const [err,   setErr]   = useState('')

  const cerrar = async () => {
    setEst('loading'); setErr('')
    try {
      const r = await authFetch(`${API_BASE}/libro-iva/cerrar-bimestre`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ año, bimestre, observaciones: obs }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || JSON.stringify(d))
      setRes(d); setEst('ok')
      setTimeout(() => { onCerrado(); onClose() }, 2500)
    } catch(e) { setErr(e.message); setEst('error') }
  }

  return (
    <div onMouseDown={e => e.target===e.currentTarget && est!=='loading' && onClose()}
      style={{ position:'fixed', inset:0, zIndex:9999, background:'rgba(0,0,0,.65)', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
      <div style={{ background:t.bg, border:`1px solid ${t.border}`, borderRadius:16, width:'100%', maxWidth:440, boxShadow:'0 24px 64px rgba(0,0,0,.5)', overflow:'hidden' }}>
        <div style={{ padding:'18px 22px 16px', borderBottom:`1px solid ${t.border}`, display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
          <div>
            <div style={{ fontWeight:700, fontSize:15, color:t.text }}>🔒 Cerrar bimestre {NOMBRES_BIM[bimestre-1]} {año}</div>
            <div style={{ fontSize:11, color:t.textMuted, marginTop:3 }}>
              Calculará IVA neto incluyendo saldo arrastrado del bimestre anterior
            </div>
          </div>
          {est !== 'loading' && (
            <button onClick={onClose} style={{ background:'transparent', border:`1px solid ${t.border}`, borderRadius:7, color:t.textMuted, width:28, height:28, cursor:'pointer', fontSize:14, display:'flex', alignItems:'center', justifyContent:'center' }}>✕</button>
          )}
        </div>
        <div style={{ padding:'18px 22px 22px', display:'flex', flexDirection:'column', gap:14 }}>

          <div>
            <label style={{ fontSize:10, fontWeight:600, color:t.textMuted, textTransform:'uppercase', letterSpacing:'.06em', display:'block', marginBottom:4 }}>
              Observaciones (opcional)
            </label>
            <input value={obs} onChange={e=>setObs(e.target.value)}
              placeholder="Ej: Declarado el 15 de marzo, pago referencia 123..."
              style={{ width:'100%', boxSizing:'border-box', background:t.id==='caramelo'?'#F0EBE3':t.card, border:`1px solid ${t.border}`, borderRadius:8, color:t.text, fontSize:12, padding:'8px 12px', fontFamily:'inherit', outline:'none' }}/>
          </div>

          {est === 'ok' && res && (
            <div style={{ padding:'14px 16px', borderRadius:10, background:t.greenSub, border:`1px solid ${t.green}44`, display:'flex', flexDirection:'column', gap:6 }}>
              <div style={{ fontSize:14, fontWeight:700, color:t.green }}>✅ Bimestre cerrado</div>
              <div style={{ fontSize:12, color:t.green, opacity:.85 }}>IVA ventas FE: {cop(res.iva_ventas)}</div>
              <div style={{ fontSize:12, color:t.green, opacity:.85 }}>IVA descontable: {cop(res.iva_compras)}</div>
              {res.saldo_anterior > 0 && <div style={{ fontSize:12, color:t.green, opacity:.85 }}>Saldo a favor anterior: {cop(res.saldo_anterior)}</div>}
              <div style={{ fontSize:13, fontWeight:700, color:t.green, marginTop:4 }}>
                {res.a_favor === 'empresa'
                  ? `Saldo a tu favor: ${cop(Math.abs(res.iva_neto))} — se arrastra`
                  : `IVA a pagar a la DIAN: ${cop(res.iva_neto)}`}
              </div>
            </div>
          )}

          {est === 'error' && (
            <div style={{ padding:'10px 14px', borderRadius:9, background:'#fef2f244', border:'1px solid #dc262644', fontSize:12, color:'#dc2626' }}>
              <strong>❌ Error:</strong> {err}
            </div>
          )}

          {est !== 'ok' && (
            <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
              <button onClick={onClose} disabled={est==='loading'} style={{ background:'transparent', border:`1px solid ${t.border}`, borderRadius:9, color:t.textMuted, padding:'9px 18px', cursor:'pointer', fontFamily:'inherit', fontSize:12, opacity:est==='loading'?.5:1 }}>
                Cancelar
              </button>
              <button onClick={cerrar} disabled={est==='loading'} style={{ background:est==='error'?'#dc2626':t.accent, border:'none', borderRadius:9, color:'#fff', padding:'9px 22px', cursor:'pointer', fontFamily:'inherit', fontSize:12, fontWeight:700, opacity:est==='loading'?.75:1, display:'flex', alignItems:'center', gap:8 }}>
                {est==='loading' && <div style={{ width:13, height:13, border:'2px solid rgba(255,255,255,.35)', borderTopColor:'#fff', borderRadius:'50%', animation:'spin .65s linear infinite' }}/>}
                {est==='loading' ? 'Calculando…' : est==='error' ? 'Reintentar' : '🔒 Cerrar bimestre'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Historial de cierres ──────────────────────────────────────────────────────

function HistorialCierres({ año, refresh, onCerrar, authFetch }) {
  const t   = useTheme()
  const ref = useRef(authFetch); ref.current = authFetch
  const [data,    setData]    = useState([])
  const [loading, setLoading] = useState(false)

  const cargar = useCallback(async () => {
    setLoading(true)
    try {
      const r = await ref.current(`${API_BASE}/libro-iva/historial-cierres?año=${año}`)
      if (r.ok) setData(await r.json())
    } catch(_){}
    finally { setLoading(false) }
  }, [año, refresh])

  useEffect(() => { cargar() }, [cargar])

  const cerrados = data.map(d => d.bimestre)

  return (
    <GlassCard style={{ padding:0 }}>
      <div style={{ padding:'14px 20px', borderBottom:`1px solid ${t.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <SectionTitle>📅 Bimestres {año}</SectionTitle>
        <span style={{ fontSize:11, color:t.textMuted }}>Haz clic en "Cerrar" para calcular y guardar el IVA neto</span>
      </div>
      {loading ? <Spinner/> : (
        <div style={{ overflowX:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
            <thead>
              <tr style={{ background:t.tableAlt }}>
                <Th>Período</Th>
                <Th right>IVA ventas</Th>
                <Th right>IVA compras</Th>
                <Th right>Saldo anterior</Th>
                <Th right>IVA neto</Th>
                <Th center>Estado</Th>
                <Th center>Acción</Th>
              </tr>
            </thead>
            <tbody>
              {BIMESTRES.map(b => {
                const cierre = data.find(d => d.bimestre === b.n)
                const aFavor = cierre && parseInt(cierre.iva_neto) < 0
                return (
                  <tr key={b.n} style={{ borderBottom:`1px solid ${t.border}` }}
                    onMouseEnter={e=>e.currentTarget.style.background=t.cardHover}
                    onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                    <td style={{ padding:'10px 14px', color:t.text, fontWeight:600 }}>{b.label}</td>
                    <td style={{ padding:'10px 14px', textAlign:'right', color:t.accent, fontVariantNumeric:'tabular-nums' }}>
                      {cierre ? cop(cierre.iva_ventas) : '—'}
                    </td>
                    <td style={{ padding:'10px 14px', textAlign:'right', color:t.green, fontVariantNumeric:'tabular-nums' }}>
                      {cierre ? cop(cierre.iva_compras) : '—'}
                    </td>
                    <td style={{ padding:'10px 14px', textAlign:'right', color:t.textMuted, fontVariantNumeric:'tabular-nums' }}>
                      {cierre && parseInt(cierre.saldo_anterior) > 0 ? cop(cierre.saldo_anterior) : '—'}
                    </td>
                    <td style={{ padding:'10px 14px', textAlign:'right', fontWeight:700, fontVariantNumeric:'tabular-nums', color: cierre ? (aFavor ? t.green : t.accent) : t.textMuted }}>
                      {cierre
                        ? (aFavor ? '−' : '') + cop(Math.abs(parseInt(cierre.iva_neto)))
                        : '—'}
                    </td>
                    <td style={{ padding:'10px 14px', textAlign:'center' }}>
                      {cierre ? (
                        <span style={{ fontSize:10, fontWeight:700, padding:'2px 8px', borderRadius:99, background: aFavor ? t.greenSub : t.accentSub, color: aFavor ? t.green : t.accent }}>
                          {aFavor ? 'A favor' : 'A pagar'}
                        </span>
                      ) : (
                        <span style={{ fontSize:10, color:t.textMuted }}>Pendiente</span>
                      )}
                    </td>
                    <td style={{ padding:'10px 10px', textAlign:'center' }}>
                      <button onClick={() => onCerrar(b.n)} style={{
                        background: cierre ? t.tableAlt : t.accent,
                        border: `1px solid ${cierre ? t.border : t.accent}`,
                        color: cierre ? t.textMuted : '#fff',
                        borderRadius:7, padding:'5px 12px',
                        cursor:'pointer', fontFamily:'inherit',
                        fontSize:11, fontWeight:700, whiteSpace:'nowrap',
                      }}>
                        {cierre ? '🔄 Recalcular' : '🔒 Cerrar'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </GlassCard>
  )
}

// ── Tabla ventas FE ───────────────────────────────────────────────────────────

function TablaVentasFE({ desde, hasta, authFetch }) {
  const t   = useTheme()
  const ref = useRef(authFetch); ref.current = authFetch
  const [data, setData] = useState(null)
  const [load, setLoad] = useState(false)
  const [err,  setErr]  = useState(null)

  const cargar = useCallback(async () => {
    setLoad(true); setErr(null)
    try {
      const r = await ref.current(`${API_BASE}/libro-iva/ventas?desde=${desde}&hasta=${hasta}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch(e){ setErr(e.message) } finally { setLoad(false) }
  }, [desde, hasta])

  useEffect(() => { cargar() }, [cargar])

  if (load) return <Spinner/>
  if (err)  return <ErrorMsg msg={err}/>
  if (!data || data.registros.length === 0) return <EmptyState msg="Sin facturas electrónicas emitidas con IVA en este período."/>

  const tot = data.totales
  return (
    <div style={{ overflowX:'auto' }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
        <thead>
          <tr style={{ background:useTheme().tableAlt }}>
            <Th>Fecha</Th><Th>FE #</Th><Th>Cliente</Th><Th>NIT</Th><Th>Concepto</Th>
            <Th center>Tarifa</Th><Th right>Total c/IVA</Th><Th right>Base</Th><Th right>IVA</Th>
          </tr>
        </thead>
        <tbody>
          {data.registros.map((r,i) => (
            <tr key={i} style={{ borderBottom:`1px solid ${t.border}` }}
              onMouseEnter={e=>e.currentTarget.style.background=t.cardHover}
              onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
              <td style={{ padding:'8px 14px', color:t.textMuted, whiteSpace:'nowrap' }}>{fmtF(r.fecha)}</td>
              <td style={{ padding:'8px 10px', color:t.accent, fontWeight:700 }}>{r.factura_numero||'—'}</td>
              <td style={{ padding:'8px 14px', color:t.text, maxWidth:130, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.cliente_nombre}</td>
              <td style={{ padding:'8px 12px', color:t.textMuted, fontFamily:'monospace', fontSize:10 }}>{r.nit_cliente==='222222222222'?'—':r.nit_cliente}</td>
              <td style={{ padding:'8px 14px', color:t.textSub, maxWidth:160, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.concepto}</td>
              <td style={{ padding:'8px 10px', textAlign:'center' }}>
                <span style={{ fontSize:10, fontWeight:700, padding:'2px 7px', borderRadius:99, background:t.accentSub, color:t.accent }}>{r.tarifa_iva}%</span>
              </td>
              <td style={{ padding:'8px 14px', textAlign:'right', color:t.textMuted, fontVariantNumeric:'tabular-nums' }}>{cop(r.total_con_iva)}</td>
              <td style={{ padding:'8px 14px', textAlign:'right', color:t.text, fontVariantNumeric:'tabular-nums' }}>{cop(r.base_gravable)}</td>
              <td style={{ padding:'8px 14px', textAlign:'right', color:t.accent, fontWeight:700, fontVariantNumeric:'tabular-nums' }}>{cop(r.iva_valor)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ background:t.tableFoot, borderTop:`1px solid ${t.border}` }}>
            <td colSpan={6} style={{ padding:'9px 14px', fontSize:10, color:t.textMuted, fontWeight:600, textAlign:'right' }}>{tot.num_lineas} líneas</td>
            <td style={{ padding:'9px 14px', textAlign:'right', color:t.textMuted, fontVariantNumeric:'tabular-nums' }}>{cop(tot.total_con_iva)}</td>
            <td style={{ padding:'9px 14px', textAlign:'right', color:t.text, fontWeight:700, fontVariantNumeric:'tabular-nums' }}>{cop(tot.base_gravable)}</td>
            <td style={{ padding:'9px 14px', textAlign:'right', color:t.accent, fontWeight:700, fontSize:13, fontVariantNumeric:'tabular-nums' }}>{cop(tot.iva_generado)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

// ── Tabla compras IVA descontable ─────────────────────────────────────────────

function TablaComprasIVA({ desde, hasta, authFetch }) {
  const t   = useTheme()
  const ref = useRef(authFetch); ref.current = authFetch
  const [data, setData] = useState(null)
  const [load, setLoad] = useState(false)
  const [err,  setErr]  = useState(null)

  const cargar = useCallback(async () => {
    setLoad(true); setErr(null)
    try {
      const r = await ref.current(`${API_BASE}/libro-iva/compras?desde=${desde}&hasta=${hasta}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch(e){ setErr(e.message) } finally { setLoad(false) }
  }, [desde, hasta])

  useEffect(() => { cargar() }, [cargar])

  if (load) return <Spinner/>
  if (err)  return <ErrorMsg msg={err}/>
  if (!data || data.registros.length === 0) return (
    <div style={{ padding:16 }}>
      <EmptyState msg="Sin compras con IVA en este período. Al registrar compras en el tab Compras, activa el toggle 'Precio incluye IVA'."/>
    </div>
  )

  const tot = data.totales
  return (
    <div style={{ overflowX:'auto' }}>
      <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
        <thead>
          <tr style={{ background:t.tableAlt }}>
            <Th>Fecha</Th><Th>Proveedor</Th><Th>Concepto</Th>
            <Th center>Tarifa</Th><Th right>Cantidad</Th>
            <Th right>Total c/IVA</Th><Th right>Base</Th><Th right>IVA desc.</Th>
          </tr>
        </thead>
        <tbody>
          {data.registros.map((r,i) => (
            <tr key={i} style={{ borderBottom:`1px solid ${t.border}` }}
              onMouseEnter={e=>e.currentTarget.style.background=t.cardHover}
              onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
              <td style={{ padding:'8px 14px', color:t.textMuted, whiteSpace:'nowrap' }}>{fmtF(r.fecha)}</td>
              <td style={{ padding:'8px 14px', color:t.text, maxWidth:130, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.proveedor}</td>
              <td style={{ padding:'8px 14px', color:t.textSub, maxWidth:160, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.concepto}</td>
              <td style={{ padding:'8px 10px', textAlign:'center' }}>
                <span style={{ fontSize:10, fontWeight:700, padding:'2px 7px', borderRadius:99, background:t.greenSub, color:t.green }}>{r.tarifa_iva}%</span>
              </td>
              <td style={{ padding:'8px 14px', textAlign:'right', color:t.textMuted }}>{r.cantidad}</td>
              <td style={{ padding:'8px 14px', textAlign:'right', color:t.textMuted, fontVariantNumeric:'tabular-nums' }}>{cop(r.total_con_iva)}</td>
              <td style={{ padding:'8px 14px', textAlign:'right', color:t.text, fontVariantNumeric:'tabular-nums' }}>{cop(r.base_gravable)}</td>
              <td style={{ padding:'8px 14px', textAlign:'right', color:t.green, fontWeight:700, fontVariantNumeric:'tabular-nums' }}>{cop(r.iva_valor)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr style={{ background:t.tableFoot, borderTop:`1px solid ${t.border}` }}>
            <td colSpan={5} style={{ padding:'9px 14px', fontSize:10, color:t.textMuted, fontWeight:600, textAlign:'right' }}>{tot.num_lineas} compras</td>
            <td style={{ padding:'9px 14px', textAlign:'right', color:t.textMuted, fontVariantNumeric:'tabular-nums' }}>{cop(tot.total_con_iva)}</td>
            <td style={{ padding:'9px 14px', textAlign:'right', color:t.text, fontWeight:700, fontVariantNumeric:'tabular-nums' }}>{cop(tot.base_gravable)}</td>
            <td style={{ padding:'9px 14px', textAlign:'right', color:t.green, fontWeight:700, fontSize:13, fontVariantNumeric:'tabular-nums' }}>{cop(tot.iva_descontable)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────

export default function TabLibroIVA() {
  const t   = useTheme()
  const { authFetch } = useAuth()

  const año = new Date().getFullYear()
  const [bim,   setBim]   = useState(currentBim())
  const [modo,  setModo]  = useState('bimestral')
  const [desde, setDesde] = useState(() => bimDates(currentBim())[0])
  const [hasta, setHasta] = useState(() => bimDates(currentBim())[1])

  const [resumen,    setResumen]    = useState(null)
  const [loadRes,    setLoadRes]    = useState(false)
  const [vista,      setVista]      = useState('ventas')
  const [modalBim,   setModalBim]   = useState(null)   // bimestre a cerrar
  const [cierreRfsh, setCierreRfsh] = useState(0)

  const aplicarBim = n => {
    setBim(n)
    const [d,h] = bimDates(n)
    setDesde(d); setHasta(h)
  }

  useEffect(() => {
    if (!desde || !hasta) return
    setLoadRes(true)
    authFetch(`${API_BASE}/libro-iva/resumen?desde=${desde}&hasta=${hasta}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setResumen(d) })
      .catch(() => {})
      .finally(() => setLoadRes(false))
  }, [desde, hasta])

  const lbl = { fontSize:10, fontWeight:600, color:t.textMuted, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4, display:'block' }
  const inp = { background:t.id==='caramelo'?'#F0EBE3':t.card, border:`1px solid ${t.border}`, borderRadius:8, color:t.text, fontSize:12, padding:'7px 11px', fontFamily:'inherit', outline:'none' }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:20 }}>

      {/* Banner RST */}
      <div style={{ padding:'12px 18px', borderRadius:12, background:t.accentSub, border:`1px solid ${t.accent}33`, display:'flex', alignItems:'center', gap:10, fontSize:12, color:t.accent }}>
        <span style={{ fontSize:20 }}>📗</span>
        <div>
          <strong>Libro de IVA — Régimen Simple de Tributación</strong>
          <span style={{ marginLeft:10, opacity:.7, fontSize:11 }}>
            IVA extraído de precio final · Solo FE emitidas · Saldo bimestral arrastrado automáticamente
          </span>
        </div>
      </div>

      {/* Selector período */}
      <GlassCard style={{ padding:'14px 20px' }}>
        <div style={{ display:'flex', gap:10, flexWrap:'wrap', alignItems:'flex-end' }}>
          <div style={{ display:'flex', gap:0, border:`1px solid ${t.border}`, borderRadius:8, overflow:'hidden' }}>
            {['bimestral','custom'].map(m => (
              <button key={m} onClick={() => setModo(m)} style={{ background:modo===m?t.accent:'transparent', color:modo===m?'#fff':t.textMuted, border:'none', padding:'7px 14px', cursor:'pointer', fontFamily:'inherit', fontSize:11, fontWeight:600, transition:'all .15s' }}>
                {m==='bimestral'?'📅 Bimestral':'🗓️ Fechas'}
              </button>
            ))}
          </div>
          {modo==='bimestral' ? (
            <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
              {BIMESTRES.map(b => (
                <button key={b.n} onClick={() => aplicarBim(b.n)} style={{ background:bim===b.n?t.accent:t.accentSub, border:`1px solid ${bim===b.n?t.accent:t.border}`, color:bim===b.n?'#fff':t.textMuted, borderRadius:8, padding:'6px 14px', cursor:'pointer', fontFamily:'inherit', fontSize:11, fontWeight:bim===b.n?700:500, transition:'all .15s' }}>
                  {b.label}
                </button>
              ))}
            </div>
          ) : (
            <div style={{ display:'flex', gap:10, alignItems:'flex-end', flexWrap:'wrap' }}>
              <div><label style={lbl}>Desde</label><input type="date" value={desde} onChange={e=>setDesde(e.target.value)} style={inp}/></div>
              <div><label style={lbl}>Hasta</label><input type="date" value={hasta} onChange={e=>setHasta(e.target.value)} style={inp}/></div>
            </div>
          )}
          <div style={{ fontSize:11, color:t.textMuted, alignSelf:'center' }}>
            {fmtF(desde)} → {fmtF(hasta)}
          </div>
        </div>
      </GlassCard>

      {/* KPIs */}
      {loadRes && !resumen && <Spinner/>}
      {resumen && (
        <div style={{ display:'flex', gap:10, flexWrap:'wrap' }}>
          <Kpi label="IVA generado (FE)" value={cop(resumen.ventas.total_iva)} sub={`Base: ${cop(resumen.ventas.total_base)}`} color={t.accent} icon="🧾"/>
          <Kpi label="IVA descontable" value={cop(resumen.compras.total_iva)} sub={`Total compras: ${cop(resumen.compras.total_bruto)}`} color={t.green} icon="🛒"/>
          <Kpi label="IVA neto del período" value={cop(Math.abs(resumen.iva_neto.valor))} sub={resumen.iva_neto.a_favor==='empresa'?'✅ Saldo a tu favor':'💳 A pagar a la DIAN'} color={resumen.iva_neto.a_favor==='empresa'?t.green:t.accent} icon="⚖️"/>
        </div>
      )}

      {/* Cuadro neto */}
      {resumen && <CuadroNeto resumen={resumen}/>}

      {/* Historial cierres */}
      <HistorialCierres
        año={año}
        refresh={cierreRfsh}
        authFetch={authFetch}
        onCerrar={n => setModalBim(n)}
      />

      {/* Libros detallados */}
      <GlassCard style={{ padding:0 }}>
        <div style={{ padding:'14px 20px', borderBottom:`1px solid ${t.border}`, display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10 }}>
          <SectionTitle>{vista==='ventas'?'🧾 Libro IVA ventas — FE emitidas':'🛒 Libro IVA compras — IVA descontable'}</SectionTitle>
          <div style={{ display:'flex', gap:6 }}>
            {['ventas','compras'].map(v => (
              <button key={v} onClick={() => setVista(v)} style={{ background:vista===v?t.accent:t.accentSub, border:`1px solid ${vista===v?t.accent:t.border}`, color:vista===v?'#fff':t.textMuted, borderRadius:8, padding:'6px 14px', cursor:'pointer', fontFamily:'inherit', fontSize:11, fontWeight:vista===v?700:500, transition:'all .15s' }}>
                {v==='ventas'?'🧾 Ventas FE':'🛒 Compras'}
              </button>
            ))}
          </div>
        </div>
        {vista==='ventas'
          ? <TablaVentasFE   desde={desde} hasta={hasta} authFetch={authFetch}/>
          : <TablaComprasIVA desde={desde} hasta={hasta} authFetch={authFetch}/>
        }
      </GlassCard>

      {/* Nota */}
      <div style={{ padding:'12px 16px', borderRadius:10, fontSize:11, color:t.textMuted, background:t.tableAlt, border:`1px solid ${t.border}`, lineHeight:1.6 }}>
        <strong>💡 Flujo bimestral:</strong> Al finalizar cada bimestre, haz clic en "🔒 Cerrar" para
        calcular el IVA neto. Si el saldo es a tu favor, se arrastra automáticamente
        al siguiente período. Si hay que pagar, ese es el valor exacto para declarar ante la DIAN.
        Recuerda marcar el toggle <strong>"Precio incluye IVA"</strong> al registrar compras de proveedores
        para acumular el IVA descontable.
      </div>

      {/* Modal cierre */}
      {modalBim && (
        <ModalCierre
          bimestre={modalBim}
          año={año}
          authFetch={authFetch}
          onClose={() => setModalBim(null)}
          onCerrado={() => { setModalBim(null); setCierreRfsh(r => r+1) }}
        />
      )}
    </div>
  )
}
