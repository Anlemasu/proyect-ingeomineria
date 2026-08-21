<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import type { ColumnDef } from '@tanstack/vue-table'
import {
  RefreshCw, FileSpreadsheet, Printer, CalendarX2,
} from 'lucide-vue-next'

import PageHeader from '@/components/shared/PageHeader.vue'
import DataTable from '@/components/shared/DataTable.vue'

import { tripsApi } from '@/api/trips.api'
import { expensesApi } from '@/api/expenses.api'
import { usePermissions } from '@/composables/usePermissions'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, formatTime, todayBogota } from '@/utils/formatDate'
import { getApiErrorMessage, toastApiError } from '@/utils/handleApiError'
import { printDailyReport } from '@/utils/printDailyReport'
import { exportDailyReportExcel } from '@/utils/exportDailyReportExcel'
import type { Trip, DailyReportData } from '@/types'

const { hasRole } = usePermissions()
const canSeeValue = computed(() => !hasRole('cashier'))
const canSeeAdvances = computed(() => !hasRole('cashier'))

// ── Fecha del reporte ──────────────────────────────────────────────────────
const today = todayBogota()
const selectedDate = ref(today)
const reportDate = ref(today)

function generateReport() {
  reportDate.value = selectedDate.value
}

// ── Datos en paralelo ──────────────────────────────────────────────────────
const { data: tripsData, isLoading: tripsLoading, refetch: refetchTrips } = useQuery({
  queryKey: computed(() => ['reports-daily', 'trips', reportDate.value]),
  queryFn: () => tripsApi.list({ date: reportDate.value }).then(r => r.data),
})

const { data: expensesData, isLoading: expensesLoading, refetch: refetchExpenses } = useQuery({
  queryKey: computed(() => ['reports-daily', 'expenses', reportDate.value]),
  queryFn: () => expensesApi.list({ date: reportDate.value }).then(r => r.data),
})

const isLoading = computed(() => tripsLoading.value || expensesLoading.value)
const hasLoadedOnce = computed(() => tripsData.value !== undefined && expensesData.value !== undefined)

function refreshAll() {
  refetchTrips()
  refetchExpenses()
}

// ── Datos derivados ────────────────────────────────────────────────────────
const trips = computed(() => tripsData.value ?? [])
const expenses = computed(() => expensesData.value ?? [])
const activeTrips = computed(() => trips.value.filter(t => t.state))
// Anticipos consumidos: derivados de los viajes del día con anticipo asociado (ver análisis Parte 7)
const advancesConsumed = computed(() => trips.value.filter(t => t.advance !== null))

const totalCollected = computed(() => activeTrips.value.reduce((sum, t) => sum + Number(t.value), 0))
const totalExpenses = computed(() => expenses.value.reduce((sum, e) => sum + Number(e.value), 0))
const netBalance = computed(() => totalCollected.value - totalExpenses.value)
const totalAdvancesConsumed = computed(() => advancesConsumed.value.reduce((sum, t) => sum + Number(t.value), 0))

const byPaymentMethod = computed(() => {
  const groups = new Map<string, { name: string; tripCount: number; total: number }>()
  for (const t of activeTrips.value) {
    const name = t.payment_detail?.name ?? '—'
    const entry = groups.get(name) ?? { name, tripCount: 0, total: 0 }
    entry.tripCount += 1
    entry.total += Number(t.value)
    groups.set(name, entry)
  }
  return Array.from(groups.values())
})

const isEmptyDay = computed(() =>
  hasLoadedOnce.value && trips.value.length === 0 && expenses.value.length === 0 && advancesConsumed.value.length === 0,
)

const reportData = computed<DailyReportData>(() => ({
  date: reportDate.value,
  trips: trips.value,
  expenses: expenses.value,
  advancesConsumed: advancesConsumed.value,
  summary: {
    totalTrips: activeTrips.value.length,
    totalCollected: totalCollected.value,
    totalExpenses: totalExpenses.value,
    netBalance: netBalance.value,
    byPaymentMethod: byPaymentMethod.value,
  },
}))

// ── Exportación ────────────────────────────────────────────────────────────
function handleExportExcel() {
  try {
    exportDailyReportExcel(reportDate.value, reportData.value)
  } catch (err) {
    toastApiError(err)
  }
}

function handleExportPdf() {
  printDailyReport(reportDate.value, reportData.value)
}

// ── Columnas tabla de viajes ───────────────────────────────────────────────
const tripColumns = computed<ColumnDef<Trip>[]>(() => {
  const cols: ColumnDef<Trip>[] = [
    { id: 'voucher_num', header: 'N° Vale', cell: ({ row }) => h('span', { class: 'font-mono font-bold text-gold-800' }, `#${row.original.voucher_num}`) },
    { id: 'date_register', header: 'Hora registro', cell: ({ row }) => formatTime(row.original.date_register) },
    { id: 'client', header: 'Cliente', cell: ({ row }) => row.original.client_detail?.name ?? '—' },
    { id: 'plaque', header: 'Placa', cell: ({ row }) => row.original.vehicle_detail?.plaque ?? '—' },
    { id: 'pin', header: 'PIN Ambiental', cell: ({ row }) => row.original.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0' },
    { id: 'origin', header: 'Origen', cell: ({ row }) => row.original.origin_site_detail?.name ?? '—' },
    { id: 'material', header: 'Tipo Material', cell: ({ row }) => row.original.material_type_detail?.name ?? '—' },
    { id: 'vehicle_type', header: 'Tipo Vehículo', cell: ({ row }) => row.original.vehicle_detail?.vehicle_type_detail?.name ?? '—' },
  ]

  if (canSeeValue.value) {
    cols.push({
      id: 'value',
      header: 'Valor',
      cell: ({ row }) => h('span', { class: 'font-semibold text-gray-900' }, formatCurrency(row.original.value)),
    })
  }

  cols.push(
    { id: 'payment', header: 'Medio de Pago', cell: ({ row }) => row.original.payment_detail?.name ?? '—' },
    { id: 'extern_voucher', header: 'N° Vale Externo', cell: ({ row }) => row.original.extern_voucher_num ?? '—' },
    { id: 'invoice', header: 'N° Factura', cell: ({ row }) => row.original.invoice ?? '—' },
    {
      id: 'observations',
      header: 'Observaciones',
      size: 220,
      cell: ({ row }) => h('span', {
        class: 'block truncate',
        title: row.original.observations ?? undefined,
      }, row.original.observations ?? '—'),
    },
    {
      id: 'state',
      header: 'Estado',
      cell: ({ row }) => h('span', {
        class: [
          'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
          row.original.state ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800',
        ],
      }, row.original.state ? 'Activo' : 'Anulado'),
    },
  )

  return cols
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between flex-wrap gap-4">
      <PageHeader title="Reporte Diario de Operaciones" description="Vista consolidada de la operación de un día: viajes, gastos y anticipos consumidos" />

      <div v-if="hasLoadedOnce" class="flex items-center gap-2">
        <button
          type="button"
          @click="handleExportExcel"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <FileSpreadsheet class="w-4 h-4" /> Exportar Excel
        </button>
        <button
          type="button"
          @click="handleExportPdf"
          class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <Printer class="w-4 h-4" /> Exportar PDF
        </button>
      </div>
    </div>

    <!-- ── Selector de fecha ──────────────────────────────────────────────── -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-md shadow-stone-300/50 p-6 flex items-end gap-4 flex-wrap">
      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1.5">Fecha del reporte</label>
        <input
          v-model="selectedDate"
          type="date"
          class="px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
        />
      </div>
      <button
        type="button"
        @click="generateReport"
        class="flex items-center gap-2 px-5 py-2.5 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 disabled:opacity-50 transition-colors shadow-sm"
        :disabled="isLoading"
      >
        <RefreshCw class="w-4 h-4" :class="isLoading ? 'animate-spin' : ''" />
        {{ isLoading ? 'Generando...' : 'Generar Reporte' }}
      </button>
      <button
        type="button"
        @click="refreshAll"
        class="p-2.5 rounded-lg text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
        title="Actualizar"
      >
        <RefreshCw class="w-4 h-4" :class="isLoading ? 'animate-spin text-gold-600' : ''" />
      </button>
    </div>

    <!-- ── Día vacío ──────────────────────────────────────────────────────── -->
    <div v-if="isEmptyDay" class="bg-white rounded-xl border border-gray-200 shadow-md shadow-stone-300/50 py-16 flex flex-col items-center justify-center text-center">
      <CalendarX2 class="w-12 h-12 text-gray-300 mb-3" />
      <p class="text-sm font-medium text-gray-500">Sin actividad registrada para el {{ formatDate(reportDate) }}</p>
    </div>

    <template v-else>
      <!-- ── Tarjetas resumen ─────────────────────────────────────────────── -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="bg-gold-50 rounded-xl p-4">
          <span class="text-xs font-medium text-gold-700 uppercase tracking-wide">Total Viajes</span>
          <p class="text-2xl font-bold text-gold-800 mt-1">{{ hasLoadedOnce ? reportData.summary.totalTrips : '—' }}</p>
        </div>
        <div class="bg-emerald-50 rounded-xl p-4">
          <span class="text-xs font-medium text-emerald-600 uppercase tracking-wide">Total Recaudado</span>
          <p class="text-2xl font-bold text-emerald-700 mt-1">{{ formatCurrency(reportData.summary.totalCollected) }}</p>
        </div>
        <div class="bg-red-50 rounded-xl p-4">
          <span class="text-xs font-medium text-red-500 uppercase tracking-wide">Total Gastos</span>
          <p class="text-2xl font-bold text-red-600 mt-1">{{ formatCurrency(reportData.summary.totalExpenses) }}</p>
        </div>
        <div :class="reportData.summary.netBalance >= 0 ? 'bg-gold-50' : 'bg-red-50'" class="rounded-xl p-4">
          <span :class="reportData.summary.netBalance >= 0 ? 'text-gold-700' : 'text-red-500'" class="text-xs font-medium uppercase tracking-wide">Saldo Neto</span>
          <p :class="reportData.summary.netBalance >= 0 ? 'text-gold-800' : 'text-red-600'" class="text-2xl font-bold mt-1">{{ formatCurrency(reportData.summary.netBalance) }}</p>
        </div>
      </div>

      <!-- ── Desglose por medio de pago ───────────────────────────────────── -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-md shadow-stone-300/50 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-100">
          <h2 class="text-sm font-semibold text-gray-800">Desglose por medio de pago</h2>
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
              <tr v-if="isLoading">
                <td colspan="3" class="px-4 py-4"><div class="h-4 bg-gray-200 rounded animate-pulse" /></td>
              </tr>
              <tr v-else-if="reportData.summary.byPaymentMethod.length === 0">
                <td colspan="3" class="px-4 py-6 text-center text-xs text-gray-400">Sin viajes registrados para esta fecha.</td>
              </tr>
              <tr v-for="p in reportData.summary.byPaymentMethod" :key="p.name" class="hover:bg-gray-50">
                <td class="px-4 py-3 text-gray-700">{{ p.name }}</td>
                <td class="px-4 py-3 text-right text-gray-700">{{ p.tripCount }}</td>
                <td class="px-4 py-3 text-right font-semibold text-gray-900">{{ formatCurrency(p.total) }}</td>
              </tr>
            </tbody>
            <tfoot v-if="reportData.summary.byPaymentMethod.length > 0">
              <tr class="bg-gray-50 border-t-2 border-gray-200">
                <td class="px-4 py-3 text-xs font-semibold text-gray-600">Total</td>
                <td class="px-4 py-3 text-right text-xs font-semibold text-gray-600">{{ reportData.summary.totalTrips }}</td>
                <td class="px-4 py-3 text-right text-sm font-bold text-gray-900">{{ formatCurrency(reportData.summary.totalCollected) }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <!-- ── Viajes del día ───────────────────────────────────────────────── -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-md shadow-stone-300/50 p-6">
        <div class="flex items-center gap-2 mb-4">
          <h2 class="text-sm font-semibold text-gray-800">Viajes del día</h2>
          <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs font-semibold">{{ trips.length }}</span>
        </div>
        <DataTable :columns="(tripColumns as any)" :data="(trips as any)" :is-loading="isLoading" />
      </div>

      <!-- ── Gastos del día ───────────────────────────────────────────────── -->
      <div class="bg-white rounded-xl border border-gray-200 shadow-md shadow-stone-300/50 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
          <h2 class="text-sm font-semibold text-gray-800">Gastos del día</h2>
          <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs font-semibold">{{ expenses.length }}</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-gray-50 border-b border-gray-100">
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Fecha</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Descripción</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Valor</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Usuario</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <template v-if="isLoading">
                <tr v-for="i in 3" :key="i">
                  <td colspan="4" class="px-4 py-3"><div class="h-4 bg-gray-200 rounded animate-pulse" /></td>
                </tr>
              </template>
              <tr v-else-if="expenses.length === 0">
                <td colspan="4" class="px-4 py-10 text-center text-xs text-gray-400">No se registraron gastos para esta fecha.</td>
              </tr>
              <tr v-for="e in expenses" :key="e.id" class="hover:bg-gray-50">
                <td class="px-4 py-3 text-gray-600 text-xs">{{ formatDate(e.date) }}</td>
                <td class="px-4 py-3 text-gray-900 max-w-xs truncate">{{ e.description }}</td>
                <td class="px-4 py-3 text-right font-medium text-gray-900">{{ formatCurrency(e.value) }}</td>
                <td class="px-4 py-3 text-gray-500 text-xs">#{{ e.user }}</td>
              </tr>
            </tbody>
            <tfoot v-if="expenses.length > 0">
              <tr class="bg-gray-50 border-t-2 border-gray-200">
                <td colspan="2" class="px-4 py-3 text-xs font-semibold text-gray-600">Total</td>
                <td class="px-4 py-3 text-right text-sm font-bold text-red-600">{{ formatCurrency(totalExpenses) }}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      <!-- ── Anticipos consumidos ─────────────────────────────────────────── -->
      <div v-if="canSeeAdvances" class="bg-white rounded-xl border border-gray-200 shadow-md shadow-stone-300/50 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
          <h2 class="text-sm font-semibold text-gray-800">Anticipos consumidos</h2>
          <span class="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs font-semibold">{{ advancesConsumed.length }}</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="bg-gray-50 border-b border-gray-100">
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cliente</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Anticipo ID</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Valor Descontado</th>
                <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Viaje asociado</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <template v-if="isLoading">
                <tr v-for="i in 3" :key="i">
                  <td colspan="4" class="px-4 py-3"><div class="h-4 bg-gray-200 rounded animate-pulse" /></td>
                </tr>
              </template>
              <tr v-else-if="advancesConsumed.length === 0">
                <td colspan="4" class="px-4 py-10 text-center text-xs text-gray-400">No se consumieron anticipos en esta fecha.</td>
              </tr>
              <tr v-for="t in advancesConsumed" :key="t.id" class="hover:bg-gray-50">
                <td class="px-4 py-3 font-medium text-gray-900">{{ t.client_detail?.name ?? '—' }}</td>
                <td class="px-4 py-3 text-gray-600">#{{ t.advance }}</td>
                <td class="px-4 py-3 text-right font-semibold text-gray-900">{{ formatCurrency(t.value) }}</td>
                <td class="px-4 py-3 text-gray-600">#{{ t.voucher_num }}</td>
              </tr>
            </tbody>
            <tfoot v-if="advancesConsumed.length > 0">
              <tr class="bg-gray-50 border-t-2 border-gray-200">
                <td colspan="2" class="px-4 py-3 text-xs font-semibold text-gray-600">Total</td>
                <td class="px-4 py-3 text-right text-sm font-bold text-gray-900">{{ formatCurrency(totalAdvancesConsumed) }}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>
