<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { BadgeCheck, X, CheckSquare, Square, ChevronDown, ChevronUp } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'

type ARow = Record<string, unknown>

import DataTable from '@/components/shared/DataTable.vue'
import SearchableSelect from '@/components/shared/SearchableSelect.vue'
import DatePickerInput from '@/components/shared/DatePickerInput.vue'
import { usePersistedRef } from '@/composables/usePersistedFilters'
import { tripsApi } from '@/api/trips.api'
import { certificatesApi } from '@/api/certificates.api'
import { clientsApi } from '@/api/clients.api'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import { toastApiError } from '@/utils/handleApiError'
import { useAuthStore } from '@/stores/auth.store'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate } from '@/utils/formatDate'
import type { Trip, Certificate, Client } from '@/types'

const qc = useQueryClient()
const authStore = useAuthStore()
const canManage = computed(() =>
  ['superuser', 'certifier'].includes(authStore.user?.role ?? '')
)

type Tab = 'pending' | 'certified'
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

const { data: certificatesData } = useQuery({
  queryKey: ['certificates'],
  queryFn: () => certificatesApi.list().then(r => r.data),
})
const certificates = computed(() => certificatesData.value ?? [])

const { data: paymentMethodsData } = useQuery({
  queryKey: ['payment-methods'],
  queryFn: () => paymentMethodsApi.list().then(r => r.data),
})
const paymentMethods = computed(() => paymentMethodsData.value ?? [])
const certificateOptions = computed(() => certificates.value.map(c => ({ id: c.id, name: c.number })))

// ── Filtros ────────────────────────────────────────────────────────────────
const filterClient = usePersistedRef<number | null>('sigmo_filters_certification_client', null)
const filterDateFrom = usePersistedRef('sigmo_filters_certification_date_from', '')
const filterDateTo = usePersistedRef('sigmo_filters_certification_date_to', '')
const filterCertificate = usePersistedRef<number | null>('sigmo_filters_certification_certificate', null)
const filterPayment = usePersistedRef<number | null>('sigmo_filters_certification_payment', null)

// ── Pendientes (state=true, certificate=null) ──────────────────────────────
const pendingTrips = computed<Trip[]>(() => {
  return allTrips.value.filter(t => {
    if (!t.state || t.certificate !== null) return false
    if (filterClient.value && t.client_detail?.id !== filterClient.value) return false
    if (filterPayment.value && t.payment_detail?.id !== filterPayment.value) return false
    if (filterDateFrom.value && t.date < filterDateFrom.value) return false
    if (filterDateTo.value && t.date > filterDateTo.value) return false
    return true
  })
})

// ── Certificados (certificate !== null) ─────────────────────────────────────
const certifiedTrips = computed<Trip[]>(() => {
  return allTrips.value.filter(t => {
    if (t.certificate === null) return false
    if (filterClient.value && t.client_detail?.id !== filterClient.value) return false
    if (filterPayment.value && t.payment_detail?.id !== filterPayment.value) return false
    if (filterDateFrom.value && t.date < filterDateFrom.value) return false
    if (filterDateTo.value && t.date > filterDateTo.value) return false
    if (filterCertificate.value && t.certificate !== filterCertificate.value) return false
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

// ── Modal: asignar certificado ─────────────────────────────────────────────
const showCertificateModal = ref(false)
const certificateMode = ref<'new' | 'existing'>('new')
const certificateNumber = ref('')
const certificateNumberError = ref('')
const existingCertificateId = ref<number | null>(null)

function openCertificateModal() {
  certificateMode.value = 'new'
  certificateNumber.value = ''
  certificateNumberError.value = ''
  existingCertificateId.value = null
  showCertificateModal.value = true
}

function closeCertificateModal() {
  showCertificateModal.value = false
}

const assignMutation = useMutation({
  mutationFn: async () => {
    const trips = selectedTrips.value
    const tripIds = trips.map(t => t.id)

    let certificateId: number
    if (certificateMode.value === 'new') {
      const num = certificateNumber.value.trim()
      if (!num) { certificateNumberError.value = 'El número de certificado es requerido.'; throw new Error('validation') }
      if (num.length > 15) { certificateNumberError.value = 'Máximo 15 caracteres.'; throw new Error('validation') }
      certificateNumberError.value = ''
      const res = await certificatesApi.create({ number: num, trip_ids: tripIds })
      certificateId = res.data.id
    } else {
      if (!existingCertificateId.value) { throw new Error('Selecciona un certificado existente.') }
      const res = await certificatesApi.assignTripsToExistingCertificate({
        certificate_id: existingCertificateId.value as number,
        trip_ids: tripIds,
      })
      certificateId = res.data.id
    }

    return { certificateId, count: trips.length }
  },
  onSuccess: ({ count }) => {
    toast.success(`${count} viaje${count !== 1 ? 's' : ''} certificado${count !== 1 ? 's' : ''} correctamente.`)
    selectedIds.value = new Set()
    qc.invalidateQueries({ queryKey: ['trips'] })
    qc.invalidateQueries({ queryKey: ['certificates'] })
    closeCertificateModal()
  },
  onError: (err: unknown) => {
    if (err instanceof Error && err.message === 'validation') return
    if (err instanceof Error && !err.message.includes('validation')) {
      toast.error(err.message)
    } else {
      toastApiError(err)
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

// ── Columnas Tab 2 (certificados) ──────────────────────────────────────────
const certifiedColumns: ColumnDef<ARow>[] = [
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
    accessorKey: 'certificate',
    header: 'N° Certificado',
    cell: info => {
      const certificateId = info.getValue() as number | null
      if (!certificateId) return '—'
      const cert = certificates.value.find(c => c.id === certificateId)
      return cert ? h('span', { class: 'font-medium text-gold-700' }, cert.number) : `#${certificateId}`
    },
  },
  {
    accessorKey: 'certificate_pos',
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

const certifiedRows = computed(() => certifiedTrips.value as unknown as ARow[])

// Reset filtros al cambiar tab
watch(activeTab, () => {
  filterClient.value = null
  filterDateFrom.value = ''
  filterDateTo.value = ''
  filterCertificate.value = null
  filterPayment.value = null
  selectedIds.value = new Set()
})
</script>

<template>
  <div class="p-4 lg:p-6 space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold text-gray-900">Certificación</h1>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200 overflow-x-auto">
      <nav class="flex gap-1 w-max min-w-full" aria-label="Tabs">
        <button
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
          :class="activeTab === 'pending'
            ? 'border-gold-500 text-gold-700'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'pending'"
        >
          Pendientes de Certificar
          <span
            v-if="pendingTrips.length"
            class="ml-2 inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700"
          >
            {{ pendingTrips.length }}
          </span>
        </button>
        <button
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
          :class="activeTab === 'certified'
            ? 'border-gold-500 text-gold-700'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = 'certified'"
        >
          Registros Certificados
        </button>
      </nav>
    </div>

    <!-- ── Filtros comunes ──────────────────────────────────────────────── -->
    <div class="flex flex-wrap gap-3">
      <div class="w-56">
        <label class="block text-xs text-gray-500 mb-1">Cliente</label>
        <SearchableSelect
          :options="clients"
          v-model="filterClient"
          placeholder="Todos"
          clearable
        />
      </div>
      <div>
        <label class="block text-xs text-gray-500 mb-1">Fecha desde</label>
        <DatePickerInput v-model="filterDateFrom" />
      </div>
      <div>
        <label class="block text-xs text-gray-500 mb-1">Fecha hasta</label>
        <DatePickerInput v-model="filterDateTo" />
      </div>
      <!-- Método de pago (ambas tabs) -->
      <div class="w-56">
        <label class="block text-xs text-gray-500 mb-1">Medio de pago</label>
        <SearchableSelect
          :options="paymentMethods"
          v-model="filterPayment"
          placeholder="Todos"
          clearable
        />
      </div>
      <!-- Filtro adicional Tab 2 -->
      <div v-if="activeTab === 'certified'" class="w-56">
        <label class="block text-xs text-gray-500 mb-1">Certificado</label>
        <SearchableSelect
          :options="certificateOptions"
          v-model="filterCertificate"
          placeholder="Todos"
          clearable
        />
      </div>
      <div class="flex items-end">
        <button
          class="px-3 py-2 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg transition-colors"
          @click="filterClient = null; filterDateFrom = ''; filterDateTo = ''; filterCertificate = null; filterPayment = null"
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
                    <CheckSquare v-if="allSelected" class="w-4 h-4 text-gold-700" />
                    <div
                      v-else-if="someSelected"
                      class="w-4 h-4 rounded border-2 border-gold-400 bg-gold-100"
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
                      class="w-3 h-3 text-gold-600"
                    />
                    <ChevronDown
                      v-else-if="sortKey === col.key && sortDir === 'desc'"
                      class="w-3 h-3 text-gold-600"
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
                  No hay viajes pendientes de certificar con los filtros seleccionados.
                </td>
              </tr>

              <!-- Rows -->
              <tr
                v-else
                v-for="trip in sortedPending"
                :key="trip.id"
                class="border-b border-gray-100 transition-colors cursor-pointer"
                :class="selectedIds.has(trip.id) ? 'bg-gold-50' : 'hover:bg-gray-50'"
                @click="toggleTrip(trip.id)"
              >
                <td class="px-4 py-3">
                  <div class="flex items-center justify-center">
                    <CheckSquare v-if="selectedIds.has(trip.id)" class="w-4 h-4 text-gold-700" />
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
          class="sticky bottom-0 mt-0 bg-white border border-gold-200 rounded-xl shadow-lg px-5 py-4 flex items-center justify-between gap-4"
        >
          <div class="text-sm text-gray-700">
            <span class="font-semibold text-gold-800">{{ selectedIds.size }}</span>
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
              class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold-500 text-stone-900 text-sm font-medium hover:bg-gold-600 transition-colors"
              @click="openCertificateModal"
            >
              <BadgeCheck class="w-4 h-4" />
              Asignar Certificado
            </button>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Tab 2: Certificados ──────────────────────────────────────────── -->
    <div v-else>
      <DataTable
        :data="certifiedRows"
        :columns="certifiedColumns"
        :is-loading="tripsLoading"
      />
    </div>
  </div>

  <!-- ── Modal: Asignar Certificado ───────────────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="showCertificateModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      @click.self="closeCertificateModal"
    >
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b-2 border-gold-200 bg-gold-50/40">
          <div>
            <h2 class="text-base font-semibold text-gray-900">Asignar Certificado</h2>
            <p class="text-xs text-gray-400 mt-0.5">
              {{ selectedIds.size }} viaje{{ selectedIds.size !== 1 ? 's' : '' }} —
              {{ formatCurrency(selectedTotal) }}
            </p>
          </div>
          <button class="text-gray-400 hover:text-gray-600 transition-colors" @click="closeCertificateModal">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Body -->
        <div class="px-6 py-5 space-y-5">
          <!-- Modo: nuevo / existente -->
          <div class="flex gap-3">
            <label
              class="flex-1 flex items-center gap-2 rounded-lg border-2 px-4 py-3 cursor-pointer transition-colors"
              :class="certificateMode === 'new' ? 'border-gold-500 bg-gold-50' : 'border-gray-200 hover:border-gray-300'"
            >
              <input v-model="certificateMode" type="radio" value="new" class="sr-only" />
              <span
                class="w-4 h-4 rounded-full border-2 flex-shrink-0"
                :class="certificateMode === 'new' ? 'border-gold-500 bg-gold-500' : 'border-gray-300'"
              />
              <span class="text-sm font-medium text-gray-800">Nuevo certificado</span>
            </label>
            <label
              class="flex-1 flex items-center gap-2 rounded-lg border-2 px-4 py-3 cursor-pointer transition-colors"
              :class="certificateMode === 'existing' ? 'border-gold-500 bg-gold-50' : 'border-gray-200 hover:border-gray-300'"
            >
              <input v-model="certificateMode" type="radio" value="existing" class="sr-only" />
              <span
                class="w-4 h-4 rounded-full border-2 flex-shrink-0"
                :class="certificateMode === 'existing' ? 'border-gold-500 bg-gold-500' : 'border-gray-300'"
              />
              <span class="text-sm font-medium text-gray-800">Certificado existente</span>
            </label>
          </div>

          <!-- Nuevo certificado -->
          <div v-if="certificateMode === 'new'">
            <label class="block text-sm font-medium text-gray-700 mb-1">
              N° de Certificado <span class="text-red-500">*</span>
            </label>
            <input
              v-model="certificateNumber"
              type="text"
              maxlength="15"
              placeholder="Ej: CERT-2024-001"
              class="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
              :class="certificateNumberError ? 'border-red-400' : 'border-gray-300'"
              @input="certificateNumberError = ''"
            />
            <p v-if="certificateNumberError" class="mt-1 text-xs text-red-500">{{ certificateNumberError }}</p>
            <p class="mt-1 text-xs text-gray-400">Máximo 15 caracteres.</p>
          </div>

          <!-- Certificado existente -->
          <div v-else>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Seleccionar certificado <span class="text-red-500">*</span>
            </label>
            <SearchableSelect
              :options="certificateOptions"
              v-model="existingCertificateId"
              placeholder="Buscar certificado..."
            />
            <p v-if="!certificates.length" class="mt-1 text-xs text-gray-400">No hay certificados registrados aún.</p>
          </div>

          <!-- Resumen de viajes seleccionados -->
          <div class="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 space-y-1.5 max-h-40 overflow-y-auto">
            <p class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Viajes a certificar</p>
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
            @click="closeCertificateModal"
          >
            Cancelar
          </button>
          <button
            :disabled="assignMutation.isPending.value"
            class="px-4 py-2 text-sm font-medium bg-gold-500 text-stone-900 rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
