import { useState } from 'react'
import {
  useTheme, useFetch, Card, SectionTitle, KpiCard,
  Spinner, ErrorMsg, StyledInput, EmptyState, cop, num,
} from '../components/shared.jsx'

function MovRow({ m, t }) {
  const esEntrada = m.tipo === 'entrada'
  return (
    <tr style={{ borderBottom: `1px solid ${t.border}` }}
      onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
      <td style={{ padding: '8px 12px', color: t.textMuted, fontSize: 11, whiteSpace: 'nowrap' }}>{m.fecha}</td>
      <td style={{ padding: '8px 12px', color: t.textMuted, fontSize: 10 }}>{m.hora}</td>
      <td style={{ padding: '8px 12px' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          background: esEntrada ? (t.id === 'caramelo' ? '#f0fdf4' : '#052e1650') : (t.id === 'caramelo' ? '#fff7ed' : '#431a0850'),
          color: esEntrada ? t.green : t.yellow,
          border: `1px solid ${esEntrada ? t.green : t.yellow}33`,
          padding: '2px 8px', borderRadius: 99, fontSize: 10, fontWeight: 600,
        }}>
          {esEntrada ? '▲ Entrada' : '▼ Salida'}
        </span>
      </td>
      <td style={{ padding: '8px 12px', color: t.textSub, fontSize: 11 }}>{m.concepto}</td>
      <td style={{ padding: '8px 12px', textAlign: 'right', color: esEntrada ? t.green : 'transparent', fontWeight: 600 }}>
        {esEntrada ? `+${num(m.entrada)}` : ''}
      </td>
      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.yellow, fontWeight: 600 }}>
        {!esEntrada && m.salida > 0 ? `-${num(m.salida)}` : ''}
      </td>
      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.text, fontWeight: 600 }}>{num(m.saldo)}</td>
      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.textMuted, fontSize: 11 }}>{cop(m.costo_unitario)}</td>
      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.accent, fontWeight: 600 }}>{cop(m.costo_promedio)}</td>
      <td style={{ padding: '8px 12px', textAlign: 'right', color: t.blue }}>{cop(m.valor_total)}</td>
    </tr>
  )
}

function ProductoKardex({ item, t }) {
  const [abierto, setAbierto] = useState(false)
  const movs = item.movimientos || []
  const margen = item.costo_promedio && item.costo_promedio > 0 ? item : null

  return (
    <div style={{
      background: t.card, border: `1px solid ${t.border}`,
      borderRadius: 10, overflow: 'hidden', marginBottom: 10,
    }}>
      {/* Header producto */}
      <div
        onClick={() => setAbierto(p => !p)}
        style={{
          padding: '12px 16px', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', cursor: 'pointer', userSelect: 'none',
        }}
        onMouseEnter={e => e.currentTarget.style.background = t.cardHover}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: 16 }}>📦</span>
          <div>
            <div style={{ fontWeight: 600, color: t.text }}>{item.producto}</div>
            <div style={{ fontSize: 10, color: t.textMuted, marginTop: 2 }}>
              {movs.length} movimiento{movs.length !== 1 ? 's' : ''}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10, color: t.textMuted }}>Entradas</div>
            <div style={{ color: t.green, fontWeight: 600 }}>{num(item.total_entradas)}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10, color: t.textMuted }}>Stock actual</div>
            <div style={{ color: item.stock_actual > 0 ? t.text : '#f87171', fontWeight: 600 }}>
              {num(item.stock_actual)}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10, color: t.textMuted }}>Costo prom.</div>
            <div style={{ color: t.accent, fontWeight: 600 }}>{cop(item.costo_promedio)}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 10, color: t.textMuted }}>Valor inv.</div>
            <div style={{ color: t.blue, fontWeight: 700 }}>{cop(item.valor_inventario)}</div>
          </div>
          <span style={{ color: t.textMuted, fontSize: 11, transition: 'transform .2s', transform: abierto ? 'rotate(90deg)' : 'rotate(0deg)', display: 'inline-block' }}>▶</span>
        </div>
      </div>

      {/* Tabla de movimientos */}
      {abierto && (
        <div style={{ borderTop: `1px solid ${t.border}`, overflowX: 'auto' }}>
          {item.salidas_est > 0 && (
            <div style={{
              padding: '8px 16px', background: t.tableAlt,
              fontSize: 11, color: t.textMuted,
              borderBottom: `1px solid ${t.border}`,
            }}>
              ℹ️ Salidas estimadas: <strong style={{ color: t.yellow }}>{num(item.salidas_est)}</strong> unidades
              (total entradas − stock actual). Para salidas exactas por venta, el sistema requiere cruze de nombres con Excel.
            </div>
          )}
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr style={{ background: t.tableAlt }}>
                {['Fecha', 'Hora', 'Tipo', 'Concepto', 'Entrada', 'Salida', 'Saldo', 'Costo Unit.', 'C. Prom.', 'Valor'].map((h, i) => (
                  <th key={i} style={{
                    padding: '7px 12px',
                    textAlign: [4,5,6,7,8,9].includes(i) ? 'right' : 'left',
                    fontSize: 9, color: t.textMuted, textTransform: 'uppercase',
                    letterSpacing: '.07em', fontWeight: 500,
                    borderBottom: `1px solid ${t.border}`, whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {movs.map((m, i) => <MovRow key={i} m={m} t={t} />)}
            </tbody>
            <tfoot>
              <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                <td colSpan={4} style={{ padding: '8px 12px', fontSize: 9, color: t.textMuted, fontWeight: 600 }}>TOTALES</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', color: t.green, fontWeight: 700 }}>{num(item.total_entradas)}</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', color: t.yellow, fontWeight: 700 }}>{num(item.salidas_est)}</td>
                <td style={{ padding: '8px 12px', textAlign: 'right', color: t.text, fontWeight: 700 }}>{num(item.stock_actual)}</td>
                <td colSpan={2} />
                <td style={{ padding: '8px 12px', textAlign: 'right', color: t.blue, fontWeight: 700 }}>{cop(item.valor_inventario)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

export default function TabKardex({ refreshKey }) {
  const t = useTheme()
  const [busqueda, setBusqueda] = useState('')
  const [query,    setQuery]    = useState('')

  const { data, loading, error } = useFetch(
    query ? `/kardex?q=${encodeURIComponent(query)}` : '/kardex',
    [query, refreshKey]
  )

  const handleSearch = (v) => {
    setBusqueda(v)
    clearTimeout(window._kardexTimer)
    window._kardexTimer = setTimeout(() => setQuery(v), 300)
  }

  const items        = data?.kardex || []
  const totalValor   = data?.valor_inventario_total || 0
  const tieneDatos   = data?.tiene_datos

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: t.text }}>Kárdex de Inventario</div>
          <div style={{ fontSize: 11, color: t.textMuted, marginTop: 3 }}>
            Movimientos por producto · Método promedio ponderado (NIIF pymes)
          </div>
        </div>
        <StyledInput
          value={busqueda}
          onChange={e => handleSearch(e.target.value)}
          placeholder="🔍  Buscar producto..."
          style={{ width: 260 }}
        />
      </div>

      {loading && <Spinner />}
      {error   && <ErrorMsg msg={`Error: ${error}`} />}

      {!loading && !error && (
        <>
          {!tieneDatos ? (
            <Card>
              <div style={{ padding: '32px 24px', textAlign: 'center' }}>
                <div style={{ fontSize: 36, marginBottom: 12 }}>📋</div>
                <div style={{ color: t.text, fontWeight: 600, fontSize: 14, marginBottom: 10 }}>
                  El Kárdex se construye automáticamente
                </div>
                <div style={{ color: t.textMuted, fontSize: 12, maxWidth: 400, margin: '0 auto', lineHeight: 1.7 }}>
                  Cada vez que registres una compra de mercancía en Telegram, el sistema construirá el kárdex con el método de promedio ponderado.
                </div>
                <code style={{
                  display: 'inline-block', marginTop: 14,
                  background: t.tableAlt, color: t.accent,
                  border: `1px solid ${t.border}`,
                  padding: '8px 16px', borderRadius: 8, fontSize: 12,
                }}>
                  /compra 20 brocha 2" a 2500 de Ferrisariato
                </code>
                <div style={{ color: t.textMuted, fontSize: 11, marginTop: 10 }}>
                  Una vez registres compras, aquí verás entradas, salidas, saldos y costo promedio por producto.
                </div>
              </div>
            </Card>
          ) : (
            <>
              {/* KPIs */}
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <KpiCard label="Productos" value={items.length} sub="Con historial de compras" icon="📦" color={t.textSub} />
                <KpiCard label="Valor inventario" value={cop(totalValor)} sub="Costo promedio × stock" icon="💰" color={t.blue} />
              </div>

              {/* Lista productos */}
              {items.length === 0 ? (
                <Card><EmptyState msg="Sin resultados para la búsqueda." /></Card>
              ) : (
                items.map(item => <ProductoKardex key={item.producto} item={item} t={t} />)
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
