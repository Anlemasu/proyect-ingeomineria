<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'

import {
  RefreshCw, Pencil, Ban, CheckCircle, AlertTriangle, Search,
} from 'lucide-vue-next'

import PageHeader       from '@/components/shared/PageHeader.vue'
import CurrencyInput    from '@/components/shared/CurrencyInput.vue'
import SearchableSelect from '@/components/shared/SearchableSelect.vue'

import { tripsApi }          from '@/api/trips.api'
import { clientsApi }        from '@/api/clients.api'
import { originsApi }        from '@/api/origins.api'
import { materialsApi }      from '@/api/materials.api'
import { vehiclesApi }       from '@/api/vehicles.api'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import { advancesApi }       from '@/api/advances.api'
import { useAuthStore }      from '@/stores/auth.store'
import { todayBogota }       from '@/utils/formatDate'
import { formatCurrency }    from '@/utils/formatCurrency'
import { getApiErrorMessage } from '@/utils/handleApiError'
import type { Trip } from '@/types'

const authStore    = useAuthStore()
const queryClient  = useQueryClient()

const role          = computed(() => authStore.user?.role ?? '')
const isSuperuser   = computed(() => role.value === 'superuser')
const canAnnul      = computed(() => role.value === 'superuser' || role.value === 'commercial_admin')
// Igual que en el formulario de registro: solo superuser/commercial_admin pueden mover la fecha del viaje
const canChangeDate = computed(() => role.value === 'superuser' || role.value === 'commercial_admin')

const today = todayBogota()

// ── Queries ───────────────────────────────────────────────────────────────────
// cashier/commercial_admin solo ajustan viajes del día en curso (SAME_DAY_ONLY_ROLES
// en el backend). superuser puede consultar y ajustar viajes de fechas pasadas (RF-37),
// por eso solo a ese rol se le muestra el selector de fecha.
const selectedDate = ref(today)
const { data: tripsData, isLoading, refetch } = useQuery({
  queryKey: ['trips-adjustments', selectedDate],
  queryFn:  () => tripsApi.list({ date: selectedDate.value }).then(r => r.data),
  refetchInterval: 30_000,
})
const trips = computed(() => tripsData.value ?? [])
const isHistoricalView = computed(() => selectedDate.value !== today)

// ── Búsqueda por número de vale ───────────────────────────────────────────────
const voucherSearch = ref('')
const filteredTrips = computed(() => {
  const q = voucherSearch.value.trim()
  if (!q) return trips.value
  return trips.value.filter(t => String(t.voucher_num).includes(q))
})

const { data: clientsData } = useQuery({
  queryKey: ['clients'],
  queryFn:  () => clientsApi.list({ state: 'true' }).then(r => r.data),
})
const { data: originsData } = useQuery({
  queryKey: ['origins'],
  queryFn:  () => originsApi.list().then(r => r.data),
})
const { data: materialsData } = useQuery({
  queryKey: ['materials'],
  queryFn:  () => materialsApi.list().then(r => r.data),
})
const { data: vehiclesData } = useQuery({
  queryKey: ['vehicles'],
  queryFn:  () => vehiclesApi.list().then(r => r.data),
})
const { data: paymentsData } = useQuery({
  queryKey: ['payments'],
  queryFn:  () => paymentMethodsApi.list().then(r => r.data),
})

const clientOptions   = computed(() => (clientsData.value ?? []).filter(c => c.state).map(c => ({ id: c.id, name: c.name })))
const originOptions   = computed(() => (originsData.value ?? []).filter(o => o.state).map(o => ({ id: o.id, name: o.name })))
const materialOptions = computed(() => (materialsData.value ?? []).filter(m => m.state).map(m => ({ id: m.id, name: m.name })))
const vehicleOptions  = computed(() => (vehiclesData.value ?? []).map(v => ({ id: v.id, name: v.plaque })))
const paymentList     = computed(() => (paymentsData.value ?? []).filter(p => p.state))

// ── Drawer edición ────────────────────────────────────────────────────────────
const editTrip          = ref<Trip | null>(null)
const editClient        = ref<number | undefined>(undefined)
const editOrigin        = ref<number | undefined>(undefined)
const editMaterial      = ref<number | undefined>(undefined)
const editVehicle       = ref<number | undefined>(undefined)
const editPayment       = ref<number | undefined>(undefined)
const editValue         = ref<number | undefined>(undefined)
const editDate          = ref('')
const editExtern        = ref('')
const editJustification = ref('')
const editLoading       = ref(false)

function openEdit(trip: Trip) {
  editTrip.value          = trip
  editClient.value        = trip.client_detail?.id
  editOrigin.value        = trip.origin_site_detail?.id
  editMaterial.value      = trip.material_type_detail?.id
  editVehicle.value       = trip.vehicle_detail?.id
  editPayment.value       = trip.payment_detail?.id
  editValue.value         = parseFloat(trip.value)
  editDate.value          = trip.date
  editExtern.value        = trip.extern_voucher_num ?? ''
  editJustification.value = ''
}

// ── Anticipo — auto-asignación al editar, igual que en el registro de viajes ──
const { data: editAdvancesData } = useQuery({
  queryKey: computed(() => ['advances', editClient.value]),
  queryFn:  () => editClient.value
    ? advancesApi.list({ client: editClient.value }).then(r => r.data)
    : Promise.resolve([]),
  enabled: computed(() => !!editClient.value),
})
const editActiveAdvance = computed(() =>
  (editAdvancesData.value ?? []).find(a => (a.available_balance ?? 0) > 0) ?? null
)
const editIsAdvancePayment = computed(() =>
  paymentList.value.find(p => p.id === editPayment.value)?.is_advance === true
)
const editAdvanceId = ref<number | null>(null)
watch([editActiveAdvance, editIsAdvancePayment], ([advance, isAdvance]) => {
  editAdvanceId.value = isAdvance ? (advance?.id ?? null) : null
})

// ── Reasignación de anticipo al cambiar el cliente ─────────────────────────────
// Si el cliente del viaje cambia, el saldo se devuelve completo al cliente
// anterior y se reevalúa desde cero contra el anticipo activo del cliente
// nuevo (mismas reglas que el registro de un viaje nuevo, ver
// reallocate_advance_on_client_change en el backend). Si el nuevo cliente no
// alcanza, hace falta justificar — igual que en TripsPage al registrar.
const editClientChanged = computed(() =>
  !!editTrip.value && editClient.value !== editTrip.value.client_detail?.id
)
const editHasActiveAdvance = computed(() => editActiveAdvance.value !== null)
const editBalanceSufficient = computed(() => {
  if (!editIsAdvancePayment.value) return true
  if (!editHasActiveAdvance.value) return false
  return (editActiveAdvance.value?.available_balance ?? 0) >= (editValue.value ?? 0)
})
const editNeedsJustification = computed(() =>
  editClientChanged.value && editIsAdvancePayment.value && !editBalanceSufficient.value
)
const editCanSubmit = computed(() => {
  if (!editNeedsJustification.value) return true
  return isSuperuser.value && editJustification.value.trim().length > 0
})
watch(editClient, () => { editJustification.value = '' })

async function saveEdit() {
  if (!editTrip.value) return
  if (!editCanSubmit.value) {
    toast.error('El nuevo cliente no tiene saldo de anticipo suficiente. Justifique el ajuste para guardarlo como deuda pendiente.')
    return
  }

  editLoading.value = true
  try {
    const patch: Record<string, unknown> = {}
    const orig = editTrip.value

    if (editClient.value    !== orig.client_detail?.id)        patch.client        = editClient.value
    if (editOrigin.value    !== orig.origin_site_detail?.id)   patch.origin_site   = editOrigin.value
    if (editMaterial.value  !== orig.material_type_detail?.id) patch.material_type = editMaterial.value
    if (editVehicle.value   !== orig.vehicle_detail?.id)       patch.vehicle       = editVehicle.value
    if (editPayment.value   !== orig.payment_detail?.id)       patch.payment       = editPayment.value
    if (editValue.value     !== parseFloat(orig.value))        patch.value         = editValue.value
    if (editDate.value      !== orig.date)                     patch.date          = editDate.value
    if (editAdvanceId.value !== (orig.advance ?? null))        patch.advance       = editAdvanceId.value

    const currentExtern = orig.extern_voucher_num ?? ''
    if (editExtern.value !== currentExtern) patch.extern_voucher_num = editExtern.value.trim() || null

    if (Object.keys(patch).length === 0) {
      toast.info('Sin cambios que guardar')
      editTrip.value = null
      return
    }

    // Cambio de cliente en viaje financiado con anticipo: el backend
    // recalcula el anticipo (devuelve saldo al cliente anterior, descuenta
    // del nuevo) e ignora cualquier `advance` que se le mande — esta
    // justificación solo aplica si el nuevo cliente no alcanza a cubrir el
    // valor del viaje (ver reallocate_advance_on_client_change).
    if (editNeedsJustification.value) patch.justification = editJustification.value.trim()

    await tripsApi.patch(orig.id, patch)
    toast.success('Viaje actualizado correctamente')
    editTrip.value = null
    refetch()
    queryClient.invalidateQueries({ queryKey: ['trips', 'today'] })
    queryClient.invalidateQueries({ queryKey: ['cash-closing-today'] })
    // Cualquier edición que toque valor/cliente/medio de pago puede haber
    // movido saldo de anticipo (mismo cliente vía sync_advance_movement_on_trip_change,
    // o entre clientes vía reallocate_advance_on_client_change) — invalidar
    // 'advances'/'advance-balance' por prefijo cubre tanto la query global
    // de AdvancesPage (alerta de saldos negativos) como las scoped por cliente.
    queryClient.invalidateQueries({ queryKey: ['advances'] })
    queryClient.invalidateQueries({ queryKey: ['advance-balance'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard', 'advances'] })
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  } finally {
    editLoading.value = false
  }
}

// ── Modal anulación ───────────────────────────────────────────────────────────
const annulTrip          = ref<Trip | null>(null)
const annulJustification = ref('')
const annulLoading       = ref(false)

function openAnnul(trip: Trip) {
  annulTrip.value          = trip
  annulJustification.value = ''
}

async function confirmAnnul() {
  if (!annulTrip.value) return
  if (!annulJustification.value.trim()) {
    toast.error('La justificación es obligatoria para anular un viaje')
    return
  }
  annulLoading.value = true
  try {
    await tripsApi.patch(annulTrip.value.id, {
      state:         false,
      justification: annulJustification.value.trim(),
    })
    toast.success(`Viaje #${annulTrip.value.voucher_num} anulado`)
    annulTrip.value = null
    refetch()
    queryClient.invalidateQueries({ queryKey: ['trips', 'today'] })
    queryClient.invalidateQueries({ queryKey: ['cash-closing-today'] })
    // La anulación revierte el saldo de anticipo si el viaje estaba financiado.
    queryClient.invalidateQueries({ queryKey: ['advances'] })
    queryClient.invalidateQueries({ queryKey: ['advance-balance'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard', 'advances'] })
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  } finally {
    annulLoading.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="Ajustes del Día"
      subtitle="Corrección de viajes antes del cierre de caja"
    />

    <!-- Barra de filtros -->
    <div class="flex flex-wrap items-center gap-3">
      <div class="relative w-full sm:w-auto">
        <Search class="w-4 h-4 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          v-model="voucherSearch"
          type="text"
          inputmode="numeric"
          placeholder="Buscar por N° de vale..."
          class="pl-8 pr-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 w-full sm:w-56"
        />
      </div>
      <input
        v-if="isSuperuser"
        v-model="selectedDate"
        type="date"
        :max="today"
        class="px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 bg-white"
      />
      <span v-if="isHistoricalView" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700">
        <AlertTriangle class="w-3 h-3" />Vista histórica
      </span>
      <button
        type="button"
        @click="refetch()"
        class="p-2 rounded-lg text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
        title="Actualizar"
      >
        <RefreshCw class="w-4 h-4" :class="isLoading ? 'animate-spin text-gold-600' : ''" />
      </button>
      <span class="text-xs text-gray-400 sm:ml-auto">
        {{ filteredTrips.length }} viaje{{ filteredTrips.length !== 1 ? 's' : '' }} —
        {{ filteredTrips.filter(t => t.state).length }} activo{{ filteredTrips.filter(t => t.state).length !== 1 ? 's' : '' }}
      </span>
    </div>

    <!-- Tabla de viajes -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-100">
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Vale</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cliente</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Placa</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Material</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Valor</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Medio de pago</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Estado</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Acciones</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-if="isLoading && trips.length === 0">
              <td colspan="8" class="px-4 py-12 text-center text-xs text-gray-400">
                <RefreshCw class="w-4 h-4 animate-spin inline-block mr-2" />Cargando viajes...
              </td>
            </tr>
            <tr v-else-if="filteredTrips.length === 0">
              <td colspan="8" class="px-4 py-12 text-center text-xs text-gray-400">
                {{ voucherSearch.trim()
                  ? 'Sin resultados para ese número de vale'
                  : isHistoricalView ? 'Sin viajes registrados en esta fecha' : 'Sin viajes registrados hoy' }}
              </td>
            </tr>
            <tr
              v-for="trip in filteredTrips"
              :key="trip.id"
              class="hover:bg-gray-50 transition-colors"
              :class="!trip.state ? 'opacity-40' : ''"
            >
              <td class="px-4 py-3">
                <span class="font-mono font-bold text-gold-800">#{{ trip.voucher_num }}</span>
              </td>
              <td class="px-4 py-3 font-medium text-gray-900 max-w-[150px] truncate">
                {{ trip.client_detail?.name ?? '—' }}
              </td>
              <td class="px-4 py-3 font-mono tracking-wider text-gray-800">
                {{ trip.vehicle_detail?.plaque ?? '—' }}
              </td>
              <td class="px-4 py-3 text-xs text-gray-600">
                {{ trip.material_type_detail?.name ?? '—' }}
              </td>
              <td class="px-4 py-3 text-right font-semibold text-gray-900">
                {{ formatCurrency(trip.value) }}
              </td>
              <td class="px-4 py-3 text-xs text-gray-600">
                {{ trip.payment_detail?.name ?? '—' }}
              </td>
              <td class="px-4 py-3">
                <span
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium"
                  :class="trip.state
                    ? 'bg-green-50 text-green-700'
                    : 'bg-red-50 text-red-600'"
                >
                  <CheckCircle v-if="trip.state" class="w-3 h-3" />
                  <Ban v-else class="w-3 h-3" />
                  {{ trip.state ? 'Activo' : 'Anulado' }}
                </span>
              </td>
              <td class="px-4 py-3">
                <div v-if="trip.state" class="flex items-center gap-0.5">
                  <button
                    type="button"
                    @click="openEdit(trip)"
                    class="p-1.5 rounded text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
                    title="Editar viaje"
                  >
                    <Pencil class="w-4 h-4" />
                  </button>
                  <button
                    v-if="canAnnul"
                    type="button"
                    @click="openAnnul(trip)"
                    class="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    title="Anular viaje"
                  >
                    <Ban class="w-4 h-4" />
                  </button>
                </div>
                <span v-else class="text-xs text-gray-400 px-1.5">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Drawer edición ─────────────────────────────────────────────────── -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-150"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div v-if="editTrip" class="fixed inset-0 z-50 flex justify-end">
          <div class="absolute inset-0 bg-black/30" @click="editTrip = null" />
          <div class="relative bg-white w-full max-w-sm shadow-2xl flex flex-col">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between shrink-0">
              <div>
                <h3 class="text-sm font-semibold text-gray-800">
                  Editar Viaje #{{ editTrip.voucher_num }}
                </h3>
                <p class="text-xs text-gray-500 mt-0.5">
                  {{ editTrip.client_detail?.name }} — {{ editTrip.vehicle_detail?.plaque }}
                </p>
              </div>
              <button
                type="button"
                @click="editTrip = null"
                class="text-gray-400 hover:text-gray-600 text-lg leading-none"
              >✕</button>
            </div>

            <div class="p-6 space-y-5 flex-1 overflow-y-auto">
              <!-- Cliente -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Cliente</label>
                <SearchableSelect
                  :options="clientOptions"
                  v-model="editClient"
                  placeholder="Buscar cliente..."
                />
              </div>

              <!-- Origen -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Origen del material</label>
                <SearchableSelect
                  :options="originOptions"
                  v-model="editOrigin"
                  placeholder="Buscar origen..."
                />
              </div>

              <!-- Tipo de material -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Tipo de material</label>
                <select
                  v-model="editMaterial"
                  class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 bg-white"
                >
                  <option v-for="m in materialOptions" :key="m.id" :value="m.id">{{ m.name }}</option>
                </select>
              </div>

              <!-- Vehículo -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Vehículo (placa)</label>
                <SearchableSelect
                  :options="vehicleOptions"
                  v-model="editVehicle"
                  placeholder="Buscar placa..."
                />
              </div>

              <!-- Fecha -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Fecha</label>
                <input
                  v-model="editDate"
                  type="date"
                  :readonly="!canChangeDate"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                  :class="canChangeDate
                    ? 'border-gray-300 bg-white'
                    : 'border-gray-200 bg-gray-50 text-gray-600 cursor-default'"
                />
                <p v-if="!canChangeDate" class="mt-1 text-xs text-gray-400">Solo el día actual</p>
              </div>

              <!-- Medio de pago -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Medio de pago</label>
                <select
                  v-model="editPayment"
                  class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 bg-white"
                >
                  <option v-for="p in paymentList" :key="p.id" :value="p.id">{{ p.name }}</option>
                </select>
              </div>

              <!-- Info anticipo (auto-asignado, igual que en el registro) -->
              <div
                v-if="editIsAdvancePayment"
                class="text-xs px-3 py-2 rounded-lg border"
                :class="editActiveAdvance
                  ? 'bg-green-50 text-green-700 border-green-200'
                  : 'bg-red-50 text-red-700 border-red-200'"
              >
                <span v-if="editActiveAdvance">
                  Anticipo activo: <strong>#{{ editActiveAdvance.id }}</strong> —
                  Saldo: <strong>{{ formatCurrency(editActiveAdvance.available_balance ?? 0) }}</strong>
                </span>
                <span v-else>Sin anticipo disponible para este cliente</span>
                <p v-if="editClientChanged" class="mt-1 text-[11px] opacity-80">
                  Al guardar, el saldo se devuelve al cliente anterior y el viaje pasa a descontarse de este anticipo.
                </p>
              </div>

              <!-- Saldo insuficiente tras el cambio de cliente -->
              <div v-if="editNeedsJustification" class="px-3 py-2 rounded-lg bg-red-50 border border-red-200">
                <div class="flex items-start gap-2 text-red-700 text-xs">
                  <AlertTriangle class="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <div class="space-y-0.5">
                    <p class="font-semibold">Saldo insuficiente para el nuevo cliente</p>
                    <p>Saldo disponible: <strong>{{ formatCurrency(editActiveAdvance?.available_balance ?? 0) }}</strong></p>
                    <p>Valor del viaje: <strong>{{ formatCurrency(editValue ?? 0) }}</strong></p>
                  </div>
                </div>
                <div v-if="isSuperuser" class="mt-2 pt-2 border-t border-red-200">
                  <label class="block text-xs font-medium text-red-700 mb-1">
                    Justificación <span class="text-red-500">*</span>
                  </label>
                  <textarea
                    v-model="editJustification"
                    rows="2"
                    placeholder="Motivo — el viaje quedará como deuda pendiente del nuevo cliente..."
                    class="w-full px-3 py-2 text-sm border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
                  />
                </div>
                <p v-else class="mt-2 text-xs text-red-600">
                  Solo el superusuario puede guardar este ajuste como deuda pendiente.
                </p>
              </div>

              <!-- Valor -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Valor del servicio</label>
                <CurrencyInput v-model="editValue" />
              </div>

              <!-- Vale externo -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">N° Vale externo</label>
                <input
                  v-model="editExtern"
                  type="text"
                  maxlength="20"
                  placeholder="Opcional"
                  class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                />
              </div>
            </div>

            <div class="px-6 py-4 border-t border-gray-100 shrink-0">
              <button
                type="button"
                @click="saveEdit"
                :disabled="editLoading || !editCanSubmit"
                class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 disabled:opacity-50 transition-colors"
              >
                <RefreshCw v-if="editLoading" class="w-4 h-4 animate-spin" />
                {{ editLoading ? 'Guardando...' : 'Guardar cambios' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ── Modal anulación ────────────────────────────────────────────────── -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-150"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-100"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="annulTrip"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
        >
          <div class="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div class="flex items-start gap-3 mb-4">
              <div class="p-2 bg-red-100 rounded-lg shrink-0">
                <AlertTriangle class="w-5 h-5 text-red-600" />
              </div>
              <div>
                <h3 class="text-sm font-semibold text-gray-800">
                  Anular Viaje #{{ annulTrip.voucher_num }}
                </h3>
                <p class="text-xs text-gray-500 mt-0.5">
                  {{ annulTrip.client_detail?.name }} ·
                  {{ annulTrip.vehicle_detail?.plaque }} ·
                  {{ formatCurrency(annulTrip.value) }}
                </p>
              </div>
            </div>

            <p class="text-sm text-gray-600 mb-4">
              Esta acción no puede revertirse. El viaje quedará anulado y
              no se incluirá en el cierre de caja.
            </p>

            <div class="mb-5">
              <label class="block text-xs font-medium text-gray-700 mb-1.5">
                Justificación <span class="text-red-500">*</span>
              </label>
              <textarea
                v-model="annulJustification"
                rows="3"
                placeholder="Motivo de la anulación..."
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
                autofocus
              />
            </div>

            <div class="flex gap-2 justify-end">
              <button
                type="button"
                @click="annulTrip = null"
                class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              >Cancelar</button>
              <button
                type="button"
                @click="confirmAnnul"
                :disabled="annulLoading || !annulJustification.trim()"
                class="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 disabled:opacity-50 flex items-center gap-2"
              >
                <RefreshCw v-if="annulLoading" class="w-4 h-4 animate-spin" />
                {{ annulLoading ? 'Anulando...' : 'Confirmar anulación' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
