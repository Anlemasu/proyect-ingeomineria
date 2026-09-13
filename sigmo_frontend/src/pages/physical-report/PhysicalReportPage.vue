<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { Eye, X, Archive, RotateCcw, AlertTriangle, Save } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'

import DataTable from '@/components/shared/DataTable.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import DatePickerInput from '@/components/shared/DatePickerInput.vue'
import InlineCountInput from './InlineCountInput.vue'
import { physicalReportsApi } from '@/api/physicalReports.api'
import { useAuthStore } from '@/stores/auth.store'
import { formatDate, todayBogota } from '@/utils/formatDate'
import { toastApiError } from '@/utils/handleApiError'
import type { PhysicalReportSummary } from '@/types'

const qc = useQueryClient()
const authStore = useAuthStore()
const canManage = computed(() =>
  ['superuser', 'cashier', 'commercial_admin'].includes(authStore.user?.role ?? '')
)

// ── Vista abierta / cerrada + filtro de fecha ─────────────────────────────
// La fecha seleccionada controla, para TODA la tabla: qué valor trae el
// campo de registro rápido de cada fila (`day_count`) y a qué fecha se
// calculan 'Acumulado'/'Restantes' — así se puede ver "cómo iba" en
// cualquier día, no solo hoy (ver services.get_open_physical_reports en el
// backend, que siempre decide qué anticipos aparecen con el acumulado REAL
// de hoy, sin importar esta fecha).
type View = 'open' | 'closed'
const view = ref<View>('open')
const listDate = ref<string>(todayBogota())

const { data: openData, isLoading: openLoading } = useQuery({
  queryKey: computed(() => ['physical-reports', listDate.value]),
  queryFn: () => physicalReportsApi.list({ date: listDate.value }).then(r => r.data),
  refetchInterval: 15_000,
})
const { data: closedData, isLoading: closedLoading } = useQuery({
  queryKey: computed(() => ['physical-reports-closed', listDate.value]),
  queryFn: () => physicalReportsApi.listClosed({ date: listDate.value }).then(r => r.data),
  enabled: computed(() => view.value === 'closed'),
})

const rows = computed<PhysicalReportSummary[]>(() =>
  (view.value === 'open' ? openData.value : closedData.value) ?? []
)
const rowsLoading = computed(() => (view.value === 'open' ? openLoading.value : closedLoading.value))

function invalidateLists() {
  qc.invalidateQueries({ queryKey: ['physical-reports'] })
  qc.invalidateQueries({ queryKey: ['physical-reports-closed'] })
}

// ── Campo inline "Conteo físico" + botón único "Guardar todos" ───────────
// Valores que el usuario está escribiendo ahora mismo, por anticipo — se
// reinicia cada vez que cambian los datos de la fecha seleccionada (nueva
// fecha, o después de guardar) para que siempre parta de lo ya guardado.
const inlineCounts = ref<Record<number, number | undefined>>({})

watch([rows, listDate], () => {
  const next: Record<number, number | undefined> = {}
  for (const row of rows.value) {
    next[row.advance] = row.day_count ?? undefined
  }
  inlineCounts.value = next
}, { immediate: true })

// Solo las filas donde el valor escrito difiere de lo ya guardado para esta
// fecha entran en "Guardar todos" — reenviar lo que no cambió no aporta
// nada (y el backend ya lo trata como no-op si igual llega).
const pendingBulkEntries = computed(() =>
  rows.value
    .filter(row => row.day_editable !== false)
    .map(row => ({ row, count: inlineCounts.value[row.advance] }))
    .filter(({ row, count }) => count != null && count !== (row.day_count ?? undefined))
    .map(({ row, count }) => ({ advance: row.advance, count: count as number }))
)

const bulkSaveMutation = useMutation({
  mutationFn: () => physicalReportsApi.bulkRegisterEntries(listDate.value, pendingBulkEntries.value).then(r => r.data),
  onSuccess: (results) => {
    const ok = results.filter(r => r.status === 'ok').length
    const errors = results.filter(r => r.status === 'error')
    if (ok > 0) toast.success(`Conteo físico guardado: ${ok} registro(s).`)
    for (const err of errors) {
      const row = rows.value.find(r => r.advance === err.advance)
      toast.error(`${row?.client_detail?.name ?? `Anticipo #${err.advance}`}: ${err.error}`)
    }
    invalidateLists()
  },
  onError: (err) => toastApiError(err),
})

// ── Definir cupo esperado (cuando el anticipo no lo tiene) ───────────────
const quotaAdvance = ref<PhysicalReportSummary | null>(null)
const quotaInput = ref<number | undefined>(undefined)

function openQuotaModal(row: PhysicalReportSummary) {
  quotaAdvance.value = row
  quotaInput.value = undefined
}
function closeQuotaModal() {
  quotaAdvance.value = null
}

const quotaMutation = useMutation({
  mutationFn: () => physicalReportsApi.setQuota(quotaAdvance.value!.advance, quotaInput.value!),
  onSuccess: () => {
    toast.success('Cupo esperado definido correctamente.')
    invalidateLists()
    closeQuotaModal()
  },
  onError: (err) => toastApiError(err),
})

// ── Detalle / ajuste individual de un día (el "ojito") ───────────────────
// Sigue siendo necesario después de la ventana de ajuste rápido (30 min):
// ahí es donde se corrige con justificación. También sirve para que
// auditor/contador revisen el historial de un día puntual.
const detailAdvance = ref<PhysicalReportSummary | null>(null)
const detailDate = ref<string>(todayBogota())
const countInput = ref<number | undefined>(undefined)
const entryJustification = ref('')

function openEntryModal(row: PhysicalReportSummary) {
  detailAdvance.value = row
  detailDate.value = listDate.value
  entryJustification.value = ''
}
function closeEntryModal() {
  detailAdvance.value = null
}

const { data: detailData, isFetching: detailLoading } = useQuery({
  queryKey: computed(() => ['physical-report-detail', detailAdvance.value?.advance, detailDate.value]),
  queryFn: () =>
    physicalReportsApi
      .detail(detailAdvance.value!.advance, { date: detailDate.value })
      .then(r => r.data),
  enabled: computed(() => !!detailAdvance.value && !!detailDate.value),
})

// Ya pasó la ventana de ajuste rápido (30 min): corregir desde aquí exige
// justificación. Dentro de la ventana (o sin ningún conteo todavía), no.
const needsJustification = computed(() =>
  detailData.value?.day_detail != null
  && detailData.value.day_detail.physical_count != null
  && detailData.value.day_detail.editable === false
)

watch([detailData, detailDate], () => {
  countInput.value = detailData.value?.day_detail?.physical_count ?? undefined
  entryJustification.value = ''
})

const registerMutation = useMutation({
  mutationFn: () =>
    physicalReportsApi.registerEntry(detailAdvance.value!.advance, {
      date: detailDate.value,
      count: countInput.value!,
      justification: needsJustification.value ? entryJustification.value.trim() : undefined,
    }),
  onSuccess: () => {
    toast.success('Conteo físico guardado correctamente.')
    invalidateLists()
    qc.invalidateQueries({ queryKey: ['physical-report-detail'] })
  },
  onError: (err) => toastApiError(err),
})

// ── Finalizar / deshacer / reabrir ────────────────────────────────────────
const closingAdvance = ref<PhysicalReportSummary | null>(null)

const closeMutation = useMutation({
  mutationFn: (row: PhysicalReportSummary) => physicalReportsApi.close(row.advance),
  onSuccess: (_res, row) => {
    invalidateLists()
    toast.success(`Conteo físico finalizado — ${row.client_detail.name}.`, {
      action: {
        label: 'Deshacer',
        onClick: () => undoCloseMutation.mutate(row),
      },
      duration: 15_000,
    })
  },
  onError: (err) => toastApiError(err),
  onSettled: () => { closingAdvance.value = null },
})

const undoCloseMutation = useMutation({
  mutationFn: (row: PhysicalReportSummary) => physicalReportsApi.undoClose(row.advance),
  onSuccess: () => {
    toast.success('Cierre deshecho.')
    invalidateLists()
  },
  onError: (err) => toastApiError(err),
})

const reopeningAdvance = ref<PhysicalReportSummary | null>(null)
const reopenJustification = ref('')

function openReopenModal(row: PhysicalReportSummary) {
  reopeningAdvance.value = row
  reopenJustification.value = ''
}
function closeReopenModal() {
  reopeningAdvance.value = null
}

const reopenMutation = useMutation({
  mutationFn: () => physicalReportsApi.reopen(reopeningAdvance.value!.advance, reopenJustification.value.trim()),
  onSuccess: () => {
    toast.success('Registro reabierto correctamente.')
    invalidateLists()
    closeReopenModal()
  },
  onError: (err) => toastApiError(err),
})

// ── Columnas ──────────────────────────────────────────────────────────────
const columns = computed<ColumnDef<PhysicalReportSummary>[]>(() => [
  {
    id: 'client_name',
    header: 'Cliente',
    accessorFn: row => row.client_detail?.name ?? '—',
  },
  {
    accessorKey: 'advance',
    header: 'N° Anticipo',
    cell: info => {
      const row = info.row.original
      return h('div', { class: 'flex items-center gap-2' }, [
        h('span', {}, `#${row.advance}`),
        row.is_active
          ? h('span', { class: 'inline-flex px-1.5 py-0.5 rounded text-[11px] font-medium bg-green-100 text-green-700' }, 'Activo')
          : h('span', {
              class: 'inline-flex px-1.5 py-0.5 rounded text-[11px] font-medium bg-gray-100 text-gray-500',
              title: 'Este anticipo ya no es el activo del cliente: los viajes nuevos se descuentan contra otro. Sigue visible aquí porque su conteo físico no se ha cerrado.',
            }, 'Congelado'),
      ])
    },
  },
  {
    accessorKey: 'date',
    header: 'Fecha Anticipo',
    cell: info => formatDate(info.getValue() as string),
  },
  {
    id: 'expected',
    header: 'Cupo Esperado',
    cell: info => {
      const row = info.row.original
      if (row.expected_trips_quantity != null) {
        return h('span', {}, String(row.expected_trips_quantity))
      }
      if (!canManage.value) return h('span', { class: 'text-gray-400' }, '—')
      return h('button', {
        class: 'text-xs font-medium text-gold-700 hover:text-gold-800 underline underline-offset-2',
        onClick: () => openQuotaModal(row),
      }, 'Definir cupo')
    },
  },
  {
    accessorKey: 'cumulative_entered',
    header: 'Acumulado a la Fecha',
  },
  {
    id: 'remaining',
    header: 'Restantes',
    cell: info => {
      const val = info.row.original.remaining
      if (val == null) return h('span', { class: 'text-gray-400' }, '—')
      return h('span', { class: val > 0 ? 'text-amber-700 font-medium' : 'text-green-700 font-medium' }, String(val))
    },
  },
  {
    id: 'day_count',
    header: 'Conteo Físico del Día',
    cell: info => {
      const row = info.row.original
      if (canManage.value && view.value === 'open' && row.day_editable !== false) {
        return h(InlineCountInput, {
          modelValue: inlineCounts.value[row.advance],
          'onUpdate:modelValue': (v: number | undefined) => {
            inlineCounts.value = { ...inlineCounts.value, [row.advance]: v }
          },
        })
      }
      if (row.day_count == null) return h('span', { class: 'text-gray-400' }, '—')
      const outOfWindow = canManage.value && view.value === 'open' && row.day_editable === false
      return h('span', { class: outOfWindow ? 'text-gray-400 text-xs italic' : '' },
        outOfWindow ? `${row.day_count} (ajustar con el ojito)` : String(row.day_count)
      )
    },
  },
  {
    id: 'actions',
    header: '',
    cell: info => {
      const row = info.row.original
      const buttons = [
        h('button', {
          class: 'p-1 text-gray-400 hover:text-gold-700 transition-colors',
          title: 'Ver detalle / ajustar individualmente',
          onClick: () => openEntryModal(row),
        }, h(Eye, { class: 'w-4 h-4' })),
      ]
      if (canManage.value) {
        if (view.value === 'open') {
          buttons.push(h('button', {
            class: 'p-1 text-gray-400 hover:text-red-600 transition-colors',
            title: 'Finalizar conteo físico',
            onClick: () => { closingAdvance.value = row },
          }, h(Archive, { class: 'w-4 h-4' })))
        } else {
          buttons.push(h('button', {
            class: 'p-1 text-gray-400 hover:text-gold-700 transition-colors',
            title: 'Reabrir conteo físico',
            onClick: () => openReopenModal(row),
          }, h(RotateCcw, { class: 'w-4 h-4' })))
        }
      }
      return h('div', { class: 'flex items-center gap-1' }, buttons)
    },
  },
])
</script>

<template>
  <div class="p-4 lg:p-6 space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold text-gray-900">Reporte Físico</h1>
        <p class="text-sm text-gray-500 mt-1">
          Conciliación de vales físicos contra los viajes registrados en el sistema, por anticipo.
        </p>
      </div>
    </div>

    <!-- Vista abierta / cerrada -->
    <div class="border-b border-gray-200">
      <nav class="flex gap-1" aria-label="Tabs">
        <button
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
          :class="view === 'open'
            ? 'border-gold-500 text-gold-700'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="view = 'open'"
        >
          Pendientes
        </button>
        <button
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
          :class="view === 'closed'
            ? 'border-gold-500 text-gold-700'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="view = 'closed'"
        >
          Cerrados
        </button>
      </nav>
    </div>

    <!-- Filtro de fecha + Guardar todos -->
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div class="max-w-xs">
        <label class="block text-sm font-medium text-gray-700 mb-1">Fecha</label>
        <DatePickerInput v-model="listDate" :max="todayBogota()" />
      </div>
      <button
        v-if="canManage && view === 'open'"
        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold-500 text-stone-900 text-sm font-medium hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        :disabled="!pendingBulkEntries.length || bulkSaveMutation.isPending.value"
        @click="bulkSaveMutation.mutate()"
      >
        <Save class="w-4 h-4" />
        {{ bulkSaveMutation.isPending.value ? 'Guardando...' : `Guardar todos${pendingBulkEntries.length ? ` (${pendingBulkEntries.length})` : ''}` }}
      </button>
    </div>

    <DataTable :data="rows" :columns="columns" :is-loading="rowsLoading" />

    <!-- ── Modal: definir cupo esperado ──────────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="quotaAdvance"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
        @click.self="closeQuotaModal"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm">
          <div class="flex items-center justify-between px-6 py-4 border-b-2 border-gold-200 bg-gold-50/40">
            <h2 class="text-base font-semibold text-gray-900">Definir cupo esperado</h2>
            <button class="text-gray-400 hover:text-gray-600 transition-colors" @click="closeQuotaModal">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="px-6 py-5 space-y-4">
            <p class="text-sm text-gray-600">
              Cliente: <strong>{{ quotaAdvance.client_detail?.name }}</strong>
            </p>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Cantidad de viajes esperados <span class="text-red-500">*</span>
              </label>
              <input
                v-model.number="quotaInput"
                type="number"
                min="1"
                step="1"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
              />
            </div>
          </div>
          <div class="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-100">
            <button
              class="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              @click="closeQuotaModal"
            >
              Cancelar
            </button>
            <button
              class="px-4 py-2 text-sm font-medium bg-gold-500 text-stone-900 rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!quotaInput || quotaInput < 1 || quotaMutation.isPending.value"
              @click="quotaMutation.mutate()"
            >
              {{ quotaMutation.isPending.value ? 'Guardando...' : 'Guardar' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Modal: detalle / ajuste individual de un día ────────────────── -->
    <Teleport to="body">
      <div
        v-if="detailAdvance"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
        @click.self="closeEntryModal"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
          <div class="flex items-center justify-between px-6 py-4 border-b-2 border-gold-200 bg-gold-50/40 flex-shrink-0">
            <h2 class="text-base font-semibold text-gray-900">Conteo físico — {{ detailAdvance.client_detail?.name }}</h2>
            <button class="text-gray-400 hover:text-gray-600 transition-colors" @click="closeEntryModal">
              <X class="w-5 h-5" />
            </button>
          </div>

          <div class="px-6 py-5 space-y-4 overflow-y-auto">
            <div class="grid grid-cols-3 gap-4 text-sm">
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wide">Cupo esperado</p>
                <p class="font-medium text-gray-900">{{ detailAdvance.expected_trips_quantity ?? '—' }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wide">Acumulado</p>
                <p class="font-medium text-gray-900">{{ detailData?.cumulative_entered ?? detailAdvance.cumulative_entered }}</p>
              </div>
              <div>
                <p class="text-xs text-gray-500 uppercase tracking-wide">Restantes</p>
                <p class="font-medium text-gray-900">{{ (detailData?.remaining ?? detailAdvance.remaining) ?? '—' }}</p>
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Fecha</label>
              <DatePickerInput v-model="detailDate" :max="todayBogota()" />
            </div>

            <p v-if="detailLoading" class="text-xs text-gray-400">Consultando...</p>
            <template v-else-if="detailData?.day_detail">
              <div
                v-if="detailData.day_detail.other_advance_trips_count > 0"
                class="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 flex items-start gap-2"
              >
                <AlertTriangle class="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  Este cliente tiene <strong>{{ detailData.day_detail.other_advance_trips_count }}</strong>
                  viaje(s) ese día registrados en
                  {{ detailData.day_detail.other_advance_ids.length > 1 ? 'otros anticipos' : 'otro anticipo' }}
                  (#{{ detailData.day_detail.other_advance_ids.join(', #') }})
                </span>
              </div>

              <div class="rounded-lg border border-gray-200 p-4 space-y-2 text-sm">
                <div class="flex items-center justify-between">
                  <span class="text-gray-500">Viajes registrados en el sistema ese día</span>
                  <span class="font-medium text-gray-900">{{ detailData.day_detail.system_count }}</span>
                </div>
                <div class="flex items-center justify-between">
                  <span class="text-gray-500">Vales físicos ya guardados ese día</span>
                  <span class="font-medium text-gray-900">{{ detailData.day_detail.physical_count ?? 'Sin registrar' }}</span>
                </div>
                <div
                  v-if="detailData.day_detail.difference != null && detailData.day_detail.difference !== 0"
                  class="flex items-center gap-1.5 text-amber-700 font-medium pt-1"
                >
                  <AlertTriangle class="w-4 h-4 shrink-0" />
                  Diferencia: {{ detailData.day_detail.difference > 0 ? '+' : '' }}{{ detailData.day_detail.difference }}
                </div>
                <p v-if="!detailData.day_detail.editable" class="text-xs text-gray-500 pt-1">
                  Ya pasó la ventana de ajuste rápido (30 min): cualquier corrección desde aquí exige justificación.
                </p>
              </div>

              <div v-if="detailData.day_detail.history.length > 1" class="text-xs text-gray-500 space-y-1">
                <p class="font-medium text-gray-600">Historial de correcciones de este día:</p>
                <div v-for="h in detailData.day_detail.history" :key="h.id" class="flex items-center justify-between">
                  <span>{{ h.user_name }} — {{ h.count }} {{ h.justification ? `(${h.justification})` : '' }}</span>
                </div>
              </div>
            </template>

            <template v-if="canManage">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Conteo físico del día <span class="text-red-500">*</span>
                </label>
                <input
                  v-model.number="countInput"
                  type="number"
                  min="0"
                  step="1"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
                />
              </div>

              <div v-if="needsJustification">
                <label class="block text-sm font-medium text-gray-700 mb-1">
                  Justificación de la corrección <span class="text-red-500">*</span>
                </label>
                <textarea
                  v-model="entryJustification"
                  rows="3"
                  placeholder="Motivo de la corrección..."
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400 resize-none"
                />
              </div>
            </template>
          </div>

          <div v-if="canManage" class="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-100 flex-shrink-0">
            <button
              class="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              @click="closeEntryModal"
            >
              Cancelar
            </button>
            <button
              class="px-4 py-2 text-sm font-medium bg-gold-500 text-stone-900 rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="countInput == null || countInput < 0 || (needsJustification && !entryJustification.trim()) || registerMutation.isPending.value"
              @click="registerMutation.mutate()"
            >
              {{ registerMutation.isPending.value ? 'Guardando...' : 'Guardar conteo' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Modal: reabrir ────────────────────────────────────────────── -->
    <Teleport to="body">
      <div
        v-if="reopeningAdvance"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
        @click.self="closeReopenModal"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg">
          <div class="flex items-center justify-between px-6 py-4 border-b-2 border-gold-200 bg-gold-50/40">
            <h2 class="text-base font-semibold text-gray-900">Reabrir conteo físico</h2>
            <button class="text-gray-400 hover:text-gray-600 transition-colors" @click="closeReopenModal">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="px-6 py-5 space-y-4">
            <p class="text-sm text-gray-600">
              Cliente: <strong>{{ reopeningAdvance.client_detail?.name }}</strong>
            </p>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Justificación <span class="text-red-500">*</span>
              </label>
              <textarea
                v-model="reopenJustification"
                rows="3"
                placeholder="Motivo de la reapertura..."
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400 resize-none"
              />
            </div>
          </div>
          <div class="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-100">
            <button
              class="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
              @click="closeReopenModal"
            >
              Cancelar
            </button>
            <button
              class="px-4 py-2 text-sm font-medium bg-gold-500 text-stone-900 rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!reopenJustification.trim() || reopenMutation.isPending.value"
              @click="reopenMutation.mutate()"
            >
              {{ reopenMutation.isPending.value ? 'Reabriendo...' : 'Reabrir' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── Confirmación: finalizar ───────────────────────────────────── -->
    <ConfirmDialog
      :open="!!closingAdvance"
      title="Finalizar conteo físico"
      :description="closingAdvance
        ? `¿Finalizar el conteo físico de ${closingAdvance.client_detail?.name}? Podrás deshacerlo inmediatamente después, o reabrirlo más tarde con una justificación.`
        : ''"
      confirm-label="Finalizar"
      :loading="closeMutation.isPending.value"
      @cancel="closingAdvance = null"
      @confirm="closeMutation.mutate(closingAdvance!)"
    />
  </div>
</template>
