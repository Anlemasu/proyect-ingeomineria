<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Plus, Pencil, Download, AlertTriangle, X, Eye, FileText, Truck } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'

type ARow = Record<string, unknown>

import DataTable from '@/components/shared/DataTable.vue'
import CurrencyInput from '@/components/shared/CurrencyInput.vue'
import { advancesApi } from '@/api/advances.api'
import { clientsApi } from '@/api/clients.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { useAuthStore } from '@/stores/auth.store'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, toISODate } from '@/utils/formatDate'
import type { Advance, AdvanceMovement, Client } from '@/types'

const qc = useQueryClient()
const authStore = useAuthStore()
const isSuperuser = computed(() => authStore.user?.role === 'superuser')
const canManage = computed(() =>
  ['superuser', 'accountant', 'commercial_admin'].includes(authStore.user?.role ?? '')
)

type Tab = 'registro' | 'estado' | 'historial'
const activeTab = ref<Tab>('registro')

const tabs = [
  { id: 'registro' as Tab, label: 'Registro de Anticipos' },
  { id: 'estado' as Tab, label: 'Estado de Cuenta' },
  { id: 'historial' as Tab, label: 'Historial de Movimientos' },
]

// ── Queries ────────────────────────────────────────────────────────────────
const { data: advancesData, isLoading: advancesLoading } = useQuery({
  queryKey: ['advances'],
  queryFn: () => advancesApi.list().then(r => r.data),
  refetchInterval: 60_000,
})
const advances = computed(() => advancesData.value ?? [])

const { data: clientsData } = useQuery({
  queryKey: ['clients'],
  queryFn: () => clientsApi.list().then(r => r.data),
})
const clients = computed(() => clientsData.value ?? [])

// ── Alerts (clientes con saldo negativo) ──────────────────────────────────
const clientBalances = computed(() => {
  const map = new Map<number, { client: Client; balance: number }>()
  for (const adv of advances.value) {
    const entry = map.get(adv.client)
    if (entry) {
      entry.balance += adv.available_balance
    } else {
      map.set(adv.client, { client: adv.client_detail, balance: adv.available_balance })
    }
  }
  return [...map.values()]
})

const dismissedAlerts = ref<Set<number>>(new Set())
const visibleAlerts = computed(() =>
  clientBalances.value
    .filter(c => c.balance < 0 && !dismissedAlerts.value.has(c.client.id))
)

function dismissAlert(clientId: number) {
  dismissedAlerts.value = new Set([...dismissedAlerts.value, clientId])
}

// ── Panel de detalle ───────────────────────────────────────────────────────
const detailAdvance = ref<Advance | null>(null)

function openDetail(advance: Advance) {
  detailAdvance.value = advance
}

function closeDetail() {
  detailAdvance.value = null
}

// ── Tab 1: Registro — formulario ──────────────────────────────────────────
const showModal = ref(false)
const editingAdvance = ref<Advance | null>(null)

const schema = toTypedSchema(z.object({
  client: z.number({ message: 'Selecciona un cliente' }),
  date: z.string().min(1, 'La fecha es requerida'),
  value: z.number({ message: 'Ingresa el valor' }).positive('Debe ser mayor a cero'),
  transfer_num: z.number({ message: 'N° consignación requerido' }).int('Debe ser un entero').positive('Debe ser mayor a cero'),
  trips_quantity: z.number({ message: '' }).int('Debe ser un entero').min(0, 'No puede ser negativo').optional(),
  proforma_number: z.number({ message: '' }).int().positive().optional(),
  observations: z.string().optional(),
}))

const { handleSubmit, isSubmitting, resetForm, setValues } = useForm({
  validationSchema: schema,
  initialValues: {
    client: undefined as number | undefined,
    date: toISODate(new Date()),
    value: undefined as number | undefined,
    transfer_num: undefined as number | undefined,
    trips_quantity: undefined as number | undefined,
    proforma_number: undefined as number | undefined,
    observations: '',
  },
})

const { value: clientId, errorMessage: clientError } = useField<number | undefined>('client')
const { value: dateVal, errorMessage: dateError } = useField<string>('date')
const { value: valueField, errorMessage: valueError, handleChange: handleValueChange } = useField<number | undefined>('value')
const { value: transferNum, errorMessage: transferNumError } = useField<number | undefined>('transfer_num')
const { value: tripsQty, errorMessage: tripsQtyError } = useField<number | undefined>('trips_quantity')
const { value: proformaNum } = useField<number | undefined>('proforma_number')
const { value: observations } = useField<string>('observations')

function openCreate() {
  editingAdvance.value = null
  resetForm()
  setValues({
    client: undefined,
    date: toISODate(new Date()),
    value: undefined,
    transfer_num: undefined,
    trips_quantity: undefined,
    proforma_number: undefined,
    observations: '',
  })
  showModal.value = true
}

function openEdit(advance: Advance) {
  editingAdvance.value = advance
  setValues({
    client: advance.client,
    date: advance.date,
    value: parseFloat(advance.value),
    transfer_num: advance.transfer_num,
    trips_quantity: undefined,
    proforma_number: advance.proforma_number ?? undefined,
    observations: advance.observations ?? '',
  })
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingAdvance.value = null
}

const createMutation = useMutation({
  mutationFn: (data: Parameters<typeof advancesApi.create>[0]) => advancesApi.create(data),
  onSuccess: () => {
    toast.success('Anticipo registrado correctamente.')
    qc.invalidateQueries({ queryKey: ['advances'] })
    closeModal()
  },
  onError: (err) => toast.error(getApiErrorMessage(err)),
})

const updateMutation = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Parameters<typeof advancesApi.update>[1] }) =>
    advancesApi.update(id, data),
  onSuccess: () => {
    toast.success('Anticipo actualizado correctamente.')
    qc.invalidateQueries({ queryKey: ['advances'] })
    closeModal()
    // Actualizar el panel de detalle si está abierto
    if (detailAdvance.value?.id === editingAdvance.value?.id) {
      const updated = advances.value.find(a => a.id === editingAdvance.value?.id)
      if (updated) detailAdvance.value = updated
    }
  },
  onError: (err) => toast.error(getApiErrorMessage(err)),
})

const onSubmit = handleSubmit(async (values) => {
  if (editingAdvance.value) {
    await updateMutation.mutateAsync({
      id: editingAdvance.value.id,
      data: {
        value: values.value,
        transfer_num: values.transfer_num,
        date: values.date,
        proforma_number: values.proforma_number ?? null,
        observations: values.observations || null,
      },
    })
  } else {
    await createMutation.mutateAsync({
      client: values.client!,
      value: values.value!,
      transfer_num: values.transfer_num!,
      date: values.date,
      trips_quantity: values.trips_quantity ?? 0,
      proforma_number: values.proforma_number,
      observations: values.observations || undefined,
    })
  }
})

// ── Columnas Tab 1 ─────────────────────────────────────────────────────────
const registroColumns: ColumnDef<ARow>[] = [
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
    accessorKey: 'value',
    header: 'Valor',
    cell: info => formatCurrency(parseFloat(info.getValue() as string)),
  },
  {
    accessorKey: 'transfer_num',
    header: 'N° Consignación',
  },
  {
    accessorKey: 'proforma_number',
    header: 'N° Proforma',
    cell: info => info.getValue() ?? '—',
  },
  {
    accessorKey: 'available_balance',
    header: 'Saldo Disponible',
    cell: info => {
      const val = info.getValue() as number
      const cls = val > 0 ? 'text-green-600 font-medium' : val < 0 ? 'text-red-600 font-medium' : 'text-gray-400'
      return h('span', { class: cls }, formatCurrency(val))
    },
  },
  {
    id: 'actions',
    header: '',
    cell: info => {
      const adv = info.row.original as unknown as Advance
      return h('div', { class: 'flex items-center gap-1' }, [
        h('button', {
          class: 'p-1 text-gray-400 hover:text-blue-600 transition-colors',
          title: 'Ver detalle',
          onClick: () => openDetail(adv),
        }, h(Eye, { class: 'w-4 h-4' })),
        isSuperuser.value
          ? h('button', {
              class: 'p-1 text-gray-400 hover:text-amber-600 transition-colors',
              title: 'Editar',
              onClick: () => openEdit(adv),
            }, h(Pencil, { class: 'w-4 h-4' }))
          : null,
      ])
    },
  },
]

// ── Tab 2: Estado de Cuenta ────────────────────────────────────────────────
const selectedClientId = ref<number | ''>('')

const selectedClientAdvances = computed(() =>
  selectedClientId.value
    ? advances.value.filter(a => a.client === selectedClientId.value)
    : []
)

const selectedClientTotalIngresado = computed(() =>
  selectedClientAdvances.value
    .flatMap(a => a.movements)
    .filter(m => m.type_movement === 'ingreso')
    .reduce((s, m) => s + parseFloat(m.amount), 0)
)

const selectedClientTotalConsumido = computed(() =>
  selectedClientAdvances.value
    .flatMap(a => a.movements)
    .filter(m => m.type_movement === 'egreso')
    .reduce((s, m) => s + parseFloat(m.amount), 0)
)

const selectedClientBalance = computed(() =>
  selectedClientAdvances.value.reduce((s, a) => s + a.available_balance, 0)
)

type MovementRow = AdvanceMovement & { client_name: string; advance_id: number }

const selectedClientMovements = computed<MovementRow[]>(() =>
  selectedClientAdvances.value
    .flatMap(a =>
      a.movements.map(m => ({ ...m, client_name: a.client_detail?.name ?? '—', advance_id: a.id }))
    )
    .sort((a, b) => b.date.localeCompare(a.date))
)

// Columnas anticipos en Tab 2 (lista compacta)
const estadoAdvanceColumns: ColumnDef<ARow>[] = [
  {
    accessorKey: 'date',
    header: 'Fecha',
    cell: info => formatDate(info.getValue() as string),
  },
  {
    accessorKey: 'value',
    header: 'Valor',
    cell: info => formatCurrency(parseFloat(info.getValue() as string)),
  },
  {
    accessorKey: 'transfer_num',
    header: 'N° Consignación',
  },
  {
    accessorKey: 'available_balance',
    header: 'Saldo',
    cell: info => {
      const val = info.getValue() as number
      const cls = val > 0 ? 'text-green-600 font-medium' : val < 0 ? 'text-red-600 font-medium' : 'text-gray-400'
      return h('span', { class: cls }, formatCurrency(val))
    },
  },
  {
    id: 'actions',
    header: '',
    cell: info => h('button', {
      class: 'p-1 text-gray-400 hover:text-blue-600 transition-colors',
      title: 'Ver detalle',
      onClick: () => openDetail(info.row.original as unknown as Advance),
    }, h(Eye, { class: 'w-4 h-4' })),
  },
]

// ── Tab 3: Historial ───────────────────────────────────────────────────────
const filterClientId = ref<number | ''>('')
const filterDateFrom = ref('')
const filterDateTo = ref('')

const allMovements = computed<MovementRow[]>(() => {
  const result: MovementRow[] = []
  for (const adv of advances.value) {
    if (filterClientId.value && adv.client !== filterClientId.value) continue
    for (const m of adv.movements) {
      if (filterDateFrom.value && m.date < filterDateFrom.value) continue
      if (filterDateTo.value && m.date > filterDateTo.value) continue
      result.push({ ...m, client_name: adv.client_detail?.name ?? '—', advance_id: adv.id })
    }
  }
  return result.sort((a, b) => b.date.localeCompare(a.date))
})

const movementColumns: ColumnDef<ARow>[] = [
  {
    accessorKey: 'date',
    header: 'Fecha',
    cell: info => formatDate(info.getValue() as string),
  },
  {
    accessorKey: 'client_name',
    header: 'Cliente',
  },
  {
    accessorKey: 'advance_id',
    header: 'Anticipo',
  },
  {
    accessorKey: 'type_movement',
    header: 'Tipo',
    cell: info => {
      const val = info.getValue() as string
      const isIngreso = val === 'ingreso'
      return h('span', {
        class: isIngreso
          ? 'inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700'
          : 'inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700',
      }, isIngreso ? 'Ingreso' : 'Egreso')
    },
  },
  {
    accessorKey: 'amount',
    header: 'Valor',
    cell: info => formatCurrency(parseFloat(info.getValue() as string)),
  },
  {
    accessorKey: 'trips_quantity',
    header: 'Viajes',
  },
  {
    accessorKey: 'description',
    header: 'Descripción',
    cell: info => (info.getValue() as string | null) ?? '—',
  },
  {
    accessorKey: 'trip',
    header: 'Viaje N°',
    cell: info => info.getValue() ?? '—',
  },
]

// Columnas movimientos Tab 2 (sin client_name)
const estadoMovColumns: ColumnDef<ARow>[] = movementColumns.filter(
  c => !('accessorKey' in c && c.accessorKey === 'client_name')
)

// ── CSV Export ─────────────────────────────────────────────────────────────
function downloadCsv(rows: Record<string, unknown>[], filename: string) {
  if (!rows.length) { toast.info('No hay datos para exportar.'); return }
  const headers = Object.keys(rows[0])
  const csv = [
    headers.join(','),
    ...rows.map(row => headers.map(k => JSON.stringify(row[k] ?? '')).join(',')),
  ].join('\n')
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function exportEstadoCuenta() {
  const clientObj = clients.value.find(c => c.id === selectedClientId.value)
  const rows = selectedClientMovements.value.map(m => ({
    'Fecha': m.date,
    'Anticipo ID': m.advance_id,
    'Tipo': m.type_movement === 'ingreso' ? 'Ingreso' : 'Egreso',
    'Valor': m.amount,
    'Viajes': m.trips_quantity,
    'Descripción': m.description ?? '',
    'Viaje N°': m.trip ?? '',
  }))
  downloadCsv(rows, `estado_cuenta_${clientObj?.abrev_name ?? 'cliente'}.csv`)
}

function exportHistorial() {
  const rows = allMovements.value.map(m => ({
    'Fecha': m.date,
    'Cliente': m.client_name,
    'Anticipo ID': m.advance_id,
    'Tipo': m.type_movement === 'ingreso' ? 'Ingreso' : 'Egreso',
    'Valor': m.amount,
    'Viajes': m.trips_quantity,
    'Descripción': m.description ?? '',
    'Viaje N°': m.trip ?? '',
  }))
  downloadCsv(rows, `historial_movimientos.csv`)
}

// ── Cast data para DataTable ───────────────────────────────────────────────
const advancesRows = computed(() => advances.value as unknown as ARow[])
const estadoAdvanceRows = computed(() => selectedClientAdvances.value as unknown as ARow[])
const estadoMovRows = computed(() => selectedClientMovements.value as unknown as ARow[])
const historialRows = computed(() => allMovements.value as unknown as ARow[])

watch(activeTab, () => {
  filterClientId.value = ''
  filterDateFrom.value = ''
  filterDateTo.value = ''
})
</script>

<template>
  <div class="p-4 lg:p-6 space-y-5">
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h1 class="text-2xl font-semibold text-gray-900">Anticipos</h1>
      <div class="flex flex-wrap gap-2">
        <button
          v-if="canManage && activeTab === 'registro'"
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          @click="openCreate"
        >
          <Plus class="w-4 h-4" />
          Registrar Anticipo
        </button>
        <button
          v-if="activeTab === 'estado' && selectedClientId"
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50 transition-colors"
          @click="exportEstadoCuenta"
        >
          <Download class="w-4 h-4" />
          Exportar CSV
        </button>
        <button
          v-if="activeTab === 'historial' && allMovements.length"
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50 transition-colors"
          @click="exportHistorial"
        >
          <Download class="w-4 h-4" />
          Exportar CSV
        </button>
      </div>
    </div>

    <!-- Alerts panel -->
    <div v-if="visibleAlerts.length" class="space-y-2">
      <div
        v-for="alert in visibleAlerts"
        :key="alert.client.id"
        class="flex items-center justify-between gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm"
      >
        <div class="flex items-center gap-2 text-red-700">
          <AlertTriangle class="w-4 h-4 flex-shrink-0" />
          <span>
            <strong>{{ alert.client.name }}</strong> — Saldo negativo:
            <strong>{{ formatCurrency(alert.balance) }}</strong>
          </span>
        </div>
        <button class="text-red-400 hover:text-red-600 transition-colors" @click="dismissAlert(alert.client.id)">
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="border-b border-gray-200 overflow-x-auto">
      <nav class="flex gap-1 w-max min-w-full" aria-label="Tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
          :class="activeTab === tab.id
            ? 'border-blue-600 text-blue-600'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </nav>
    </div>

    <!-- ── Tab 1: Registro ──────────────────────────────────────────────── -->
    <div v-if="activeTab === 'registro'">
      <DataTable
        :data="advancesRows"
        :columns="registroColumns"
        :is-loading="advancesLoading"
      />
    </div>

    <!-- ── Tab 2: Estado de Cuenta ────────────────────────────────────── -->
    <div v-else-if="activeTab === 'estado'" class="space-y-6">
      <div class="max-w-xs">
        <label class="block text-sm font-medium text-gray-700 mb-1">Seleccionar cliente</label>
        <select
          v-model="selectedClientId"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="">— Selecciona un cliente —</option>
          <option v-for="c in clients" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>

      <template v-if="selectedClientId">
        <!-- Balance cards -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div class="rounded-xl border border-gray-200 bg-white p-5">
            <p class="text-xs text-gray-500 uppercase tracking-wide">Total Ingresado</p>
            <p class="mt-1 text-2xl font-semibold text-green-600">
              {{ formatCurrency(selectedClientTotalIngresado) }}
            </p>
          </div>
          <div class="rounded-xl border border-gray-200 bg-white p-5">
            <p class="text-xs text-gray-500 uppercase tracking-wide">Total Consumido</p>
            <p class="mt-1 text-2xl font-semibold text-red-600">
              {{ formatCurrency(selectedClientTotalConsumido) }}
            </p>
          </div>
          <div
            class="rounded-xl border p-5"
            :class="selectedClientBalance < 0 ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200'"
          >
            <p class="text-xs text-gray-500 uppercase tracking-wide">Saldo Disponible</p>
            <p
              class="mt-1 text-2xl font-semibold"
              :class="selectedClientBalance < 0 ? 'text-red-600' : 'text-blue-700'"
            >
              {{ formatCurrency(selectedClientBalance) }}
            </p>
          </div>
        </div>

        <!-- Lista de anticipos del cliente -->
        <div>
          <h3 class="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
            <FileText class="w-4 h-4 text-gray-400" />
            Anticipos registrados
            <span class="text-xs font-normal text-gray-400">(clic en ojo para ver detalle)</span>
          </h3>
          <DataTable
            :data="estadoAdvanceRows"
            :columns="estadoAdvanceColumns"
          />
        </div>

        <!-- Historial de movimientos del cliente -->
        <div>
          <h3 class="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
            <Truck class="w-4 h-4 text-gray-400" />
            Historial de movimientos
          </h3>
          <DataTable
            :data="estadoMovRows"
            :columns="estadoMovColumns"
          />
        </div>
      </template>

      <div v-else class="flex items-center justify-center h-48 text-gray-400 text-sm">
        Selecciona un cliente para ver su estado de cuenta.
      </div>
    </div>

    <!-- ── Tab 3: Historial ────────────────────────────────────────────── -->
    <div v-else class="space-y-4">
      <div class="flex flex-wrap gap-3">
        <div>
          <label class="block text-xs text-gray-500 mb-1">Cliente</label>
          <select
            v-model="filterClientId"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Todos</option>
            <option v-for="c in clients" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Desde</label>
          <input
            v-model="filterDateFrom"
            type="date"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Hasta</label>
          <input
            v-model="filterDateTo"
            type="date"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div class="flex items-end">
          <button
            class="px-3 py-2 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg transition-colors"
            @click="filterClientId = ''; filterDateFrom = ''; filterDateTo = ''"
          >
            Limpiar
          </button>
        </div>
      </div>

      <DataTable
        :data="historialRows"
        :columns="movementColumns"
        :is-loading="advancesLoading"
      />
    </div>
  </div>

  <!-- ── Panel de detalle (drawer lateral) ─────────────────────────────── -->
  <Teleport to="body">
    <template v-if="detailAdvance">
      <!-- Overlay -->
      <div
        class="fixed inset-0 z-40 bg-black/30"
        @click="closeDetail"
      />

      <!-- Drawer -->
      <div class="fixed inset-y-0 right-0 z-50 flex flex-col w-full max-w-md bg-white shadow-2xl border-l border-gray-200">
        <!-- Drawer header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <div>
            <p class="text-xs text-gray-400 uppercase tracking-wide">Detalle del anticipo</p>
            <p class="text-base font-semibold text-gray-900 mt-0.5">
              {{ detailAdvance.client_detail?.name }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="isSuperuser"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-700 text-xs font-medium hover:bg-amber-100 transition-colors"
              @click="openEdit(detailAdvance); closeDetail()"
            >
              <Pencil class="w-3.5 h-3.5" />
              Editar
            </button>
            <button
              class="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
              @click="closeDetail"
            >
              <X class="w-5 h-5" />
            </button>
          </div>
        </div>

        <!-- Drawer body -->
        <div class="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          <!-- Datos principales -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <p class="text-xs text-gray-400 uppercase tracking-wide mb-1">Fecha</p>
              <p class="text-sm font-medium text-gray-900">{{ formatDate(detailAdvance.date) }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 uppercase tracking-wide mb-1">Valor del anticipo</p>
              <p class="text-sm font-semibold text-gray-900">{{ formatCurrency(parseFloat(detailAdvance.value)) }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 uppercase tracking-wide mb-1">N° Consignación</p>
              <p class="text-sm font-medium text-gray-900">{{ detailAdvance.transfer_num }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400 uppercase tracking-wide mb-1">N° Proforma</p>
              <p class="text-sm font-medium text-gray-900">{{ detailAdvance.proforma_number ?? '—' }}</p>
            </div>
          </div>

          <!-- Saldo disponible -->
          <div
            class="rounded-xl p-4 border"
            :class="detailAdvance.available_balance < 0
              ? 'bg-red-50 border-red-200'
              : detailAdvance.available_balance === 0
                ? 'bg-gray-50 border-gray-200'
                : 'bg-green-50 border-green-200'"
          >
            <p class="text-xs text-gray-500 uppercase tracking-wide">Saldo Disponible</p>
            <p
              class="text-2xl font-bold mt-1"
              :class="detailAdvance.available_balance < 0 ? 'text-red-600' : detailAdvance.available_balance === 0 ? 'text-gray-400' : 'text-green-700'"
            >
              {{ formatCurrency(detailAdvance.available_balance) }}
            </p>
          </div>

          <!-- Observaciones -->
          <div>
            <p class="text-xs text-gray-400 uppercase tracking-wide mb-2">Observaciones</p>
            <div
              class="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700 min-h-[60px]"
            >
              {{ detailAdvance.observations || 'Sin observaciones.' }}
            </div>
          </div>

          <!-- Movimientos -->
          <div>
            <p class="text-xs text-gray-400 uppercase tracking-wide mb-3">
              Movimientos ({{ detailAdvance.movements.length }})
            </p>
            <div
              v-if="!detailAdvance.movements.length"
              class="text-sm text-gray-400 text-center py-4"
            >
              Sin movimientos registrados.
            </div>
            <div v-else class="space-y-2">
              <div
                v-for="mov in [...detailAdvance.movements].sort((a, b) => b.date.localeCompare(a.date))"
                :key="mov.id"
                class="flex items-start gap-3 rounded-lg border border-gray-100 bg-white px-4 py-3"
              >
                <span
                  class="mt-0.5 inline-flex flex-shrink-0 px-2 py-0.5 rounded-full text-xs font-medium"
                  :class="mov.type_movement === 'ingreso'
                    ? 'bg-green-100 text-green-700'
                    : 'bg-red-100 text-red-700'"
                >
                  {{ mov.type_movement === 'ingreso' ? 'Ingreso' : 'Egreso' }}
                </span>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center justify-between gap-2">
                    <p class="text-sm font-semibold text-gray-900">
                      {{ formatCurrency(parseFloat(mov.amount)) }}
                    </p>
                    <p class="text-xs text-gray-400">{{ formatDate(mov.date) }}</p>
                  </div>
                  <p class="text-xs text-gray-500 mt-0.5 truncate">
                    {{ mov.description ?? '—' }}
                  </p>
                  <div class="flex gap-3 mt-1 text-xs text-gray-400">
                    <span v-if="mov.trips_quantity > 0">Viajes: {{ mov.trips_quantity }}</span>
                    <span v-if="mov.trip">Viaje N°: {{ mov.trip }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </Teleport>

  <!-- ── Modal: Registrar / Editar Anticipo ────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="showModal"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      @click.self="closeModal"
    >
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <!-- Modal header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <h2 class="text-base font-semibold text-gray-900">
            {{ editingAdvance ? 'Editar Anticipo' : 'Registrar Anticipo' }}
          </h2>
          <button class="text-gray-400 hover:text-gray-600 transition-colors" @click="closeModal">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Modal body -->
        <form class="px-6 py-5 space-y-4 overflow-y-auto" @submit.prevent="onSubmit">
          <!-- Cliente -->
          <div v-if="!editingAdvance">
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Cliente <span class="text-red-500">*</span>
            </label>
            <select
              v-model="clientId"
              class="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="clientError ? 'border-red-400' : 'border-gray-300'"
            >
              <option :value="undefined">— Selecciona un cliente —</option>
              <option v-for="c in clients" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <p v-if="clientError" class="mt-1 text-xs text-red-500">{{ clientError }}</p>
          </div>
          <div v-else>
            <label class="block text-sm font-medium text-gray-700 mb-1">Cliente</label>
            <p class="px-3 py-2 bg-gray-50 rounded-lg text-sm text-gray-600">
              {{ editingAdvance.client_detail?.name }}
            </p>
          </div>

          <!-- Fecha -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Fecha <span class="text-red-500">*</span>
            </label>
            <input
              v-model="dateVal"
              type="date"
              class="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="dateError ? 'border-red-400' : 'border-gray-300'"
            />
            <p v-if="dateError" class="mt-1 text-xs text-red-500">{{ dateError }}</p>
          </div>

          <!-- Valor -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Valor <span class="text-red-500">*</span>
            </label>
            <CurrencyInput
              :model-value="(valueField as number | null) ?? null"
              :class="valueError ? 'ring-1 ring-red-400' : ''"
              @update:model-value="handleValueChange($event)"
            />
            <p v-if="valueError" class="mt-1 text-xs text-red-500">{{ valueError }}</p>
          </div>

          <!-- N° Consignación -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              N° Consignación <span class="text-red-500">*</span>
            </label>
            <input
              v-model.number="transferNum"
              type="number"
              step="1"
              min="1"
              placeholder="Ej: 123456"
              class="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="transferNumError ? 'border-red-400' : 'border-gray-300'"
            />
            <p v-if="transferNumError" class="mt-1 text-xs text-red-500">{{ transferNumError }}</p>
          </div>

          <!-- N° Viajes (solo en creación) -->
          <div v-if="!editingAdvance">
            <label class="block text-sm font-medium text-gray-700 mb-1">N° de Viajes</label>
            <input
              v-model.number="tripsQty"
              type="number"
              step="1"
              min="0"
              placeholder="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="tripsQtyError ? 'border-red-400' : 'border-gray-300'"
            />
            <p v-if="tripsQtyError" class="mt-1 text-xs text-red-500">{{ tripsQtyError }}</p>
            <p class="mt-1 text-xs text-gray-400">Cantidad de viajes asociados al ingreso inicial del anticipo.</p>
          </div>

          <!-- N° Proforma -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">N° Proforma</label>
            <input
              v-model.number="proformaNum"
              type="number"
              step="1"
              min="1"
              placeholder="Opcional"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <!-- Observaciones -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Observaciones</label>
            <textarea
              v-model="observations"
              rows="3"
              placeholder="Opcional"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
          </div>

          <!-- Footer -->
          <div class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              @click="closeModal"
            >
              Cancelar
            </button>
            <button
              type="submit"
              :disabled="isSubmitting"
              class="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {{ isSubmitting ? 'Guardando...' : (editingAdvance ? 'Guardar cambios' : 'Registrar') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>
