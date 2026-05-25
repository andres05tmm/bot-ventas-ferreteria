/**
 * ReporteFinanciero.jsx
 *
 * Renderiza el reporte financiero como HTML invisible listo para capturar
 * con html2canvas y convertir a PDF. Diseño inspirado en estados NIIF pymes.
 *
 * Props:
 *   datos: objeto con campos del endpoint /chat/reporte-datos
 *   forwardRef: ref apuntando al div raíz (para html2canvas)
 */

import { forwardRef } from 'react'

// ── Helpers de formato ────────────────────────────────────────────────────────

function cop(valor) {
  const n = Number(valor) || 0
  return '$' + n.toLocaleString('es-CO', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function pct(parte, total) {
  if (!total) return '0%'
  return ((Number(parte) / Number(total)) * 100).toFixed(1) + '%'
}

// ── Estilos inline (fondo siempre blanco, independiente del tema) ─────────────

const S = {
  page: {
    width: '794px',
    padding: '40px',
    backgroundColor: '#ffffff',
    fontFamily: 'Arial, Helvetica, sans-serif',
    color: '#111111',
    fontSize: '13px',
    lineHeight: '1.5',
    boxSizing: 'border-box',
  },
  header: {
    backgroundColor: '#C8200E',
    color: '#ffffff',
    padding: '28px 32px 24px',
    borderRadius: '6px 6px 0 0',
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
    marginBottom: '0',
  },
  logoSvg: {
    flexShrink: 0,
  },
  headerTexts: {
    flex: 1,
  },
  headerTitle: {
    fontSize: '22px',
    fontWeight: 'bold',
    margin: 0,
    letterSpacing: '0.5px',
  },
  headerSub: {
    fontSize: '12px',
    opacity: 0.88,
    margin: '3px 0 0',
  },
  reportTitle: {
    textAlign: 'right',
    fontSize: '11px',
    opacity: 0.88,
    marginTop: '6px',
  },
  section: {
    border: '1px solid #e0e0e0',
    borderTop: 'none',
    padding: '18px 24px',
    backgroundColor: '#ffffff',
  },
  sectionLast: {
    border: '1px solid #e0e0e0',
    borderTop: 'none',
    padding: '18px 24px',
    backgroundColor: '#ffffff',
    borderRadius: '0 0 6px 6px',
  },
  sectionTitle: {
    fontSize: '11px',
    fontWeight: 'bold',
    color: '#888888',
    textTransform: 'uppercase',
    letterSpacing: '0.8px',
    marginBottom: '12px',
    borderBottom: '1px solid #eeeeee',
    paddingBottom: '6px',
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '4px 0',
  },
  rowTotal: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '6px 0',
    fontWeight: 'bold',
    borderTop: '1px solid #cccccc',
    marginTop: '4px',
  },
  numRight: {
    textAlign: 'right',
    minWidth: '120px',
    fontVariantNumeric: 'tabular-nums',
  },
  numRightBold: {
    textAlign: 'right',
    minWidth: '120px',
    fontVariantNumeric: 'tabular-nums',
    fontWeight: 'bold',
  },
  pctCell: {
    textAlign: 'right',
    minWidth: '55px',
    color: '#666666',
    fontSize: '12px',
  },
  positive: { color: '#15803d', fontWeight: 'bold' },
  negative: { color: '#dc2626', fontWeight: 'bold' },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '12px',
  },
  th: {
    textAlign: 'left',
    padding: '6px 8px',
    backgroundColor: '#f3f3f3',
    fontWeight: 'bold',
    fontSize: '11px',
    color: '#555555',
    borderBottom: '1px solid #dddddd',
  },
  thRight: {
    textAlign: 'right',
    padding: '6px 8px',
    backgroundColor: '#f3f3f3',
    fontWeight: 'bold',
    fontSize: '11px',
    color: '#555555',
    borderBottom: '1px solid #dddddd',
  },
  td: {
    padding: '6px 8px',
    borderBottom: '1px solid #eeeeee',
  },
  tdRight: {
    textAlign: 'right',
    padding: '6px 8px',
    borderBottom: '1px solid #eeeeee',
    fontVariantNumeric: 'tabular-nums',
  },
  indicadoresGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '12px',
  },
  indicadorCard: {
    backgroundColor: '#f8f8f8',
    borderRadius: '5px',
    padding: '10px 12px',
    textAlign: 'center',
    border: '1px solid #eeeeee',
  },
  indicadorValor: {
    fontSize: '18px',
    fontWeight: 'bold',
    color: '#C8200E',
    display: 'block',
    lineHeight: 1.2,
  },
  indicadorLabel: {
    fontSize: '10px',
    color: '#888888',
    marginTop: '3px',
    display: 'block',
  },
  footer: {
    marginTop: '20px',
    textAlign: 'center',
    fontSize: '10px',
    color: '#aaaaaa',
    borderTop: '1px solid #eeeeee',
    paddingTop: '12px',
  },
}

// ── Logo SVG de la ferretería ─────────────────────────────────────────────────

function LogoFerreteria() {
  return (
    <svg style={S.logoSvg} width="56" height="56" viewBox="0 0 56 56" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="56" height="56" rx="10" fill="white" fillOpacity="0.18"/>
      {/* Martillo */}
      <rect x="12" y="26" width="22" height="8" rx="2" fill="white"/>
      <rect x="30" y="18" width="8" height="20" rx="2" fill="white" fillOpacity="0.85"/>
      {/* Llave */}
      <circle cx="38" cy="36" r="6" stroke="white" strokeWidth="2.5" fill="none"/>
      <line x1="38" y1="30" x2="38" y2="20" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
    </svg>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────

const ReporteFinanciero = forwardRef(function ReporteFinanciero({ datos }, ref) {
  if (!datos) return null

  const {
    periodo = 'mes',
    fecha_generacion = new Date().toLocaleDateString('es-CO'),
    estado_resultados = {},
    indicadores = {},
    gastos_categorias = [],
    top_productos = [],
    proyeccion = {},
    cuentas_pagar = [],
  } = datos

  const {
    ingresos = 0,
    cmv = 0,
    utilidad_bruta = 0,
    gastos_operativos = 0,
    utilidad_neta = 0,
  } = estado_resultados

  const utilidadNeta = Number(utilidad_neta)
  const esPositiva = utilidadNeta >= 0

  return (
    <div ref={ref} style={S.page}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={S.header}>
        <LogoFerreteria />
        <div style={S.headerTexts}>
          <p style={S.headerTitle}>FERRETERÍA PUNTO ROJO</p>
          <p style={S.headerSub}>Cartagena, Colombia</p>
        </div>
        <div style={S.reportTitle}>
          <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '4px' }}>REPORTE FINANCIERO</div>
          <div>Período: {periodo === 'mes' ? 'Mes actual' : 'Semana actual'}</div>
          <div>Generado: {fecha_generacion}</div>
        </div>
      </div>

      {/* ── Estado de Resultados ───────────────────────────────────────────── */}
      <div style={S.section}>
        <div style={S.sectionTitle}>Estado de Resultados</div>

        <div style={S.row}>
          <span>Ingresos totales</span>
          <div style={{ display: 'flex', gap: '40px' }}>
            <span style={S.numRight}>{cop(ingresos)}</span>
            <span style={S.pctCell}>100%</span>
          </div>
        </div>

        <div style={S.row}>
          <span style={{ color: '#555' }}>(−) Costo de mercancía vendida</span>
          <div style={{ display: 'flex', gap: '40px' }}>
            <span style={S.numRight}>{cop(cmv)}</span>
            <span style={S.pctCell}>{pct(cmv, ingresos)}</span>
          </div>
        </div>

        <div style={S.rowTotal}>
          <span>= Utilidad Bruta</span>
          <div style={{ display: 'flex', gap: '40px' }}>
            <span style={S.numRightBold}>{cop(utilidad_bruta)}</span>
            <span style={{ ...S.pctCell, fontWeight: 'bold' }}>{pct(utilidad_bruta, ingresos)}</span>
          </div>
        </div>

        <div style={{ ...S.row, marginTop: '8px' }}>
          <span style={{ color: '#555' }}>(−) Gastos operativos</span>
          <div style={{ display: 'flex', gap: '40px' }}>
            <span style={S.numRight}>{cop(gastos_operativos)}</span>
            <span style={S.pctCell}>{pct(gastos_operativos, ingresos)}</span>
          </div>
        </div>

        <div style={S.rowTotal}>
          <span>= Utilidad Neta</span>
          <div style={{ display: 'flex', gap: '40px' }}>
            <span style={{ ...S.numRightBold, ...(esPositiva ? S.positive : S.negative) }}>
              {cop(utilidadNeta)}
            </span>
            <span style={{ ...S.pctCell, fontWeight: 'bold', color: esPositiva ? '#15803d' : '#dc2626' }}>
              {pct(utilidadNeta, ingresos)}
            </span>
          </div>
        </div>
      </div>

      {/* ── Indicadores Clave ─────────────────────────────────────────────── */}
      <div style={S.section}>
        <div style={S.sectionTitle}>Indicadores Clave</div>
        <div style={S.indicadoresGrid}>
          <div style={S.indicadorCard}>
            <span style={S.indicadorValor}>{pct(utilidad_bruta, ingresos)}</span>
            <span style={S.indicadorLabel}>Margen Bruto</span>
          </div>
          <div style={S.indicadorCard}>
            <span style={{ ...S.indicadorValor, color: esPositiva ? '#15803d' : '#dc2626' }}>
              {pct(utilidadNeta, ingresos)}
            </span>
            <span style={S.indicadorLabel}>Margen Neto</span>
          </div>
          <div style={S.indicadorCard}>
            <span style={S.indicadorValor}>{cop(indicadores.ticket_promedio || 0)}</span>
            <span style={S.indicadorLabel}>Ticket Promedio</span>
          </div>
          <div style={S.indicadorCard}>
            <span style={S.indicadorValor}>{Number(indicadores.transacciones || 0).toLocaleString('es-CO')}</span>
            <span style={S.indicadorLabel}>Transacciones</span>
          </div>
        </div>
      </div>

      {/* ── Desglose de Gastos ────────────────────────────────────────────── */}
      {gastos_categorias.length > 0 && (
        <div style={S.section}>
          <div style={S.sectionTitle}>Desglose de Gastos por Categoría</div>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Categoría</th>
                <th style={S.thRight}>Monto</th>
                <th style={S.thRight}>% del Total</th>
              </tr>
            </thead>
            <tbody>
              {gastos_categorias.map((g, i) => (
                <tr key={i} style={{ backgroundColor: i % 2 === 0 ? '#f9f9f9' : '#ffffff' }}>
                  <td style={S.td}>{g.categoria || '—'}</td>
                  <td style={S.tdRight}>{cop(g.monto)}</td>
                  <td style={S.tdRight}>{pct(g.monto, gastos_operativos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Top 5 Productos ───────────────────────────────────────────────── */}
      {top_productos.length > 0 && (
        <div style={S.section}>
          <div style={S.sectionTitle}>Top 5 Productos por Ingresos</div>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={{ ...S.th, width: '32px' }}>#</th>
                <th style={S.th}>Producto</th>
                <th style={S.thRight}>Ingresos</th>
                <th style={S.thRight}>% Ventas</th>
                <th style={S.thRight}>Unidades</th>
              </tr>
            </thead>
            <tbody>
              {top_productos.slice(0, 5).map((p, i) => (
                <tr key={i} style={{ backgroundColor: i % 2 === 0 ? '#f9f9f9' : '#ffffff' }}>
                  <td style={{ ...S.td, fontWeight: 'bold', color: '#C8200E' }}>{i + 1}</td>
                  <td style={S.td}>{p.producto || '—'}</td>
                  <td style={S.tdRight}>{cop(p.ingresos)}</td>
                  <td style={S.tdRight}>{pct(p.ingresos, ingresos)}</td>
                  <td style={S.tdRight}>{(Number(p.unidades) || 0).toLocaleString('es-CO')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Proyección de Cierre ──────────────────────────────────────────── */}
      {(proyeccion.caja_actual != null) && (
        <div style={S.section}>
          <div style={S.sectionTitle}>Proyección de Cierre de Mes</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '10px' }}>
            {[
              { label: 'Caja Actual', valor: cop(proyeccion.caja_actual) },
              { label: 'Proyección Fin de Mes', valor: cop(proyeccion.proyeccion_fin_mes) },
              { label: 'Prom. diario ventas', valor: cop(proyeccion.promedio_diario_ventas) },
              { label: 'Prom. diario gastos', valor: cop(proyeccion.promedio_diario_gastos) },
            ].map((item, i) => (
              <div key={i} style={{ ...S.indicadorCard, textAlign: 'left' }}>
                <span style={{ fontSize: '15px', fontWeight: 'bold', display: 'block' }}>{item.valor}</span>
                <span style={S.indicadorLabel}>{item.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Cuentas por Pagar ─────────────────────────────────────────────── */}
      {cuentas_pagar.length > 0 && (
        <div style={S.sectionLast}>
          <div style={S.sectionTitle}>Cuentas por Pagar (Proveedores)</div>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Proveedor</th>
                <th style={S.th}>Factura</th>
                <th style={S.thRight}>Saldo Pendiente</th>
              </tr>
            </thead>
            <tbody>
              {cuentas_pagar.map((c, i) => (
                <tr key={i} style={{ backgroundColor: i % 2 === 0 ? '#f9f9f9' : '#ffffff' }}>
                  <td style={S.td}>{c.proveedor || '—'}</td>
                  <td style={S.td}>{c.factura || '—'}</td>
                  <td style={{ ...S.tdRight, fontWeight: 'bold', color: '#dc2626' }}>{cop(c.saldo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <div style={S.footer}>
        Generado automáticamente por FerreBot · ferreteriapuntorojo.com
      </div>

    </div>
  )
})

export default ReporteFinanciero
