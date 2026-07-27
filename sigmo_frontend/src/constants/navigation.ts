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
        roles: ['superuser', 'cashier'],
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
        roles: ['superuser', 'cashier'],
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
        roles: ['superuser', 'accountant', 'commercial_admin'],
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
        roles: ['superuser', 'cashier', 'commercial_admin'],
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
        roles: ['superuser', 'commercial_admin', 'accountant', 'auditor'],
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
