<script setup lang="ts">
import { ref, reactive, computed, h } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { format, parseISO } from 'date-fns'
import { Eye, Download, X, FilterX } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'
import DataTable from '@/components/shared/DataTable.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import { auditApi } from '@/api/audit.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { ACTION_CONFIG, ALL_ACTIONS, ALL_MODELS, MODEL_LABEL } from '@/constants/audit'
import type { AuditLogEntry } from '@/types'

// ── Constants ─────────────────────────────────────────────────────────────────

// Common field names → Spanish labels for the diff view
const FIELD_LABEL: Record<string, string> = {
  id: 'ID', name: 'Nombre', email: 'Correo', username: 'Usuario',
  role: 'Rol', role_display: 'Rol (texto)', state: 'Estado',
  date: 'Fecha', date_register: 'Fecha de registro', value: 'Valor',
  nit: 'NIT', address: 'Dirección', phone: 'Teléfono', city: 'Ciudad',
  transfer_num: 'Nº Transferencia', observations: 'Observaciones',
  description: 'Descripción', justification: 'Justificación',
  abrev_name: 'Abreviación', facturation_name: 'Empresa a facturar',
  validate_certification: 'Validar certificación',
  client: 'Cliente', vehicle: 'Vehículo', material_type: 'Tipo material',
  payment: 'Pago', origin_site: 'Origen', invoice: 'Factura',
  invoice_pos: 'Pos factura', extern_voucher_num: 'Voucher externo',
  voucher_num: 'Nº voucher', certification_state: 'Estado certificación',
  certification_num: 'Nº certificación', is_advance: 'Es anticipo',
  capacity: 'Capacidad', plaque: 'Placa', start_date: 'Fecha inicio',
  end_date: 'Fecha fin', proforma_number: 'Nº proforma',
  available_balance: 'Saldo disponible', amount: 'Monto',
  type_movement: 'Tipo movimiento', trips_quantity: 'Cantidad viajes',
}

// ── Filters (all applied server-side) ────────────────────────────────────────

const filters = reactive({
  user: '',       // cast to number on send; '' = no filter
  action: '',
  model: '',
  date_from: '',
  date_to: '',
})

const hasActiveFilters = computed(() =>
  !!(filters.user || filters.action || filters.model || filters.date_from || filters.date_to)
)

function clearFilters() {
  filters.user = ''
  filters.action = ''
  filters.model = ''
  filters.date_from = ''
  filters.date_to = ''
}

// ── Query ──────────────────────────────────────────────────────────────────────

const queryParams = computed(() => {
  const p: Record<string, string | number> = {}
  if (filters.user)      p.user = Number(filters.user)
  if (filters.action)    p.action = filters.action
  if (filters.model)     p.model = filters.model
  if (filters.date_from) p.date_from = filters.date_from
  if (filters.date_to)   p.date_to = filters.date_to
  return p
})

const { data: rawEntries, isLoading, isError, error } = useQuery({
  queryKey: computed(() => ['audit-log', queryParams.value]),
  queryFn: async () => {
    const res = await auditApi.list(queryParams.value as Parameters<typeof auditApi.list>[0])
    return res.data
  },
})

const allEntries = computed<AuditLogEntry[]>(() => rawEntries.value ?? [])

// ── User dropdown — built from loaded entries (auditor cannot call usersApi.list()) ──

const uniqueUsers = computed(() => {
  const map = new Map<number, string>()
  for (const e of allEntries.value) {
    if (e.user !== null) map.set(e.user, e.user_name)
  }
  return [...map.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

// ── Detail drawer ──────────────────────────────────────────────────────────────

const selectedEntry = ref<AuditLogEntry | null>(null)
const showDetail = ref(false)

function openDetail(entry: AuditLogEntry) {
  selectedEntry.value = entry
  showDetail.value = true
}

function closeDetail() {
  showDetail.value = false
  selectedEntry.value = null
}

// ── Diff computation ──────────────────────────────────────────────────────────

interface DiffRow {
  key: string
  label: string
  prev: unknown
  next: unknown
  createOnly: boolean
}

function formatFieldValue(key: string, value: unknown): string {
  if (/password/i.test(key)) return '••••••••'   // mask sensitive fields
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

const diffRows = computed<DiffRow[]>(() => {
  const entry = selectedEntry.value
  if (!entry) return []
  const { previous_data: prev, new_data: next } = entry

  if (!prev && !next) return []

  // Create action — show all fields from new_data
  if (!prev && next) {
    return Object.keys(next).map(key => ({
      key, label: FIELD_LABEL[key] ?? key, prev: undefined, next: next[key], createOnly: true,
    }))
  }

  // Update / annul — show only changed fields
  if (prev && next) {
    const allKeys = new Set([...Object.keys(prev), ...Object.keys(next)])
    return [...allKeys]
      .filter(k => JSON.stringify(prev[k]) !== JSON.stringify(next[k]))
      .map(key => ({
        key, label: FIELD_LABEL[key] ?? key, prev: prev[key], next: next[key], createOnly: false,
      }))
  }

  // Only prev (edge case)
  return Object.keys(prev!).map(key => ({
    key, label: FIELD_LABEL[key] ?? key, prev: prev![key], next: undefined, createOnly: false,
  }))
})

const hasDiff = computed(() =>
  !!selectedEntry.value && (!!selectedEntry.value.previous_data || !!selectedEntry.value.new_data)
)

// ── CSV export (all filtered rows, not just visible page) ─────────────────────

function exportCsv() {
  if (!allEntries.value.length) {
    toast.info('No hay registros para exportar.')
    return
  }
  const rows = allEntries.value.map(e => ({
    'Fecha/Hora':    formatTs(e.timestamp),
    'Usuario':       e.user_name,
    'Acción':        ACTION_CONFIG[e.action]?.label ?? e.action_display,
    'Entidad':       MODEL_LABEL[e.model_name] ?? e.model_name,
    'ID Registro':   e.object_id ?? '',
    'IP':            e.ip_address ?? '',
    'Justificación': e.justification ?? '',
  }))
  const headers = Object.keys(rows[0])
  const csv = [
    headers.join(','),
    ...rows.map(row =>
      headers.map(k => JSON.stringify((row as Record<string, unknown>)[k] ?? '')).join(',')
    ),
  ].join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `audit_log_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTs(ts: string): string {
  try { return format(parseISO(ts), 'dd/MM/yyyy HH:mm:ss') } catch { return ts }
}

function actionBadge(action: string) {
  const cfg = ACTION_CONFIG[action]
  return { label: cfg?.label ?? action, cls: cfg?.cls ?? 'bg-gray-100 text-gray-600' }
}

// ── Table columns ──────────────────────────────────────────────────────────────

const columns: ColumnDef<AuditLogEntry>[] = [
  {
    accessorKey: 'timestamp',
    header: 'Fecha/Hora',
    cell: ({ row }) =>
      h('span', { class: 'text-xs text-gray-600 font-mono whitespace-nowrap' }, formatTs(row.original.timestamp)),
  },
  {
    accessorKey: 'user_name',
    header: 'Usuario',
  },
  {
    accessorKey: 'action',
    header: 'Acción',
    cell: ({ row }) => {
      const { label, cls } = actionBadge(row.original.action)
      return h('span', { class: `inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}` }, label)
    },
  },
  {
    accessorKey: 'model_name',
    header: 'Entidad',
    cell: ({ row }) =>
      h('span', {}, MODEL_LABEL[row.original.model_name] ?? row.original.model_name),
  },
  {
    accessorKey: 'object_id',
    header: 'ID',
    cell: ({ row }) =>
      h('span', { class: 'text-gray-500 font-mono text-xs' },
        row.original.object_id != null ? String(row.original.object_id) : '—'),
  },
  {
    accessorKey: 'ip_address',
    header: 'IP',
    cell: ({ row }) =>
      h('span', { class: 'text-xs text-gray-500 font-mono' }, row.original.ip_address ?? '—'),
  },
  {
    id: 'detail',
    header: '',
    cell: ({ row }) =>
      h('button', {
        class: 'p-1 text-gray-400 hover:text-gold-700 transition-colors',
        title: 'Ver detalle completo',
        onClick: () => openDetail(row.original),
      }, h(Eye, { class: 'w-4 h-4' })),
  },
]
</script>

<template>
  <div>
    <!-- Page header -->
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <PageHeader title="Log de Auditoría" description="Registro de acciones del sistema (solo lectura)" />
      <button
        @click="exportCsv"
        class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
      >
        <Download class="w-4 h-4" />
        Exportar CSV
      </button>
    </div>

    <!-- Filter bar -->
    <div class="bg-white border border-gray-200 rounded-lg p-4 mb-4">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">

        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1">Usuario</label>
          <select v-model="filters.user"
            class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400">
            <option value="">Todos</option>
            <option v-for="u in uniqueUsers" :key="u.id" :value="String(u.id)">{{ u.name }}</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1">Tipo de acción</label>
          <select v-model="filters.action"
            class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400">
            <option value="">Todas</option>
            <option v-for="a in ALL_ACTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1">Entidad</label>
          <select v-model="filters.model"
            class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400">
            <option value="">Todas</option>
            <option v-for="m in ALL_MODELS" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1">Fecha desde</label>
          <input v-model="filters.date_from" type="date"
            class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" />
        </div>

        <div>
          <label class="block text-xs font-medium text-gray-500 mb-1">Fecha hasta</label>
          <input v-model="filters.date_to" type="date"
            class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" />
        </div>

        <div class="flex items-end">
          <button
            @click="clearFilters"
            :disabled="!hasActiveFilters"
            class="flex items-center gap-1.5 w-full justify-center px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FilterX class="w-4 h-4" />
            Limpiar
          </button>
        </div>
      </div>
    </div>

    <!-- Results summary -->
    <div class="mb-3 text-sm text-gray-500 h-5">
      <template v-if="!isLoading && !isError">
        {{ allEntries.length.toLocaleString() }} registro{{ allEntries.length !== 1 ? 's' : '' }}
        <span v-if="hasActiveFilters"> — filtrados</span>
      </template>
    </div>

    <!-- API error -->
    <div v-if="isError" class="mb-4 p-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md">
      {{ getApiErrorMessage(error) }}
    </div>

    <!-- Table — DataTable handles pagination (10/25/50), search, sorting, loading, and empty state -->
    <DataTable
      :columns="(columns as any)"
      :data="(allEntries as any)"
      :is-loading="isLoading"
    />

    <!-- ── DETAIL DRAWER ─────────────────────────────────────────────────────── -->
    <teleport to="body">
      <div v-if="showDetail && selectedEntry" class="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div class="absolute inset-0 bg-black/40" @click="closeDetail" />

        <div class="relative bg-white w-full max-w-2xl max-h-[85vh] rounded-xl shadow-2xl overflow-y-auto flex flex-col">
          <!-- Drawer header -->
          <div class="sticky top-0 bg-white z-10 flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <div>
              <h2 class="text-base font-semibold text-gray-900">Detalle de entrada</h2>
              <p class="text-xs text-gray-400 mt-0.5">#{{ selectedEntry.id }}</p>
            </div>
            <button @click="closeDetail"
              class="p-1.5 text-gray-400 hover:text-gray-700 rounded-md hover:bg-gray-100">
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- Body -->
          <div class="px-6 py-5 space-y-6 flex-1">

            <!-- Basic info -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div>
                <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">Fecha / Hora</p>
                <p class="text-gray-800 font-mono text-xs">{{ formatTs(selectedEntry.timestamp) }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">Usuario</p>
                <p class="text-gray-800">{{ selectedEntry.user_name }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">Acción</p>
                <span :class="`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${actionBadge(selectedEntry.action).cls}`">
                  {{ actionBadge(selectedEntry.action).label }}
                </span>
              </div>
              <div>
                <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">Entidad</p>
                <p class="text-gray-800">{{ MODEL_LABEL[selectedEntry.model_name] ?? selectedEntry.model_name }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">ID Registro</p>
                <p class="text-gray-800 font-mono">{{ selectedEntry.object_id ?? '—' }}</p>
              </div>
              <div>
                <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">IP</p>
                <p class="text-gray-800 font-mono text-xs">{{ selectedEntry.ip_address ?? '—' }}</p>
              </div>
            </div>

            <!-- Justification -->
            <div v-if="selectedEntry.justification"
              class="bg-amber-50 border border-amber-200 rounded-md px-4 py-3">
              <p class="text-xs font-semibold text-amber-700 mb-1">Justificación</p>
              <p class="text-sm text-amber-900">{{ selectedEntry.justification }}</p>
            </div>

            <!-- Diff / data section -->
            <div v-if="hasDiff">
              <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
                {{ selectedEntry.previous_data ? 'Campos modificados' : 'Datos registrados' }}
              </p>

              <p v-if="diffRows.length === 0" class="text-sm text-gray-400 italic">
                No se detectaron cambios en los campos.
              </p>

              <div v-else class="space-y-2">
                <div v-for="row in diffRows" :key="row.key"
                  class="border border-gray-100 rounded-md overflow-hidden text-sm">
                  <!-- Field label -->
                  <div class="bg-gray-50 px-3 py-1 text-xs font-medium text-gray-500 border-b border-gray-100">
                    {{ row.label }}
                  </div>

                  <!-- Create action: single value -->
                  <div v-if="row.createOnly" class="px-3 py-2">
                    <p class="font-mono text-green-700 break-all whitespace-pre-wrap">
                      {{ formatFieldValue(row.key, row.next) }}
                    </p>
                  </div>

                  <!-- Update/annul: before vs after -->
                  <div v-else class="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 divide-x-0 sm:divide-x divide-gray-100">
                    <div class="px-3 py-2">
                      <p class="text-xs text-gray-400 mb-1">Antes</p>
                      <p class="font-mono text-red-600 break-all whitespace-pre-wrap line-through decoration-red-300">
                        {{ formatFieldValue(row.key, row.prev) }}
                      </p>
                    </div>
                    <div class="px-3 py-2">
                      <p class="text-xs text-gray-400 mb-1">Después</p>
                      <p class="font-mono text-green-700 break-all whitespace-pre-wrap">
                        {{ formatFieldValue(row.key, row.next) }}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- No payload (login / logout / access_denied) -->
            <p v-else class="text-sm text-gray-400 italic">
              Este tipo de acción no registra campos adicionales.
            </p>

          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>
