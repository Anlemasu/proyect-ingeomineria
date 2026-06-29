export const ROLES = {
  SUPERUSER: 'superuser',
  COMMERCIAL_ADMIN: 'commercial_admin',
  CASHIER: 'cashier',
  ACCOUNTANT: 'accountant',
  AUDITOR: 'auditor',
} as const

export type RoleKey = keyof typeof ROLES
export type RoleValue = typeof ROLES[RoleKey]

export const ROLE_LABELS: Record<string, string> = {
  superuser: 'Superusuario',
  commercial_admin: 'Administrador Comercial',
  cashier: 'Operador de Caja',
  accountant: 'Contador',
  auditor: 'Auditor',
}

export const ROLE_COLORS: Record<string, string> = {
  superuser: 'bg-purple-100 text-purple-800',
  commercial_admin: 'bg-blue-100 text-blue-800',
  cashier: 'bg-green-100 text-green-800',
  accountant: 'bg-amber-100 text-amber-800',
  auditor: 'bg-gray-100 text-gray-800',
}
