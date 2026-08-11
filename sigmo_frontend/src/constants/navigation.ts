import type { Component } from 'vue'
import {
  LayoutDashboard,
  Route,
  SlidersHorizontal,
  Archive,
  Building2,
  Package,
  Truck,
  CreditCard,
  DollarSign,
  MapPin,
  Navigation,
  Map,
  Wallet,
  FileText,
  Receipt,
  BarChart2,
  CalendarRange,
  TrendingUp,
  Users,
  ScrollText,
} from 'lucide-vue-next'

export interface NavLeaf {
  type: 'leaf'
  label: string
  path: string
  icon: Component
  roles: string[]
  // FASE 6.3: apaga la entrada de menú y bloquea la ruta directa sin
  // borrar la configuración — para secciones montadas pero sin
  // funcionalidad real todavía (ej. apps/reports, hoy vacía). Ausente u
  // `true` = visible/accesible normalmente (comportamiento previo).
  enabled?: boolean
}

export interface NavGroup {
  type: 'group'
  label: string
  icon: Component
  children: NavLeaf[]
}

export type NavItem = NavLeaf | NavGroup

export const navigation: NavItem[] = [
  {
    type: 'leaf',
    label: 'Dashboard',
    path: '/',
    icon: LayoutDashboard,
    roles: ['superuser', 'commercial_admin', 'cashier', 'accountant', 'auditor'],
  },
  {
    type: 'group',
    label: 'Operación',
    icon: Route,
    children: [
      {
        type: 'leaf',
        label: 'Registro de Viajes',
        path: '/trips',
        icon: Truck,
        roles: ['superuser', 'cashier', 'commercial_admin'],
      },
      {
        type: 'leaf',
        label: 'Ajustes del Día',
        path: '/trips/adjustments',
        icon: SlidersHorizontal,
        roles: ['superuser', 'cashier', 'commercial_admin'],
      },
      {
        type: 'leaf',
        label: 'Cierre de Caja',
        path: '/cash-closing',
        icon: Archive,
        roles: ['superuser', 'cashier', 'commercial_admin'],
      },
    ],
  },
  {
    type: 'leaf',
    label: 'Clientes',
    path: '/masters/clients',
    icon: Building2,
    roles: ['superuser', 'commercial_admin', 'accountant', 'auditor'],
  },
  {
    type: 'group',
    label: 'Maestros',
    icon: Package,
    children: [
      {
        type: 'leaf',
        label: 'Materiales',
        path: '/masters/materials',
        icon: Package,
        roles: ['superuser', 'commercial_admin', 'auditor'],
      },
      {
        type: 'leaf',
        label: 'Vehículos',
        path: '/masters/vehicles',
        icon: Truck,
        roles: ['superuser', 'commercial_admin', 'auditor'],
      },
      {
        type: 'leaf',
        label: 'Medios de Pago',
        path: '/masters/payment-methods',
        icon: CreditCard,
        roles: ['superuser', 'commercial_admin', 'auditor'],
      },
      {
        type: 'leaf',
        label: 'Tarifas',
        path: '/masters/tariffs',
        icon: DollarSign,
        roles: ['superuser', 'commercial_admin', 'auditor'],
      },
      {
        type: 'leaf',
        label: 'Pines Ambientales',
        path: '/masters/pins',
        icon: MapPin,
        roles: ['superuser', 'commercial_admin', 'auditor'],
      },
      {
        type: 'leaf',
        label: 'Orígenes',
        path: '/masters/origins',
        icon: Navigation,
        roles: ['superuser', 'commercial_admin', 'cashier', 'auditor'],
      },
      {
        type: 'leaf',
        label: 'Ciudades',
        path: '/masters/cities',
        icon: Map,
        roles: ['superuser', 'commercial_admin', 'auditor'],
      },
    ],
  },
  {
    type: 'group',
    label: 'Finanzas',
    icon: Wallet,
    children: [
      {
        type: 'leaf',
        label: 'Anticipos',
        path: '/advances',
        icon: Wallet,
        // cashier/auditor: acceso de solo consulta (no pueden crear/editar,
        // ver AdvancesPage.vue canManage/isSuperuser) — backend ya lo permite:
        // AdvanceListCreateView.get/AdvanceBalanceView.get no restringen por rol.
        roles: ['superuser', 'accountant', 'commercial_admin', 'cashier', 'auditor'],
      },
      {
        type: 'leaf',
        label: 'Facturación',
        path: '/invoicing',
        icon: FileText,
        roles: ['superuser', 'accountant'],
      },
      {
        type: 'leaf',
        label: 'Gastos',
        path: '/expenses',
        icon: Receipt,
        // accountant/auditor tienen acceso real de solo lectura (backend:
        // ExpenseListCreateView.get no restringe por rol) — antes no
        // aparecían aquí y solo podían llegar por URL directa.
        roles: ['superuser', 'cashier', 'commercial_admin', 'accountant', 'auditor'],
      },
    ],
  },
  {
    type: 'group',
    label: 'Reportes',
    icon: BarChart2,
    children: [
      {
        type: 'leaf',
        label: 'Consulta de Viajes',
        path: '/reports/general',
        icon: TrendingUp,
        roles: ['superuser', 'commercial_admin', 'accountant', 'auditor', 'cashier'],
      },
      {
        type: 'leaf',
        label: 'Reporte Diario',
        path: '/reports/daily',
        icon: CalendarRange,
        roles: ['superuser', 'commercial_admin', 'accountant', 'auditor', 'cashier'],
      },
      {
        type: 'leaf',
        label: 'Reporte por Rango',
        path: '/reports/range',
        icon: BarChart2,
        roles: ['superuser', 'commercial_admin', 'accountant', 'auditor'],
        // FASE 6.3: placeholder sin funcionalidad real (UnderConstruction en
        // el router) — se retoma cuando apps/reports (hoy vacía) se
        // complete. Reactivar quitando esta línea o poniéndola en `true`.
        enabled: false,
      },
    ],
  },
  {
    type: 'group',
    label: 'Administración',
    icon: Users,
    children: [
      {
        type: 'leaf',
        label: 'Usuarios',
        path: '/admin/users',
        icon: Users,
        roles: ['superuser'],
      },
      {
        type: 'leaf',
        label: 'Log de Auditoría',
        path: '/admin/audit-log',
        icon: ScrollText,
        roles: ['superuser', 'auditor'],
      },
    ],
  },
]

// FASE 5.4: única fuente de roles por ruta — la usan tanto el menú
// (useNavigation.isLeafVisible) como las guardas de Vue Router
// (router/index.ts), para no mantener dos listas de roles que puedan
// desincronizarse entre sí (como pasaba antes con Gastos).
export function getAllowedRoles(path: string): string[] | undefined {
  for (const item of navigation) {
    if (item.type === 'leaf' && item.path === path) return item.enabled === false ? [] : item.roles
    if (item.type === 'group') {
      const child = item.children.find(c => c.path === path)
      if (child) return child.enabled === false ? [] : child.roles
    }
  }
  return undefined
}
