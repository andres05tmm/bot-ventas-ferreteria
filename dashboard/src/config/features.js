/*
 * features.js — feature flags del dashboard (se resuelven en build time desde
 * las env VITE_*). Reflejan los flags del backend (config.py) para mostrar u
 * ocultar tabs por ferretería.
 *
 * Default = visible (true) cuando la var NO está seteada, para que Punto Rojo
 * —que no define estas VITE_*— siga viendo todos los tabs. Una ferretería nueva
 * sin un módulo debe setear su VITE_*=false al hacer `npm run build`.
 */
const off = (v) => v === 'false' || v === false

export const FEATURES = {
  // Módulo fiscal (FE DIAN): Facturación, Facturas recibidas, Libro IVA, Compras Fiscal
  facturacion: !off(import.meta.env.VITE_FE_HABILITADA),
  // Inventario + Kárdex
  inventario: !off(import.meta.env.VITE_INVENTARIO_HABILITADO),
  // Caja + Gastos
  caja: !off(import.meta.env.VITE_CAJA_HABILITADA),
}

// Mapa ruta → flag. Las rutas no listadas son núcleo (siempre visibles).
const RUTA_FEATURE = {
  '/facturacion': 'facturacion',
  '/facturas-recibidas': 'facturacion',
  '/libro-iva': 'facturacion',
  '/compras-fiscal': 'facturacion',
  '/inventario': 'inventario',
  '/kardex': 'inventario',
  '/caja': 'caja',
  '/gastos': 'caja',
}

/** ¿La ruta está habilitada según los feature flags? Núcleo siempre true. */
export function isRouteEnabled(path) {
  const flag = RUTA_FEATURE[path]
  return flag ? FEATURES[flag] : true
}
