<script setup lang="ts">
import { ref, computed } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import {
  Truck, TrendingUp, Wallet, AlertTriangle, RefreshCw, FileWarning,
} from 'lucide-vue-next'

import PageHeader from '@/components/shared/PageHeader.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'

import { tripsApi } from '@/api/trips.api'
import { expensesApi } from '@/api/expenses.api'
import { advancesApi } from '@/api/advances.api'
import { invoicesApi } from '@/api/invoices.api'
import { auditApi } from '@/api/audit.api'
import { useAuthStore } from '@/stores/auth.store'
import { ROLE_LABELS, ROLE_COLORS } from '@/constants/roles'
import { navigation, type NavLeaf } from '@/constants/navigation'
import { ACTION_CONFIG, MODEL_LABEL } from '@/constants/audit'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, formatTime, todayBogota } from '@/utils/formatDate'
import { getApiErrorMessage } from '@/utils/handleApiError'
import type { Trip, Advance } from '@/types'

// "NO FACTURA" en vez de "No requiere factura" — Invoice.number tiene max_length=15
// en el backend y el texto original (19 caracteres) excede el límite. Ver Parte 9.
const NO_INVOICE_LABEL = 'NO FACTURA'

const authStore = useAuthStore()
const queryClient = useQueryClient()
const role = computed(() => authStore.user?.role)

const today = todayBogota()

// ── Visibilidad de secciones por rol (display logic — el enforcement real vive en el router/backend) ──
const showDailySummary = computed(() => ['cashier', 'commercial_admin', 'superuser'].includes(role.value ?? ''))
const showLowBalanceAdvances = computed(() => ['commercial_admin', 'superuser'].includes(role.value ?? ''))
const showFinishedAdvances = computed(() => ['accountant', 'superuser'].includes(role.value ?? ''))
const showUnfacturedTrips = computed(() => ['accountant', 'superuser'].includes(role.value ?? ''))
const canValidate = computed(() => ['accountant', 'superuser'].includes(role.value ?? ''))

const dailySummaryLinkTarget = '/trips'

// ── Resumen del día (cashier, commercial_admin, superuser) ────────────────────
const {
  data: tripsTodayData, isLoading: tripsTodayLoading, isError: tripsTodayIsError,
  error: tripsTodayErrorObj, refetch: refetchTripsToday,
} = useQuery({
  queryKey: ['dashboard', 'trips-today'],
  queryFn: () => tripsApi.list({ date: today, state: true }).then(r => r.data),
  enabled: showDailySummary,
  refetchInterval: 60_000,
})

const {
  data: expensesTodayData, isLoading: expensesTodayLoading, isError: expensesTodayIsError,
  error: expensesTodayErrorObj, refetch: refetchExpensesToday,
} = useQuery({
  queryKey: ['dashboard', 'expenses-today'],
  queryFn: () => expensesApi.list({ date: today }).then(r => r.data),
  enabled: showDailySummary,
  refetchInterval: 60_000,
})

const dailySummaryLoading = computed(() => tripsTodayLoading.value || expensesTodayLoading.value)
const dailySummaryError = computed(() => tripsTodayIsError.value || expensesTodayIsError.value)
function retryDailySummary() {
  refetchTripsToday()
  refetchExpensesToday()
}

const tripsToday = computed(() => tripsTodayData.value ?? [])
const expensesToday = computed(() => expensesTodayData.value ?? [])
const totalTripsToday = computed(() => tripsToday.value.length)
const totalRecaudado = computed(() => tripsToday.value.reduce((s, t) => s + Number(t.value), 0))
const totalGastos = computed(() => expensesToday.value.reduce((s, e) => s + Number(e.value), 0))
const saldoNeto = computed(() => totalRecaudado.value - totalGastos.value)

const paymentBreakdown = computed(() => {
  const map = new Map<string, { name: string; count: number; total: number }>()
  for (const t of tripsToday.value) {
    const name = t.payment_detail?.name ?? '—'
    const entry = map.get(name) ?? { name, count: 0, total: 0 }
    entry.count += 1
    entry.total += Number(t.value)
    map.set(name, entry)
  }
  return [...map.values()]
})

const lastTrips = computed(() =>
  [...tripsToday.value].sort((a, b) => b.voucher_num - a.voucher_num).slice(0, 5),
)

// ── Anticipos (commercial_admin: bajo saldo — accountant: finalizados — superuser: ambos) ──
const {
  data: advancesData, isLoading: advancesLoading, isError: advancesIsError,
  error: advancesErrorObj, refetch: refetchAdvances,
} = useQuery({
  queryKey: ['dashboard', 'advances'],
  queryFn: () => advancesApi.list().then(r => r.data),
  enabled: computed(() => showLowBalanceAdvances.value || showFinishedAdvances.value),
  refetchInterval: 60_000,
})

const advances = computed(() => advancesData.value ?? [])

const lowBalanceAdvances = computed(() => advances.value
  .filter(a => a.available_balance > 0 && a.available_balance < Number(a.value) * 0.30)
  .sort((a, b) => a.available_balance - b.available_balance)
  .slice(0, 15)
  .map(a => ({
    advance: a,
    percent: Number(a.value) > 0 ? (a.available_balance / Number(a.value)) * 100 : 0,
  })),
)

function lastMovementDate(a: Advance): string {
  if (a.movements.length === 0) return a.date
  return a.movements.reduce((latest, m) => (m.date > latest ? m.date : latest), a.movements[0].date)
}

const finishedAdvances = computed(() => advances.value
  .filter(a => a.available_balance === 0)
  .map(a => ({ advance: a, lastMovement: lastMovementDate(a) }))
  .sort((a, b) => b.lastMovement.localeCompare(a.lastMovement))
  .slice(0, 15),
)

// ── Viajes sin facturar (accountant, superuser) ───────────────────────────────
const {
  data: tripsUnfacturedData, isLoading: tripsUnfacturedLoading, isError: tripsUnfacturedIsError,
  error: tripsUnfacturedErrorObj, refetch: refetchTripsUnfactured,
} = useQuery({
  queryKey: ['dashboard', 'trips-unfactured'],
  queryFn: () => tripsApi.list({ state: true }).then(r => r.data),
  enabled: showUnfacturedTrips,
  refetchInterval: 60_000,
})

const tripsUnfactured = computed(() => (tripsUnfacturedData.value ?? [])
  .filter(t => t.invoice === null && t.payment_detail?.is_advance === false)
  .sort((a, b) => b.date.localeCompare(a.date))
  .slice(0, 15),
)

// ── AUDITOR: accesos rápidos (derivados de navigation.ts, no hardcodeados) ────
const auditorQuickLinks = computed<NavLeaf[]>(() => {
  const leaves: NavLeaf[] = []
  for (const item of navigation) {
    if (item.type === 'leaf') {
      if (item.path !== '/' && item.enabled !== false && item.roles.includes('auditor')) leaves.push(item)
    } else {
      for (const child of item.children) {
        if (child.enabled !== false && child.roles.includes('auditor')) leaves.push(child)
      }
    }
  }
  return leaves
})

// ── AUDITOR: actividad reciente del log de auditoría ──────────────────────────
const {
  data: recentAuditData, isLoading: recentAuditLoading, isError: recentAuditIsError,
  refetch: refetchRecentAudit,
} = useQuery({
  queryKey: ['dashboard', 'audit-recent'],
  queryFn: () => auditApi.list().then(r => r.data),
  enabled: computed(() => role.value === 'auditor'),
  refetchInterval: 60_000,
})
const recentAudit = computed(() => (recentAuditData.value ?? []).slice(0, 8))

// ── "Validar" — marcar viaje como que no requiere factura ─────────────────────
const noFacturaInvoiceId = ref<number | null>(null)
const confirmTrip = ref<Trip | null>(null)
const validating = ref(false)

async function getOrCreateNoFacturaId(): Promise<number> {
  if (noFacturaInvoiceId.value !== null) return noFacturaInvoiceId.value
  const res = await invoicesApi.list()
  const found = res.data.find(i => i.number === NO_INVOICE_LABEL)
  if (found) {
    noFacturaInvoiceId.value = found.id
    return found.id
  }
  const created = await invoicesApi.create({ number: NO_INVOICE_LABEL })
  noFacturaInvoiceId.value = created.data.id
  return created.data.id
}

async function confirmValidate() {
  if (!confirmTrip.value) return
  validating.value = true
  try {
    const invoiceId = await getOrCreateNoFacturaId()
    await tripsApi.patch(confirmTrip.value.id, { invoice: invoiceId })
    toast.success('Viaje marcado como no requiere factura.')
    queryClient.invalidateQueries({ queryKey: ['dashboard', 'trips-unfactured'] })
    queryClient.invalidateQueries({ queryKey: ['trips'] })
    confirmTrip.value = null
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  } finally {
    validating.value = false
  }
}
</script>

<template>
  <!-- ── AUDITOR: bienvenida + accesos rápidos + actividad reciente ──────────── -->
  <div v-if="role === 'auditor'" class="space-y-6">
    <!-- Banner de bienvenida -->
    <div class="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 flex flex-col sm:flex-row items-center gap-6">
      <img src="/logo_amarillo.jpeg" alt="Ingeominería" class="w-40 rounded-xl shadow-sm shrink-0" />
      <div class="text-center sm:text-left">
        <h1 class="text-2xl font-bold text-gray-900">SIGMO</h1>
        <p class="text-gray-500 text-sm">Sistema Integral de Gestión Minera y Operativa</p>
        <p class="text-gray-900 mt-3">Bienvenido, {{ authStore.user?.name }}</p>
        <span
          class="inline-block mt-2 text-xs font-medium px-3 py-1 rounded-full"
          :class="ROLE_COLORS[authStore.user?.role ?? ''] ?? 'bg-gray-100 text-gray-800'"
        >
          {{ ROLE_LABELS[authStore.user?.role ?? ''] ?? authStore.user?.role }}
        </span>
      </div>
    </div>

    <!-- Accesos rápidos de consulta -->
    <section class="space-y-3">
      <h2 class="text-sm font-semibold text-gray-800">Accesos rápidos de consulta</h2>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        <router-link
          v-for="link in auditorQuickLinks"
          :key="link.path"
          :to="link.path"
          class="flex items-center gap-3 bg-white rounded-xl border border-gray-200 shadow-sm p-4 hover:border-gold-300 hover:shadow-md transition-all"
        >
          <div class="w-9 h-9 rounded-lg bg-gold-50 flex items-center justify-center shrink-0">
            <component :is="link.icon" class="w-4 h-4 text-gold-700" />
          </div>
          <span class="text-sm font-medium text-gray-800">{{ link.label }}</span>
        </router-link>
      </div>
    </section>

    <!-- Actividad reciente del sistema -->
    <section class="space-y-3">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-800">Actividad reciente del sistema</h2>
        <router-link to="/admin/audit-log" class="text-xs text-gold-700 hover:text-gold-800 font-medium">
          Ver log completo
        </router-link>
      </div>

      <div v-if="recentAuditIsError" class="flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
        <div class="flex items-center gap-2 text-amber-700 text-sm">
          <AlertTriangle class="w-4 h-4 shrink-0" />
          Error al cargar esta sección. Intenta de nuevo.
        </div>
        <button type="button" @click="refetchRecentAudit()" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-100">
          <RefreshCw class="w-3.5 h-3.5" /> Reintentar
        </button>
      </div>
      <div v-else class="bg-white rounded-xl border border-gray-200 shadow-sm divide-y divide-gray-50">
        <div v-if="recentAuditLoading" class="p-4 space-y-3">
          <div v-for="i in 5" :key="i" class="h-4 bg-gray-100 rounded animate-pulse" />
        </div>
        <div v-else-if="recentAudit.length === 0" class="p-6 text-center text-sm text-gray-400">
          Sin actividad registrada.
        </div>
        <div v-else v-for="entry in recentAudit" :key="entry.id" class="flex items-center justify-between gap-3 px-4 py-3">
          <div class="flex items-center gap-3">
            <span
              class="text-xs font-medium px-2 py-1 rounded-full whitespace-nowrap"
              :class="ACTION_CONFIG[entry.action]?.cls ?? 'bg-gray-100 text-gray-600'"
            >
              {{ ACTION_CONFIG[entry.action]?.label ?? entry.action_display }}
            </span>
            <span class="text-sm text-gray-800">{{ MODEL_LABEL[entry.model_name] ?? entry.model_name }}</span>
          </div>
          <div class="text-xs text-gray-400 text-right shrink-0">
            <p>{{ entry.user_name }}</p>
            <p>{{ formatDate(entry.timestamp) }} {{ formatTime(entry.timestamp) }}</p>
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- ── OTROS ROLES: dashboard operativo ─────────────────────────────────────── -->
  <div v-else class="space-y-6">
    <PageHeader title="Dashboard" description="Resumen operativo según tu rol" />

    <!-- ── Resumen del día ─────────────────────────────────────────────────── -->
    <section v-if="showDailySummary" class="space-y-4">
      <h2 class="text-sm font-semibold text-gray-800">Resumen del día — {{ formatDate(today) }}</h2>

      <div v-if="dailySummaryError" class="flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
        <div class="flex items-center gap-2 text-amber-700 text-sm">
          <AlertTriangle class="w-4 h-4 shrink-0" />
          Error al cargar esta sección. Intenta de nuevo.
        </div>
        <button type="button" @click="retryDailySummary" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-100">
          <RefreshCw class="w-3.5 h-3.5" /> Reintentar
        </button>
      </div>

      <template v-else>
        <div v-if="dailySummaryLoading" class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div v-for="i in 4" :key="i" class="h-24 bg-gray-100 rounded-xl animate-pulse" />
        </div>
        <template v-else>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-gold-50 rounded-xl p-4">
              <div class="flex items-center gap-2 mb-2">
                <Truck class="w-4 h-4 text-gold-600" />
                <span class="text-xs font-medium text-gold-700 uppercase tracking-wide">Total Viajes hoy</span>
              </div>
              <p class="text-2xl font-bold text-gold-800">{{ totalTripsToday }}</p>
            </div>
            <div class="bg-emerald-50 rounded-xl p-4">
              <div class="flex items-center gap-2 mb-2">
                <TrendingUp class="w-4 h-4 text-emerald-500" />
                <span class="text-xs font-medium text-emerald-600 uppercase tracking-wide">Total Recaudado hoy</span>
              </div>
              <p class="text-2xl font-bold text-emerald-700">{{ formatCurrency(totalRecaudado) }}</p>
            </div>
            <div class="bg-red-50 rounded-xl p-4">
              <div class="flex items-center gap-2 mb-2">
                <Wallet class="w-4 h-4 text-red-400" />
                <span class="text-xs font-medium text-red-500 uppercase tracking-wide">Total Gastos hoy</span>
              </div>
              <p class="text-2xl font-bold text-red-600">{{ formatCurrency(totalGastos) }}</p>
            </div>
            <div :class="saldoNeto >= 0 ? 'bg-gold-50' : 'bg-red-50'" class="rounded-xl p-4">
              <span :class="saldoNeto >= 0 ? 'text-gold-700' : 'text-red-500'" class="text-xs font-medium uppercase tracking-wide">Saldo Neto</span>
              <p :class="saldoNeto >= 0 ? 'text-gold-800' : 'text-red-600'" class="text-2xl font-bold mt-1">{{ formatCurrency(saldoNeto) }}</p>
            </div>
          </div>

          <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-100">
              <h3 class="text-sm font-semibold text-gray-800">Desglose por medio de pago</h3>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-gray-50 border-b border-gray-100">
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Medio de Pago</th>
                    <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Viajes</th>
                    <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Total (COP)</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50">
                  <tr v-if="paymentBreakdown.length === 0">
                    <td colspan="3" class="px-4 py-6 text-center text-xs text-gray-400">Sin viajes registrados hoy</td>
                  </tr>
                  <tr v-for="p in paymentBreakdown" :key="p.name" class="hover:bg-gray-50">
                    <td class="px-4 py-3 text-gray-700">{{ p.name }}</td>
                    <td class="px-4 py-3 text-right text-gray-700">{{ p.count }}</td>
                    <td class="px-4 py-3 text-right font-semibold text-gray-900">{{ formatCurrency(p.total) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
              <h3 class="text-sm font-semibold text-gray-800">Últimos viajes registrados hoy</h3>
              <router-link :to="dailySummaryLinkTarget" class="text-xs text-gold-700 hover:text-gold-800 font-medium">
                Ver todos los viajes de hoy
              </router-link>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-gray-50 border-b border-gray-100">
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Vale</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Fecha</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cliente</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Placa</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Tipo Vehículo</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Medio de Pago</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50">
                  <tr v-if="lastTrips.length === 0">
                    <td colspan="6" class="px-4 py-6 text-center text-xs text-gray-400">Sin viajes registrados hoy</td>
                  </tr>
                  <tr v-for="t in lastTrips" :key="t.id" class="hover:bg-gray-50">
                    <td class="px-4 py-3 font-mono font-bold text-gold-800">#{{ t.voucher_num }}</td>
                    <td class="px-4 py-3 text-gray-600 text-xs">{{ formatDate(t.date_register) }}</td>
                    <td class="px-4 py-3 text-gray-900">{{ t.client_detail?.name ?? '—' }}</td>
                    <td class="px-4 py-3 font-mono text-gray-700">{{ t.vehicle_detail?.plaque ?? '—' }}</td>
                    <td class="px-4 py-3 text-gray-700">{{ t.vehicle_detail?.vehicle_type_detail?.name ?? '—' }}</td>
                    <td class="px-4 py-3 text-gray-700">{{ t.payment_detail?.name ?? '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </template>
    </section>

    <!-- ── Anticipos próximos a agotarse ───────────────────────────────────── -->
    <section v-if="showLowBalanceAdvances" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-800">Anticipos próximos a agotarse</h2>
        <router-link to="/advances" class="text-xs text-gold-700 hover:text-gold-800 font-medium">Ver todos</router-link>
      </div>

      <div v-if="advancesIsError" class="flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
        <div class="flex items-center gap-2 text-amber-700 text-sm">
          <AlertTriangle class="w-4 h-4 shrink-0" />
          Error al cargar esta sección. Intenta de nuevo.
        </div>
        <button type="button" @click="refetchAdvances()" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-100">
          <RefreshCw class="w-3.5 h-3.5" /> Reintentar
        </button>
      </div>
      <div v-else-if="advancesLoading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="i in 3" :key="i" class="h-32 bg-gray-100 rounded-xl animate-pulse" />
      </div>
      <div v-else-if="lowBalanceAdvances.length === 0" class="bg-white rounded-xl border border-gray-200 shadow-sm p-6 text-center text-sm text-gray-400">
        Sin anticipos próximos a agotarse.
      </div>
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div v-for="{ advance: a, percent } in lowBalanceAdvances" :key="a.id" class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 space-y-3">
          <p class="font-bold text-gray-900">{{ a.client_detail?.name ?? '—' }}</p>
          <div>
            <p class="text-xs text-gray-500">Saldo disponible</p>
            <p :class="percent < 15 ? 'text-red-600' : 'text-amber-600'" class="text-lg font-bold">{{ formatCurrency(a.available_balance) }}</p>
          </div>
          <div>
            <div class="flex items-center justify-between text-xs text-gray-500 mb-1">
              <span>Porcentaje restante</span>
              <span class="font-semibold">{{ percent.toFixed(0) }}%</span>
            </div>
            <div class="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full"
                :class="percent < 15 ? 'bg-red-500' : 'bg-amber-500'"
                :style="{ width: `${Math.min(percent, 100)}%` }"
              />
            </div>
          </div>
          <p class="text-xs text-gray-500">Valor original del anticipo: <span class="font-semibold text-gray-700">{{ formatCurrency(a.value) }}</span></p>
          <router-link
            to="/advances"
            class="block w-full text-center px-3 py-2 text-xs font-medium text-gold-800 border border-gold-200 rounded-lg hover:bg-gold-50 transition-colors"
          >
            Ver detalle
          </router-link>
        </div>
      </div>
    </section>

    <!-- ── Anticipos finalizados recientemente ─────────────────────────────── -->
    <section v-if="showFinishedAdvances" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-800">Anticipos finalizados recientemente</h2>
        <router-link to="/advances" class="text-xs text-gold-700 hover:text-gold-800 font-medium">Ver todos</router-link>
      </div>

      <div v-if="advancesIsError" class="flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
        <div class="flex items-center gap-2 text-amber-700 text-sm">
          <AlertTriangle class="w-4 h-4 shrink-0" />
          Error al cargar esta sección. Intenta de nuevo.
        </div>
        <button type="button" @click="refetchAdvances()" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-100">
          <RefreshCw class="w-3.5 h-3.5" /> Reintentar
        </button>
      </div>
      <div v-else class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-gray-50 border-b border-gray-100">
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cliente</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Valor original (COP)</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Fecha último movimiento</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Anticipo</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <template v-if="advancesLoading">
                <tr v-for="i in 3" :key="i"><td colspan="4" class="px-4 py-3"><div class="h-4 bg-gray-100 rounded animate-pulse" /></td></tr>
              </template>
              <tr v-else-if="finishedAdvances.length === 0">
                <td colspan="4" class="px-4 py-6 text-center text-xs text-gray-400">Sin anticipos finalizados recientemente.</td>
              </tr>
              <tr v-for="{ advance: a, lastMovement } in finishedAdvances" :key="a.id" class="hover:bg-gray-50">
                <td class="px-4 py-3 font-medium text-gray-900">{{ a.client_detail?.name ?? '—' }}</td>
                <td class="px-4 py-3 text-right text-gray-700">{{ formatCurrency(a.value) }}</td>
                <td class="px-4 py-3 text-gray-600 text-xs">{{ formatDate(lastMovement) }}</td>
                <td class="px-4 py-3 text-gray-600">#{{ a.id }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- ── Viajes sin facturar ──────────────────────────────────────────────── -->
    <section v-if="showUnfacturedTrips" class="space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-800">Viajes sin facturar (efectivo y transferencia)</h2>
        <router-link to="/invoicing" class="text-xs text-gold-700 hover:text-gold-800 font-medium">Ver todos</router-link>
      </div>

      <div v-if="tripsUnfacturedIsError" class="flex items-center justify-between gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
        <div class="flex items-center gap-2 text-amber-700 text-sm">
          <AlertTriangle class="w-4 h-4 shrink-0" />
          Error al cargar esta sección. Intenta de nuevo.
        </div>
        <button type="button" @click="refetchTripsUnfactured()" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-700 border border-amber-300 rounded-lg hover:bg-amber-100">
          <RefreshCw class="w-3.5 h-3.5" /> Reintentar
        </button>
      </div>
      <div v-else class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-gray-50 border-b border-gray-100">
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Vale</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Fecha</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cliente</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Placa</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Medio de Pago</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Valor (COP)</th>
                <th v-if="canValidate" class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Acción</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <template v-if="tripsUnfacturedLoading">
                <tr v-for="i in 3" :key="i"><td :colspan="canValidate ? 7 : 6" class="px-4 py-3"><div class="h-4 bg-gray-100 rounded animate-pulse" /></td></tr>
              </template>
              <tr v-else-if="tripsUnfactured.length === 0">
                <td :colspan="canValidate ? 7 : 6" class="px-4 py-8 text-center text-xs text-gray-400">
                  <FileWarning class="w-5 h-5 mx-auto mb-1.5 text-gray-300" />
                  No hay viajes pendientes de facturar.
                </td>
              </tr>
              <tr v-for="t in tripsUnfactured" :key="t.id" class="hover:bg-gray-50">
                <td class="px-4 py-3 font-mono font-bold text-gold-800">#{{ t.voucher_num }}</td>
                <td class="px-4 py-3 text-gray-600 text-xs">{{ formatDate(t.date) }}</td>
                <td class="px-4 py-3 text-gray-900">{{ t.client_detail?.name ?? '—' }}</td>
                <td class="px-4 py-3 font-mono text-gray-700">{{ t.vehicle_detail?.plaque ?? '—' }}</td>
                <td class="px-4 py-3 text-gray-700">{{ t.payment_detail?.name ?? '—' }}</td>
                <td class="px-4 py-3 text-right font-semibold text-gray-900">{{ formatCurrency(t.value) }}</td>
                <td v-if="canValidate" class="px-4 py-3">
                  <button
                    type="button"
                    @click="confirmTrip = t"
                    class="px-3 py-1.5 text-xs font-medium text-gold-800 border border-gold-200 rounded-lg hover:bg-gold-50 transition-colors"
                  >
                    Validar
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <ConfirmDialog
      :open="!!confirmTrip"
      title="Confirmar que no requiere factura"
      :description="confirmTrip ? `¿Confirmar que el viaje #${confirmTrip.voucher_num} del cliente ${confirmTrip.client_detail?.name ?? '—'} no requiere factura?` : ''"
      confirm-label="Confirmar"
      :loading="validating"
      @confirm="confirmValidate"
      @cancel="confirmTrip = null"
    />
  </div>
</template>
