<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Plus, Pencil, Download, AlertTriangle, X, Eye, FileText, Truck, Wrench } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'

type ARow = Record<string, unknown>

import DataTable from '@/components/shared/DataTable.vue'
import CurrencyInput from '@/components/shared/CurrencyInput.vue'
import SearchableSelect from '@/components/shared/SearchableSelect.vue'
import { advancesApi } from '@/api/advances.api'
import { clientsApi } from '@/api/clients.api'
import { getApiErrorMessage, toastApiError } from '@/utils/handleApiError'
import { useAuthStore } from '@/stores/auth.store'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, todayBogota } from '@/utils/formatDate'
import type { Advance, AdvanceMovement, Client, AdvanceCorrectValuePreview } from '@/types'

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
// cajero: sin Historial de Movimientos (solo Registro y Estado de Cuenta)
const visibleTabs = computed(() =>
  authStore.user?.role === 'cashier' ? tabs.filter(t => t.id !== 'historial') : tabs
)

// ── Queries ────────────────────────────────────────────────────────────────
const { data: advancesData, isLoading: advancesLoading } = useQuery({
  queryKey: ['advances'],
  queryFn: () => advancesApi.list().then(r => r.data),
  refetchInterval: 8_000,
})
const advances = computed(() => advancesData.value ?? [])

const { data: pendingDebtsSummaryData } = useQuery({
  queryKey: ['advances-pending-debts-summary'],
  queryFn: () => advancesApi.pendingDebtsSummary().then(r => r.data),
  refetchInterval: 8_000,
})
// Claves del objeto son client_id como string (formato JSON) — se busca por
// String(clientId) al leerlo.
const pendingDebtsByClient = computed(() => pendingDebtsSummaryData.value ?? {})

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
    date: todayBogota(),
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
    date: todayBogota(),
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

// ── Corrección de valor original (Superusuario/Contador/Admin Comercial) ──
// Única forma real de cambiar `value` una vez el anticipo tiene movimientos
// (siempre, desde que se crea) — ver advancesApi.correctValue.
const correctingAdvance   = ref<Advance | null>(null)
const correctValueInput   = ref<number | undefined>(undefined)
const correctJustification = ref('')
const correctPreview        = ref<AdvanceCorrectValuePreview | null>(null)
const correctPreviewLoading = ref(false)
const correctSubmitLoading  = ref(false)

function openCorrectValue(advance: Advance) {
  correctingAdvance.value    = advance
  correctValueInput.value    = parseFloat(advance.value)
  correctJustification.value = ''
  correctPreview.value       = null
}

function closeCorrectValue() {
  correctingAdvance.value = null
  correctPreview.value    = null
}

// Previsualiza (debounced, sin escribir nada) el impacto ANTES de que el
// usuario confirme — si la reducción deja el saldo negativo, el backend
// devuelve qué viajes quedarían como deuda pendiente.
let correctPreviewTimeout: ReturnType<typeof setTimeout> | undefined
watch(correctValueInput, (val) => {
  if (correctPreviewTimeout) clearTimeout(correctPreviewTimeout)
  correctPreview.value = null
  if (!correctingAdvance.value || val === undefined || val === null || val <= 0) return
  if (val === parseFloat(correctingAdvance.value.value)) return

  const advanceId = correctingAdvance.value.id
  correctPreviewTimeout = setTimeout(async () => {
    correctPreviewLoading.value = true
    try {
      const res = await advancesApi.previewCorrectValue(advanceId, val)
      correctPreview.value = res.data
    } catch (err) {
      toastApiError(err)
    } finally {
      correctPreviewLoading.value = false
    }
  }, 400)
})

const correctWouldUnlink = computed(() => (correctPreview.value?.trips_to_unlink.length ?? 0) > 0)

async function submitCorrectValue() {
  if (!correctingAdvance.value || correctValueInput.value === undefined) return
  if (!correctJustification.value.trim()) {
    toast.error('La justificación es obligatoria para corregir el valor de un anticipo.')
    return
  }
  correctSubmitLoading.value = true
  try {
    const res = await advancesApi.correctValue(correctingAdvance.value.id, {
      correct_value: correctValueInput.value,
      justification: correctJustification.value.trim(),
    })
    const settledCount = res.data.settled_trips.length
    toast.success(
      settledCount > 0
        ? `Valor corregido correctamente. Se liquidaron ${settledCount} viaje(s) de deuda pendiente.`
        : 'Valor del anticipo corregido correctamente.'
    )
    qc.invalidateQueries({ queryKey: ['advances'] })
    qc.invalidateQueries({ queryKey: ['advances-pending-debts-summary'] })
    qc.invalidateQueries({ queryKey: ['advance-balance'] })
    closeCorrectValue()
  } catch (err) {
    toastApiError(err)
  } finally {
    correctSubmitLoading.value = false
  }
}

const createMutation = useMutation({
  mutationFn: (data: Parameters<typeof advancesApi.create>[0]) => advancesApi.create(data),
  onSuccess: () => {
    toast.success('Anticipo registrado correctamente.')
    qc.invalidateQueries({ queryKey: ['advances'] })
    closeModal()
  },
  onError: (err) => toastApiError(err),
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
  onError: (err) => toastApiError(err),
})

const onSubmit = handleSubmit(async (values) => {
  // mutateAsync sigue rechazando la promesa aunque onError ya haya mostrado
  // el toast — sin este try/catch, cualquier error de validación (ej. editar
  // `value` de un anticipo con movimientos) quedaba como unhandled rejection
  // en consola además del toast.
  try {
    if (editingAdvance.value) {
      // `value` no va aquí: una vez el anticipo tiene movimientos (siempre,
      // desde que se crea) el backend lo bloquea de plano — para eso existe
      // el flujo separado "Corregir valor" (openCorrectValue más abajo).
      await updateMutation.mutateAsync({
        id: editingAdvance.value.id,
        data: {
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
  } catch {
    // ya manejado por onError de cada mutación (toastApiError)
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
          class: 'p-1 text-gray-400 hover:text-gold-700 transition-colors',
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
        canManage.value
          ? h('button', {
              class: 'p-1 text-gray-400 hover:text-gold-700 transition-colors',
              title: 'Corregir valor',
              onClick: () => openCorrectValue(adv),
            }, h(Wrench, { class: 'w-4 h-4' }))
          : null,
      ])
    },
  },
]

// ── Tab 2: Estado de Cuenta ────────────────────────────────────────────────
const selectedClientId = ref<number | null>(null)

const selectedClientAdvances = computed(() =>
  selectedClientId.value
    ? advances.value.filter(a => a.client === selectedClientId.value)
    : []
)

// Deuda pendiente y saldo neto real del cliente (viajes registrados sin
// saldo suficiente, aún sin liquidar contra ningún anticipo — ver
// AdvanceBalanceView/settle_pending_debts en el backend). La suma simple de
// `available_balance` de los anticipos (selectedClientBalance, más abajo) NO
// incluye esta deuda, así que puede mostrar un saldo más alto del real.
const { data: selectedClientBalanceData } = useQuery({
  queryKey: computed(() => ['advance-balance', selectedClientId.value]),
  queryFn: () => selectedClientId.value
    ? advancesApi.balance(selectedClientId.value).then(r => r.data)
    : Promise.resolve(null),
  enabled: computed(() => !!selectedClientId.value),
  refetchInterval: 8_000,
})
const pendingDebts = computed(() => selectedClientBalanceData.value?.pending_debts ?? [])
const totalPendingDebt = computed(() => Number(selectedClientBalanceData.value?.total_pending_debt ?? 0))

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

const selectedClientAdvancesBalance = computed(() =>
  selectedClientAdvances.value.reduce((s, a) => s + a.available_balance, 0)
)
// Saldo neto real: saldo de anticipos menos deuda pendiente sin liquidar.
const selectedClientBalance = computed(() =>
  selectedClientAdvancesBalance.value - totalPendingDebt.value
)

// Resumen de saldos de todos los clientes (vista antes de seleccionar uno)
type ClientSummaryRow = {
  client: Client
  totalIngresado: number
  totalConsumido: number
  pendingDebt: number
  saldo: number
}

const clientsSummary = computed<ClientSummaryRow[]>(() =>
  clients.value.map(c => {
    const clientAdvances = advances.value.filter(a => a.client === c.id)
    const movements = clientAdvances.flatMap(a => a.movements)
    const totalIngresado = movements
      .filter(m => m.type_movement === 'ingreso')
      .reduce((s, m) => s + parseFloat(m.amount), 0)
    const totalConsumido = movements
      .filter(m => m.type_movement === 'egreso')
      .reduce((s, m) => s + parseFloat(m.amount), 0)
    const advancesBalance = clientAdvances.reduce((s, a) => s + a.available_balance, 0)
    const pendingDebt = Number(pendingDebtsByClient.value[String(c.id)] ?? 0)
    return { client: c, totalIngresado, totalConsumido, pendingDebt, saldo: advancesBalance - pendingDebt }
  })
)

const clientsSummaryColumns: ColumnDef<ARow>[] = [
  {
    accessorFn: row => (row as unknown as ClientSummaryRow).client.name,
    id: 'client_name',
    header: 'Cliente',
  },
  {
    accessorKey: 'totalIngresado',
    header: 'Saldo Total',
    cell: info => formatCurrency(info.getValue() as number),
  },
  {
    accessorKey: 'totalConsumido',
    header: 'Saldo Ejecutado',
    cell: info => formatCurrency(info.getValue() as number),
  },
  {
    accessorKey: 'pendingDebt',
    header: 'Deuda Pendiente',
    cell: info => {
      const val = info.getValue() as number
      return val > 0 ? h('span', { class: 'text-amber-600 font-medium' }, formatCurrency(val)) : '—'
    },
  },
  {
    accessorKey: 'saldo',
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
      class: 'p-1 text-gray-400 hover:text-gold-700 transition-colors',
      title: 'Ver estado de cuenta',
      onClick: () => { selectedClientId.value = (info.row.original as unknown as ClientSummaryRow).client.id },
    }, h(Eye, { class: 'w-4 h-4' })),
  },
]

type MovementRow = AdvanceMovement & { client_name: string; advance_id: number }

// `date` es un DateField (solo día, sin hora) — dos movimientos del mismo
// día quedaban en orden indeterminado ordenando solo por esa columna. `id`
// refleja el orden real de creación, así que desempata de forma consistente
// (más reciente primero = id más alto primero).
function sortMovementsDesc<T extends { date: string; id: number }>(movements: T[]): T[] {
  return [...movements].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id)
}

const selectedClientMovements = computed<MovementRow[]>(() =>
  sortMovementsDesc(
    selectedClientAdvances.value.flatMap(a =>
      a.movements.map(m => ({ ...m, client_name: a.client_detail?.name ?? '—', advance_id: a.id }))
    )
  )
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
      class: 'p-1 text-gray-400 hover:text-gold-700 transition-colors',
      title: 'Ver detalle',
      onClick: () => openDetail(info.row.original as unknown as Advance),
    }, h(Eye, { class: 'w-4 h-4' })),
  },
]

// ── Tab 3: Historial ───────────────────────────────────────────────────────
const filterClientId = ref<number | null>(null)
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
  return sortMovementsDesc(result)
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
const clientsSummaryRows = computed(() => clientsSummary.value as unknown as ARow[])
const estadoMovRows = computed(() => selectedClientMovements.value as unknown as ARow[])
const historialRows = computed(() => allMovements.value as unknown as ARow[])

watch(activeTab, () => {
  filterClientId.value = null
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
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gold-500 text-stone-900 text-sm font-medium hover:bg-gold-600 transition-colors"
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
          v-for="tab in visibleTabs"
          :key="tab.id"
          class="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
          :class="activeTab === tab.id
            ? 'border-gold-500 text-gold-700'
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
        <SearchableSelect
          :options="clients"
          v-model="selectedClientId"
          placeholder="Buscar cliente..."
          clearable
        />
      </div>

      <template v-if="selectedClientId">
        <!-- Balance cards -->
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4" :class="totalPendingDebt > 0 ? 'lg:grid-cols-4' : ''">
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
            :class="selectedClientBalance < 0 ? 'bg-red-50 border-red-200' : 'bg-gold-50 border-gold-200'"
          >
            <p class="text-xs text-gray-500 uppercase tracking-wide">Saldo Disponible</p>
            <p
              class="mt-1 text-2xl font-semibold"
              :class="selectedClientBalance < 0 ? 'text-red-600' : 'text-gold-800'"
            >
              {{ formatCurrency(selectedClientBalance) }}
            </p>
          </div>
          <div v-if="totalPendingDebt > 0" class="rounded-xl border bg-amber-50 border-amber-200 p-5">
            <p class="text-xs text-amber-700 uppercase tracking-wide">Deuda Pendiente</p>
            <p class="mt-1 text-2xl font-semibold text-amber-700">
              {{ formatCurrency(totalPendingDebt) }}
            </p>
          </div>
        </div>

        <!-- Viajes registrados como deuda pendiente, aún sin liquidar contra
             ningún anticipo — se liquidan automáticamente (FIFO) cuando se
             registre el próximo anticipo de este cliente. -->
        <div v-if="pendingDebts.length > 0">
          <h3 class="text-sm font-semibold text-amber-700 mb-2 flex items-center gap-2">
            <AlertTriangle class="w-4 h-4" />
            Deuda pendiente por liquidar
          </h3>
          <div class="rounded-xl border border-amber-200 overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-amber-50">
                <tr>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-amber-700 uppercase tracking-wide">Vale</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-amber-700 uppercase tracking-wide">Fecha</th>
                  <th class="px-4 py-2 text-right text-xs font-semibold text-amber-700 uppercase tracking-wide">Valor</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-amber-700 uppercase tracking-wide">Justificación</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-amber-100 bg-white">
                <tr v-for="d in pendingDebts" :key="d.trip">
                  <td class="px-4 py-2 font-medium text-gray-900">#{{ d.voucher_num }}</td>
                  <td class="px-4 py-2 text-gray-700">{{ formatDate(d.date) }}</td>
                  <td class="px-4 py-2 text-right font-semibold text-amber-700">{{ formatCurrency(parseFloat(d.value)) }}</td>
                  <td class="px-4 py-2 text-gray-600">{{ d.justification || '—' }}</td>
                </tr>
              </tbody>
            </table>
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

      <div v-else>
        <h3 class="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2">
          <FileText class="w-4 h-4 text-gray-400" />
          Clientes
          <span class="text-xs font-normal text-gray-400">(clic en el ojo para ver el estado de cuenta)</span>
        </h3>
        <DataTable
          :data="clientsSummaryRows"
          :columns="clientsSummaryColumns"
          :is-loading="advancesLoading"
        />
      </div>
    </div>

    <!-- ── Tab 3: Historial ────────────────────────────────────────────── -->
    <div v-else class="space-y-4">
      <div class="flex flex-wrap gap-3">
        <div class="w-56">
          <label class="block text-xs text-gray-500 mb-1">Cliente</label>
          <SearchableSelect
            :options="clients"
            v-model="filterClientId"
            placeholder="Todos"
            clearable
          />
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Desde</label>
          <input
            v-model="filterDateFrom"
            type="date"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
          />
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">Hasta</label>
          <input
            v-model="filterDateTo"
            type="date"
            class="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
          />
        </div>
        <div class="flex items-end">
          <button
            class="px-3 py-2 text-sm text-gray-500 hover:text-gray-700 border border-gray-300 rounded-lg transition-colors"
            @click="filterClientId = null; filterDateFrom = ''; filterDateTo = ''"
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

  <!-- ── Panel de detalle ───────────────────────────────────────────────── -->
  <Teleport to="body">
    <div v-if="detailAdvance" class="fixed inset-0 z-50 flex items-center justify-center p-4">
      <!-- Overlay -->
      <div
        class="absolute inset-0 bg-black/30"
        @click="closeDetail"
      />

      <!-- Panel -->
      <div class="relative flex flex-col w-full max-w-md max-h-[85vh] rounded-xl bg-white shadow-2xl overflow-hidden">
        <!-- Drawer header -->
        <div class="flex items-center justify-between px-6 py-4 border-b-2 border-gold-200 bg-gold-50/40 flex-shrink-0">
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
              v-if="canManage"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gold-300 bg-gold-50 text-gold-700 text-xs font-medium hover:bg-gold-100 transition-colors"
              @click="openCorrectValue(detailAdvance); closeDetail()"
            >
              <Wrench class="w-3.5 h-3.5" />
              Corregir valor
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
                v-for="mov in sortMovementsDesc(detailAdvance.movements)"
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
    </div>
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
        <div class="flex items-center justify-between px-6 py-4 border-b-2 border-gold-200 bg-gold-50/40 flex-shrink-0">
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
            <SearchableSelect
              :options="clients"
              v-model="clientId"
              placeholder="Buscar cliente..."
            />
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
              class="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
              :class="dateError ? 'border-red-400' : 'border-gray-300'"
            />
            <p v-if="dateError" class="mt-1 text-xs text-red-500">{{ dateError }}</p>
          </div>

          <!-- Valor: solo editable al crear — una vez el anticipo tiene
               movimientos (siempre, desde que se crea) el backend bloquea
               este campo de plano; para eso existe "Corregir valor". -->
          <div v-if="!editingAdvance">
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
          <div v-else>
            <label class="block text-sm font-medium text-gray-700 mb-1">Valor original</label>
            <p class="px-3 py-2 bg-gray-50 rounded-lg text-sm text-gray-600">
              {{ formatCurrency(parseFloat(editingAdvance.value)) }}
            </p>
            <button
              v-if="canManage"
              type="button"
              @click="openCorrectValue(editingAdvance); closeModal()"
              class="mt-1 text-xs text-gold-700 hover:text-gold-800 font-medium underline underline-offset-2"
            >
              Corregir valor
            </button>
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
              class="w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
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
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
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
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400"
            />
          </div>

          <!-- Observaciones -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Observaciones</label>
            <textarea
              v-model="observations"
              rows="3"
              placeholder="Opcional"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400 resize-none"
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
              class="px-4 py-2 text-sm font-medium bg-gold-500 text-stone-900 rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {{ isSubmitting ? 'Guardando...' : (editingAdvance ? 'Guardar cambios' : 'Registrar') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>

  <!-- ── Modal: Corregir valor del anticipo ─────────────────────────────── -->
  <Teleport to="body">
    <div
      v-if="correctingAdvance"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      @click.self="closeCorrectValue"
    >
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <div class="flex items-center justify-between px-6 py-4 border-b-2 border-gold-200 bg-gold-50/40 flex-shrink-0">
          <h2 class="text-base font-semibold text-gray-900">Corregir valor del anticipo</h2>
          <button class="text-gray-400 hover:text-gray-600 transition-colors" @click="closeCorrectValue">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="px-6 py-5 space-y-4 overflow-y-auto">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wide">Cliente</p>
              <p class="text-sm font-medium text-gray-900">{{ correctingAdvance.client_detail?.name }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-500 uppercase tracking-wide">Valor original</p>
              <p class="text-sm font-medium text-gray-900">{{ formatCurrency(parseFloat(correctingAdvance.value)) }}</p>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Valor correcto <span class="text-red-500">*</span>
            </label>
            <CurrencyInput
              :model-value="correctValueInput ?? null"
              @update:model-value="correctValueInput = $event ?? undefined"
            />
          </div>

          <p v-if="correctPreviewLoading" class="text-xs text-gray-400">Calculando impacto...</p>

          <div v-else-if="correctWouldUnlink" class="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-2">
            <p class="text-sm font-semibold text-amber-700 flex items-center gap-1.5">
              <AlertTriangle class="w-4 h-4 shrink-0" />
              Esta corrección dejará como deuda pendiente:
            </p>
            <ul class="text-xs text-amber-700 space-y-1 pl-1">
              <li v-for="t in correctPreview?.trips_to_unlink" :key="t.trip">
                Vale #{{ t.voucher_num }} — {{ formatCurrency(parseFloat(t.value)) }}
              </li>
            </ul>
            <p class="text-xs text-amber-600">
              Estos viajes se liquidarán automáticamente contra el próximo anticipo que se le registre a este cliente.
            </p>
          </div>

          <p v-else-if="correctPreview" class="text-xs text-gray-500">
            Saldo disponible resultante: <strong>{{ formatCurrency(parseFloat(correctPreview.prospective_balance)) }}</strong>
          </p>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Justificación <span class="text-red-500">*</span>
            </label>
            <textarea
              v-model="correctJustification"
              rows="3"
              placeholder="Motivo de la corrección..."
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400 resize-none"
            />
          </div>
        </div>

        <div class="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-100 flex-shrink-0">
          <button
            type="button"
            @click="closeCorrectValue"
            :disabled="correctSubmitLoading"
            class="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
          >
            Cancelar
          </button>
          <button
            type="button"
            :disabled="correctSubmitLoading || !correctValueInput || !correctJustification.trim()"
            @click="submitCorrectValue"
            class="px-4 py-2 text-sm font-medium bg-gold-500 text-stone-900 rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {{ correctSubmitLoading ? 'Aplicando...' : 'Confirmar corrección' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
