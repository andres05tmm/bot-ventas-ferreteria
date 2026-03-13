import { useState, useMemo } from 'react'
import { createPortal } from 'react-dom'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, StyledInput, EmptyState, Th, cop, API_BASE,
} from '../components/shared.jsx'

function metodoBadge(metodo, t) {
  const raw = (metodo || '').toLowerCase()
  if (raw.includes('efect'))  return { bg: '#052e16', color: '#4ade80', border: '#4ade8033' }
  if (raw.includes('nequi'))  return { bg: '#172554', color: '#93c5fd', border: '#93c5fd33' }
  if (raw.includes('billet')) return { bg: '#172554', color: '#818cf8', border: '#818cf833' }
  if (raw.includes('transf')) return { bg: '#1c1917', color: '#d4d4aa', border: '#d4d4aa33' }
  if (raw.includes('tarjet')) return { bg: '#1e1b4b', color: '#a5b4fc', border: '#a5b4fc33' }
  return { bg: t.card, color: t.textMuted, border: t.border }
}

function exportCSV(ventas) {
  const headers = ['#','Fecha','Hora','Producto','Cliente','Cantidad','Precio Unit.','Total','Vendedor','Método']
  const rows = ventas.map(v => [
    v.num, v.fecha, v.hora, v.producto, v.cliente||'Consumidor Final',
    v.cantidad, v.precio_unitario, v.total, v.vendedor, v.metodo||'',
  ])
  const csv = [headers,...rows].map(r=>r.map(c=>`"${c}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8;'})
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href=url; a.download=`ventas_${new Date().toISOString().slice(0,10)}.csv`; a.click()
  URL.revokeObjectURL(url)
}

// ── Modal Editar Venta ────────────────────────────────────────────────────────
const METODOS = ['efectivo','transferencia','nequi','daviplata','datafono','otro']

function ModalEditarVenta({ venta, onClose, onGuardado }) {
  const t = useTheme()
  const [form, setForm] = useState({
    producto:        venta.producto       || '',
    cantidad:        venta.cantidad       || '',
    precio_unitario: venta.precio_unitario|| '',
    total:           venta.total          || '',
    metodo_pago:     venta.metodo         || 'efectivo',
    cliente:         venta.cliente        || '',
    vendedor:        venta.vendedor       || '',
  })
  const [estado, setEstado] = useState('idle')
  const [err,    setErr]    = useState('')
  const set = (k,v) => setForm(f=>({...f,[k]:v}))

  const guardar = async () => {
    setEstado('saving'); setErr('')
    try {
      const body = {}
      if (form.producto        !== venta.producto)        body.producto        = form.producto
      if (String(form.cantidad)!== String(venta.cantidad))body.cantidad        = Number(form.cantidad)
      if (String(form.precio_unitario)!==String(venta.precio_unitario)) body.precio_unitario = Number(form.precio_unitario)
      if (String(form.total)   !== String(venta.total))   body.total           = Number(form.total)
      if (form.metodo_pago     !== venta.metodo)          body.metodo_pago     = form.metodo_pago
      if (form.cliente         !== venta.cliente)         body.cliente         = form.cliente
      if (form.vendedor        !== venta.vendedor)        body.vendedor        = form.vendedor
      if (!Object.keys(body).length) { onClose(); return }
      const r = await fetch(`${API_BASE}/ventas/${venta.num}`, {
        method:'PATCH', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail||'Error')
      setEstado('ok')
      setTimeout(() => { onGuardado(); onClose() }, 700)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  const inp = {
    width:'100%', boxSizing:'border-box',
    background: t.id==='caramelo'?'#f8fafc':'#111',
    border:`1px solid ${t.border}`, borderRadius:7,
    color:t.text, fontSize:12, padding:'7px 10px',
    outline:'none', fontFamily:'inherit',
  }
  const lbl = { fontSize:10, color:t.textMuted, textTransform:'uppercase', letterSpacing:'.07em', marginBottom:3, display:'block' }

  return createPortal(
    <div onMouseDown={e=>e.target===e.currentTarget&&onClose()} style={{
      position:'fixed',inset:0,zIndex:9999,background:'rgba(0,0,0,.6)',
      display:'flex',alignItems:'center',justifyContent:'center',padding:16,
    }}>
      <div style={{
        background:t.bg, border:`1px solid ${t.border}`, borderRadius:14,
        width:'100%', maxWidth:440, maxHeight:'90vh', overflowY:'auto',
        boxShadow:'0 24px 64px rgba(0,0,0,.4)',
      }}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'18px 20px 0'}}>
          <div>
            <div style={{fontWeight:700,fontSize:14,color:t.text}}>✏️ Editar venta #{venta.num}</div>
            <div style={{fontSize:11,color:t.textMuted,marginTop:2}}>Solo se actualizan los campos que cambies</div>
          </div>
          <button onClick={onClose} style={{background:'transparent',border:`1px solid ${t.border}`,borderRadius:7,color:t.textMuted,width:28,height:28,cursor:'pointer',fontSize:14,display:'flex',alignItems:'center',justifyContent:'center'}}>✕</button>
        </div>
        <div style={{padding:'16px 20px 20px',display:'flex',flexDirection:'column',gap:11}}>

          <div><label style={lbl}>Producto</label>
            <input style={inp} value={form.producto} onChange={e=>set('producto',e.target.value)}/></div>

          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:10}}>
            <div><label style={lbl}>Cantidad</label>
              <input style={inp} type="number" value={form.cantidad} onChange={e=>set('cantidad',e.target.value)}/></div>
            <div><label style={lbl}>V. Unitario</label>
              <input style={inp} type="number" value={form.precio_unitario} onChange={e=>set('precio_unitario',e.target.value)}/></div>
            <div><label style={lbl}>Total</label>
              <input style={inp} type="number" value={form.total} onChange={e=>set('total',e.target.value)}/></div>
          </div>

          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
            <div><label style={lbl}>Método de pago</label>
              <select style={inp} value={form.metodo_pago} onChange={e=>set('metodo_pago',e.target.value)}>
                {METODOS.map(m=><option key={m} value={m}>{m}</option>)}
              </select></div>
            <div><label style={lbl}>Vendedor</label>
              <input style={inp} value={form.vendedor} onChange={e=>set('vendedor',e.target.value)}/></div>
          </div>

          <div><label style={lbl}>Cliente</label>
            <input style={inp} value={form.cliente} onChange={e=>set('cliente',e.target.value)} placeholder="Consumidor Final"/></div>

          {err && <div style={{padding:'7px 10px',background:'#fef2f2',border:'1px solid #fca5a5',borderRadius:7,fontSize:11,color:'#dc2626'}}>⚠ {err}</div>}

          <div style={{display:'flex',gap:8,justifyContent:'flex-end',marginTop:4}}>
            <button onClick={onClose} style={{background:'transparent',border:`1px solid ${t.border}`,borderRadius:8,color:t.textMuted,padding:'8px 16px',cursor:'pointer',fontFamily:'inherit',fontSize:12}}>Cancelar</button>
            <button onClick={guardar} disabled={estado==='saving'} style={{
              background:estado==='ok'?t.green:estado==='err'?'#dc2626':t.accent,
              border:'none',borderRadius:8,color:'#fff',padding:'8px 20px',
              cursor:'pointer',fontFamily:'inherit',fontSize:12,fontWeight:700,
              opacity:estado==='saving'?.7:1,transition:'background .2s',
            }}>
              {estado==='saving'?'Guardando…':estado==='ok'?'✓ Guardado':estado==='err'?'✗ Error':'Guardar cambios'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Modal Confirmar Eliminar ──────────────────────────────────────────────────
function ModalConfirmarEliminar({ venta, onClose, onEliminado }) {
  const t = useTheme()
  const [estado, setEstado] = useState('idle')
  const [err,    setErr]    = useState('')

  const eliminar = async () => {
    setEstado('saving')
    try {
      const r = await fetch(`${API_BASE}/ventas/${venta.num}`, { method:'DELETE' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail||'Error')
      setEstado('ok')
      setTimeout(() => { onEliminado(); onClose() }, 600)
    } catch(e) { setErr(e.message); setEstado('err') }
  }

  return createPortal(
    <div onMouseDown={e=>e.target===e.currentTarget&&onClose()} style={{
      position:'fixed',inset:0,zIndex:9999,background:'rgba(0,0,0,.6)',
      display:'flex',alignItems:'center',justifyContent:'center',padding:16,
    }}>
      <div style={{background:t.bg,border:`1px solid ${t.border}`,borderRadius:14,width:'100%',maxWidth:380,padding:24,boxShadow:'0 24px 64px rgba(0,0,0,.4)'}}>
        <div style={{fontSize:15,fontWeight:700,color:t.text,marginBottom:8}}>🗑 Eliminar venta #{venta.num}</div>
        <div style={{fontSize:12,color:t.textMuted,marginBottom:4}}>
          <strong style={{color:t.text}}>{venta.producto}</strong>
        </div>
        <div style={{fontSize:12,color:t.textMuted,marginBottom:16}}>
          Total: <strong style={{color:t.accent}}>{cop(venta.total)}</strong> · {venta.metodo||'—'}
        </div>
        <div style={{padding:'10px 12px',background:'#fef2f2',border:'1px solid #fca5a5',borderRadius:8,fontSize:11,color:'#dc2626',marginBottom:16}}>
          ⚠ Esta acción elimina la venta del Excel y Google Sheets, y descuenta el total de la caja del día.
        </div>
        {err && <div style={{padding:'6px 10px',background:'#fef2f2',border:'1px solid #fca5a5',borderRadius:7,fontSize:11,color:'#dc2626',marginBottom:12}}>✗ {err}</div>}
        <div style={{display:'flex',gap:8,justifyContent:'flex-end'}}>
          <button onClick={onClose} style={{background:'transparent',border:`1px solid ${t.border}`,borderRadius:8,color:t.textMuted,padding:'8px 16px',cursor:'pointer',fontFamily:'inherit',fontSize:12}}>Cancelar</button>
          <button onClick={eliminar} disabled={estado==='saving'} style={{
            background:estado==='ok'?t.green:'#dc2626',
            border:'none',borderRadius:8,color:'#fff',padding:'8px 18px',
            cursor:'pointer',fontFamily:'inherit',fontSize:12,fontWeight:700,
            opacity:estado==='saving'?.7:1,
          }}>
            {estado==='saving'?'Eliminando…':estado==='ok'?'✓ Eliminado':'Sí, eliminar'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────
export default function TabHistorial({ refreshKey }) {
  const t = useTheme()
  const [refresh, setRefresh] = useState(0)
  const { data, loading, error } = useFetch('/ventas/hoy', [refreshKey, refresh])
  const [busqueda, setBusqueda] = useState('')
  const [filtro,   setFiltro]   = useState('todos')
  const [editando, setEditando] = useState(null)
  const [eliminando, setEliminando] = useState(null)

  const todasVentas = useMemo(() => (data?.ventas||[]).map(v=>({
    ...v, estado:(v.metodo&&v.metodo.trim()&&v.metodo!=='—')?'pagado':'pendiente',
  })), [data])

  const ventas = useMemo(() => {
    let res = filtro==='todos' ? todasVentas : todasVentas.filter(v=>v.estado===filtro)
    if (busqueda) {
      const q = busqueda.toLowerCase()
      res = res.filter(v=>
        String(v.producto).toLowerCase().includes(q)||
        String(v.cliente ).toLowerCase().includes(q)||
        String(v.vendedor).toLowerCase().includes(q)||
        String(v.num     ).includes(q)
      )
    }
    return res
  }, [todasVentas,filtro,busqueda])

  const total      = ventas.reduce((a,v)=>a+(parseFloat(v.total)||0),0)
  const totalTodo  = todasVentas.reduce((a,v)=>a+(parseFloat(v.total)||0),0)
  const pagados    = todasVentas.filter(v=>v.estado==='pagado').length
  const pendientes = todasVentas.filter(v=>v.estado==='pendiente').length

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>

      {editando   && <ModalEditarVenta       venta={editando}    onClose={()=>setEditando(null)}    onGuardado={()=>setRefresh(r=>r+1)}/>}
      {eliminando && <ModalConfirmarEliminar venta={eliminando}  onClose={()=>setEliminando(null)} onEliminado={()=>setRefresh(r=>r+1)}/>}

      {/* KPIs */}
      <div style={{display:'flex',gap:10,flexWrap:'wrap'}}>
        {[
          {label:'Total hoy',     value:cop(totalTodo),     color:t.accent},
          {label:'Registros',     value:todasVentas.length, color:t.text},
          {label:'✅ Pagados',    value:pagados,            color:t.green},
          {label:'⏳ Sin método', value:pendientes,         color:t.yellow},
        ].map(item=>(
          <div key={item.label} style={{background:t.card,border:`1px solid ${t.border}`,borderRadius:8,padding:'10px 16px',flex:1,minWidth:120}}>
            <div style={{fontSize:10,color:t.textMuted,textTransform:'uppercase',letterSpacing:'.08em',marginBottom:5}}>{item.label}</div>
            <div style={{fontSize:18,fontWeight:700,color:item.color}}>{item.value}</div>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:8}}>
        <div style={{display:'flex',gap:6}}>
          {['todos','pagado','pendiente'].map(f=>(
            <PeriodBtn key={f} active={filtro===f} onClick={()=>setFiltro(f)}>
              {f==='todos'?'Todos':f==='pagado'?'✅ Pagados':'⏳ Pendientes'}
            </PeriodBtn>
          ))}
        </div>
        <div style={{display:'flex',gap:8,alignItems:'center'}}>
          <StyledInput value={busqueda} onChange={e=>setBusqueda(e.target.value)} placeholder="Buscar..." style={{width:200}}/>
          {todasVentas.length>0&&(
            <button onClick={()=>exportCSV(todasVentas)} style={{
              background:t.accentSub,border:`1px solid ${t.accent}55`,color:t.accent,
              borderRadius:7,padding:'7px 13px',fontSize:11,fontWeight:600,
              fontFamily:'inherit',whiteSpace:'nowrap',cursor:'pointer',
            }}>↓ Exportar CSV</button>
          )}
        </div>
      </div>

      {/* Tabla */}
      <Card style={{padding:0}}>
        <div style={{padding:'14px 18px',borderBottom:`1px solid ${t.border}`}}>
          <SectionTitle>
            Ventas del Día — {new Date().toLocaleDateString('es-CO',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}
          </SectionTitle>
        </div>
        <div style={{overflowX:'auto'}}>
          {ventas.length===0
            ? <EmptyState msg={busqueda?'Sin resultados.':'No hay ventas registradas hoy.'}/>
            : (
              <table style={{width:'100%',borderCollapse:'collapse',fontSize:12}}>
                <thead>
                  <tr style={{background:t.tableAlt}}>
                    <Th>#</Th><Th>Hora</Th><Th>Producto</Th><Th>Cliente</Th>
                    <Th center>Cant.</Th><Th right>V. Unit.</Th><Th right>Total</Th>
                    <Th>Vendedor</Th><Th center>Método</Th><Th center>Estado</Th>
                    <Th center>Acciones</Th>
                  </tr>
                </thead>
                <tbody>
                  {ventas.map((v,i)=>{
                    const badge = metodoBadge(v.metodo,t)
                    return (
                      <tr key={i} style={{borderBottom:`1px solid ${t.border}`}}
                        onMouseEnter={e=>e.currentTarget.style.background=t.cardHover}
                        onMouseLeave={e=>e.currentTarget.style.background='transparent'}
                      >
                        <td style={{padding:'8px 14px',color:t.accent,fontWeight:700}}>{v.num}</td>
                        <td style={{padding:'8px 14px',color:t.textMuted,fontStyle:'italic',whiteSpace:'nowrap'}}>{v.hora}</td>
                        <td style={{padding:'8px 14px',color:t.text,maxWidth:180}}>{v.producto}</td>
                        <td style={{padding:'8px 14px',color:t.textMuted,fontSize:11}}>{v.cliente||'Consumidor Final'}</td>
                        <td style={{padding:'8px 14px',textAlign:'center',color:t.textMuted}}>{v.cantidad}</td>
                        <td style={{padding:'8px 14px',textAlign:'right',color:t.textMuted}}>{v.precio_unitario?cop(v.precio_unitario):'—'}</td>
                        <td style={{padding:'8px 14px',textAlign:'right',color:t.green,fontWeight:600}}>{cop(v.total)}</td>
                        <td style={{padding:'8px 14px',color:t.textMuted,fontSize:11}}>{v.vendedor||'—'}</td>
                        <td style={{padding:'8px 14px',textAlign:'center'}}>
                          <span style={{display:'inline-block',padding:'2px 9px',borderRadius:99,background:badge.bg,color:badge.color,border:`1px solid ${badge.border}`,fontSize:10,fontWeight:500,whiteSpace:'nowrap'}}>
                            {v.metodo||'—'}
                          </span>
                        </td>
                        <td style={{padding:'8px 14px',textAlign:'center'}}>
                          <span style={{display:'inline-block',padding:'2px 9px',borderRadius:99,fontSize:10,fontWeight:600,
                            background:v.estado==='pagado'?'#14532d22':'#78350f22',
                            color:v.estado==='pagado'?'#4ade80':'#fbbf24',
                            border:`1px solid ${v.estado==='pagado'?'#4ade8033':'#fbbf2433'}`,
                          }}>{v.estado}</span>
                        </td>
                        <td style={{padding:'8px 10px',textAlign:'center'}}>
                          <div style={{display:'flex',gap:5,justifyContent:'center'}}>
                            <button onClick={()=>setEditando(v)} title="Editar venta" style={{
                              background:t.accentSub,border:`1px solid ${t.accent}44`,color:t.accent,
                              borderRadius:6,width:28,height:28,cursor:'pointer',fontSize:13,
                              display:'flex',alignItems:'center',justifyContent:'center',
                            }}>✏</button>
                            <button onClick={()=>setEliminando(v)} title="Eliminar venta" style={{
                              background:'#fef2f2',border:'1px solid #fca5a544',color:'#dc2626',
                              borderRadius:6,width:28,height:28,cursor:'pointer',fontSize:13,
                              display:'flex',alignItems:'center',justifyContent:'center',
                            }}>🗑</button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr style={{borderTop:`1px solid ${t.border}`,background:t.tableFoot}}>
                    <td colSpan={6} style={{padding:'10px 14px',fontSize:10,color:t.textMuted,fontWeight:600,textAlign:'right'}}>
                      SUBTOTAL ({ventas.length} registros)
                    </td>
                    <td style={{padding:'10px 14px',textAlign:'right',color:t.accent,fontWeight:700,fontSize:14}}>{cop(total)}</td>
                    <td colSpan={4}/>
                  </tr>
                </tfoot>
              </table>
            )
          }
        </div>
      </Card>
    </div>
  )
}
