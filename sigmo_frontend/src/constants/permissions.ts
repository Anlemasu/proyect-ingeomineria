import { ROLES } from './roles'

export const PERMISSIONS = {
  clients: {
    view: [ROLES.SUPERUSER, ROLES.COMMERCIAL_ADMIN, ROLES.ACCOUNTANT, ROLES.CASHIER, ROLES.AUDITOR],
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
} as const

export type PermissionModule = keyof typeof PERMISSIONS
export type PermissionAction = 'view' | 'create' | 'edit' | 'delete'
