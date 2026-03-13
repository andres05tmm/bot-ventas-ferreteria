import { useState, useMemo, useRef, useCallback } from 'react'
import {
  useTheme, useFetch, Spinner, ErrorMsg,
  Badge, StyledInput, EmptyState, Th, cop, API_BASE,
} from '../components/shared.jsx'

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

// ── Campo editable inline ─────────────────────────────────────────────────────
function CampoEditable({ valor, onGuardar, prefijo = '', placeholder = '—', color }) {
  const t = useTheme()
  const [editando, setEditando] = useState(false)
  const [val,      setVal]      = useState('')
  const [estado,   setEstado]   = useState('idle') // idle | saving | ok | err
  const inputRef = useRef(null)

  const abrir = () => {
    setVal(valor !== null && valor !== undefined ? String(valor) : '')
    setEstado('idle')
    setEditando(true)
    setTimeout(() => { inputRef.current?.focus(); inputRef.current?.select() }, 20)
  }

  const cerrar = () => { setEditando(false); setEstado('idle') }

  const guardar = useCallback(async () => {
    const str = val.trim().replace(',', '.')
    const num = parseFloat(str)
    if (isNaN(num)) { cerrar(); return }
    setEstado('saving')
    try {
      await onGuardar(num)
      setEstado('ok')
      setTimeout(cerrar, 700)
    } catch {
      setEstado('err')
      setTimeout(cerrar, 900)
    }
  }, [val, onGuardar])

  const onKey = e => {
    if (e.key === 'Enter')  guardar()
    if (e.key === 'Escape') cerrar()
  }

  if (editando) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        {prefijo && <span style={{ fontSize: 11, color: t.textMuted }}>{prefijo}</span>}
        <input
          ref={inputRef}
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={onKey}
          onBlur={guardar}
          inputMode="decimal"
          style={{
            width: 80, background: t.card,
            border: `1.5px solid ${estado === 'err' ? t.accent : t.green}`,
            borderRadius: 6, padding: '3px 7px',
            fontSize: 12, color: t.text, fontFamily: 'monospace', outline: 'none',
          }}
        />
        {estado === 'saving' && <span style={{ fontSize: 10, color: t.textMuted }}>…</span>}
        {estado === 'ok'     && <span style={{ fontSize: 13, color: t.green }}>✓</span>}
        {estado === 'err'    && <span style={{ fontSize: 13, color: t.accent }}>✗</span>}
      </div>
    )
  }

  const hayValor = valor !== null && valor !== undefined && valor !== ''
  return (
    <button
      onClick={abrir}
      title="Clic para editar"
      style={{
        background: 'none',
        border: `1px dashed ${t.border}`,
        borderRadius: 6, padding: '3px 8px', cursor: 'pointer',
        fontSize: 12, fontFamily: 'monospace',
        color: hayValor ? (color || t.text) : t.textMuted,
        transition: 'border-color .12s, background .12s',
        display: 'inline-flex', alignItems: 'center', gap: 4,
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = t.accent; e.currentTarget.style.background = t.accentSub }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.background = 'none' }}
    >
      {hayValor
        ? <>{prefijo && <span style={{ opacity:.65 }}>{prefijo}</span>}{String(valor)}</>
        : <span style={{ opacity:.45, fontSize: 11 }}>{placeholder}</span>
      }
      <span style={{ fontSize: 9, opacity: .35 }}>✏</span>
    </button>
  )
}

// ── Fila producto ─────────────────────────────────────────────────────────────
function FilaProducto({ p, alerta, onActualizado }) {
  const t = useTheme()
  const esAlerta = !!alerta

  const patchPrecio = useCallback(async (nuevo) => {
    const r = await fetch(`${API_BASE}/catalogo/${p.key}/precio`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ precio: nuevo }),
    })
    if (!r.ok) throw new Error('Error al guardar precio')
    onActualizado()
  }, [p.key, onActualizado])

  const patchStock = useCallback(async (nuevo) => {
    const r = await fetch(`${API_BASE}/inventario/${p.key}/stock`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock: nuevo }),
    })
    if (!r.ok) throw new Error('Error al guardar stock')
    onActualizado()
  }, [p.key, onActualizado])

  const bgBase  = esAlerta ? (t.id === 'caramelo' ? '#fef2f2' : '#1c0808') : 'transparent'
  const bgHover = t.cardHover

  return (
    <tr
      style={{ borderTop: `1px solid ${t.border}`, background: bgBase, transition: 'background .12s' }}
      onMouseEnter={e => e.currentTarget.style.background = bgHover}
      onMouseLeave={e => e.currentTarget.style.background = bgBase}
    >
      <td style={{ padding: '9px 14px', color: t.text, fontSize: 12 }}>
        {esAlerta && (
          <span style={{
            width: 6, height: 6, background: t.accent, borderRadius: '50%',
            display: 'inline-block', marginRight: 7, animation: 'pulse 1.5s infinite',
          }}/>
        )}
        {p.nombre}
      </td>
      <td style={{ padding: '9px 14px', color: t.textMuted, fontFamily: 'monospace', fontSize: 11 }}>
        {p.codigo || '—'}
      </td>
      <td style={{ padding: '8px 10px', textAlign: 'center' }}>
        <CampoEditable
          valor={p.precio || null}
          onGuardar={patchPrecio}
          prefijo="$"
          placeholder="sin precio"
          color={t.green}
        />
      </td>
      <td style={{ padding: '8px 10px', textAlign: 'center' }}>
        <CampoEditable
          valor={p.stock !== null && p.stock !== undefined ? p.stock : null}
          onGuardar={patchStock}
          placeholder="sin stock"
          color={p.stock > 0 ? t.blue : t.textMuted}
        />
      </td>
      <td style={{ padding: '9px 14px', textAlign: 'center' }}>
        {esAlerta ? (
          <Badge color={t.accent}>
            {alerta.motivo === 'sin_precio' ? 'Sin precio' : 'Stock 0'}
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
  const { data,        loading, error,   refetch         } = useFetch('/productos',       [refreshKey])
  const { data: alDat,                   refetch: alRef  } = useFetch('/inventario/bajo', [refreshKey])

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
    return Object.entries(grupos).sort(([a], [b]) => (parseInt(a) || 999) - (parseInt(b) || 999))
  }, [data])

  const filtrar = prods => {
    let res = prods
    if (busqueda) {
      const q = busqueda.toLowerCase()
      res = res.filter(p => p.nombre.toLowerCase().includes(q) || (p.codigo || '').toLowerCase().includes(q))
    }
    if (soloBajos) res = res.filter(p => alertaMap[p.key])
    return res
  }

  const onActualizado = useCallback(() => {
    refetch()
    alRef()
  }, [refetch, alRef])

  const totalAlertas = alDat?.total || 0

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error: ${error}`} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Barra superior */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        alignItems: 'center', flexWrap: 'wrap', gap: 10,
      }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 8, padding: '8px 14px', fontSize: 11, color: t.textSub,
          }}>
            📦 <strong style={{ color: t.text }}>{data?.total || 0}</strong> productos
          </div>

          {totalAlertas > 0 && (
            <button onClick={() => setSoloBajos(s => !s)} style={{
              background: soloBajos ? t.accent : t.accentSub,
              border: `1px solid ${t.accent}55`,
              color: soloBajos ? '#fff' : t.accent,
              borderRadius: 8, padding: '8px 14px',
              fontSize: 11, fontWeight: 600, cursor: 'pointer',
              fontFamily: 'inherit', transition: 'all .15s',
            }}>
              ⚠️ {totalAlertas} alertas{soloBajos ? ' — Ver todos' : ' — Ver solo alertas'}
            </button>
          )}

          <div style={{
            fontSize: 10, color: t.textMuted,
            background: t.card, border: `1px solid ${t.border}`,
            borderRadius: 7, padding: '5px 10px',
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <span style={{ opacity:.55 }}>✏</span>
            Clic en precio o stock para editar · Enter para guardar
          </div>
        </div>

        <StyledInput
          value={busqueda}
          onChange={e => setBusqueda(e.target.value)}
          placeholder="Buscar producto o código..."
          style={{ width: 240 }}
        />
      </div>

      {/* Categorías */}
      {categorias.map(([cat, prods]) => {
        const label     = cat.replace(/^\d+\s*/, '')
        const filtrados = filtrar(prods)
        if ((busqueda || soloBajos) && filtrados.length === 0) return null
        const alertasCat = prods.filter(p => alertaMap[p.key]).length
        const expandida  = !!(busqueda || soloBajos) || abierta === cat

        return (
          <div key={cat} style={{
            background: t.card,
            border: `1px solid ${expandida ? t.accent + '44' : t.border}`,
            borderRadius: 10, overflow: 'hidden',
            transition: 'border-color .2s',
          }}>
            {/* Header colapsable */}
            <div
              onClick={() => !(busqueda || soloBajos) && setAbierta(p => p === cat ? null : cat)}
              style={{
                padding: '12px 16px', display: 'flex',
                alignItems: 'center', justifyContent: 'space-between',
                cursor: (busqueda || soloBajos) ? 'default' : 'pointer',
                userSelect: 'none',
              }}
              onMouseEnter={e => { if (!(busqueda || soloBajos)) e.currentTarget.style.background = t.cardHover }}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ fontSize: 17 }}>{catIcon(label)}</span>
                <span style={{ fontWeight: 600, fontSize: 13, color: t.text }}>{label}</span>
                <span style={{ fontSize: 10, color: t.textMuted }}>{prods.length} productos</span>
                {alertasCat > 0 && (
                  <span style={{ fontSize: 10, color: t.accent, fontWeight: 600 }}>⚠️ {alertasCat}</span>
                )}
              </div>
              {!(busqueda || soloBajos) && (
                <span style={{
                  color: t.textMuted, fontSize: 11,
                  transition: 'transform .2s',
                  transform: expandida ? 'rotate(90deg)' : 'rotate(0deg)',
                  display: 'inline-block',
                }}>▶</span>
              )}
            </div>

            {/* Tabla editable */}
            {expandida && (
              <div style={{ borderTop: `1px solid ${t.border}`, overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: t.tableAlt }}>
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
                        key={p.key}
                        p={p}
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
