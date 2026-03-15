import { useState } from 'react'
import { useTheme, useFetch, Card, SectionTitle, KpiCard, Spinner, ErrorMsg, cop, useIsMobile } from '../components/shared.jsx'

function MetodoRow({ label, valor, icon, t }) {
  if (!valor) return null
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderBottom: `1px solid ${t.border}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <span style={{ color: t.textSub, fontSize: 13 }}>{label}</span>
      </div>
      <span style={{ color: t.text, fontWeight: 600, fontSize: 14 }}>{cop(valor)}</span>
    </div>
  )
}

function GastoRow({ g, t }) {
  return (
    <tr style={{ borderBottom: `1px solid ${t.border}` }}
      onMouseEnter={e => { e.currentTarget.style.background = t.cardHover; e.currentTarget.style.transform = 'translateX(2px)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.transform = 'translateX(0)' }}>
      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{g.hora || '—'}</td>
      <td style={{ padding: '9px 14px', color: t.text }}>{g.concepto || '—'}</td>
      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>
        <span style={{
          background: t.accentSub, color: t.accent,
          border: `1px solid ${t.accent}33`,
          padding: '2px 8px', borderRadius: 99, fontSize: 10,
        }}>
          {g.categoria || 'Gasto'}
        </span>
      </td>
      <td style={{ padding: '9px 14px', color: t.textMuted, fontSize: 11 }}>{g.origen || '—'}</td>
      <td style={{ padding: '9px 14px', textAlign: 'right', color: '#f87171', fontWeight: 600 }}>
        -{cop(g.monto)}
      </td>
    </tr>
  )
}

export default function TabCaja({ refreshKey }) {
  const t = useTheme()
  const isMobile = useIsMobile()
  const { data, loading, error } = useFetch('/caja', [refreshKey])

  if (loading) return <Spinner />
  if (error)   return <ErrorMsg msg={`Error cargando caja: ${error}`} />

  const d = data || {}
  const abierta = d.abierta
  const gastos  = d.gastos || []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Estado */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '10px 16px',
        background: abierta ? (t.id === 'caramelo' ? '#f0fdf4' : '#052e1688') : (t.id === 'caramelo' ? '#fafafa' : t.card),
        border: `1px solid ${abierta ? '#4ade8044' : t.border}`,
        borderRadius: 9,
      }}>
        <span style={{ fontSize: 18 }}>{abierta ? '🟢' : '⚫'}</span>
        <div>
          <span style={{ fontWeight: 600, color: abierta ? '#4ade80' : t.textMuted, fontSize: 13 }}>
            Caja {abierta ? 'abierta' : 'cerrada'}
          </span>
          {d.fecha && (
            <span style={{ color: t.textMuted, fontSize: 11, marginLeft: 10 }}>
              Fecha: {d.fecha}
            </span>
          )}
        </div>
        {!abierta && (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: t.textMuted }}>
            Abre la caja con /caja abrir [monto] en Telegram
          </span>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4,1fr)', gap: 10 }}>
        <KpiCard label="Monto apertura"   value={cop(d.monto_apertura)}  sub="Base inicial"          icon="🏦" color={t.textSub} />
        <KpiCard label="Total ventas hoy" value={cop(d.total_ventas)}    sub="Efectivo + transf. + datafono" icon="💰" color={t.green} />
        <KpiCard label="Total gastos"     value={cop(d.total_gastos)}    sub="Todos los egresos"      icon="💸" color="#f87171" />
        <KpiCard label="Efectivo esperado" value={cop(d.efectivo_esperado)} sub="Caja - gastos en efectivo" icon="🧮" color={t.accent} />
      </div>

      {/* Desglose por método */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12 }}>
        <Card>
          <SectionTitle>Ingresos por Método</SectionTitle>
          <MetodoRow label="Efectivo"      valor={d.efectivo}       icon="💵" t={t} />
          <MetodoRow label="Transferencia" valor={d.transferencias} icon="📲" t={t} />
          <MetodoRow label="Datáfono"      valor={d.datafono}       icon="💳" t={t} />
          {!d.efectivo && !d.transferencias && !d.datafono && (
            <div style={{ color: t.textMuted, fontSize: 12, padding: '12px 0' }}>Sin ventas registradas hoy.</div>
          )}
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            paddingTop: 12, marginTop: 4,
          }}>
            <span style={{ color: t.textMuted, fontSize: 12, fontWeight: 600 }}>TOTAL</span>
            <span style={{ color: t.green, fontSize: 16, fontWeight: 700 }}>{cop(d.total_ventas)}</span>
          </div>
        </Card>

        <Card>
          <SectionTitle>Resumen Efectivo</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[
              { label: 'Apertura',         valor: d.monto_apertura,   color: t.textSub },
              { label: '+ Ventas efectivo', valor: d.efectivo,         color: t.green },
              { label: '— Gastos de caja', valor: -d.total_gastos_caja, color: '#f87171' },
            ].map((row, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: `1px solid ${t.border}` }}>
                <span style={{ color: t.textSub, fontSize: 12 }}>{row.label}</span>
                <span style={{ color: row.color, fontWeight: 600 }}>
                  {row.valor < 0 ? `-${cop(Math.abs(row.valor))}` : cop(row.valor)}
                </span>
              </div>
            ))}
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 6 }}>
              <span style={{ color: t.text, fontWeight: 700 }}>= Efectivo en caja</span>
              <span style={{ color: t.accent, fontSize: 16, fontWeight: 700 }}>{cop(d.efectivo_esperado)}</span>
            </div>
          </div>
        </Card>
      </div>

      {/* Gastos del día */}
      <Card style={{ padding: 0 }}>
        <div style={{ padding: '14px 18px', borderBottom: `1px solid ${t.border}` }}>
          <SectionTitle>Gastos del Día ({gastos.length})</SectionTitle>
        </div>
        {gastos.length === 0 ? (
          <div style={{ padding: '24px', color: t.textMuted, fontSize: 12, textAlign: 'center' }}>
            Sin gastos registrados hoy.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: t.tableAlt }}>
                  {['Hora', 'Concepto', 'Categoría', 'Origen', 'Monto'].map((h, i) => (
                    <th key={i} style={{
                      padding: '9px 14px', textAlign: i === 4 ? 'right' : 'left',
                      fontSize: 10, color: t.textMuted, textTransform: 'uppercase',
                      letterSpacing: '.08em', fontWeight: 500,
                      borderBottom: `1px solid ${t.border}`,
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {gastos.map((g, i) => <GastoRow key={i} g={g} t={t} />)}
              </tbody>
              <tfoot>
                <tr style={{ background: t.tableFoot, borderTop: `1px solid ${t.border}` }}>
                  <td colSpan={4} style={{ padding: '10px 14px', fontSize: 10, color: t.textMuted, fontWeight: 600, textAlign: 'right' }}>
                    TOTAL GASTOS
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: '#f87171', fontWeight: 700, fontSize: 14 }}>
                    -{cop(d.total_gastos)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
