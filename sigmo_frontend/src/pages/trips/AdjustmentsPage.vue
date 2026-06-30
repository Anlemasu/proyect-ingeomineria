<script setup lang="ts">
import { ref, computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'

import {
  RefreshCw, Pencil, Ban, CheckCircle, AlertTriangle,
} from 'lucide-vue-next'

import PageHeader    from '@/components/shared/PageHeader.vue'
import CurrencyInput from '@/components/shared/CurrencyInput.vue'

import { tripsApi }          from '@/api/trips.api'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import { useAuthStore }      from '@/stores/auth.store'
import { toISODate }         from '@/utils/formatDate'
import { formatCurrency }    from '@/utils/formatCurrency'
import { getApiErrorMessage } from '@/utils/handleApiError'
import type { Trip } from '@/types'

const authStore = useAuthStore()

const role        = computed(() => authStore.user?.role ?? '')
const canAnnul    = computed(() => role.value === 'superuser' || role.value === 'commercial_admin')
const canDatePick = computed(() => role.value === 'superuser' || role.value === 'commercial_admin')

// ── Fecha ─────────────────────────────────────────────────────────────────────
const today        = toISODate(new Date())
const selectedDate = ref(today)

// ── Queries ───────────────────────────────────────────────────────────────────
const { data: tripsData, isLoading, refetch } = useQuery({
  queryKey: computed(() => ['trips-adjustments', selectedDate.value]),
  queryFn:  () => tripsApi.list({ date: selectedDate.value }).then(r => r.data),
  refetchInterval: 30_000,
})
const trips = computed(() => tripsData.value ?? [])

const { data: paymentsData } = useQuery({
  queryKey: ['payments'],
  queryFn:  () => paymentMethodsApi.list().then(r => r.data),
})
const paymentList = computed(() => (paymentsData.value ?? []).filter(p => p.state))

// ── Drawer edición ────────────────────────────────────────────────────────────
const editTrip    = ref<Trip | null>(null)
const editPayment = ref<number | undefined>(undefined)
const editValue   = ref<number | undefined>(undefined)
const editExtern  = ref('')
const editLoading = ref(false)

function openEdit(trip: Trip) {
  editTrip.value    = trip
  editPayment.value = trip.payment_detail?.id
  editValue.value   = parseFloat(trip.value)
  editExtern.value  = trip.extern_voucher_num ?? ''
}

async function saveEdit() {
  if (!editTrip.value) return
  editLoading.value = true
  try {
    const patch: Record<string, unknown> = {}

    if (editPayment.value !== editTrip.value.payment_detail?.id)
      patch.payment = editPayment.value
    if (editValue.value !== parseFloat(editTrip.value.value))
      patch.value = editValue.value
    const currentExtern = editTrip.value.extern_voucher_num ?? ''
    if (editExtern.value !== currentExtern)
      patch.extern_voucher_num = editExtern.value.trim() || null

    if (Object.keys(patch).length === 0) {
      toast.info('Sin cambios que guardar')
      editTrip.value = null
      return
    }

    await tripsApi.patch(editTrip.value.id, patch)
    toast.success('Viaje actualizado correctamente')
    editTrip.value = null
    refetch()
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
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-2">
        <label class="text-sm font-medium text-gray-700">Fecha:</label>
        <input
          v-model="selectedDate"
          type="date"
          :readonly="!canDatePick"
          class="px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          :class="canDatePick
            ? 'border-gray-300 bg-white'
            : 'border-gray-200 bg-gray-50 text-gray-600 cursor-default'"
        />
      </div>
      <button
        type="button"
        @click="refetch()"
        class="p-2 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
        title="Actualizar"
      >
        <RefreshCw class="w-4 h-4" :class="isLoading ? 'animate-spin text-blue-500' : ''" />
      </button>
      <span class="text-xs text-gray-400 ml-auto">
        {{ trips.length }} viaje{{ trips.length !== 1 ? 's' : '' }} —
        {{ trips.filter(t => t.state).length }} activo{{ trips.filter(t => t.state).length !== 1 ? 's' : '' }}
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
            <tr v-else-if="trips.length === 0">
              <td colspan="8" class="px-4 py-12 text-center text-xs text-gray-400">
                Sin viajes para la fecha seleccionada
              </td>
            </tr>
            <tr
              v-for="trip in trips"
              :key="trip.id"
              class="hover:bg-gray-50 transition-colors"
              :class="!trip.state ? 'opacity-40' : ''"
            >
              <td class="px-4 py-3">
                <span class="font-mono font-bold text-blue-700">#{{ trip.voucher_num }}</span>
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
                    class="p-1.5 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
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
              <!-- Campos no editables (referencia) -->
              <div class="bg-gray-50 rounded-lg p-4 text-xs space-y-2 text-gray-600">
                <div class="flex justify-between">
                  <span>Material:</span>
                  <span class="font-medium text-gray-900">{{ editTrip.material_type_detail?.name ?? '—' }}</span>
                </div>
                <div class="flex justify-between">
                  <span>Origen:</span>
                  <span class="font-medium text-gray-900">{{ editTrip.origin_site_detail?.name ?? '—' }}</span>
                </div>
              </div>

              <!-- Medio de pago -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1.5">Medio de pago</label>
                <select
                  v-model="editPayment"
                  class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option v-for="p in paymentList" :key="p.id" :value="p.id">{{ p.name }}</option>
                </select>
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
                  class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            <div class="px-6 py-4 border-t border-gray-100 shrink-0">
              <button
                type="button"
                @click="saveEdit"
                :disabled="editLoading"
                class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
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
