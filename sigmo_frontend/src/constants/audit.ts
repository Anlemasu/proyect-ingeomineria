export const ACTION_CONFIG: Record<string, { label: string; cls: string }> = {
  create:        { label: 'Creación',         cls: 'bg-green-100 text-green-700' },
  update:        { label: 'Modificación',     cls: 'bg-blue-100 text-blue-700' },
  annul:         { label: 'Anulación',        cls: 'bg-red-100 text-red-700' },
  delete:        { label: 'Eliminación',      cls: 'bg-red-100 text-red-700' },
  access_denied: { label: 'Acceso denegado',  cls: 'bg-amber-100 text-amber-700' },
  login:         { label: 'Inicio de sesión', cls: 'bg-gray-100 text-gray-600' },
  logout:        { label: 'Cierre de sesión', cls: 'bg-gray-100 text-gray-600' },
}

// Derived from actual log_action() calls found across all backend apps
export const ALL_ACTIONS = [
  { value: 'create',        label: 'Creación' },
  { value: 'update',        label: 'Modificación' },
  { value: 'annul',         label: 'Anulación' },
  { value: 'access_denied', label: 'Acceso denegado' },
  { value: 'login',         label: 'Inicio de sesión' },
  { value: 'logout',        label: 'Cierre de sesión' },
  { value: 'delete',        label: 'Eliminación' },
]

// Derived from actual model_name strings passed to log_action()
export const ALL_MODELS = [
  { value: 'User',          label: 'Usuario' },
  { value: 'Trip',          label: 'Viaje' },
  { value: 'Client',        label: 'Cliente' },
  { value: 'Advance',       label: 'Anticipo' },
  { value: 'Expense',       label: 'Gasto' },
  { value: 'Invoice',       label: 'Factura' },
  { value: 'DailySummary',  label: 'Cierre de Caja' },
  { value: 'VehicleType',   label: 'Tipo de Vehículo' },
  { value: 'MaterialType',  label: 'Tipo de Material' },
  { value: 'PaymentMethod', label: 'Medio de Pago' },
  { value: 'OriginSite',    label: 'Origen' },
  { value: 'City',          label: 'Ciudad' },
  { value: 'Tariff',        label: 'Tarifa' },
  { value: 'PinsDumper',    label: 'PIN Ambiental' },
  { value: 'Vehicle',       label: 'Vehículo' },
]

export const MODEL_LABEL: Record<string, string> = Object.fromEntries(ALL_MODELS.map(m => [m.value, m.label]))
