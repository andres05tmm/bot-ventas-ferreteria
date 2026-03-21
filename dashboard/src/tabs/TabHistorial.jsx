import { useState, useMemo } from 'react'
import { createPortal } from 'react-dom'
import {
  useTheme, useFetch, Card, SectionTitle, Spinner, ErrorMsg,
  PeriodBtn, StyledInput, EmptyState, Th, cop, API_BASE,
  useIsMobile,
} from '../components/shared.jsx'

function metodoBadge(metodo, t) {
  const raw = (metodo || '').toLowerCase()
  const light = t.id === 'caramelo'
  if (raw.includes('efect'))  return { bg: light ? '#dcfce7' : '#052e16', color: light ? '#166534' : '#4ade80', border: light ? '#86efac44' : '#4ade8033' }
  if (raw.includes('nequi'))  return { bg: light ? '#dbeafe' : '#172554', color: light ? '#1d4ed8' : '#93c5fd', border: light ? '#93c5fd44' : '#93c5fd33' }
  if (raw.includes('billet')) return { bg: light ? '#ede9fe' : '#172554', color: light ? '#6d28d9' : '#818cf8', border: light ? '#818cf844' : '#818cf833' }
  if (raw.includes('transf')) return { bg: light ? '#fef9c3' : '#1c1917', color: light ? '#a16207' : '#d4d4aa', border: light ? '#fde04744' : '#d4d4aa33' }
  if (raw.includes('tarjet')) return { bg: light ? '#e0e7ff' : '#1e1b4b', color: light ? '#4338ca' : '#a5b4fc', border: light ? '#a5b4fc44' : '#a5b4fc33' }
  return { bg: t.card, color: t.textMuted, border: t.border }
}

const FRACS = [
  [3/4,'3/4'],[1/2,'1/2'],[1/4,'1/4'],[1/3,'1/3'],[2/3,'2/3'],
  [1/8,'1/8'],[1/10,'1/10'],[1/16,'1/16'],[3/8,'3/8'],[7/8,'7/8'],
]
// Unidades que SIEMPRE se muestran en decimal (nunca fracciones)
const UNIDADES_DECIMAL = ['grm','gramos','kg','cms','mts','lt','lts','25 kg','mlt']

function cantidadLegible(val, unidad) {
  if (val === null || val === undefined || val === '') return '—'
  const s = String(val).trim()

  // Si la unidad es decimal (gramos, kg, cms...), parsear a número y mostrar decimal
  const uKey = (unidad || '').toLowerCase().replace('ó','o')
  const esDecimal = UNIDADES_DECIMAL.includes(uKey)

  if (esDecimal) {
    // Parsear "133 y 3/10" → 133.3, o "1/2" → 0.5, o "10" → 10
    let n = parseFloat(s.replace(',','.'))
    if (isNaN(n)) {
      // Intentar parsear fracciones tipo "133 y 3/10"
      const mixto = s.match(/^(\d+)\s*y\s*(\d+)\/(\d+)$/)
      if (mixto) n = parseFloat(mixto[1]) + parseFloat(mixto[2]) / parseFloat(mixto[3])
      const simple = s.match(/^(\d+)\/(\d+)$/)
      if (simple) n = parseFloat(simple[1]) / parseFloat(simple[2])
    }
    if (!isNaN(n)) {
      return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '')
    }
    return s
  }

  // Para galones y unidades: mostrar fracciones legibles
  if (/[\/y]/.test(s) && !/^\d+$/.test(s)) return s
  const n = parseFloat(s.replace(',','.'))
  if (isNaN(n)) return s
  if (Number.isInteger(n)) return String(n)
  const entero = Math.floor(n)
  const frac   = n - entero
  for (const [dec, label] of FRACS) {
    if (Math.abs(frac - dec) < 0.005) return entero > 0 ? `${entero} ${label}` : label
  }
  return n.toFixed(2).replace(/\.?0+$/, '')
}

const UNIDAD_ESTILOS = {
  'galón': { color:'#a16207', bg:'#fef9c320' },
  'galon': { color:'#a16207', bg:'#fef9c320' },
  'kg':    { color:'#166534', bg:'#dcfce720' },
  'gramos':{ color:'#166534', bg:'#dcfce720' },
  'grm':   { color:'#166534', bg:'#dcfce720' },
  'mts':   { color:'#1d4ed8', bg:'#dbeafe20' },
  'cms':   { color:'#6d28d9', bg:'#ede9fe20' },
  'lt':    { color:'#0369a1', bg:'#e0f2fe20' },
  'lts':   { color:'#0369a1', bg:'#e0f2fe20' },
}
function UnidadBadge({ unidad, t }) {
  if (!unidad || unidad.toLowerCase() === 'unidad') return null
  const key = unidad.toLowerCase().replace('ó','o')
  const est = UNIDAD_ESTILOS[key] || { color: t.textMuted, bg: 'transparent' }
  return (
    <span style={{
      fontSize:9, fontWeight:600, padding:'1px 5px', borderRadius:4,
      color: est.color, background: est.bg, marginLeft:4, whiteSpace:'nowrap',
    }}>{unidad}</span>
  )
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

// ── Modal Editar Venta (edita UNA línea) ─────────────────────────────────────
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
      if (form.producto         !== venta.producto)                         body.producto        = form.producto
      if (String(form.cantidad) !== String(venta.cantidad))                 body.cantidad        = Number(form.cantidad)
      if (String(form.precio_unitario) !== String(venta.precio_unitario))   body.precio_unitario = Number(form.precio_unitario)
      if (String(form.total)    !== String(venta.total))                    body.total           = Number(form.total)
      if (form.metodo_pago      !== venta.metodo)                           body.metodo_pago     = form.metodo_pago
      if (form.cliente          !== venta.cliente)                          body.cliente         = form.cliente
      if (form.vendedor         !== venta.vendedor)                         body.vendedor        = form.vendedor
      if (!Object.keys(body).length) { onClose(); return }
      // Enviar producto_original para identificar la fila en ventas multi-producto
      body.producto_original = venta.producto
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
    background: t.id === 'caramelo' ? '#f8fafc' : '#111',
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

// ── Modal Confirmar Eliminar — agrupa TODOS los productos del consecutivo ─────
function ModalConfirmarEliminar({ grupo, onClose, onEliminado }) {
  const t = useTheme()
  const [estado, setEstado] = useState('idle')
  const [err,    setErr]    = useState('')
  const [borrando, setBorrando] = useState(null) // null = nada, 'todo' = consecutivo, index = producto individual

  const consecutivo = grupo[0]?.num
  const totalGrupo  = grupo.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const esMultiple  = grupo.length > 1

  const eliminarTodo = async () => {
    setEstado('saving'); setBorrando('todo')
    try {
      const r = await fetch(`${API_BASE}/ventas/${consecutivo}`, { method: 'DELETE' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('ok')
      setTimeout(() => { onEliminado(); onClose() }, 600)
    } catch(e) { setErr(e.message); setEstado('err'); setBorrando(null) }
  }

  const eliminarLinea = async (v, idx) => {
    setEstado('saving'); setBorrando(idx)
    try {
      const r = await fetch(
        `${API_BASE}/ventas/${consecutivo}/linea?producto=${encodeURIComponent(v.producto)}`,
        { method: 'DELETE' }
      )
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Error')
      setEstado('ok')
      setTimeout(() => { onEliminado(); onClose() }, 600)
    } catch(e) { setErr(e.message); setEstado('err'); setBorrando(null) }
  }

  return createPortal(
    <div onMouseDown={e=>e.target===e.currentTarget&&onClose()} style={{
      position:'fixed',inset:0,zIndex:9999,background:'rgba(0,0,0,.6)',
      display:'flex',alignItems:'center',justifyContent:'center',padding:16,
    }}>
      <div style={{background:t.bg,border:`1px solid ${t.border}`,borderRadius:14,width:'100%',maxWidth:440,padding:24,boxShadow:'0 24px 64px rgba(0,0,0,.4)'}}>
        <div style={{fontSize:15,fontWeight:700,color:t.text,marginBottom:10}}>
          🗑 Eliminar {esMultiple ? `consecutivo #${consecutivo}` : `venta #${consecutivo}`}
        </div>

        {/* Lista de productos — con botón individual si es multi-producto */}
        <div style={{
          background:t.tableAlt, border:`1px solid ${t.border}`,
          borderRadius:8, marginBottom:14, overflow:'hidden',
        }}>
          {grupo.map((v, i) => (
            <div key={i} style={{
              display:'flex', justifyContent:'space-between', alignItems:'center',
              padding:'8px 12px',
              borderBottom: i < grupo.length - 1 ? `1px solid ${t.border}` : 'none',
            }}>
              <div style={{flex:1, minWidth:0}}>
                <span style={{color:t.text,fontSize:12}}>{v.producto}</span>
                <span style={{color:t.textMuted,fontSize:10,marginLeft:8}}>
                  ×{cantidadLegible(v.cantidad, v.unidad_medida)}
                </span>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:8}}>
                <span style={{color:t.green,fontWeight:600,fontSize:12}}>{cop(v.total)}</span>
                {esMultiple && (
                  <button
                    onClick={() => eliminarLinea(v, i)}
                    disabled={estado === 'saving'}
                    title={`Eliminar solo "${v.producto}"`}
                    style={{
                      background:'transparent', border:`1px solid #dc262644`,
                      borderRadius:6, width:26, height:26, cursor:'pointer',
                      fontSize:11, color:'#dc2626',
                      display:'flex',alignItems:'center',justifyContent:'center',
                      opacity: estado === 'saving' && borrando === i ? 0.5 : 1,
                    }}
                  >
                    {estado === 'saving' && borrando === i ? '…' : '✕'}
                  </button>
                )}
              </div>
            </div>
          ))}
          {/* Total del grupo */}
          <div style={{
            display:'flex', justifyContent:'space-between', alignItems:'center',
            padding:'9px 12px',
            background: t.tableFoot,
            borderTop:`1px solid ${t.border}`,
          }}>
            <span style={{fontSize:11,color:t.textMuted,fontWeight:600}}>
              TOTAL {esMultiple ? `(${grupo.length} productos)` : ''}
            </span>
            <span style={{color:t.accent,fontWeight:700,fontSize:14}}>{cop(totalGrupo)}</span>
          </div>
        </div>

        {/* Info método y vendedor */}
        <div style={{fontSize:12,color:t.textMuted,marginBottom:14,display:'flex',gap:16}}>
          <span>Método: <strong style={{color:t.text}}>{grupo[0]?.metodo || '—'}</strong></span>
          <span>Vendedor: <strong style={{color:t.text}}>{grupo[0]?.vendedor || '—'}</strong></span>
        </div>

        {esMultiple && (
          <div style={{
            padding:'8px 12px', borderRadius:8, marginBottom:12,
            background: `${t.blue}12`, border:`1px solid ${t.blue}33`,
            fontSize:11, color:t.blue,
          }}>
            💡 Usá el botón ✕ de cada producto para eliminar solo uno, o "Eliminar todo" para borrar el consecutivo completo.
          </div>
        )}

        <div style={{padding:'10px 12px',background:'#fef2f2',border:'1px solid #fca5a5',borderRadius:8,fontSize:11,color:'#dc2626',marginBottom:16}}>
          ⚠ Se elimina del Excel y Google Sheets, y se descuenta de la caja.
        </div>

        {err && <div style={{padding:'6px 10px',background:'#fef2f2',border:'1px solid #fca5a5',borderRadius:7,fontSize:11,color:'#dc2626',marginBottom:12}}>✗ {err}</div>}

        <div style={{display:'flex',gap:8,justifyContent:'flex-end'}}>
          <button onClick={onClose} style={{background:'transparent',border:`1px solid ${t.border}`,borderRadius:8,color:t.textMuted,padding:'8px 16px',cursor:'pointer',fontFamily:'inherit',fontSize:12}}>Cancelar</button>
          <button onClick={eliminarTodo} disabled={estado==='saving'} style={{
            background:estado==='ok'?t.green:'#dc2626',
            border:'none',borderRadius:8,color:'#fff',padding:'8px 18px',
            cursor:'pointer',fontFamily:'inherit',fontSize:12,fontWeight:700,
            opacity:estado==='saving' && borrando==='todo' ?.7:1,
          }}>
            {estado==='saving' && borrando==='todo' ?'Eliminando…':estado==='ok'?'✓ Eliminado': esMultiple ? 'Eliminar todo' : 'Sí, eliminar'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────
function KpiHistorial({ label, value, color }) {
  const t = useTheme()
  const [hov, setHov] = useState(false)
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: t.card,
        border: `1px solid ${hov ? color : t.border}`,
        borderRadius: 12, padding: '14px 18px',
        flex: 1, minWidth: 120, cursor: 'default',
        transition: 'border-color .2s ease, box-shadow .25s ease',
        boxShadow: hov ? `0 0 0 3px ${color}44, 0 0 16px ${color}22` : 'none',
      }}
    >
      <div style={{ fontSize: 10, color: t.textMuted, textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 8 }}>
        {label}
      </div>
      <div style={{
        fontSize: hov ? 22 : 18, fontWeight: 700, color: hov ? color : color,
        transition: 'font-size .2s ease',
        fontVariantNumeric: 'tabular-nums',
      }}>
        {value}
      </div>
    </div>
  )
}

export default function TabHistorial({ refreshKey }) {
  const t = useTheme()
  const isMobile = useIsMobile()
  const [refresh,    setRefresh]    = useState(0)
  const { data, loading, error }    = useFetch('/ventas/hoy', [refreshKey, refresh])
  const [busqueda,   setBusqueda]   = useState('')
  const [filtro,     setFiltro]     = useState('todos')
  const [editando,   setEditando]   = useState(null)
  // eliminando ahora es el GRUPO completo (array), no una sola venta
  const [eliminando, setEliminando] = useState(null)

  // Filas planas con estado calculado
  const todasVentas = useMemo(() => (data?.ventas || []).map(v => ({
    ...v,
    estado: (v.metodo && v.metodo.trim() && v.metodo !== '—') ? 'pagado' : 'pendiente',
  })), [data])

  // Agrupar por consecutivo para el botón de eliminar
  const gruposPorConsecutivo = useMemo(() => {
    const mapa = {}
    for (const v of todasVentas) {
      const key = String(v.num)
      if (!mapa[key]) mapa[key] = []
      mapa[key].push(v)
    }
    return mapa
  }, [todasVentas])

  const ventas = useMemo(() => {
    let res = filtro === 'todos' ? todasVentas : todasVentas.filter(v => v.estado === filtro)
    if (busqueda) {
      const q = busqueda.toLowerCase()
      res = res.filter(v =>
        String(v.producto).toLowerCase().includes(q) ||
        String(v.cliente ).toLowerCase().includes(q) ||
        String(v.vendedor).toLowerCase().includes(q) ||
        String(v.num     ).includes(q)
      )
    }
    return res
  }, [todasVentas, filtro, busqueda])

  const total      = ventas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const totalTodo  = todasVentas.reduce((a, v) => a + (parseFloat(v.total) || 0), 0)
  const pagados    = todasVentas.filter(v => v.estado === 'pagado').length
  const pendientes = todasVentas.filter(v => v.estado === 'pendiente').length

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>

      {editando   && <ModalEditarVenta       venta={editando}   onClose={()=>setEditando(null)}    onGuardado={()=>setRefresh(r=>r+1)}/>}
      {eliminando && <ModalConfirmarEliminar grupo={eliminando} onClose={()=>setEliminando(null)} onEliminado={()=>setRefresh(r=>r+1)}/>}

      {/* KPIs */}
      <div style={{display:'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4,1fr)', gap:10}}>
        {[
          {label:'Total hoy',     value:cop(totalTodo),     color:t.accent},
          {label:'Registros',     value:todasVentas.length, color:t.text},
          {label:'✅ Pagados',    value:pagados,            color:t.green},
          {label:'⏳ Sin método', value:pendientes,         color:t.yellow},
        ].map(item=>(
          <KpiHistorial key={item.label} label={item.label} value={item.value} color={item.color}/>
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
                  {ventas.map((v, i) => {
                    const badge        = metodoBadge(v.metodo, t)
                    const grupoConsec  = gruposPorConsecutivo[String(v.num)] || [v]
                    const esMultiple   = grupoConsec.length > 1
                    // Saber si esta fila es la primera de su consecutivo (para no repetir el icono)
                    const primeraDelGrupo = grupoConsec[0] === v ||
                      ventas.findIndex(x => String(x.num) === String(v.num)) === i

                    return (
                      <tr key={i} style={{
                        borderBottom:`1px solid ${t.border}`,
                        background: esMultiple ? (t.id==='caramelo' ? '#fefce810' : `${t.yellow}08`) : 'transparent',
                        transition: 'background .15s ease',
                      }}
                        onMouseEnter={e=>{ e.currentTarget.style.background = t.cardHover }}
                        onMouseLeave={e=>{ e.currentTarget.style.background = esMultiple ? (t.id==='caramelo' ? '#fefce810' : `${t.yellow}08`) : 'transparent' }}
                      >
                        <td style={{padding: isMobile ? '7px 8px' : '8px 14px',color:t.accent,fontWeight:700}}>
                          {v.num}
                          {esMultiple && (
                            <span style={{
                              fontSize:8,fontWeight:700,marginLeft:4,
                              background:t.yellow,color:'#000',
                              padding:'1px 4px',borderRadius:3,
                            }} title={`Venta con ${grupoConsec.length} productos`}>
                              ×{grupoConsec.length}
                            </span>
                          )}
                        </td>
                        <td style={{padding:'8px 14px',color:t.textMuted,fontStyle:'italic',whiteSpace:'nowrap'}}>{v.hora}</td>
                        <td style={{padding:'8px 14px',color:t.text,maxWidth:180}}>{v.producto}</td>
                        <td style={{padding:'8px 14px',color:t.textMuted,fontSize:11}}>{v.cliente||'Consumidor Final'}</td>
                        <td style={{padding:'8px 14px',textAlign:'center',color:t.textMuted}}>
                          <span style={{fontFamily:'monospace'}}>{cantidadLegible(v.cantidad, v.unidad_medida)}</span>
                          <UnidadBadge unidad={v.unidad_medida} t={t}/>
                        </td>
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
                            background:v.estado==='pagado' ? `${t.green}18` : `${t.yellow}18`,
                            color:v.estado==='pagado' ? t.green : t.yellow,
                            border:`1px solid ${v.estado==='pagado' ? t.green : t.yellow}33`,
                          }}>{v.estado}</span>
                        </td>
                        <td style={{padding:'8px 10px',textAlign:'center'}}>
                          <div style={{display:'flex',gap:5,justifyContent:'center'}}>
                            <button
                              onClick={()=>setEditando(v)}
                              title="Editar esta línea"
                              style={{
                                background:t.accentSub,border:`1px solid ${t.accent}44`,color:t.accent,
                                borderRadius:6,width:28,height:28,cursor:'pointer',fontSize:13,
                                display:'flex',alignItems:'center',justifyContent:'center',
                              }}>✏</button>
                            <button
                              onClick={()=>setEliminando(grupoConsec)}
                              title={esMultiple
                                ? `Eliminar consecutivo #${v.num} (${grupoConsec.length} productos)`
                                : `Eliminar venta #${v.num}`}
                              style={{
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
