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
  movements: AdvanceMovement[]
}

export interface AdvanceBalance {
  client_id: number
  balance: number
}

export interface DailySummaryPayment {
  payment_method: number
  payment_method_name: string
  total: string
}

export interface DailySummary {
  id: number
  date: string
  total_trips: number
  total_volume: string
  avg_trip_value: string
  total_expenses: string
  payment_details: DailySummaryPayment[]
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
}

export interface DailyReportData {
  date: string
  trips: Trip[]
  expenses: Expense[]
  advancesConsumed: Trip[]
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
}
