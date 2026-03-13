import { useState, useMemo, useRef, useCallback } from 'react'
import {
  useTheme, useFetch, Spinner, ErrorMsg,
  Badge, StyledInput, EmptyState, Th, API_BASE,
} from '../components/shared.jsx'

// ── Utilidades de fracciones ──────────────────────────────────────────────────

// Convierte string a decimal: "2 3/4" → 2.75, "1/2" → 0.5, "3" → 3, "2.5" → 2.5
function parseFraccion(str) {
  if (!str || !str.trim()) return null
  str = str.trim().replace(',', '.')

  // Fracción mixta: "2 3/4"
  const mixto = str.match(/^(\d+(?:\.\d+)?)\s+(\d+)\/(\d+)$/)
  if (mixto) {
    const entero = parseFloat(mixto[1])
    const num    = parseFloat(mixto[2])
    const den    = parseFloat(mixto[3])
    if (den === 0) return null
    return entero + num / den
  }

  // Fracción simple: "3/4"
  const simple = str.match(/^(\d+)\/(\d+)$/)
  if (simple) {
    const num = parseFloat(simple[1])
    const den = parseFloat(simple[2])
    if (den === 0) return null
    return num / den
  }

  // Número decimal o entero
  const n = parseFloat(str)
  return isNaN(n) ? null : n
}

// Convierte decimal a string legible: 2.75 → "2 3/4", 0.5 → "1/2", 3 → "3"
const FRACS_CONOCIDAS = [
  [1/16, '1/16'], [1/8,  '1/8'],  [1/4,  '1/4'],
  [1/3,  '1/3'],  [3/8,  '3/8'],  [1/2,  '1/2'],
  [5/8,  '5/8'],  [2/3,  '2/3'],  [3/4,  '3/4'],
  [7/8,  '7/8'],  [1/10, '1/10'],
]

function decimalAFrac(val) {
  if (val === null || val === undefined) return null
  val = parseFloat(val)
  if (isNaN(val)) return null
  if (Number.isInteger(val)) return String(val)

  const entero = Math.floor(val)
  const frac   = val - entero

  // Buscar fracción conocida más cercana (tolerancia ±0.005)
  for (const [dec, label] of FRACS_CONOCIDAS) {
    if (Math.abs(frac - dec) < 0.005) {
      return entero > 0 ? `${entero} ${label}` : label
    }
  }

  // Fallback: 2 decimales
  return val.toFixed(2).replace(/\.?0+$/, '')
}

function catIcon(cat) {
  const c = (cat || '').toLowerCase()
  if (c.includes('pint') || c.includes('vinilo') || c.includes('color'))               return '🎨'
  if (c.includes('thinner') || c.includes('varsol') || c.includes('solvente'))        return '🧪'
  if (c.includes('lija') || c.includes('esmeril') || c.includes('abras'))             return '🪚'
  if (c.includes('tornill') || c.includes('clav') || c.includes('perno'))             return '🔩'
  if (c.includes('adhesiv') || c.includes('pega') || c.includes('silicon'))           return '🧲'
  if (c.includes('ferret') || c.includes('herram') || c.includes('brocha') || c.includes('rodillo')) return '🔧'
  if (c.includes('granel'))                                                            return '⚖️'
  return '📦'
}

// ── Campo precio (editable simple) ───────────────────────────────────────────
function CampoPrecio({ valor, onGuardar }) {
  const t = useTheme()
  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState('')
  const [estado,   setEstado]   = useState('idle')
  const inputRef = useRef(null)

  const abrir = () => {
    setVal(valor ? String(valor) : '')
    setEstado('idle')
    setEditando(true)
    setTimeout(() => { inputRef.current?.focus(); inputRef.current?.select() }, 20)
  }
  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = useCallback(async () => {
    const num = parseFloat(val.replace(',', '.'))
    if (isNaN(num)) { cerrar(); return }
    setEstado('saving')
    try {
      await onGuardar(num)
      setEstado('ok')
      setTimeout(cerrar, 700)
    } catch { setEstado('err'); setTimeout(cerrar, 900) }
  }, [val, onGuardar])

  const onKey = e => { if (e.key === 'Enter') guardar(); if (e.key === 'Escape') cerrar() }

  if (editando) {
    return (
      <div style={{ display:'flex', alignItems:'center', gap:4 }}>
        <span style={{ fontSize:11, color:t.textMuted }}>$</span>
        <input
          ref={inputRef} value={val} onChange={e => setVal(e.target.value)}
          onKeyDown={onKey} onBlur={guardar} inputMode="decimal"
          style={{
            width:80, background:t.card,
            border:`1.5px solid ${estado==='err' ? t.accent : t.green}`,
            borderRadius:6, padding:'3px 7px',
            fontSize:12, color:t.text, fontFamily:'monospace', outline:'none',
          }}
        />
        {estado==='saving' && <span style={{fontSize:10,color:t.textMuted}}>…</span>}
        {estado==='ok'     && <span style={{fontSize:13,color:t.green}}>✓</span>}
        {estado==='err'    && <span style={{fontSize:13,color:t.accent}}>✗</span>}
      </div>
    )
  }

  const hay = valor !== null && valor !== undefined && valor
  return (
    <button onClick={abrir} title="Clic para editar" style={{
      background:'none', border:`1px dashed ${t.border}`,
      borderRadius:6, padding:'3px 8px', cursor:'pointer',
      fontSize:12, fontFamily:'monospace',
      color: hay ? t.green : t.textMuted,
      transition:'border-color .12s, background .12s',
      display:'inline-flex', alignItems:'center', gap:4,
    }}
    onMouseEnter={e => { e.currentTarget.style.borderColor=t.accent; e.currentTarget.style.background=t.accentSub }}
    onMouseLeave={e => { e.currentTarget.style.borderColor=t.border; e.currentTarget.style.background='none' }}
    >
      {hay ? <><span style={{opacity:.65}}>$</span>{String(valor)}</> : <span style={{opacity:.4,fontSize:11}}>sin precio</span>}
      <span style={{fontSize:9,opacity:.3}}>✏</span>
    </button>
  )
}

// ── Campo stock con soporte de fracciones ─────────────────────────────────────
function CampoStock({ valor, onGuardar, fraccionesDisp }) {
  const t = useTheme()
  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState('')
  const [estado,   setEstado]   = useState('idle')
  const inputRef = useRef(null)

  // Fracciones disponibles para botones rápidos (de precios_fraccion del producto)
  const fracBtns = useMemo(() => {
    if (!fraccionesDisp) return []
    return Object.keys(fraccionesDisp)
      .filter(k => k !== 'unidad_suelta')
      .sort((a, b) => {
        const pa = parseFraccion(a) || 0
        const pb = parseFraccion(b) || 0
        return pb - pa  // de mayor a menor: 3/4, 1/2, 1/4 ...
      })
  }, [fraccionesDisp])

  const valorDisplay = decimalAFrac(valor)

  const abrir = () => {
    setVal(valorDisplay || '')
    setEstado('idle')
    setEditando(true)
    setTimeout(() => { inputRef.current?.focus(); inputRef.current?.select() }, 20)
  }
  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = useCallback(async (strVal) => {
    const src = strVal !== undefined ? strVal : val
    const num = parseFraccion(String(src))
    if (num === null || num < 0) { cerrar(); return }
    setEstado('saving')
    try {
      await onGuardar(num)
      setEstado('ok')
      setTimeout(cerrar, 700)
    } catch { setEstado('err'); setTimeout(cerrar, 900) }
  }, [val, onGuardar])

  const onKey = e => {
    if (e.key === 'Enter')  guardar()
    if (e.key === 'Escape') cerrar()
  }

  // Suma o resta fracción rápida
  const sumar   = frac => {
    const base = parseFraccion(val) || 0
    const add  = parseFraccion(frac) || 0
    setVal(decimalAFrac(base + add) || '')
  }
  const restar  = frac => {
    const base = parseFraccion(val) || 0
    const sub  = parseFraccion(frac) || 0
    const res  = Math.max(0, base - sub)
    setVal(decimalAFrac(res) || '0')
  }

  if (editando) {
    return (
      <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:6, padding:'4px 0' }}>
        {/* Input principal */}
        <div style={{ display:'flex', alignItems:'center', gap:4 }}>
          <input
            ref={inputRef} value={val} onChange={e => setVal(e.target.value)}
            onKeyDown={onKey}
            placeholder="ej: 2 3/4"
            inputMode="decimal"
            style={{
              width:90, background:t.card,
              border:`1.5px solid ${estado==='err' ? t.accent : t.green}`,
              borderRadius:6, padding:'4px 8px',
              fontSize:13, color:t.text, fontFamily:'monospace',
              outline:'none', textAlign:'center',
            }}
          />
          <button onClick={() => guardar()} style={{
            background:t.green+'22', border:`1px solid ${t.green}44`,
            color:t.green, borderRadius:6, padding:'4px 8px',
            fontSize:12, cursor:'pointer',
          }}>✓</button>
          <button onClick={cerrar} style={{
            background:'none', border:`1px solid ${t.border}`,
            color:t.textMuted, borderRadius:6, padding:'4px 8px',
            fontSize:12, cursor:'pointer',
          }}>✕</button>
        </div>

        {/* Botones de fracción rápida (+ y -) */}
        {fracBtns.length > 0 && (
          <div style={{ display:'flex', flexWrap:'wrap', gap:3, justifyContent:'center' }}>
            {fracBtns.map(frac => (
              <div key={frac} style={{ display:'flex', gap:1 }}>
                <button
                  onClick={() => restar(frac)}
                  title={`− ${frac}`}
                  style={{
                    background:t.accentSub, border:`1px solid ${t.accent}33`,
                    color:t.accent, borderRadius:'5px 0 0 5px',
                    padding:'2px 6px', fontSize:10, cursor:'pointer', fontWeight:700,
                  }}>−</button>
                <span style={{
                  background:t.card, border:`1px solid ${t.border}`,
                  borderLeft:'none', borderRight:'none',
                  padding:'2px 7px', fontSize:10, color:t.text,
                  display:'flex', alignItems:'center',
                }}>{frac}</span>
                <button
                  onClick={() => sumar(frac)}
                  title={`+ ${frac}`}
                  style={{
                    background:t.green+'22', border:`1px solid ${t.green}33`,
                    color:t.green, borderRadius:'0 5px 5px 0',
                    padding:'2px 6px', fontSize:10, cursor:'pointer', fontWeight:700,
                  }}>+</button>
              </div>
            ))}
          </div>
        )}

        {/* Ayuda */}
        <span style={{ fontSize:9, color:t.textMuted, opacity:.7 }}>
          Acepta: 3 · 1/2 · 2 3/4 · 0.5
        </span>

        {estado==='saving' && <span style={{fontSize:10,color:t.textMuted}}>Guardando…</span>}
        {estado==='ok'     && <span style={{fontSize:11,color:t.green}}>✓ Guardado</span>}
        {estado==='err'    && <span style={{fontSize:11,color:t.accent}}>✗ Error</span>}
      </div>
    )
  }

  const hay = valor !== null && valor !== undefined
  const esFrac = hay && !Number.isInteger(parseFloat(valor))
  return (
    <button onClick={abrir} title="Clic para editar stock" style={{
      background:'none', border:`1px dashed ${t.border}`,
      borderRadius:6, padding:'3px 8px', cursor:'pointer',
      fontSize:12, fontFamily:'monospace',
      color: hay ? (esFrac ? t.yellow : t.blue) : t.textMuted,
      transition:'border-color .12s, background .12s',
      display:'inline-flex', alignItems:'center', gap:4,
    }}
    onMouseEnter={e => { e.currentTarget.style.borderColor=t.accent; e.currentTarget.style.background=t.accentSub }}
    onMouseLeave={e => { e.currentTarget.style.borderColor=t.border; e.currentTarget.style.background='none' }}
    >
      {hay
        ? <span style={{ fontWeight: esFrac ? 600 : 400 }}>{valorDisplay}</span>
        : <span style={{opacity:.4, fontSize:11}}>sin stock</span>
      }
      {fraccionesDisp && hay && <span style={{fontSize:9,opacity:.5,marginLeft:1}}>gal</span>}
      <span style={{fontSize:9,opacity:.3}}>✏</span>
    </button>
  )
}

// ── Fila de producto ──────────────────────────────────────────────────────────
function FilaProducto({ p, alerta, onActualizado }) {
  const t = useTheme()
  const esAlerta = !!alerta

  const patchPrecio = useCallback(async (nuevo) => {
    const r = await fetch(`${API_BASE}/catalogo/${p.key}/precio`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ precio: nuevo }),
    })
    if (!r.ok) throw new Error('Error precio')
    onActualizado()
  }, [p.key, onActualizado])

  const patchStock = useCallback(async (nuevo) => {
    const r = await fetch(`${API_BASE}/inventario/${p.key}/stock`, {
      method:'PATCH', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ stock: nuevo }),
    })
    if (!r.ok) throw new Error('Error stock')
    onActualizado()
  }, [p.key, onActualizado])

  const bgBase  = esAlerta ? (t.id==='caramelo' ? '#fef2f2' : '#1c0808') : 'transparent'

  return (
    <tr
      style={{ borderTop:`1px solid ${t.border}`, background:bgBase, transition:'background .12s' }}
      onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
      onMouseLeave={e => e.currentTarget.style.background = bgBase}
    >
      <td style={{ padding:'9px 14px', color:t.text, fontSize:12 }}>
        {esAlerta && (
          <span style={{
            width:6, height:6, background:t.accent, borderRadius:'50%',
            display:'inline-block', marginRight:7, animation:'pulse 1.5s infinite',
          }}/>
        )}
        {p.nombre}
        {p.precios_fraccion && (
          <span style={{
            marginLeft:6, fontSize:9, color:t.textMuted,
            background:t.border, borderRadius:3, padding:'1px 5px',
          }}>fraccionable</span>
        )}
      </td>
      <td style={{ padding:'9px 14px', color:t.textMuted, fontFamily:'monospace', fontSize:11 }}>
        {p.codigo || '—'}
      </td>
      <td style={{ padding:'8px 10px', textAlign:'center' }}>
        <CampoPrecio valor={p.precio || null} onGuardar={patchPrecio}/>
      </td>
      <td style={{ padding:'8px 10px', textAlign:'center' }}>
        <CampoStock
          valor={p.stock !== null && p.stock !== undefined ? p.stock : null}
          onGuardar={patchStock}
          fraccionesDisp={p.precios_fraccion || null}
        />
      </td>
      <td style={{ padding:'9px 14px', textAlign:'center' }}>
        {esAlerta ? (
          <Badge color={t.accent}>
            {alerta.motivo==='sin_precio' ? 'Sin precio' : 'Stock 0'}
          </Badge>
        ) : (
          <Badge color={t.green}>OK</Badge>
        )}
      </td>
    </tr>
  )
}

// ── Tab principal ─────────────────────────────────────────────────────────────
export default function TabInventario({ refreshKey }) {
  const t = useTheme()
  const { data, loading, error, refetch        } = useFetch('/productos',       [refreshKey])
  const { data: alDat,          refetch: alRef  } = useFetch('/inventario/bajo', [refreshKey])

  const [busqueda,  setBusqueda]  = useState('')
  const [soloBajos, setSoloBajos] = useState(false)
  const [abierta,   setAbierta]   = useState(null)

  const alertaMap = useMemo(() => {
    const m = {}
    ;(alDat?.alertas || []).forEach(a => { m[a.key] = a })
    return m
  }, [alDat])

  const categorias = useMemo(() => {
    const grupos = {}
    ;(data?.productos || []).forEach(p => {
      const cat = p.categoria || 'Sin categoría'
      if (!grupos[cat]) grupos[cat] = []
      grupos[cat].push(p)
    })
    return Object.entries(grupos).sort(([a], [b]) => (parseInt(a)||999) - (parseInt(b)||999))
  }, [data])

  const filtrar = prods => {
    let res = prods
    if (busqueda) {
      const q = busqueda.toLowerCase()
      res = res.filter(p => p.nombre.toLowerCase().includes(q) || (p.codigo||'').toLowerCase().includes(q))
    }
    if (soloBajos) res = res.filter(p => alertaMap[p.key])
    return res
  }

  const onActualizado = useCallback(() => { refetch(); alRef() }, [refetch, alRef])
  const totalAlertas  = alDat?.total || 0

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>

      {/* Barra superior */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10 }}>
        <div style={{ display:'flex', gap:8, flexWrap:'wrap', alignItems:'center' }}>
          <div style={{
            background:t.card, border:`1px solid ${t.border}`,
            borderRadius:8, padding:'8px 14px', fontSize:11, color:t.textSub,
          }}>
            📦 <strong style={{color:t.text}}>{data?.total||0}</strong> productos
          </div>

          {totalAlertas > 0 && (
            <button onClick={() => setSoloBajos(s => !s)} style={{
              background: soloBajos ? t.accent : t.accentSub,
              border:`1px solid ${t.accent}55`,
              color: soloBajos ? '#fff' : t.accent,
              borderRadius:8, padding:'8px 14px',
              fontSize:11, fontWeight:600, cursor:'pointer',
              fontFamily:'inherit', transition:'all .15s',
            }}>
              ⚠️ {totalAlertas} alertas{soloBajos ? ' — Ver todos' : ' — Ver solo alertas'}
            </button>
          )}

          <div style={{
            fontSize:10, color:t.textMuted,
            background:t.card, border:`1px solid ${t.border}`,
            borderRadius:7, padding:'5px 10px',
            display:'flex', alignItems:'center', gap:5,
          }}>
            <span style={{opacity:.55}}>✏</span>
            Clic en precio o stock · Pinturas aceptan fracciones (ej: <strong>2 3/4</strong>)
          </div>
        </div>

        <StyledInput
          value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          placeholder="Buscar producto o código..."
          style={{ width:240 }}
        />
      </div>

      {/* Categorías */}
      {categorias.map(([cat, prods]) => {
        const label    = cat.replace(/^\d+\s*/, '')
        const filtrados = filtrar(prods)
        if ((busqueda || soloBajos) && filtrados.length === 0) return null
        const alertasCat = prods.filter(p => alertaMap[p.key]).length
        const expandida  = !!(busqueda || soloBajos) || abierta === cat

        return (
          <div key={cat} style={{
            background:t.card,
            border:`1px solid ${expandida ? t.accent+'44' : t.border}`,
            borderRadius:10, overflow:'hidden',
            transition:'border-color .2s',
          }}>
            <div
              onClick={() => !(busqueda || soloBajos) && setAbierta(p => p===cat ? null : cat)}
              style={{
                padding:'12px 16px', display:'flex',
                alignItems:'center', justifyContent:'space-between',
                cursor:(busqueda || soloBajos) ? 'default' : 'pointer',
                userSelect:'none',
              }}
              onMouseEnter={e => { if (!(busqueda||soloBajos)) e.currentTarget.style.background=t.cardHover }}
              onMouseLeave={e => e.currentTarget.style.background='transparent'}
            >
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <span style={{fontSize:17}}>{catIcon(label)}</span>
                <span style={{fontWeight:600, fontSize:13, color:t.text}}>{label}</span>
                <span style={{fontSize:10, color:t.textMuted}}>{prods.length} productos</span>
                {alertasCat > 0 && (
                  <span style={{fontSize:10, color:t.accent, fontWeight:600}}>⚠️ {alertasCat}</span>
                )}
              </div>
              {!(busqueda || soloBajos) && (
                <span style={{
                  color:t.textMuted, fontSize:11,
                  transition:'transform .2s',
                  transform: expandida ? 'rotate(90deg)' : 'rotate(0deg)',
                  display:'inline-block',
                }}>▶</span>
              )}
            </div>

            {expandida && (
              <div style={{ borderTop:`1px solid ${t.border}`, overflowX:'auto' }}>
                <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
                  <thead>
                    <tr style={{ background:t.tableAlt }}>
                      <Th>Producto</Th>
                      <Th>Código</Th>
                      <Th center>Precio</Th>
                      <Th center>Stock</Th>
                      <Th center>Estado</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtrados.map(p => (
                      <FilaProducto
                        key={p.key} p={p}
                        alerta={alertaMap[p.key]}
                        onActualizado={onActualizado}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}

      {categorias.length === 0 && <EmptyState msg="No hay productos cargados." />}
    </div>
  )
}
