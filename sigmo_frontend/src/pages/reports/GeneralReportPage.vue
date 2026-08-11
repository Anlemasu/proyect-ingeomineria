<script setup lang="ts">
import { ref, reactive, computed, h } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  useVueTable, getCoreRowModel, getSortedRowModel, getFilteredRowModel, getPaginationRowModel,
  FlexRender,
  type ColumnDef, type SortingState, type ColumnFiltersState, type VisibilityState,
} from '@tanstack/vue-table'
import {
  Search, FilterX, SlidersHorizontal, FileSpreadsheet, Printer, Copy,
  ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight,
} from 'lucide-vue-next'

import PageHeader from '@/components/shared/PageHeader.vue'
import SearchableSelect from '@/components/shared/SearchableSelect.vue'

import { tripsApi } from '@/api/trips.api'
import { clientsApi } from '@/api/clients.api'
import { materialsApi } from '@/api/materials.api'
import { vehicleTypesApi } from '@/api/vehicles.api'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import { invoicesApi } from '@/api/invoices.api'
import { useAuthStore } from '@/stores/auth.store'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, formatTime } from '@/utils/formatDate'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { printGeneralQuery } from '@/utils/printReport'
import { exportGeneralQueryExcel } from '@/utils/exportGeneralQueryExcel'
import { copyTableToClipboard } from '@/utils/copyTableToClipboard'
import type { Trip, UserRole } from '@/types'

// ── Configuración de columnas (rutas verificadas contra TripReadSerializer, Parte 8) ──
type ColumnKey =
  | 'voucher_num' | 'date' | 'date_register' | 'client_detail.name' | 'origin_site_detail.name'
  | 'vehicle_detail.plaque' | 'vehicle_detail.dumper_detail.ambiental_pin' | 'material_type_detail.name'
  | 'vehicle_detail.vehicle_type_detail.name' | 'vehicle_detail.vehicle_type_detail.capacity'
  | 'payment_detail.name' | 'value' | 'extern_voucher_num'
  | 'state' | 'invoice_number' | 'certification_state' | 'certification_num' | 'advance' | 'summary'

interface ColumnConfigItem {
  key: ColumnKey
  label: string
  roles: 'all' | UserRole[]
}

const RESTRICTED_ROLES: UserRole[] = ['superuser', 'commercial_admin', 'accountant', 'auditor']

// 'observations' y 'user_registered' del prompt original se omiten: no existen en el
// backend (Trip no tiene campo de observaciones persistido ni FK a User) — ver análisis Parte 8.
const COLUMN_CONFIG: ColumnConfigItem[] = [
  { key: 'voucher_num', label: 'N° Vale', roles: 'all' },
  { key: 'date', label: 'Fecha del viaje', roles: 'all' },
  { key: 'date_register', label: 'Hora', roles: 'all' },
  { key: 'client_detail.name', label: 'Cliente', roles: 'all' },
  { key: 'origin_site_detail.name', label: 'Origen del material', roles: 'all' },
  { key: 'vehicle_detail.plaque', label: 'Placa', roles: 'all' },
  { key: 'vehicle_detail.dumper_detail.ambiental_pin', label: 'PIN Ambiental', roles: 'all' },
  { key: 'material_type_detail.name', label: 'Tipo de material', roles: 'all' },
  { key: 'vehicle_detail.vehicle_type_detail.name', label: 'Tipo de vehículo', roles: 'all' },
  { key: 'vehicle_detail.vehicle_type_detail.capacity', label: 'Capacidad (m³)', roles: 'all' },
  { key: 'payment_detail.name', label: 'Medio de pago', roles: 'all' },
  { key: 'value', label: 'Valor', roles: 'all' },
  { key: 'extern_voucher_num', label: 'N° Vale externo', roles: 'all' },
  { key: 'state', label: 'Estado', roles: RESTRICTED_ROLES },
  { key: 'invoice_number', label: 'N° Factura', roles: RESTRICTED_ROLES },
  { key: 'certification_state', label: 'Estado certificación', roles: RESTRICTED_ROLES },
  { key: 'certification_num', label: 'N° Certificado', roles: RESTRICTED_ROLES },
  { key: 'advance', label: 'Anticipo asociado (ID)', roles: RESTRICTED_ROLES },
  { key: 'summary', label: 'Cierre de caja (ID)', roles: RESTRICTED_ROLES },
]

const STORAGE_KEY = 'sigmo_columns_general'

// Ancho mínimo por columna — evita que el texto se sobreponga cuando hay
// muchas columnas visibles a la vez (ver ajuste de tablas, punto 1).
const COLUMN_MIN_WIDTH: Partial<Record<ColumnKey, number>> = {
  voucher_num: 90,
  date: 110,
  date_register: 90,
  'client_detail.name': 200,
  'origin_site_detail.name': 180,
  'vehicle_detail.plaque': 100,
  'vehicle_detail.dumper_detail.ambiental_pin': 130,
  'material_type_detail.name': 160,
  'vehicle_detail.vehicle_type_detail.name': 150,
  'vehicle_detail.vehicle_type_detail.capacity': 120,
  'payment_detail.name': 140,
  value: 130,
  extern_voucher_num: 130,
  state: 100,
  invoice_number: 110,
  certification_state: 140,
  certification_num: 130,
  advance: 140,
  summary: 140,
}
function columnMinWidth(columnId: string): number {
  return COLUMN_MIN_WIDTH[columnId as ColumnKey] ?? 120
}

// ── Rol actual y columnas permitidas ───────────────────────────────────────────
const authStore = useAuthStore()
const currentRole = computed<UserRole | undefined>(() => authStore.user?.role)

const allowedKeys = computed(() => new Set(
  COLUMN_CONFIG
    .filter(c => c.roles === 'all' || (currentRole.value != null && (c.roles as UserRole[]).includes(currentRole.value)))
    .map(c => c.key),
))

const canSeeStateColumn = computed(() => allowedKeys.value.has('state'))

function sanitizeVisibility(v: VisibilityState): VisibilityState {
  const result: VisibilityState = { ...v }
  for (const col of COLUMN_CONFIG) {
    if (!allowedKeys.value.has(col.key)) result[col.key] = false
  }
  return result
}

function loadInitialVisibility(): VisibilityState {
  let stored: Record<string, boolean> = {}
  try {
    stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')
  } catch {
    stored = {}
  }
  const v: VisibilityState = {}
  for (const col of COLUMN_CONFIG) {
    v[col.key] = stored[col.key] !== false
  }
  return sanitizeVisibility(v)
}

function persistVisibility(v: VisibilityState) {
  const toStore: Record<string, boolean> = {}
  for (const col of COLUMN_CONFIG) {
    if (allowedKeys.value.has(col.key)) toStore[col.key] = v[col.key] !== false
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore))
}

const columnVisibility = ref<VisibilityState>(loadInitialVisibility())

function isColVisible(key: ColumnKey): boolean {
  return columnVisibility.value[key] !== false
}

function toggleColumn(key: ColumnKey) {
  columnVisibility.value = sanitizeVisibility({ ...columnVisibility.value, [key]: !isColVisible(key) })
  persistVisibility(columnVisibility.value)
}

const showColumnsMenu = ref(false)

// ── Datos de referencia para filtros y para resolver N° Factura ───────────────
const { data: clientsData } = useQuery({
  queryKey: ['clients'],
  queryFn: () => clientsApi.list({ state: 'true' }).then(r => r.data),
})
const { data: materialsData } = useQuery({
  queryKey: ['materials'],
  queryFn: () => materialsApi.list().then(r => r.data),
})
const { data: vehicleTypesData } = useQuery({
  queryKey: ['vehicle-types'],
  queryFn: () => vehicleTypesApi.list().then(r => r.data),
})
const { data: paymentsData } = useQuery({
  queryKey: ['payments'],
  queryFn: () => paymentMethodsApi.list().then(r => r.data),
})
const { data: invoicesData } = useQuery({
  queryKey: ['invoices'],
  queryFn: () => invoicesApi.list().then(r => r.data),
  enabled: computed(() => allowedKeys.value.has('invoice_number')),
})

const clientOptions = computed(() => (clientsData.value ?? []).filter(c => c.state).map(c => ({ id: c.id, name: c.name })))
const materialOptions = computed(() => (materialsData.value ?? []).filter(m => m.state))
const vehicleTypeOptions = computed(() => (vehicleTypesData.value ?? []).filter(v => v.state))
const paymentOptions = computed(() => (paymentsData.value ?? []).filter(p => p.state))

const invoiceNumberMap = computed<Record<number, string>>(() =>
  Object.fromEntries((invoicesData.value ?? []).map(i => [i.id, i.number])),
)

// ── Filtros ─────────────────────────────────────────────────────────────────────
interface FilterState {
  dateFrom: string
  dateTo: string
  client: number | null
  plaque: string
  materialType: number | null
  vehicleType: number | null
  payment: number | null
  invoiceStatus: '' | 'facturado' | 'sin_facturar'
  state: '' | 'true' | 'false'
  voucherNum: string
}

function emptyFilters(): FilterState {
  return {
    dateFrom: '', dateTo: '', client: null, plaque: '',
    materialType: null, vehicleType: null, payment: null,
    invoiceStatus: '', state: '', voucherNum: '',
  }
}

const filters = reactive<FilterState>(emptyFilters())

const activeFilterCount = computed(() => {
  let n = 0
  if (filters.dateFrom) n++
  if (filters.dateTo) n++
  if (filters.client) n++
  if (filters.plaque) n++
  if (filters.materialType) n++
  if (filters.vehicleType) n++
  if (filters.payment) n++
  if (filters.invoiceStatus) n++
  if (canSeeStateColumn.value && filters.state) n++
  if (filters.voucherNum) n++
  return n
})

// ── Consulta (server-side: date_from, date_to, client, state — resto client-side) ──
const appliedFilters = ref<FilterState | null>(null)
const hasQueried = computed(() => appliedFilters.value !== null)

function buildServerParams(f: FilterState) {
  const p: { date_from?: string; date_to?: string; client?: number; state?: boolean } = {}
  if (f.dateFrom) p.date_from = f.dateFrom
  if (f.dateTo) p.date_to = f.dateTo
  if (f.client) p.client = f.client
  if (f.state) p.state = f.state === 'true'
  return p
}

const { data: rawTripsData, isLoading, isError, error } = useQuery({
  queryKey: computed(() => ['general-query', appliedFilters.value]),
  queryFn: () => tripsApi.list(buildServerParams(appliedFilters.value!)).then(r => r.data),
  enabled: computed(() => appliedFilters.value !== null),
})

function runQuery() {
  appliedFilters.value = { ...filters }
}

function clearFilters() {
  Object.assign(filters, emptyFilters())
  appliedFilters.value = null
}

function applyClientFilters(trips: Trip[], f: FilterState): Trip[] {
  return trips.filter(t => {
    if (f.plaque && !(t.vehicle_detail?.plaque ?? '').toLowerCase().includes(f.plaque.trim().toLowerCase())) return false
    if (f.materialType && t.material_type_detail?.id !== f.materialType) return false
    if (f.vehicleType && t.vehicle_detail?.vehicle_type_detail?.id !== f.vehicleType) return false
    if (f.payment && t.payment_detail?.id !== f.payment) return false
    if (f.invoiceStatus === 'facturado' && t.invoice == null) return false
    if (f.invoiceStatus === 'sin_facturar' && t.invoice != null) return false
    if (f.voucherNum && String(t.voucher_num) !== f.voucherNum.trim()) return false
    return true
  })
}

const rawTrips = computed(() => rawTripsData.value ?? [])
const clientFilteredTrips = computed(() =>
  appliedFilters.value ? applyClientFilters(rawTrips.value, appliedFilters.value) : [],
)

// ── Tabla (useVueTable directo — DataTable.vue no soporta columnVisibility/columnFilters/footer) ──
const sorting = ref<SortingState>([])
const columnFilters = ref<ColumnFiltersState>([])
const pageSize = ref(25)
const pageIndex = ref(0)

const columns = computed<ColumnDef<Trip>[]>(() => [
  {
    id: 'voucher_num', accessorKey: 'voucher_num', header: 'N° Vale',
    cell: ({ row }) => h('span', { class: 'font-mono font-bold text-gold-800' }, `#${row.original.voucher_num}`),
  },
  { id: 'date', accessorKey: 'date', header: 'Fecha del viaje', cell: ({ row }) => formatDate(row.original.date) },
  { id: 'date_register', accessorKey: 'date_register', header: 'Hora', cell: ({ row }) => formatTime(row.original.date_register) },
  { id: 'client_detail.name', accessorKey: 'client_detail.name', header: 'Cliente' },
  { id: 'origin_site_detail.name', accessorKey: 'origin_site_detail.name', header: 'Origen del material' },
  { id: 'vehicle_detail.plaque', accessorKey: 'vehicle_detail.plaque', header: 'Placa' },
  {
    id: 'vehicle_detail.dumper_detail.ambiental_pin',
    accessorFn: row => row.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0',
    header: 'PIN Ambiental',
  },
  { id: 'material_type_detail.name', accessorKey: 'material_type_detail.name', header: 'Tipo de material' },
  { id: 'vehicle_detail.vehicle_type_detail.name', accessorKey: 'vehicle_detail.vehicle_type_detail.name', header: 'Tipo de vehículo' },
  {
    id: 'vehicle_detail.vehicle_type_detail.capacity',
    accessorFn: row => Number(row.vehicle_detail?.vehicle_type_detail?.capacity ?? 0),
    header: 'Capacidad (m³)',
    cell: ({ getValue }) => (getValue() as number).toLocaleString('es-CO'),
  },
  { id: 'payment_detail.name', accessorKey: 'payment_detail.name', header: 'Medio de pago' },
  {
    id: 'value', accessorFn: row => Number(row.value), header: 'Valor',
    cell: ({ row }) => h('span', { class: 'font-semibold text-gray-900' }, formatCurrency(row.original.value)),
  },
  { id: 'extern_voucher_num', accessorFn: row => row.extern_voucher_num ?? '—', header: 'N° Vale externo' },
  {
    id: 'state', accessorFn: row => (row.state ? 'Activo' : 'Anulado'), header: 'Estado',
    cell: ({ row }) => h('span', {
      class: [
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        row.original.state ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800',
      ],
    }, row.original.state ? 'Activo' : 'Anulado'),
  },
  {
    id: 'invoice_number',
    accessorFn: row => (row.invoice != null ? (invoiceNumberMap.value[row.invoice] ?? `#${row.invoice}`) : null),
    header: 'N° Factura',
    cell: ({ getValue }) => (getValue() as string | null) ?? '—',
  },
  {
    id: 'certification_state',
    accessorFn: row => (row.certification_state === true ? 'Sí' : row.certification_state === false ? 'No' : null),
    header: 'Estado certificación',
    cell: ({ getValue }) => (getValue() as string | null) ?? '—',
  },
  { id: 'certification_num', accessorFn: row => row.certification_num ?? null, header: 'N° Certificado', cell: ({ getValue }) => (getValue() as string | null) ?? '—' },
  { id: 'advance', accessorFn: row => row.advance, header: 'Anticipo asociado (ID)', cell: ({ getValue }) => (getValue() != null ? `#${getValue()}` : '—') },
  { id: 'summary', accessorFn: row => row.summary, header: 'Cierre de caja (ID)', cell: ({ getValue }) => (getValue() != null ? `#${getValue()}` : '—') },
])

const table = useVueTable({
  get data() { return clientFilteredTrips.value },
  get columns() { return columns.value },
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  state: {
    get sorting() { return sorting.value },
    get columnFilters() { return columnFilters.value },
    get columnVisibility() { return columnVisibility.value },
    get pagination() { return { pageIndex: pageIndex.value, pageSize: pageSize.value } },
  },
  onSortingChange: (updater) => {
    sorting.value = typeof updater === 'function' ? updater(sorting.value) : updater
  },
  onColumnFiltersChange: (updater) => {
    columnFilters.value = typeof updater === 'function' ? updater(columnFilters.value) : updater
    pageIndex.value = 0
  },
  onColumnVisibilityChange: (updater) => {
    const next = typeof updater === 'function' ? updater(columnVisibility.value) : updater
    columnVisibility.value = sanitizeVisibility(next)
    persistVisibility(columnVisibility.value)
  },
  onPaginationChange: (updater) => {
    const next = typeof updater === 'function' ? updater({ pageIndex: pageIndex.value, pageSize: pageSize.value }) : updater
    pageIndex.value = next.pageIndex
    pageSize.value = next.pageSize
  },
})

// Reiniciar a la primera página cuando cambian los datos o el tamaño de página
function resetPage() { pageIndex.value = 0 }

const sortedRows = computed(() => table.getSortedRowModel().rows.map(r => r.original))
const totalFilteredCount = computed(() => sortedRows.value.length)
const isValueColumnVisible = computed(() => isColVisible('value'))
const footerTotalValue = computed(() => sortedRows.value.reduce((s, t) => s + Number(t.value), 0))

const pageStart = computed(() => (totalFilteredCount.value === 0 ? 0 : pageIndex.value * pageSize.value + 1))
const pageEnd = computed(() => Math.min((pageIndex.value + 1) * pageSize.value, totalFilteredCount.value))

// ── Columnas visibles (misma fuente para tabla y export) ───────────────────────
const visibleColumnConfigs = computed(() => COLUMN_CONFIG.filter(c => allowedKeys.value.has(c.key) && isColVisible(c.key)))

// ── Resumen de filtros activos (para PDF) ──────────────────────────────────────
const filterSummaryText = computed(() => {
  if (!appliedFilters.value) return ''
  const f = appliedFilters.value
  const parts: string[] = []
  if (f.dateFrom) parts.push(`Fecha desde ${formatDate(f.dateFrom)}`)
  if (f.dateTo) parts.push(`Fecha hasta ${formatDate(f.dateTo)}`)
  if (f.client) parts.push(`Cliente: ${clientOptions.value.find(c => c.id === f.client)?.name ?? f.client}`)
  if (f.plaque) parts.push(`Placa: ${f.plaque}`)
  if (f.materialType) parts.push(`Material: ${materialOptions.value.find(m => m.id === f.materialType)?.name ?? f.materialType}`)
  if (f.vehicleType) parts.push(`Tipo vehículo: ${vehicleTypeOptions.value.find(v => v.id === f.vehicleType)?.name ?? f.vehicleType}`)
  if (f.payment) parts.push(`Medio de pago: ${paymentOptions.value.find(p => p.id === f.payment)?.name ?? f.payment}`)
  if (f.invoiceStatus) parts.push(`Facturación: ${f.invoiceStatus === 'facturado' ? 'Facturado' : 'Sin facturar'}`)
  if (canSeeStateColumn.value && f.state) parts.push(`Estado: ${f.state === 'true' ? 'Activo' : 'Anulado'}`)
  if (f.voucherNum) parts.push(`N° Vale: ${f.voucherNum}`)
  return parts.join(', ')
})

// ── Exportación ────────────────────────────────────────────────────────────────
function handleExportExcel() {
  try {
    exportGeneralQueryExcel(sortedRows.value, visibleColumnConfigs.value, invoiceNumberMap.value)
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
}

function handleExportPdf() {
  printGeneralQuery(sortedRows.value, visibleColumnConfigs.value, filterSummaryText.value, invoiceNumberMap.value)
}

const tableEl = ref<HTMLTableElement | null>(null)
async function handleCopy() {
  if (!tableEl.value) return
  try {
    await copyTableToClipboard(tableEl.value)
    toast.success('Tabla copiada al portapapeles')
  } catch {
    toast.error('No se pudo copiar la tabla')
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader title="Consulta de Viajes" description="Consulta libre de viajes registrados, con filtros y columnas configurables" />

    <!-- ── Barra de filtros ───────────────────────────────────────────────── -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Fecha desde</label>
          <input v-model="filters.dateFrom" type="date" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Fecha hasta</label>
          <input v-model="filters.dateTo" type="date" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Cliente</label>
          <SearchableSelect :options="clientOptions" v-model="filters.client" placeholder="Todos" :clearable="true" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Placa</label>
          <input v-model="filters.plaque" type="text" placeholder="Búsqueda parcial" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Tipo de material</label>
          <SearchableSelect :options="materialOptions" v-model="filters.materialType" placeholder="Todos" :clearable="true" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Tipo de vehículo</label>
          <SearchableSelect :options="vehicleTypeOptions" v-model="filters.vehicleType" placeholder="Todos" :clearable="true" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Medio de pago</label>
          <SearchableSelect :options="paymentOptions" v-model="filters.payment" placeholder="Todos" :clearable="true" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Estado de facturación</label>
          <select v-model="filters.invoiceStatus" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 bg-white">
            <option value="">Todos</option>
            <option value="facturado">Facturado</option>
            <option value="sin_facturar">Sin facturar</option>
          </select>
        </div>
        <div v-if="canSeeStateColumn">
          <label class="block text-xs font-medium text-gray-700 mb-1.5">Estado del viaje</label>
          <select v-model="filters.state" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 bg-white">
            <option value="">Todos</option>
            <option value="true">Activo</option>
            <option value="false">Anulado</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1.5">N° Vale</label>
          <input v-model="filters.voucherNum" type="number" placeholder="Exacto" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" />
        </div>
      </div>

      <div class="mt-5 flex flex-wrap items-center gap-3">
        <button
          type="button"
          @click="runQuery"
          :disabled="isLoading"
          class="flex items-center gap-2 px-5 py-2.5 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 disabled:opacity-50 transition-colors shadow-sm"
        >
          <Search class="w-4 h-4" />
          Consultar{{ activeFilterCount > 0 ? ` (${activeFilterCount} filtro${activeFilterCount > 1 ? 's' : ''} activo${activeFilterCount > 1 ? 's' : ''})` : '' }}
        </button>
        <button
          type="button"
          @click="clearFilters"
          class="flex items-center gap-2 px-4 py-2.5 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <FilterX class="w-4 h-4" />
          Limpiar filtros
        </button>
      </div>
    </div>

    <!-- ── Toolbar (solo tras primera consulta) ──────────────────────────── -->
    <div v-if="hasQueried" class="flex items-center justify-between flex-wrap gap-3">
      <span class="px-3 py-1.5 rounded-full bg-gray-100 text-gray-700 text-sm font-medium">
        {{ totalFilteredCount }} resultado{{ totalFilteredCount !== 1 ? 's' : '' }} encontrado{{ totalFilteredCount !== 1 ? 's' : '' }}
      </span>
      <div class="flex items-center gap-2">
        <div class="relative">
          <button
            type="button"
            @click="showColumnsMenu = !showColumnsMenu"
            class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <SlidersHorizontal class="w-4 h-4" /> Columnas
          </button>
          <Transition
            enter-active-class="transition-all duration-100" enter-from-class="opacity-0 translate-y-1"
            enter-to-class="opacity-100 translate-y-0" leave-active-class="transition-all duration-75" leave-to-class="opacity-0"
          >
            <div v-if="showColumnsMenu" class="absolute right-0 z-40 mt-1 w-64 max-h-80 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg p-2">
              <label
                v-for="col in COLUMN_CONFIG.filter(c => allowedKeys.has(c.key))"
                :key="col.key"
                class="flex items-center gap-2 px-2 py-1.5 text-sm text-gray-700 hover:bg-gray-50 rounded cursor-pointer"
              >
                <input type="checkbox" :checked="isColVisible(col.key)" @change="toggleColumn(col.key)" class="rounded border-gray-300" />
                {{ col.label }}
              </label>
            </div>
          </Transition>
        </div>
        <button
          type="button"
          @click="handleExportExcel"
          :disabled="totalFilteredCount === 0"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <FileSpreadsheet class="w-4 h-4" /> Exportar Excel
        </button>
        <button
          type="button"
          @click="handleExportPdf"
          :disabled="totalFilteredCount === 0"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Printer class="w-4 h-4" /> Exportar PDF
        </button>
        <button
          type="button"
          @click="handleCopy"
          :disabled="totalFilteredCount === 0"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title="Copiar tabla al portapapeles"
        >
          <Copy class="w-4 h-4" /> Copiar
        </button>
      </div>
    </div>

    <!-- ── Error de backend ───────────────────────────────────────────────── -->
    <div v-if="isError" class="p-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md">
      {{ getApiErrorMessage(error) }}
    </div>

    <!-- ── Estado sin consulta aún ────────────────────────────────────────── -->
    <div v-if="!hasQueried" class="bg-white rounded-xl border border-gray-200 shadow-sm py-20 flex flex-col items-center justify-center text-center">
      <Search class="w-12 h-12 text-gray-300 mb-3" />
      <p class="text-sm font-medium text-gray-500">Aplica los filtros y presiona Consultar para ver los resultados.</p>
    </div>

    <!-- ── Tabla ──────────────────────────────────────────────────────────── -->
    <div v-else class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="overflow-auto max-h-[65vh]">
        <table ref="tableEl" class="w-full text-sm">
          <thead class="bg-gray-50 border-b border-gray-200">
            <tr class="sticky top-0 z-20 bg-gray-50">
              <th
                v-for="header in table.getHeaderGroups()[0].headers"
                :key="header.id"
                :style="{ minWidth: columnMinWidth(header.id) + 'px' }"
                class="px-3 py-2.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider whitespace-nowrap"
                :class="header.column.getCanSort() ? 'cursor-pointer select-none' : ''"
                @click="header.column.getToggleSortingHandler()?.($event)"
              >
                <div class="flex items-center gap-1">
                  <FlexRender :render="header.column.columnDef.header" :props="header.getContext()" />
                  <span v-if="header.column.getCanSort()">
                    <ChevronUp v-if="header.column.getIsSorted() === 'asc'" class="w-3 h-3" />
                    <ChevronDown v-else-if="header.column.getIsSorted() === 'desc'" class="w-3 h-3" />
                    <ChevronsUpDown v-else class="w-3 h-3 text-gray-400" />
                  </span>
                </div>
              </th>
            </tr>
            <tr class="sticky top-[37px] z-20 bg-white border-b border-gray-200" data-copy-skip>
              <th v-for="header in table.getHeaderGroups()[0].headers" :key="`f-${header.id}`" class="px-3 py-1.5">
                <input
                  type="text"
                  :value="(header.column.getFilterValue() as string) ?? ''"
                  @input="header.column.setFilterValue(($event.target as HTMLInputElement).value); resetPage()"
                  :placeholder="String(header.column.columnDef.header)"
                  class="w-full h-6 px-1.5 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-gold-400"
                />
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-if="isLoading">
              <tr v-for="i in 10" :key="i" class="border-b border-gray-100">
                <td v-for="j in table.getHeaderGroups()[0].headers.length" :key="j" class="px-3 py-2.5">
                  <div class="h-4 bg-gray-200 rounded animate-pulse" />
                </td>
              </tr>
            </template>
            <template v-else-if="table.getRowModel().rows.length === 0">
              <tr>
                <td :colspan="table.getHeaderGroups()[0].headers.length" class="px-4 py-12 text-center text-gray-400 text-sm">
                  No se encontraron viajes con los filtros aplicados.
                </td>
              </tr>
            </template>
            <template v-else>
              <tr
                v-for="row in table.getRowModel().rows"
                :key="row.id"
                class="border-b border-gray-100 hover:bg-gray-50 transition-colors"
                :class="!row.original.state ? 'opacity-50 line-through' : ''"
              >
                <td
                  v-for="cell in row.getVisibleCells()"
                  :key="cell.id"
                  :style="{ minWidth: columnMinWidth(cell.column.id) + 'px' }"
                  class="px-3 py-2 text-gray-700 whitespace-nowrap"
                >
                  <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot v-if="!isLoading && table.getRowModel().rows.length > 0">
            <tr class="bg-gray-50 border-t-2 border-gray-200">
              <td class="px-3 py-2.5 text-xs font-semibold text-gray-600" :colspan="isValueColumnVisible ? table.getHeaderGroups()[0].headers.length - 1 : table.getHeaderGroups()[0].headers.length">
                Total: {{ totalFilteredCount }} viaje{{ totalFilteredCount !== 1 ? 's' : '' }}
              </td>
              <td v-if="isValueColumnVisible" class="px-3 py-2.5 text-right text-sm font-bold text-gray-900">
                {{ formatCurrency(footerTotalValue) }}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <!-- ── Paginación ─────────────────────────────────────────────────────── -->
      <div v-if="totalFilteredCount > 0" class="flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-t border-gray-100 text-sm text-gray-600">
        <div class="flex items-center gap-3">
          <select v-model="pageSize" @change="resetPage" class="px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none">
            <option :value="25">25 por página</option>
            <option :value="50">50 por página</option>
            <option :value="100">100 por página</option>
          </select>
          <span>Mostrando {{ pageStart }}–{{ pageEnd }} de {{ totalFilteredCount }} resultados</span>
        </div>
        <div class="flex items-center gap-2">
          <button @click="table.previousPage()" :disabled="!table.getCanPreviousPage()" class="p-1 rounded hover:bg-gray-100 disabled:opacity-40">
            <ChevronLeft class="w-4 h-4" />
          </button>
          <button @click="table.nextPage()" :disabled="!table.getCanNextPage()" class="p-1 rounded hover:bg-gray-100 disabled:opacity-40">
            <ChevronRight class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
