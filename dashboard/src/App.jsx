/*
 * App.jsx — entry point del dashboard.
 * Shell con sidebar + react-router. Cada tab vive en su propia ruta.
 */
import React, { Suspense, lazy } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useOutletContext } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { ProtectedRoute } from './components/ProtectedRoute.jsx'
import { Toaster } from './components/ui/sonner.jsx'
import Login from './pages/Login.jsx'
import AppShell from './components/AppShell.jsx'
import { isRouteEnabled } from './config/features.js'

// Code-splitting por tab — cada ruta descarga su chunk on-demand.
const TabHoy             = lazy(() => import('./tabs/TabHoy.jsx'))
const TabTopProductos    = lazy(() => import('./tabs/TabTopProductos.jsx'))
const TabInventario      = lazy(() => import('./tabs/TabInventario.jsx'))
const TabHistorial       = lazy(() => import('./tabs/TabHistorial.jsx'))
const TabCaja            = lazy(() => import('./tabs/TabCaja.jsx'))
const TabGastos          = lazy(() => import('./tabs/TabGastos.jsx'))
const TabCompras         = lazy(() => import('./tabs/TabCompras.jsx'))
const TabComprasFiscal   = lazy(() => import('./tabs/TabComprasFiscal.jsx'))
const TabKardex          = lazy(() => import('./tabs/TabKardex.jsx'))
const TabResultados      = lazy(() => import('./tabs/TabResultados.jsx'))
const TabVentasRapidas   = lazy(() => import('./tabs/TabVentasRapidas.jsx'))
const TabProveedores     = lazy(() => import('./tabs/TabProveedores.jsx'))
const TabFacturacion     = lazy(() => import('./tabs/TabFacturacion.jsx'))
const TabLibroIVA        = lazy(() => import('./tabs/TabLibroIVA.jsx'))
const TabClientes        = lazy(() => import('./tabs/TabClientes.jsx'))
const FacturasElectronicasRecibidas = lazy(() => import('./tabs/FacturasElectronicasRecibidas.jsx'))

// Fallback durante la carga del chunk del tab.
function TabFallback() {
  return (
    <div className="min-h-[50vh] grid place-items-center" role="status" aria-label="Cargando vista">
      <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
    </div>
  )
}

// ── Wrapper para pasar refreshKey del Outlet a cada tab ─────────────────────
function R({ Component }) {
  const ctx = useOutletContext() || {}
  return (
    <Suspense fallback={<TabFallback />}>
      <Component refreshKey={ctx.refreshKey ?? 0} />
    </Suspense>
  )
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
            {isRouteEnabled('/caja') &&
            <Route path="/caja"                element={<R Component={TabCaja} />} />}
            {isRouteEnabled('/inventario') &&
            <Route path="/inventario"          element={<R Component={TabInventario} />} />}
            <Route path="/clientes"            element={<R Component={TabClientes} />} />
            <Route path="/compras"             element={<R Component={TabCompras} />} />
            <Route path="/proveedores"         element={<R Component={TabProveedores} />} />
            {isRouteEnabled('/gastos') &&
            <Route path="/gastos"              element={<R Component={TabGastos} />} />}
            {/* /resumen fue absorbido por /hoy en Fase C — mantenemos redirect para links guardados */}
            <Route path="/resumen"             element={<Navigate to="/hoy" replace />} />
            <Route path="/historial"           element={<R Component={TabHistorial} />} />
            {/* /historico fue absorbido por /historial?view=mes en Fase D */}
            <Route path="/historico"           element={<Navigate to="/historial?view=mes" replace />} />
            <Route path="/resultados"          element={<R Component={TabResultados} />} />
            <Route path="/resultados/top"      element={<R Component={TabTopProductos} />} />
            {isRouteEnabled('/kardex') &&
            <Route path="/kardex"              element={<R Component={TabKardex} />} />}
            {isRouteEnabled('/facturacion') &&
            <Route path="/facturacion"         element={<R Component={TabFacturacion} />} />}
            {isRouteEnabled('/facturas-recibidas') &&
            <Route path="/facturas-recibidas"  element={<R Component={FacturasElectronicasRecibidas} />} />}
            {isRouteEnabled('/libro-iva') &&
            <Route path="/libro-iva"           element={<R Component={TabLibroIVA} />} />}
            {isRouteEnabled('/compras-fiscal') &&
            <Route path="/compras-fiscal"      element={<R Component={TabComprasFiscal} />} />}
            <Route path="*"                    element={<Navigate to="/hoy" replace />} />
          </Route>
        </Routes>
      </Router>
    </ErrorBoundary>
  )
}
