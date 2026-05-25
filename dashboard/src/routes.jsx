/*
 * Routes config — fuente única de verdad de la IA del dashboard.
 * Consumida por App (Routes), Sidebar (nav) y CommandPalette (búsqueda).
 * Ver `.planning/dashboard-redesign/IA.md` para el sitemap.
 */
import {
  LayoutDashboard, ShoppingCart, Wallet, Package,
  Users, Truck, Building2, Receipt,
  History, TrendingUp, BookOpen,
  FileText, FileCheck, Calculator, FileCog,
} from 'lucide-react'

export const ROUTES = [
  // Hoy — top-level, sin grupo
  { path: '/hoy',                 label: 'Hoy',                 icon: LayoutDashboard, group: 'top' },

  // Operación
  { path: '/ventas',              label: 'Ventas Rápidas',      icon: ShoppingCart,    group: 'operacion' },
  { path: '/caja',                label: 'Caja',                icon: Wallet,          group: 'operacion' },
  { path: '/inventario',          label: 'Inventario',          icon: Package,         group: 'operacion' },

  // Gestión
  { path: '/clientes',            label: 'Clientes',            icon: Users,           group: 'gestion' },
  { path: '/compras',             label: 'Compras',             icon: Truck,           group: 'gestion' },
  { path: '/proveedores',         label: 'Proveedores',         icon: Building2,       group: 'gestion' },
  { path: '/gastos',              label: 'Gastos',              icon: Receipt,         group: 'gestion' },

  // Reportes
  { path: '/historial',           label: 'Historial',           icon: History,         group: 'reportes' },
  { path: '/resultados',          label: 'Resultados',          icon: TrendingUp,      group: 'reportes' },
  { path: '/kardex',              label: 'Kárdex',              icon: BookOpen,        group: 'reportes' },

  // Fiscal
  { path: '/facturacion',         label: 'Facturación',         icon: FileText,        group: 'fiscal' },
  { path: '/facturas-recibidas',  label: 'Facturas recibidas',  icon: FileCheck,       group: 'fiscal' },
  { path: '/libro-iva',           label: 'Libro IVA',           icon: Calculator,      group: 'fiscal' },
  { path: '/compras-fiscal',      label: 'Compras Fiscal',      icon: FileCog,         group: 'fiscal' },
]

export const GROUPS = [
  { id: 'operacion', label: 'Operación', collapsedByDefault: false },
  { id: 'gestion',   label: 'Gestión',   collapsedByDefault: false },
  { id: 'reportes',  label: 'Reportes',  collapsedByDefault: false },
  { id: 'fiscal',    label: 'Fiscal',    collapsedByDefault: true  },
]

export function routesByGroup(groupId) {
  return ROUTES.filter(r => r.group === groupId)
}

export function findRoute(path) {
  return ROUTES.find(r => r.path === path)
}
