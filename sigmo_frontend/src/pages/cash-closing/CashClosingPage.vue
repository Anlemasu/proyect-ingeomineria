<script setup lang="ts">
import { ref, computed } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'

import {
  RefreshCw, Lock, Unlock, CheckCircle, AlertTriangle,
  TrendingUp, Truck, BarChart2, Wallet,
} from 'lucide-vue-next'

import PageHeader from '@/components/shared/PageHeader.vue'

import { cashClosingApi }    from '@/api/cashClosing.api'
import { useAuthStore }      from '@/stores/auth.store'
import { formatCurrency }    from '@/utils/formatCurrency'
import { formatDate }        from '@/utils/formatDate'
import { getApiErrorMessage } from '@/utils/handleApiError'
import type { DailySummary } from '@/types'

const authStore   = useAuthStore()
const queryClient = useQueryClient()
const isSuperuser = computed(() => authStore.user?.role === 'superuser')

// ── Preview del día ───────────────────────────────────────────────────────────
const { data: todayData, isLoading: todayLoading, refetch: refetchToday } = useQuery({
  queryKey: ['cash-closing-today'],
  queryFn:  () => cashClosingApi.today().then(r => r.data),
  refetchInterval: 30_000,
})

const alreadyClosed = computed(() => todayData.value?.already_closed ?? false)
const todayPaymentDetails = computed(() => todayData.value?.payment_details ?? [])
const todayTotalRevenue   = computed(() =>
  todayPaymentDetails.value.reduce((s, p) => s + Number(p.total), 0)
)

// ── Histórico ─────────────────────────────────────────────────────────────────
const { data: historyData, isLoading: historyLoading, refetch: refetchHistory } = useQuery({
  queryKey: ['cash-closing-list'],
  queryFn:  () => cashClosingApi.list().then(r => r.data),
})
const history = computed(() => historyData.value ?? [])

// El resumen del día en curso lo trae `today()` sin id (no crea el cierre),
// pero si ya está cerrado el registro real vive en `history` — lo buscamos
// ahí para poder revertirlo.
const todayClosureRecord = computed(() =>
  history.value.find(s => s.date === todayData.value?.date && s.state === 'closed') ?? null
)

// ── Cierre ────────────────────────────────────────────────────────────────────
const confirmOpen  = ref(false)
const closingLoading = ref(false)

async function executeClose() {
  closingLoading.value = true
  try {
    await cashClosingApi.close()
    toast.success('Cierre de caja ejecutado correctamente')
    confirmOpen.value = false
    await refetchToday()
    await refetchHistory()
    queryClient.invalidateQueries({ queryKey: ['trips', 'today'] })
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  } finally {
    closingLoading.value = false
  }
}

// ── Reversión de cierre (solo superuser) ───────────────────────────────────────
const revertTarget       = ref<DailySummary | null>(null)
const revertJustification = ref('')
const revertLoading      = ref(false)

function openRevert(summary: DailySummary) {
  revertTarget.value       = summary
  revertJustification.value = ''
}

async function confirmRevert() {
  if (!revertTarget.value) return
  revertLoading.value = true
  try {
    await cashClosingApi.revert(revertTarget.value.id, revertJustification.value.trim() || undefined)
    toast.success(`Cierre del ${formatDate(revertTarget.value.date)} revertido`)
    revertTarget.value = null
    await refetchToday()
    await refetchHistory()
    queryClient.invalidateQueries({ queryKey: ['trips', 'today'] })
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  } finally {
    revertLoading.value = false
  }
}

// ── Drawer detalle histórico ───────────────────────────────────────────────────
const detailSummary = ref<DailySummary | null>(null)
const detailRevenue = computed(() =>
  (detailSummary.value?.payment_details ?? []).reduce((s, p) => s + Number(p.total), 0)
)
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="Cierre de Caja"
      subtitle="Resumen diario y ejecución del cierre"
    />

    <!-- ── Panel resumen del día ─────────────────────────────────────────── -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-semibold text-gray-800">Resumen del día en curso</h2>
          <p class="text-xs text-gray-500 mt-0.5">Actualización automática cada 30 segundos</p>
        </div>
        <div class="flex items-center gap-2">
          <span
            v-if="alreadyClosed"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-green-100 text-green-700 text-xs font-semibold"
          >
            <CheckCircle class="w-3.5 h-3.5" /> Caja cerrada
          </span>
          <button
            type="button"
            @click="refetchToday()"
            class="p-2 rounded-lg text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
            title="Actualizar ahora"
          >
            <RefreshCw
              class="w-4 h-4"
              :class="todayLoading ? 'animate-spin text-gold-600' : ''"
            />
          </button>
        </div>
      </div>

      <div v-if="todayLoading && !todayData" class="px-6 py-10 text-center text-xs text-gray-400">
        <RefreshCw class="w-4 h-4 animate-spin inline-block mr-2" />Cargando...
      </div>

      <div v-else-if="todayData" class="p-6">
        <!-- KPIs -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div class="bg-gold-50 rounded-xl p-4">
            <div class="flex items-center gap-2 mb-2">
              <Truck class="w-4 h-4 text-gold-600" />
              <span class="text-xs font-medium text-gold-700 uppercase tracking-wide">Viajes</span>
            </div>
            <p class="text-2xl font-bold text-gold-800">{{ todayData.total_trips }}</p>
          </div>
          <div class="bg-emerald-50 rounded-xl p-4">
            <div class="flex items-center gap-2 mb-2">
              <TrendingUp class="w-4 h-4 text-emerald-500" />
              <span class="text-xs font-medium text-emerald-600 uppercase tracking-wide">Ingresos</span>
            </div>
            <p class="text-2xl font-bold text-emerald-700">{{ formatCurrency(todayTotalRevenue) }}</p>
          </div>
          <div class="bg-violet-50 rounded-xl p-4">
            <div class="flex items-center gap-2 mb-2">
              <BarChart2 class="w-4 h-4 text-violet-500" />
              <span class="text-xs font-medium text-violet-600 uppercase tracking-wide">Volumen m³</span>
            </div>
            <p class="text-2xl font-bold text-violet-700">
              {{ Number(todayData.total_volume).toLocaleString('es-CO') }}
            </p>
          </div>
          <div class="bg-red-50 rounded-xl p-4">
            <div class="flex items-center gap-2 mb-2">
              <Wallet class="w-4 h-4 text-red-400" />
              <span class="text-xs font-medium text-red-500 uppercase tracking-wide">Gastos</span>
            </div>
            <p class="text-2xl font-bold text-red-600">{{ formatCurrency(todayData.total_expenses) }}</p>
          </div>
        </div>

        <!-- Desglose por medio de pago -->
        <div v-if="todayPaymentDetails.length > 0" class="mb-6">
          <h3 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Desglose por medio de pago
          </h3>
          <div class="space-y-2">
            <div
              v-for="p in todayPaymentDetails"
              :key="p.payment_method"
              class="flex items-center justify-between px-4 py-2.5 bg-gray-50 rounded-lg"
            >
              <span class="text-sm text-gray-700">{{ p.payment_method_name }}</span>
              <span class="text-sm font-semibold text-gray-900">{{ formatCurrency(p.total) }}</span>
            </div>
            <div class="flex items-center justify-between px-4 py-2.5 bg-gray-100 rounded-lg border-t border-gray-200">
              <span class="text-sm font-semibold text-gray-700">Total ingresos</span>
              <span class="text-sm font-bold text-gray-900">{{ formatCurrency(todayTotalRevenue) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="mb-6 text-sm text-gray-400 italic">
          Sin viajes registrados hoy
        </div>

        <!-- Botón de cierre -->
        <div class="pt-4 border-t border-gray-100">
          <div v-if="alreadyClosed" class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2 text-sm text-green-700">
              <CheckCircle class="w-4 h-4" />
              El cierre de caja ya fue ejecutado para el día de hoy.
            </div>
            <button
              v-if="isSuperuser && todayClosureRecord"
              type="button"
              @click="openRevert(todayClosureRecord)"
              class="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-50 transition-colors"
            >
              <Unlock class="w-4 h-4" />
              Revertir cierre
            </button>
          </div>
          <div v-else>
            <button
              type="button"
              @click="confirmOpen = true"
              :disabled="todayData.total_trips === 0"
              class="flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white text-sm font-semibold rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <Lock class="w-4 h-4" />
              Ejecutar Cierre de Caja
            </button>
            <p v-if="todayData.total_trips === 0" class="mt-2 text-xs text-gray-400">
              No hay viajes activos para cerrar.
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Histórico de cierres ──────────────────────────────────────────── -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-100">
        <h2 class="text-sm font-semibold text-gray-800">Histórico de cierres</h2>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-100">
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Fecha</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Viajes</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Volumen m³</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Valor prom.</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Gastos</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Ingresos</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Detalle</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-if="historyLoading && history.length === 0">
              <td colspan="7" class="px-4 py-10 text-center text-xs text-gray-400">
                <RefreshCw class="w-4 h-4 animate-spin inline-block mr-2" />Cargando...
              </td>
            </tr>
            <tr v-else-if="history.length === 0">
              <td colspan="7" class="px-4 py-10 text-center text-xs text-gray-400">
                Sin cierres registrados
              </td>
            </tr>
            <tr
              v-for="s in history"
              :key="s.id"
              class="hover:bg-gray-50 transition-colors"
            >
              <td class="px-4 py-3 font-medium text-gray-900">{{ formatDate(s.date) }}</td>
              <td class="px-4 py-3 text-right text-gray-700">{{ s.total_trips }}</td>
              <td class="px-4 py-3 text-right text-gray-700">
                {{ Number(s.total_volume).toLocaleString('es-CO') }}
              </td>
              <td class="px-4 py-3 text-right text-gray-700">{{ formatCurrency(s.avg_trip_value) }}</td>
              <td class="px-4 py-3 text-right text-red-600 font-medium">{{ formatCurrency(s.total_expenses) }}</td>
              <td class="px-4 py-3 text-right font-bold text-gray-900">
                {{ formatCurrency(s.payment_details.reduce((sum, p) => sum + Number(p.total), 0)) }}
              </td>
              <td class="px-4 py-3">
                <div class="flex items-center gap-3">
                  <button
                    type="button"
                    @click="detailSummary = s"
                    class="text-xs text-gold-700 hover:text-gold-800 font-medium underline underline-offset-2"
                  >
                    Ver desglose
                  </button>
                  <button
                    v-if="isSuperuser && s.state === 'closed'"
                    type="button"
                    @click="openRevert(s)"
                    class="text-xs text-amber-700 hover:text-amber-800 font-medium underline underline-offset-2"
                  >
                    Revertir
                  </button>
                  <span v-else-if="s.state === 'reverted'" class="text-xs text-gray-400 italic">
                    Revertido
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Modal confirmación cierre ──────────────────────────────────────── -->
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
          v-if="confirmOpen"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
        >
          <div class="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div class="flex items-start gap-3 mb-4">
              <div class="p-2 bg-amber-100 rounded-lg shrink-0">
                <AlertTriangle class="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <h3 class="text-sm font-semibold text-gray-800">Confirmar Cierre de Caja</h3>
                <p class="text-xs text-gray-500 mt-0.5">Esta operación no puede revertirse</p>
              </div>
            </div>

            <div class="bg-gray-50 rounded-lg p-4 mb-5 space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-600">Viajes activos:</span>
                <span class="font-semibold text-gray-900">{{ todayData?.total_trips }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Total ingresos:</span>
                <span class="font-semibold text-gray-900">{{ formatCurrency(todayTotalRevenue) }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-600">Gastos del día:</span>
                <span class="font-semibold text-red-600">{{ formatCurrency(todayData?.total_expenses ?? 0) }}</span>
              </div>
            </div>

            <p class="text-sm text-gray-600 mb-5">
              Al confirmar se cerrará la caja del día de hoy. Todos los viajes activos
              quedarán vinculados a este cierre y no podrán modificarse.
            </p>

            <div class="flex gap-2 justify-end">
              <button
                type="button"
                @click="confirmOpen = false"
                :disabled="closingLoading"
                class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              >Cancelar</button>
              <button
                type="button"
                @click="executeClose"
                :disabled="closingLoading"
                class="px-5 py-2 bg-gray-900 text-white text-sm font-semibold rounded-lg hover:bg-gray-800 disabled:opacity-50 flex items-center gap-2"
              >
                <RefreshCw v-if="closingLoading" class="w-4 h-4 animate-spin" />
                <Lock v-else class="w-4 h-4" />
                {{ closingLoading ? 'Ejecutando cierre...' : 'Sí, ejecutar cierre' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ── Modal confirmación reversión ───────────────────────────────────── -->
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
          v-if="revertTarget"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
        >
          <div class="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div class="flex items-start gap-3 mb-4">
              <div class="p-2 bg-amber-100 rounded-lg shrink-0">
                <Unlock class="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <h3 class="text-sm font-semibold text-gray-800">
                  Revertir cierre — {{ formatDate(revertTarget.date) }}
                </h3>
                <p class="text-xs text-gray-500 mt-0.5">
                  Los viajes y gastos de ese día volverán a poder registrarse.
                </p>
              </div>
            </div>

            <label class="block text-xs font-medium text-gray-600 mb-1">
              Justificación (opcional)
            </label>
            <textarea
              v-model="revertJustification"
              rows="2"
              class="w-full mb-5 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-gold-400"
              placeholder="Motivo de la reversión..."
            />

            <div class="flex gap-2 justify-end">
              <button
                type="button"
                @click="revertTarget = null"
                :disabled="revertLoading"
                class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              >Cancelar</button>
              <button
                type="button"
                @click="confirmRevert"
                :disabled="revertLoading"
                class="px-5 py-2 bg-amber-600 text-white text-sm font-semibold rounded-lg hover:bg-amber-700 disabled:opacity-50 flex items-center gap-2"
              >
                <RefreshCw v-if="revertLoading" class="w-4 h-4 animate-spin" />
                <Unlock v-else class="w-4 h-4" />
                {{ revertLoading ? 'Revirtiendo...' : 'Sí, revertir cierre' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ── Drawer desglose histórico ─────────────────────────────────────── -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-150"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div v-if="detailSummary" class="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/30" @click="detailSummary = null" />
          <div class="relative bg-white w-full max-w-sm max-h-[85vh] rounded-xl shadow-2xl flex flex-col overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between shrink-0">
              <div>
                <h3 class="text-sm font-semibold text-gray-800">
                  Cierre — {{ formatDate(detailSummary.date) }}
                </h3>
                <p class="text-xs text-gray-500 mt-0.5">{{ detailSummary.total_trips }} viajes</p>
              </div>
              <button
                type="button"
                @click="detailSummary = null"
                class="text-gray-400 hover:text-gray-600 text-lg leading-none"
              >✕</button>
            </div>

            <div class="p-6 space-y-5 flex-1 overflow-y-auto">
              <!-- KPIs -->
              <div class="grid grid-cols-2 gap-3">
                <div class="bg-gray-50 rounded-lg p-3">
                  <p class="text-xs text-gray-500 mb-1">Volumen total</p>
                  <p class="text-base font-bold text-gray-900">
                    {{ Number(detailSummary.total_volume).toLocaleString('es-CO') }} m³
                  </p>
                </div>
                <div class="bg-gray-50 rounded-lg p-3">
                  <p class="text-xs text-gray-500 mb-1">Valor promedio</p>
                  <p class="text-base font-bold text-gray-900">
                    {{ formatCurrency(detailSummary.avg_trip_value) }}
                  </p>
                </div>
                <div class="bg-red-50 rounded-lg p-3">
                  <p class="text-xs text-red-500 mb-1">Gastos</p>
                  <p class="text-base font-bold text-red-700">
                    {{ formatCurrency(detailSummary.total_expenses) }}
                  </p>
                </div>
                <div class="bg-emerald-50 rounded-lg p-3">
                  <p class="text-xs text-emerald-600 mb-1">Total ingresos</p>
                  <p class="text-base font-bold text-emerald-700">
                    {{ formatCurrency(detailRevenue) }}
                  </p>
                </div>
              </div>

              <!-- Desglose por pago -->
              <div>
                <h4 class="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  Desglose por medio de pago
                </h4>
                <div class="space-y-2">
                  <div
                    v-for="p in detailSummary.payment_details"
                    :key="p.payment_method"
                    class="flex justify-between items-center px-3 py-2 bg-gray-50 rounded-lg text-sm"
                  >
                    <span class="text-gray-700">{{ p.payment_method_name }}</span>
                    <span class="font-semibold text-gray-900">{{ formatCurrency(p.total) }}</span>
                  </div>
                  <div
                    v-if="detailSummary.payment_details.length === 0"
                    class="text-xs text-gray-400 italic px-3 py-2"
                  >
                    Sin desglose disponible
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
