/*
 * App.jsx — entry point del dashboard.
 * Fase 4 (Wave 1): nuevo shell con sidebar + react-router rutas reales.
 * Cada tab vive en su propia ruta; ThemeContext legacy se mantiene para tabs
 * aún no migradas a tokens shadcn (waves 2-4).
 */
import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useOutletContext } from 'react-router-dom'
import { ProtectedRoute } from './components/ProtectedRoute.jsx'
import { Toaster } from './components/ui/sonner.jsx'
import Login from './pages/Login.jsx'
import AppShell from './components/AppShell.jsx'

import TabHoy             from './tabs/TabHoy.jsx'
import TabResumen         from './tabs/TabResumen.jsx'
import TabTopProductos    from './tabs/TabTopProductos.jsx'
import TabInventario      from './tabs/TabInventario.jsx'
import TabHistorial       from './tabs/TabHistorial.jsx'
import TabHistoricoVentas from './tabs/TabHistoricoVentas.jsx'
import TabCaja            from './tabs/TabCaja.jsx'
import TabGastos          from './tabs/TabGastos.jsx'
import TabCompras         from './tabs/TabCompras.jsx'
import TabComprasFiscal   from './tabs/TabComprasFiscal.jsx'
import TabKardex          from './tabs/TabKardex.jsx'
import TabResultados      from './tabs/TabResultados.jsx'
import TabVentasRapidas   from './tabs/TabVentasRapidas.jsx'
import TabProveedores     from './tabs/TabProveedores.jsx'
import TabFacturacion     from './tabs/TabFacturacion.jsx'
import TabLibroIVA        from './tabs/TabLibroIVA.jsx'
import TabClientes        from './tabs/TabClientes.jsx'
import FacturasElectronicasRecibidas from './tabs/FacturasElectronicasRecibidas.jsx'

// ── Wrapper para pasar refreshKey del Outlet a cada tab ─────────────────────
function R({ Component }) {
  const ctx = useOutletContext() || {}
  return <Component refreshKey={ctx.refreshKey ?? 0} />
}

// ── Error Boundary ─────────────────────────────────────────────────────────
class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null } }
  static getDerivedStateFromError(error) { return { hasError: true, error } }
  render() {
    if (this.state.hasError) {
      const msg = this.state.error?.message || String(this.state.error)
      return (
        <div className="min-h-dvh grid place-items-center bg-background p-8">
          <div className="max-w-lg bg-surface border border-border rounded-lg p-8 shadow-md">
            <h2 className="text-lg font-semibold text-primary mb-2">Error al cargar el dashboard</h2>
            <pre className="bg-surface-2 rounded-md p-3 text-xs text-secondary-foreground overflow-x-auto whitespace-pre-wrap mb-4">
              {msg}
            </pre>
            <button
              onClick={() => window.location.reload()}
              className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm hover:bg-primary-hover"
            >
              Recargar
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <Toaster position="bottom-right" />
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route path="/"                    element={<Navigate to="/hoy" replace />} />
            <Route path="/hoy"                 element={<R Component={TabHoy} />} />
            <Route path="/ventas"              element={<R Component={TabVentasRapidas} />} />
            <Route path="/caja"                element={<R Component={TabCaja} />} />
            <Route path="/inventario"          element={<R Component={TabInventario} />} />
            <Route path="/clientes"            element={<R Component={TabClientes} />} />
            <Route path="/compras"             element={<R Component={TabCompras} />} />
            <Route path="/proveedores"         element={<R Component={TabProveedores} />} />
            <Route path="/gastos"              element={<R Component={TabGastos} />} />
            <Route path="/resumen"             element={<R Component={TabResumen} />} />
            <Route path="/historial"           element={<R Component={TabHistorial} />} />
            <Route path="/historico"           element={<R Component={TabHistoricoVentas} />} />
            <Route path="/resultados"          element={<R Component={TabResultados} />} />
            <Route path="/resultados/top"      element={<R Component={TabTopProductos} />} />
            <Route path="/kardex"              element={<R Component={TabKardex} />} />
            <Route path="/facturacion"         element={<R Component={TabFacturacion} />} />
            <Route path="/facturas-recibidas"  element={<R Component={FacturasElectronicasRecibidas} />} />
            <Route path="/libro-iva"           element={<R Component={TabLibroIVA} />} />
            <Route path="/compras-fiscal"      element={<R Component={TabComprasFiscal} />} />
            <Route path="*"                    element={<Navigate to="/hoy" replace />} />
          </Route>
        </Routes>
      </Router>
    </ErrorBoundary>
  )
}
