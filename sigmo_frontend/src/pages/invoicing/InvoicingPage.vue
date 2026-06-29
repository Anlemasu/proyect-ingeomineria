<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { FileText, X, CheckSquare, Square, Search, ChevronDown, ChevronUp } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'

type ARow = Record<string, unknown>

import DataTable from '@/components/shared/DataTable.vue'
import { tripsApi } from '@/api/trips.api'
import { invoicesApi } from '@/api/invoices.api'
import { clientsApi } from '@/api/clients.api'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { useAuthStore } from '@/stores/auth.store'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate } from '@/utils/formatDate'
import type { Trip, Invoice, Client } from '@/types'

const qc = useQueryClient()
const authStore = useAuthStore()
const canManage = computed(() =>
  ['superuser', 'accountant'].includes(authStore.user?.role ?? '')
)

type Tab = 'pending' | 'invoiced'
const activeTab = ref<Tab>('pending')

// ── Queries ────────────────────────────────────────────────────────────────
const { data: tripsData, isLoading: tripsLoading } = useQuery({
  queryKey: ['trips'],
  queryFn: () => tripsApi.list().then(r => r.data),
})
const allTrips = computed(() => tripsData.value ?? [])

const { data: clientsData } = useQuery({
  queryKey: ['clients'],
  queryFn: () => clientsApi.list().then(r => r.data),
})
const clients = computed(() => clientsData.value ?? [])

const { data: invoicesData } = useQuery({
  queryKey: ['invoices'],
  queryFn: () => invoicesApi.list().then(r => r.data),
})
const invoices = computed(() => invoicesData.value ?? [])

const { data: paymentMethodsData } = useQuery({
  queryKey: ['payment-methods'],
  queryFn: () => paymentMethodsApi.list().then(r => r.data),
})
const paymentMethods = computed(() => paymentMethodsData.value ?? [])

// ── Filtros ────────────────────────────────────────────────────────────────
const filterClient = ref<number | ''>('')
const filterDateFrom = ref('')
const filterDateTo = ref('')
const filterInvoice = ref<number | ''>('')
const filterPayment = ref<number | ''>('')

// ── Pendientes (state=true, invoice=null) ──────────────────────────────────
const pendingTrips = computed<Trip[]>(() => {
  return allTrips.value.filter(t => {
    if (!t.state || t.invoice !== null) return false
    if (filterClient.value && t.client_detail?.id !== filterClient.value) return false
    if (filterPayment.value && t.payment_detail?.id !== filterPayment.value) return false
    if (filterDateFrom.value && t.date < filterDateFrom.value) return false
    if (filterDateTo.value && t.date > filterDateTo.value) return false
    return true
  })
})

// ── Facturados (invoice !== null) ──────────────────────────────────────────
const invoicedTrips = computed<Trip[]>(() => {
  return allTrips.value.filter(t => {
    if (t.invoice === null) return false
    if (filterClient.value && t.client_detail?.id !== filterClient.value) return false
    if (filterPayment.value && t.payment_detail?.id !== filterPayment.value) return false
    if (filterDateFrom.value && t.date < filterDateFrom.value) return false
    if (filterDateTo.value && t.date > filterDateTo.value) return false
    if (filterInvoice.value && t.invoice !== filterInvoice.value) return false
    return true
  })
})

// ── Selección multi-trip ──────────────────────────────────────────────────
const selectedIds = ref<Set<number>>(new Set())

function toggleTrip(id: number) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) { next.delete(id) } else { next.add(id) }
  selectedIds.value = next
}

function toggleAll() {
  if (selectedIds.value.size === pendingTrips.value.length && pendingTrips.value.length > 0) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(pendingTrips.value.map(t => t.id))
  }
}

const allSelected = computed(
  () => pendingTrips.value.length > 0 && selectedIds.value.size === pendingTrips.value.length
)
const someSelected = computed(() => selectedIds.value.size > 0 && !allSelected.value)

const selectedTrips = computed(() => pendingTrips.value.filter(t => selectedIds.value.has(t.id)))

const selectedTotal = computed(() =>
  selectedTrips.value.reduce((s, t) => s + parseFloat(t.value), 0)
)

// Limpiar selección al cambiar filtros
watch([filterClient, filterDateFrom, filterDateTo, filterPayment], () => {
  selectedIds.value = new Set()
})

// ── Modal: asignar factura ─────────────────────────────────────────────────
const showInvoiceModal = ref(false)
const invoiceMode = ref<'new' | 'existing'>('new')
const invoiceNumber = ref('')
const invoiceNumberError = ref('')
const existingInvoiceId = ref<number | ''>('')
const isAssigning = ref(false)

function openInvoiceModal() {
  invoiceMode.value = 'new'
  invoiceNumber.value = ''
  invoiceNumberError.value = ''
  existingInvoiceId.value = ''
  showInvoiceModal.value = true
}

function closeInvoiceModal() {
  showInvoiceModal.value = false
}

const assignMutation = useMutation({
  mutationFn: async () => {
    // Crear factura si es nueva
    let invoiceId: number
    if (invoiceMode.value === 'new') {
      const num = invoiceNumber.value.trim()
      if (!num) { invoiceNumberError.value = 'El número de factura es requerido.'; throw new Error('validation') }
      if (num.length > 15) { invoiceNumberError.value = 'Máximo 15 caracteres.'; throw new Error('validation') }
      invoiceNumberError.value = ''
      const res = await invoicesApi.create({ number: num })
      invoiceId = res.data.id
    } else {
      if (!existingInvoiceId.value) { throw new Error('Selecciona una factura existente.') }
      invoiceId = existingInvoiceId.value as number
    }

    // Asignar factura a cada viaje seleccionado (en paralelo con posición secuencial)
    const trips = selectedTrips.value
    await Promise.all(
      trips.map((t, idx) =>
        tripsApi.patch(t.id, { invoice: invoiceId, invoice_pos: idx + 1 })
      )
    )
    return { invoiceId, count: trips.length }
  },
  onSuccess: ({ count }) => {
    toast.success(`${count} viaje${count !== 1 ? 's' : ''} asignado${count !== 1 ? 's' : ''} a la factura correctamente.`)
    selectedIds.value = new Set()
    qc.invalidateQueries({ queryKey: ['trips'] })
    qc.invalidateQueries({ queryKey: ['invoices'] })
    closeInvoiceModal()
  },
  onError: (err: unknown) => {
    if (err instanceof Error && err.message === 'validation') return
    if (err instanceof Error && !err.message.includes('validation')) {
      toast.error(err.message)
    } else {
      toast.error(getApiErrorMessage(err))
    }
  },
})

// ── Ordenamiento tabla pendientes ─────────────────────────────────────────
type SortKey = 'date' | 'voucher_num' | 'client' | 'value'
const sortKey = ref<SortKey>('date')
const sortDir = ref<'asc' | 'desc'>('desc')

function setSort(key: SortKey) {
  if (sortKey.value === key) { sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc' }
  else { sortKey.value = key; sortDir.value = 'asc' }
}

const sortedPending = computed(() => {
  const arr = [...pendingTrips.value]
  arr.sort((a, b) => {
    let va: string | number = ''
    let vb: string | number = ''
    if (sortKey.value === 'date') { va = a.date; vb = b.date }
    else if (sortKey.value === 'voucher_num') { va = a.voucher_num; vb = b.voucher_num }
    else if (sortKey.value === 'client') { va = a.client_detail?.name ?? ''; vb = b.client_detail?.name ?? '' }
    else if (sortKey.value === 'value') { va = parseFloat(a.value); vb = parseFloat(b.value) }
    if (va < vb) return sortDir.value === 'asc' ? -1 : 1
    if (va > vb) return sortDir.value === 'asc' ? 1 : -1
    return 0
  })
  return arr
})

// ── Columnas Tab 2 (facturados) ────────────────────────────────────────────
const invoicedColumns: ColumnDef<ARow>[] = [
  {
    accessorKey: 'voucher_num',
    header: 'N° Voucher',
  },
  {
    accessorKey: 'date',
    header: 'Fecha',
    cell: info => formatDate(info.getValue() as string),
  },
  {
    accessorFn: row => (row.client_detail as { name?: string } | undefined)?.name ?? '—',
    id: 'client_name',
    header: 'Cliente',
  },
  {
    accessorKey: 'invoice',
    header: 'N° Factura',
    cell: info => {
      const invoiceId = info.getValue() as number | null
      if (!invoiceId) return '—'
      const inv = invoices.value.find(i => i.id === invoiceId)
      return inv ? h('span', { class: 'font-medium text-blue-600' }, inv.number) : `#${invoiceId}`
    },
  },
  {
    accessorKey: 'invoice_pos',
    header: 'Pos.',
    cell: info => info.getValue() ?? '—',
  },
  {
    accessorKey: 'value',
    header: 'Valor',
    cell: info => formatCurrency(parseFloat(info.getValue() as string)),
  },
  {
    accessorFn: row => {
      const v = row.vehicle_detail as { plaque?: string } | undefined
      return v?.plaque ?? '—'
    },
    id: 'vehicle_plaque',
    header: 'Vehículo',
  },
  {
    accessorFn: row => (row.payment_detail as { name?: string } | undefined)?.name ?? '—',
    id: 'payment_name',
    header: 'Medio de Pago',
  },
]

const invoicedRows = computed(() => invoicedTrips.value as unknown as ARow[])

// Reset filtros al cambiar tab
watch(activeTab, () => {
  filterClient.value = ''
  filterDateFrom.value = ''
  filterDateTo.value = ''
  filterInvoice.value = ''
  filterPayment.value = ''
  selectedIds.value = new Set()
})
</script>

<template>
  <div class="p-6 space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900">Facturación</h1>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200">
      <nav class="flex gap-1" aria-label="Tabs">
        <button
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
          :class="activeTab === 'pending'
            ? 'border-blue-600 text-blue-600'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'pending'"
        >
          Pendientes de Facturar
          <span
            v-if="pendingTrips.length"
            class="ml-2 inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700"
          >
            {{ pendingTrips.length }}
          </span>
        </button>
        <button
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
          :class="activeTab === 'invoiced'
            ? 'border-blue-600 text-blue-600'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'invoiced'"
        >
          Registros Facturados
        </button>
      </nav>
    </div>

    <!-- ── Filtros comunes ──────────────────────────────────────────────── -->
    <div class="flex flex-wrap gap-3">
      <div>
        <label class="block text-xs text-gray-500 mb-1">Cliente</label>
        <select
          v-model="filterClient"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Todos</option>
          <option v-for="c in clients" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>
      <div>
        <label class="block text-xs text-gray-500 mb-1">Fecha desde</label>
        <input
          v-model="filterDateFrom"
          type="date"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div>
        <label class="block text-xs text-gray-500 mb-1">Fecha hasta</label>
        <input
          v-model="filterDateTo"
          type="date"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <!-- Método de pago (ambas tabs) -->
      <div>
        <label class="block text-xs text-gray-500 mb-1">Medio de pago</label>
        <select
          v-model="filterPayment"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Todos</option>
          <option v-for="pm in paymentMethods" :key="pm.id" :value="pm.id">{{ pm.name }}</option>
        </select>
      </div>
      <!-- Filtro adicional Tab 2 -->
      <div v-if="activeTab === 'invoiced'">
        <label class="block text-xs text-gray-500 mb-1">Factura</label>
        <select
          v-model="filterInvoice"
          class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">Todas</option>
          <option v-for="inv in invoices" :key="inv.id" :value="inv.id">{{ inv.number }}</option>
        </select>
      </div>
      <div class="flex items-end">
        <button
          class="px-3 py-2 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg transition-colors"
          @click="filterClient = ''; filterDateFrom = ''; filterDateTo = ''; filterInvoice = ''; filterPayment = ''"
        >
          Limpiar
        </button>
      </div>
    </div>

    <!-- ── Tab 1: Pendientes ────────────────────────────────────────────── -->
    <div v-if="activeTab === 'pending'" class="space-y-0">
      <!-- Tabla custom con checkboxes -->
      <div class="rounded-xl border border-gray-200 overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-200 bg-gray-50">
                <!-- Checkbox select-all -->
                <th class="w-10 px-4 py-3 text-left">
                  <button
                    class="flex items-center justify-center w-5 h-5"
                    :title="allSelected ? 'Deseleccionar todo' : 'Seleccionar todo'"
                    @click="toggleAll"
                  >
                    <CheckSquare v-if="allSelected" class="w-4 h-4 text-blue-600" />
                    <div
                      v-else-if="someSelected"
                      class="w-4 h-4 rounded border-2 border-blue-400 bg-blue-100"
                    />
                    <Square v-else class="w-4 h-4 text-gray-400" />
                  </button>
                </th>
                <!-- Columnas con sort -->
                <th
                  v-for="col in ([
                    { key: 'voucher_num', label: 'N° Voucher' },
                    { key: 'date', label: 'Fecha' },
                    { key: 'client', label: 'Cliente' },
                    { key: 'value', label: 'Valor' },
                  ] as { key: SortKey; label: string }[])"
                  :key="col.key"
                  class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide cursor-pointer hover:text-gray-900 select-none"
                  @click="setSort(col.key)"
                >
                  <span class="inline-flex items-center gap-1">
                    {{ col.label }}
                    <ChevronUp
                      v-if="sortKey === col.key && sortDir === 'asc'"
                      class="w-3 h-3 text-blue-500"
                    />
                    <ChevronDown
                      v-else-if="sortKey === col.key && sortDir === 'desc'"
                      class="w-3 h-3 text-blue-500"
                    />
                    <ChevronDown v-else class="w-3 h-3 text-gray-300" />
                  </span>
                </th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">Vehículo</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">Medio de Pago</th>
              </tr>
            </thead>
            <tbody>
              <!-- Loading skeleton -->
              <template v-if="tripsLoading">
                <tr v-for="i in 5" :key="i" class="border-b border-gray-100">
                  <td v-for="j in 7" :key="j" class="px-4 py-3">
                    <div class="h-4 bg-gray-100 rounded animate-pulse" />
                  </td>
                </tr>
              </template>

              <!-- Empty state -->
              <tr v-else-if="!sortedPending.length">
                <td colspan="7" class="px-4 py-12 text-center text-gray-400 text-sm">
                  No hay viajes pendientes de facturar con los filtros seleccionados.
                </td>
              </tr>

              <!-- Rows -->
              <tr
                v-else
                v-for="trip in sortedPending"
                :key="trip.id"
                class="border-b border-gray-100 transition-colors cursor-pointer"
                :class="selectedIds.has(trip.id) ? 'bg-blue-50' : 'hover:bg-gray-50'"
                @click="toggleTrip(trip.id)"
              >
                <td class="px-4 py-3">
                  <div class="flex items-center justify-center">
                    <CheckSquare v-if="selectedIds.has(trip.id)" class="w-4 h-4 text-blue-600" />
                    <Square v-else class="w-4 h-4 text-gray-300" />
                  </div>
                </td>
                <td class="px-4 py-3 font-medium text-gray-900">{{ trip.voucher_num }}</td>
                <td class="px-4 py-3 text-gray-600">{{ formatDate(trip.date) }}</td>
                <td class="px-4 py-3 text-gray-900">{{ trip.client_detail?.name ?? '—' }}</td>
                <td class="px-4 py-3 font-medium text-gray-900">{{ formatCurrency(parseFloat(trip.value)) }}</td>
                <td class="px-4 py-3 text-gray-600">{{ trip.vehicle_detail?.plaque ?? '—' }}</td>
                <td class="px-4 py-3 text-gray-500">{{ trip.payment_detail?.name ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Footer de selección (sticky) -->
      <Transition name="slide-up">
        <div
          v-if="selectedIds.size > 0"
          class="sticky bottom-0 mt-0 bg-white border border-blue-200 rounded-xl shadow-lg px-5 py-4 flex items-center justify-between gap-4"
        >
          <div class="text-sm text-gray-700">
            <span class="font-semibold text-blue-700">{{ selectedIds.size }}</span>
            viaje{{ selectedIds.size !== 1 ? 's' : '' }} seleccionado{{ selectedIds.size !== 1 ? 's' : '' }}
            <span class="mx-2 text-gray-300">|</span>
            Total:
            <span class="font-semibold text-gray-900 ml-1">{{ formatCurrency(selectedTotal) }}</span>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 transition-colors"
              @click="selectedIds = new Set()"
            >
              Limpiar selección
            </button>
            <button
              v-if="canManage"
              class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
              @click="openInvoiceModal"
            >
              <FileText class="w-4 h-4" />
              Asignar Factura
            </button>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Tab 2: Facturados ────────────────────────────────────────────── -->
    <div v-else>
      <DataTable
        :data="invoicedRows"
        :columns="invoicedColumns"
        :is-loading="tripsLoading"
      />
    </div>
  </div>

  <!-- ── Modal: Asignar Factura ─────────────────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="showInvoiceModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      @click.self="closeInvoiceModal"
    >
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div>
            <h2 class="text-base font-semibold text-gray-900">Asignar Factura</h2>
            <p class="text-xs text-gray-400 mt-0.5">
              {{ selectedIds.size }} viaje{{ selectedIds.size !== 1 ? 's' : '' }} —
              {{ formatCurrency(selectedTotal) }}
            </p>
          </div>
          <button class="text-gray-400 hover:text-gray-600 transition-colors" @click="closeInvoiceModal">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Body -->
        <div class="px-6 py-5 space-y-5">
          <!-- Modo: nueva / existente -->
          <div class="flex gap-3">
            <label
              class="flex-1 flex items-center gap-2 rounded-lg border-2 px-4 py-3 cursor-pointer transition-colors"
              :class="invoiceMode === 'new' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'"
            >
              <input v-model="invoiceMode" type="radio" value="new" class="sr-only" />
              <span
                class="w-4 h-4 rounded-full border-2 flex-shrink-0"
                :class="invoiceMode === 'new' ? 'border-blue-500 bg-blue-500' : 'border-gray-300'"
              />
              <span class="text-sm font-medium text-gray-800">Nueva factura</span>
            </label>
            <label
              class="flex-1 flex items-center gap-2 rounded-lg border-2 px-4 py-3 cursor-pointer transition-colors"
              :class="invoiceMode === 'existing' ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'"
            >
              <input v-model="invoiceMode" type="radio" value="existing" class="sr-only" />
              <span
                class="w-4 h-4 rounded-full border-2 flex-shrink-0"
                :class="invoiceMode === 'existing' ? 'border-blue-500 bg-blue-500' : 'border-gray-300'"
              />
              <span class="text-sm font-medium text-gray-800">Factura existente</span>
            </label>
          </div>

          <!-- Nueva factura -->
          <div v-if="invoiceMode === 'new'">
            <label class="block text-sm font-medium text-gray-700 mb-1">
              N° de Factura <span class="text-red-500">*</span>
            </label>
            <input
              v-model="invoiceNumber"
              type="text"
              maxlength="15"
              placeholder="Ej: FAC-2024-001"
              class="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="invoiceNumberError ? 'border-red-400' : 'border-gray-300'"
              @input="invoiceNumberError = ''"
            />
            <p v-if="invoiceNumberError" class="mt-1 text-xs text-red-500">{{ invoiceNumberError }}</p>
            <p class="mt-1 text-xs text-gray-400">Máximo 15 caracteres.</p>
          </div>

          <!-- Factura existente -->
          <div v-else>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Seleccionar factura <span class="text-red-500">*</span>
            </label>
            <select
              v-model="existingInvoiceId"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">— Selecciona una factura —</option>
              <option v-for="inv in invoices" :key="inv.id" :value="inv.id">
                {{ inv.number }}
              </option>
            </select>
            <p v-if="!invoices.length" class="mt-1 text-xs text-gray-400">No hay facturas registradas aún.</p>
          </div>

          <!-- Resumen de viajes seleccionados -->
          <div class="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 space-y-1.5 max-h-40 overflow-y-auto">
            <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Viajes a asignar</p>
            <div
              v-for="(trip, idx) in selectedTrips"
              :key="trip.id"
              class="flex items-center justify-between text-xs text-gray-600"
            >
              <span>
                <span class="text-gray-400 mr-1">{{ idx + 1 }}.</span>
                #{{ trip.voucher_num }} — {{ trip.client_detail?.name }}
              </span>
              <span class="font-medium">{{ formatCurrency(parseFloat(trip.value)) }}</span>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-100">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            @click="closeInvoiceModal"
          >
            Cancelar
          </button>
          <button
            :disabled="assignMutation.isPending.value"
            class="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            @click="assignMutation.mutate()"
          >
            {{ assignMutation.isPending.value ? 'Asignando...' : 'Confirmar asignación' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease;
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>
