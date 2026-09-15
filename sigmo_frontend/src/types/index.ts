export type UserRole = 'superuser' | 'commercial_admin' | 'cashier' | 'accountant' | 'auditor'

export interface User {
  id: number
  name: string
  email: string
  username: string
  role: UserRole
  role_display: string
  state: boolean
}

export interface Client {
  id: number
  nit: string
  name: string
  abrev_name: string
  address: string
  phone: string
  city: number | null
  city_detail: City | null
  facturation_name: string | null
  email: string | null
  validate_certification: boolean | null
  state: boolean
  created_by: User | null
}

export interface VehicleType {
  id: number
  name: string
  capacity: string
  description: string | null
  state: boolean
}

export interface PinsDumper {
  id: number
  ambiental_pin: string
  propietary: string
  address: string
  phone: string
  email: string
  plaque: string
  expedition_site: string
  model: string
  capacity: string
  driver: string
  date_register: string
  state: boolean
}

export interface Vehicle {
  id: number
  plaque: string
  vehicle_type: number
  vehicle_type_detail: VehicleType
  dumper: number | null
  dumper_detail: PinsDumper | null
}

export interface MaterialType {
  id: number
  name: string
  description: string | null
  state: boolean
}

export interface PaymentMethod {
  id: number
  name: string
  is_advance: boolean
  state: boolean
}

export interface OriginSite {
  id: number
  name: string
  state: boolean
}

export interface City {
  id: number
  name: string
  state: boolean
}

export interface Tariff {
  id: number
  client: number | null
  client_name: string | null
  vehicle_type: number
  vehicle_type_name: string
  material_type: number | null
  material_type_name: string | null
  value: string
  start_date: string
  end_date: string | null
  state: boolean
}

export interface LoginResponse {
  access: string
  refresh: string
  user: User
}

// 8A.3: respuesta de POST /users/token/refresh/ (TokenRefreshView estándar
// de simplejwt). No trae `user` — a diferencia de LoginResponse, un
// refresh nunca vuelve a autenticar contra credenciales, solo renueva
// tokens de una sesión que ya existía.
export interface RefreshResponse {
  access: string
  refresh: string
}

export interface ApiError {
  error?: string
  detail?: string
  [key: string]: unknown
}

export interface Invoice {
  id: number
  user: number
  number: string
}

export interface Trip {
  id: number
  voucher_num: number
  date: string
  date_register: string  // ISO 8601 datetime: "2026-06-29T14:35:22Z" (antes DateField, ahora DateTimeField)
  value: string
  extern_voucher_num: string | null
  invoice_pos: number | null
  certification_state: boolean | null
  certification_num: string | null
  state: boolean
  client_detail: Client
  payment_detail: PaymentMethod
  vehicle_detail: Vehicle
  material_type_detail: MaterialType
  origin_site_detail: OriginSite
  advance: number | null
  invoice: number | null
  summary: number | null
  observations: string | null
}

export interface AdvanceMovement {
  id: number
  advance: number
  trip: number | null
  type_movement: 'ingreso' | 'egreso'
  amount: string
  trips_quantity: number
  date: string
  description: string | null
}

export interface Advance {
  id: number
  client: number
  client_detail: Client
  user: number
  value: string
  transfer_num: number
  date: string
  proforma_number: number | null
  observations: string | null
  available_balance: number
  // N° de viajes asociado al ingreso inicial del anticipo — calculado por
  // el backend desde el AdvanceMovement de ingreso inicial (ver
  // AdvanceSerializer.get_trips_quantity). Editable vía advancesApi.update.
  trips_quantity: number
  // true si es el anticipo más reciente del cliente (ver get_active_advance
  // en el backend); cualquier otro está congelado permanentemente.
  is_active: boolean
  movements: AdvanceMovement[]
}

export type PendingEntryType = 'advance' | 'transfer'
export type PendingEntryStatus = 'pending' | 'executed' | 'cancelled'

export interface PendingEntry {
  id: number
  entry_type: PendingEntryType
  status: PendingEntryStatus
  client: number
  client_detail: Client
  value: string
  date: string
  payment_method: number | null
  payment_method_detail: PaymentMethod | null
  observations: string | null
  executed_advance: number | null
  executed_trip: number | null
  created_by: number
  executed_by: number | null
  executed_at: string | null
  cancelled_by: number | null
  cancelled_at: string | null
  cancellation_justification: string | null
  created_at: string
  updated_at: string
}

export interface AdvanceBalanceDetail {
  id: number
  date: string
  value: string
  transfer_num: number
  available_balance: string
  is_active: boolean
}

export interface AdvancePendingDebt {
  trip: number
  voucher_num: number
  date: string
  value: string
  justification: string | null
}

// Un viaje que la corrección de valor de un anticipo dejaría (o dejó) como
// deuda pendiente — mismo shape en la previsualización y en la respuesta
// real de POST /advances/<id>/correct-value/.
export interface AdvanceUnlinkedTrip {
  trip: number
  voucher_num: number
  date?: string
  value: string
}

export interface AdvanceCorrectValuePreview {
  balance_before: string
  prospective_balance: string
  trips_to_unlink: AdvanceUnlinkedTrip[]
}

export interface AdvanceCorrectValueResult {
  advance: Advance
  movement: AdvanceMovement
  unlinked_trips: AdvanceUnlinkedTrip[]
  settled_trips: { trip: number; amount: string }[]
}

// ── Reporte Físico ──────────────────────────────────────────────────────────
// Conciliación de vales físicos (papel) contra lo registrado en el sistema
// por anticipo. Ver apps.physical_reports en el backend.

export interface PhysicalReportSummary {
  advance: number
  client_detail: Client
  date: string
  expected_trips_quantity: number | null
  // Con el filtro de fecha (siempre lo manda el frontend), estos dos ya
  // vienen calculados "a esa fecha" — no necesariamente el acumulado real
  // de hoy. Sin filtro (no debería pasar en la UI actual), son el
  // acumulado real completo.
  cumulative_entered: number
  // null cuando el anticipo todavía no tiene cupo esperado definido.
  remaining: number | null
  // Presentes solo cuando la request llevó `?date=` (ver physicalReportsApi.list):
  // el conteo ya guardado exactamente para esa fecha (null si no hay), y si
  // el campo inline de la tabla todavía puede editarse sin justificación
  // (ventana de ajuste rápido de 30 min) — pasada la ventana, solo se
  // ajusta individualmente desde el detalle (el "ojito"), con justificación.
  day_count?: number | null
  day_editable?: boolean
  // true si este es el anticipo ACTIVO actual del cliente (el que
  // descuenta los viajes nuevos) — false si es uno congelado (reemplazado
  // por uno más nuevo) que sigue visible aquí por historial. Un cliente
  // puede tener ambos tipos de fila a la vez en la tabla.
  is_active: boolean
}

// Resultado de un renglón de POST /physical-reports/bulk-entries/ (botón
// "Guardar todos"). Cada anticipo se procesa independiente: uno puede
// fallar (p.ej. quedó fuera de la ventana de ajuste) sin afectar al resto.
export interface BulkEntryResult {
  advance: number
  status: 'ok' | 'error'
  entry?: PhysicalCountEntry
  error?: string
}

export interface PhysicalCountEntry {
  id: number
  advance: number
  date: string
  count: number
  user: number
  user_name: string
  created_at: string
  justification: string | null
}

export interface PhysicalCountClosure {
  id: number
  advance: number
  action: 'close' | 'undo_close' | 'reopen'
  user: number
  user_name: string
  created_at: string
  justification: string | null
}

export interface PhysicalReportDayDetail {
  date: string
  // null cuando todavía no se ha registrado ningún conteo físico ese día.
  physical_count: number | null
  system_count: number
  difference: number | null
  history: PhysicalCountEntry[]
  // Dentro de la ventana de ajuste rápido (o sin ningún conteo todavía):
  // corregir desde este mismo detalle no exige justificación.
  editable: boolean
  // Viajes del MISMO cliente y la MISMA fecha pero vinculados a OTRO
  // anticipo — señal de que se podría estar mirando/registrando el conteo
  // físico equivocado (ver bug reportado: un anticipo mostraba "0 viajes"
  // aunque el cliente sí tenía viajes ese día, solo que en su OTRO
  // anticipo). `other_advance_ids` trae el/los anticipo(s) donde sí están.
  other_advance_trips_count: number
  other_advance_ids: number[]
}

export interface PhysicalReportDetail extends PhysicalReportSummary {
  closed: boolean
  last_closure: PhysicalCountClosure | null
  day_detail?: PhysicalReportDayDetail
}

// Refleja la forma real de GET /advances/balance/<client_id>/
// (AdvanceBalanceView.get en el backend) — antes este tipo tenía un campo
// `balance` que el backend nunca devolvió, así que cualquier lectura de
// `clientBalanceData.value?.balance` siempre era `undefined`.
export interface AdvanceBalance {
  client_id: number
  advances: AdvanceBalanceDetail[]
  total_advances_balance: string
  pending_debts: AdvancePendingDebt[]
  total_pending_debt: string
  net_balance: string
}

export interface DailySummaryPayment {
  payment_method: number
  payment_method_name: string
  total: string
}

// Desglose "viajes por cliente". `total_value` / `total_volume` llegan como
// string cuando vienen del backend (DRF serializa Decimal como string) y como
// number cuando los calcula el frontend (groupTripsByClient) — de ahí la unión.
export interface TripsByClientRow {
  client: number
  client_name: string
  trips_count: number
  total_value: number | string
  total_volume: number | string
}

export interface DailySummary {
  id: number
  date: string
  state: 'closed' | 'reverted'
  total_trips: number
  total_volume: string
  avg_trip_value: string
  total_expenses: string
  payment_details: DailySummaryPayment[]
  // Calculado en vivo por el backend desde los viajes activos del cierre.
  client_details: TripsByClientRow[]
}

export interface TodaySummary {
  date: string
  already_closed: boolean
  total_trips: number
  total_volume: string
  avg_trip_value: string
  total_expenses: string
  payment_details: Array<{
    payment_method: number
    payment_method_name: string
    total: number
  }>
  trips_by_client: TripsByClientRow[]
}

export interface AuditLogEntry {
  id: number
  user: number | null
  user_name: string
  action: string
  action_display: string
  model_name: string
  object_id: number | null
  previous_data: Record<string, unknown> | null
  new_data: Record<string, unknown> | null
  ip_address: string | null
  justification: string | null
  timestamp: string
}

export interface Expense {
  id: number
  user: number
  value: string
  description: string
  date: string
  state: boolean
}

// 'daily' cubre un solo día (dateFrom === dateTo). 'biweekly'/'monthly' son
// períodos fijos calculados a partir de un mes elegido (ver
// utils/reportPeriodRanges.ts) — no fechas libres. 'custom' es el único con
// selector de fecha inicio/fin libre, para casos que no calzan en un
// período fijo.
export type ReportPeriodType = 'daily' | 'biweekly' | 'monthly' | 'custom'

// Subtotal de un día dentro del rango del reporte (solo tiene sentido
// mostrarlo cuando periodType !== 'daily', ver DailyReportPage).
export interface DailyReportBreakdownRow {
  date: string
  tripsCount: number
  totalCollected: number
  totalExpenses: number
  netBalance: number
}

export interface DailyReportData {
  periodType: ReportPeriodType
  dateFrom: string
  dateTo: string
  trips: Trip[]
  expenses: Expense[]
  advancesConsumed: Trip[]
  tripsByClient: TripsByClientRow[]
  dailyBreakdown: DailyReportBreakdownRow[]
  summary: {
    totalTrips: number
    totalCollected: number
    totalExpenses: number
    netBalance: number
    byPaymentMethod: { name: string; tripCount: number; total: number }[]
  }
}

export interface ImportResult {
  success: boolean
  created: number
  updated: number
  rejected_count: number
  rejected: Array<{ fila: number; placa?: string; motivo: string }>
  vehicles_synced: number
}
