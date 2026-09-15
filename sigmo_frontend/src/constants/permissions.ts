import { ROLES } from './roles'

export const PERMISSIONS = {
  clients: {
    // certifier: solo lectura (ver navigation.ts) — necesita consultar los
    // datos del cliente al que le certifica los viajes, no editarlos.
    view: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT, ROLES.CASHIER, ROLES.AUDITOR, ROLES.CERTIFIER],
    create: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT],
    edit: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT],
    delete: [],
  },
  masters: {
    view: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT, ROLES.CASHIER, ROLES.AUDITOR],
    create: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN],
    edit: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN],
    delete: [],
  },
  // Tarifas: Contador tiene acceso de solo lectura (view), sin crear/editar.
  tariffs: {
    view: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT, ROLES.AUDITOR],
    create: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN],
    edit: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN],
    delete: [],
  },
  // Ciudades: Contador tiene acceso completo (crear/editar), a diferencia de Tarifas.
  cities: {
    view: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT, ROLES.AUDITOR],
    create: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT],
    edit: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT],
    delete: [],
  },
  users: {
    view: [ROLES.SUPERUSER],
    create: [ROLES.SUPERUSER],
    edit: [ROLES.SUPERUSER],
    delete: [],
  },
  expenses: {
    view: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.CASHIER, ROLES.ACCOUNTANT, ROLES.AUDITOR],
    create: [ROLES.SUPERUSER, ROLES.CASHIER, ROLES.COMMERCIAL_ADMIN],
    edit: [ROLES.SUPERUSER, ROLES.CASHIER, ROLES.COMMERCIAL_ADMIN],
    delete: [],
  },
  // Pendientes: todos ven el listado; solo auditor/superuser registran,
  // editan o cancelan (ver can_manage_pending_entries en el backend).
  pendingEntries: {
    view: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.CASHIER, ROLES.ACCOUNTANT, ROLES.AUDITOR],
    create: [ROLES.SUPERUSER, ROLES.AUDITOR],
    edit: [ROLES.SUPERUSER, ROLES.AUDITOR],
    delete: [],
  },
} as const

export type PermissionModule = keyof typeof PERMISSIONS
export type PermissionAction = 'view' | 'create' | 'edit' | 'delete'
