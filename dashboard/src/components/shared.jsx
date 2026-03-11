// ── Utilidades compartidas ────────────────────────────────────────────────────

/** Formatea número como pesos colombianos: $1.250.000 */
export function cop(num) {
  if (num === null || num === undefined || isNaN(num)) return '$0'
  return '$' + Math.round(num).toLocaleString('es-CO')
}

/** Formatea número con separador de miles: 1.250 */
export function num(n) {
  if (n === null || n === undefined) return '0'
  return Number(n).toLocaleString('es-CO', { maximumFractionDigits: 2 })
}

// ── Componentes base ──────────────────────────────────────────────────────────

export function Card({ children, style = {} }) {
  return (
    <div style={{
      background: '#141414',
      border: '1px solid #2a2a2a',
      borderRadius: 10,
      padding: 20,
      ...style,
    }}>
      {children}
    </div>
  )
}

export function KpiCard({ label, value, sub, color = '#dc2626' }) {
  return (
    <Card style={{ flex: 1, minWidth: 160 }}>
      <div style={{ color: '#888', fontSize: 12, marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color, letterSpacing: -1 }}>
        {value}
      </div>
      {sub && <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>{sub}</div>}
    </Card>
  )
}

export function SectionTitle({ children }) {
  return (
    <h2 style={{
      fontSize: 15,
      fontWeight: 600,
      color: '#f5f5f5',
      marginBottom: 16,
      paddingBottom: 8,
      borderBottom: '1px solid #2a2a2a',
    }}>
      {children}
    </h2>
  )
}

export function Spinner() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 48, color: '#666' }}>
      <span style={{ fontSize: 13 }}>Cargando...</span>
    </div>
  )
}

export function ErrorMsg({ msg }) {
  return (
    <div style={{
      background: '#1a0a0a',
      border: '1px solid #7f1d1d',
      borderRadius: 8,
      padding: '12px 16px',
      color: '#f87171',
      fontSize: 13,
    }}>
      {msg}
    </div>
  )
}

export function Badge({ children, color = '#dc2626' }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      background: color + '22',
      color,
      fontSize: 11,
      fontWeight: 600,
    }}>
      {children}
    </span>
  )
}

// ── Hook de fetch ─────────────────────────────────────────────────────────────
import { useState, useEffect } from 'react'
import { API_BASE } from '../App.jsx'

export function useFetch(path, deps = []) {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`${API_BASE}${path}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(d => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, loading, error }
}
