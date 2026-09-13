<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Pencil, Loader2, X, Ban, Plus } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'

import PageHeader from '@/components/shared/PageHeader.vue'
import DataTable from '@/components/shared/DataTable.vue'
import CurrencyInput from '@/components/shared/CurrencyInput.vue'
import DatePickerInput from '@/components/shared/DatePickerInput.vue'
import SearchableSelect from '@/components/shared/SearchableSelect.vue'
import { pendingEntriesApi } from '@/api/pendingEntries.api'
import { clientsApi } from '@/api/clients.api'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import type { PendingEntry, PendingEntryType, PendingEntryStatus } from '@/types'
import { usePermissions } from '@/composables/usePermissions'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, todayBogota } from '@/utils/formatDate'
import { toastApiError } from '@/utils/handleApiError'

const { canCreate, canEdit } = usePermissions()
const queryClient = useQueryClient()
const todayISO = todayBogota()

const ENTRY_TYPE_LABELS: Record<PendingEntryType, string> = {
  advance: 'Anticipo',
  transfer: 'Transferencia',
}

const STATUS_LABELS: Record<PendingEntryStatus, string> = {
  pending: 'Pendiente',
  executed: 'Ejecutado',
  cancelled: 'Cancelado',
}

const STATUS_STYLES: Record<PendingEntryStatus, string> = {
  pending: 'bg-amber-50 text-amber-700',
  executed: 'bg-green-50 text-green-700',
  cancelled: 'bg-gray-100 text-gray-500',
}

// ── Filtros ───────────────────────────────────────────────────────────────────
const filterType = ref<'all' | PendingEntryType>('all')
const filterStatus = ref<'all' | PendingEntryStatus>('pending')

const queryParams = computed(() => ({
  ...(filterType.value !== 'all' ? { entry_type: filterType.value } : {}),
  ...(filterStatus.value !== 'all' ? { status: filterStatus.value } : {}),
}))

const { data: entriesData, isLoading } = useQuery({
  queryKey: computed(() => ['pending-entries', queryParams.value]),
  queryFn: () => pendingEntriesApi.list(queryParams.value).then(r => r.data),
})
const entries = computed(() => entriesData.value ?? [])

// ── Opciones ──────────────────────────────────────────────────────────────────
const { data: clientsData } = useQuery({
  queryKey: ['clients', { state: 'true' }],
  queryFn: () => clientsApi.list({ state: 'true' }).then(r => r.data),
})
const clientOptions = computed(() => clientsData.value ?? [])

const { data: paymentMethodsData } = useQuery({
  queryKey: ['payment-methods'],
  queryFn: () => paymentMethodsApi.list().then(r => r.data),
})
// Una transferencia pendiente nunca se paga en efectivo ni con anticipo
// (ambos son otros conceptos ya cubiertos por sus propios flujos) — solo se
// ofrecen los demás medios de pago activos (transferencia, cheque, etc.).
const paymentMethodOptions = computed(() =>
  (paymentMethodsData.value ?? []).filter(p =>
    p.state && !p.is_advance && p.name.toUpperCase() !== 'EFECTIVO'
  )
)

// ── Modal crear/editar ────────────────────────────────────────────────────────
const modalOpen = ref(false)
const editingEntry = ref<PendingEntry | null>(null)

const formSchema = toTypedSchema(
  z.object({
    entry_type: z.enum(['advance', 'transfer']),
    client: z.number({ error: 'Debe seleccionar un cliente' }).positive('Debe seleccionar un cliente'),
    value: z.number({ error: 'El valor es requerido' }).positive('El valor debe ser mayor a cero'),
    date: z.string().min(1, 'La fecha es requerida'),
    payment_method: z.number().nullable().optional(),
    observations: z.string().optional(),
  }).superRefine((data, ctx) => {
    if (data.entry_type === 'transfer' && !data.payment_method) {
      ctx.addIssue({
        code: 'custom',
        path: ['payment_method'],
        message: 'El método de pago es obligatorio para una transferencia pendiente.',
      })
    }
  })
)

const { handleSubmit, resetForm, isSubmitting, setValues } = useForm({
  validationSchema: formSchema,
  initialValues: {
    entry_type: 'advance' as PendingEntryType,
    client: undefined as unknown as number,
    value: undefined as unknown as number,
    date: todayISO,
    payment_method: null as number | null,
    observations: '',
  },
})

const { value: entryType } = useField<PendingEntryType>('entry_type')
const { value: fClient, errorMessage: clientError } = useField<number>('client')
const { value: fValue, errorMessage: valueError } = useField<number>('value')
const { value: fDate, errorMessage: dateError } = useField<string>('date')
const { value: fPaymentMethod, errorMessage: paymentMethodError } = useField<number | null>('payment_method')
const { value: fObservations } = useField<string>('observations')

function openCreate() {
  editingEntry.value = null
  resetForm({
    values: {
      entry_type: 'advance',
      client: undefined as unknown as number,
      value: undefined as unknown as number,
      date: todayISO,
      payment_method: null,
      observations: '',
    },
  })
  modalOpen.value = true
}

function openEdit(entry: PendingEntry) {
  editingEntry.value = entry
  setValues({
    entry_type: entry.entry_type,
    client: entry.client,
    value: Number(entry.value),
    date: entry.date,
    payment_method: entry.payment_method,
    observations: entry.observations ?? '',
  })
  modalOpen.value = true
}

function closeModal() {
  modalOpen.value = false
  editingEntry.value = null
}

const { mutateAsync: createEntry } = useMutation({ mutationFn: pendingEntriesApi.create })
const { mutateAsync: updateEntry } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Parameters<typeof pendingEntriesApi.update>[1] }) =>
    pendingEntriesApi.update(id, data),
})

const onSubmit = handleSubmit(async (values) => {
  try {
    if (editingEntry.value) {
      // entry_type es inmutable tras la creación — no se manda en la edición.
      await updateEntry({
        id: editingEntry.value.id,
        data: {
          client: values.client,
          value: values.value,
          date: values.date,
          payment_method: values.entry_type === 'transfer' ? values.payment_method : null,
          observations: values.observations || null,
        },
      })
      toast.success('Pendiente actualizado correctamente.')
    } else {
      await createEntry({
        entry_type: values.entry_type,
        client: values.client,
        value: values.value,
        date: values.date,
        payment_method: values.entry_type === 'transfer' ? values.payment_method : null,
        observations: values.observations || undefined,
      })
      toast.success('Pendiente registrado correctamente.')
    }
    closeModal()
    queryClient.invalidateQueries({ queryKey: ['pending-entries'] })
  } catch (err) {
    toastApiError(err)
  }
})

// ── Cancelar ──────────────────────────────────────────────────────────────────
const cancellingEntry = ref<PendingEntry | null>(null)
const cancelJustification = ref('')
const cancelLoading = ref(false)

function openCancel(entry: PendingEntry) {
  cancellingEntry.value = entry
  cancelJustification.value = ''
}

function closeCancel() {
  cancellingEntry.value = null
}

async function confirmCancel() {
  if (!cancellingEntry.value) return
  if (!cancelJustification.value.trim()) {
    toast.error('Debe justificar la cancelación.')
    return
  }
  cancelLoading.value = true
  try {
    await pendingEntriesApi.cancel(cancellingEntry.value.id, { justification: cancelJustification.value.trim() })
    toast.success(`Pendiente #${cancellingEntry.value.id} cancelado.`)
    closeCancel()
    queryClient.invalidateQueries({ queryKey: ['pending-entries'] })
  } catch (err) {
    toastApiError(err)
  } finally {
    cancelLoading.value = false
  }
}

// ── Tabla ─────────────────────────────────────────────────────────────────────
const columns: ColumnDef<PendingEntry>[] = [
  {
    accessorKey: 'date',
    header: 'Fecha',
    cell: ({ row }) => formatDate(row.original.date),
  },
  {
    id: 'client',
    header: 'Cliente',
    cell: ({ row }) => row.original.client_detail?.name ?? '—',
  },
  {
    accessorKey: 'entry_type',
    header: 'Tipo',
    cell: ({ row }) => ENTRY_TYPE_LABELS[row.original.entry_type],
  },
  {
    accessorKey: 'value',
    header: 'Valor',
    cell: ({ row }) => h('span', { class: 'font-medium text-gray-900' }, formatCurrency(Number(row.original.value))),
  },
  {
    id: 'payment_method',
    header: 'Método de pago',
    cell: ({ row }) => row.original.payment_method_detail?.name ?? '—',
  },
  {
    id: 'status',
    header: 'Estado',
    enableSorting: false,
    cell: ({ row }) => h('span', {
      class: `text-xs font-medium px-2 py-0.5 rounded ${STATUS_STYLES[row.original.status]}`,
    }, STATUS_LABELS[row.original.status]),
  },
  {
    id: 'linked',
    header: 'Vinculado a',
    cell: ({ row }) => {
      const e = row.original
      if (e.executed_advance) return `Anticipo #${e.executed_advance}`
      if (e.executed_trip) return `Viaje #${e.executed_trip}`
      return '—'
    },
  },
  {
    accessorKey: 'observations',
    header: 'Observaciones',
    cell: ({ row }) => h('span', { class: 'max-w-xs truncate block' }, row.original.observations ?? '—'),
  },
  {
    id: 'actions',
    header: 'Acciones',
    enableSorting: false,
    cell: ({ row }) => {
      if (!canEdit('pendingEntries') || row.original.status !== 'pending') return null
      return h('div', { class: 'flex items-center gap-1' }, [
        h('button', {
          type: 'button',
          title: 'Editar pendiente',
          class: 'p-1.5 rounded-lg text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors',
          onClick: () => openEdit(row.original),
        }, h(Pencil, { class: 'w-4 h-4' })),
        h('button', {
          type: 'button',
          title: 'Cancelar pendiente',
          class: 'p-1.5 rounded-lg text-gray-400 hover:text-red-700 hover:bg-red-50 transition-colors',
          onClick: () => openCancel(row.original),
        }, h(Ban, { class: 'w-4 h-4' })),
      ])
    },
  },
]
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="Pendientes"
      description="Anticipos y transferencias avisadas por clientes, pendientes de ejecutar"
    />

    <div class="bg-white rounded-xl border border-gray-200 shadow-md shadow-stone-300/50">
      <div class="px-6 py-4 border-b border-gray-100 flex flex-wrap items-center justify-between gap-4">
        <h2 class="text-sm font-semibold text-gray-800">Pendientes registrados</h2>
        <button
          v-if="canCreate('pendingEntries')"
          type="button"
          @click="openCreate"
          class="flex items-center gap-2 px-4 py-2 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 transition-colors"
        >
          <Plus class="w-4 h-4" />
          Nuevo pendiente
        </button>
      </div>

      <!-- Filtros -->
      <div class="px-6 py-4 border-b border-gray-100 flex flex-wrap items-end gap-4">
        <div class="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
          <button
            v-for="(label, type) in { all: 'Todos', advance: 'Anticipos', transfer: 'Transferencias' }"
            :key="type"
            type="button"
            @click="filterType = type as 'all' | PendingEntryType"
            class="px-3 py-2 transition-colors"
            :class="filterType === type ? 'bg-gold-500 text-stone-900' : 'text-gray-600 hover:bg-gray-50'"
          >
            {{ label }}
          </button>
        </div>
        <div class="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
          <button
            v-for="(label, st) in { pending: 'Pendientes', executed: 'Ejecutados', cancelled: 'Cancelados', all: 'Todos' }"
            :key="st"
            type="button"
            @click="filterStatus = st as 'all' | PendingEntryStatus"
            class="px-3 py-2 transition-colors"
            :class="filterStatus === st ? 'bg-gold-500 text-stone-900' : 'text-gray-600 hover:bg-gray-50'"
          >
            {{ label }}
          </button>
        </div>
      </div>

      <div class="p-6">
        <DataTable :columns="columns" :data="entries" :isLoading="isLoading" />
      </div>
    </div>

    <!-- ── Modal crear/editar ──────────────────────────────────────────────── -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-150"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-100"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div v-if="modalOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div class="bg-white rounded-xl shadow-xl border-t-4 border-gold-500 p-6 w-full max-w-md">
            <div class="flex items-center justify-between mb-5">
              <h3 class="text-sm font-semibold text-gray-800">
                {{ editingEntry ? `Editar pendiente #${editingEntry.id}` : 'Nuevo pendiente' }}
              </h3>
              <button type="button" @click="closeModal" class="text-gray-400 hover:text-gray-600 transition-colors">
                <X class="w-5 h-5" />
              </button>
            </div>

            <form @submit.prevent="onSubmit" class="space-y-4">
              <!-- Tipo -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">Tipo <span class="text-red-500">*</span></label>
                <div v-if="editingEntry" class="text-sm text-gray-700 px-3 py-2 bg-gray-50 rounded-md border border-gray-200">
                  {{ ENTRY_TYPE_LABELS[editingEntry.entry_type] }}
                </div>
                <div v-else class="flex rounded-lg border border-gray-200 overflow-hidden text-sm w-full">
                  <button
                    type="button"
                    v-for="(label, type) in ENTRY_TYPE_LABELS"
                    :key="type"
                    @click="entryType = type as PendingEntryType"
                    class="flex-1 px-3 py-2 transition-colors"
                    :class="entryType === type ? 'bg-gold-500 text-stone-900 font-medium' : 'text-gray-600 hover:bg-gray-50'"
                  >
                    {{ label }}
                  </button>
                </div>
              </div>

              <!-- Cliente -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">Cliente <span class="text-red-500">*</span></label>
                <SearchableSelect v-model="fClient" :options="clientOptions" placeholder="Buscar cliente..." />
                <p v-if="clientError" class="mt-1 text-xs text-red-500">{{ clientError }}</p>
              </div>

              <!-- Valor -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">Valor <span class="text-red-500">*</span></label>
                <CurrencyInput v-model="fValue" :class="valueError ? 'border-red-400 bg-red-50' : ''" />
                <p v-if="valueError" class="mt-1 text-xs text-red-500">{{ valueError }}</p>
              </div>

              <!-- Fecha -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">Fecha <span class="text-red-500">*</span></label>
                <DatePickerInput v-model="fDate" :error="!!dateError" />
                <p v-if="dateError" class="mt-1 text-xs text-red-500">{{ dateError }}</p>
              </div>

              <!-- Método de pago (solo transferencia) -->
              <div v-if="entryType === 'transfer'">
                <label class="block text-xs font-medium text-gray-700 mb-1">
                  Método de pago <span class="text-red-500">*</span>
                </label>
                <SearchableSelect v-model="fPaymentMethod" :options="paymentMethodOptions" placeholder="Seleccionar..." />
                <p v-if="paymentMethodError" class="mt-1 text-xs text-red-500">{{ paymentMethodError }}</p>
              </div>

              <!-- Observaciones -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">Observaciones</label>
                <textarea
                  v-model="fObservations"
                  rows="2"
                  class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
                />
              </div>

              <div class="flex gap-2 justify-end pt-2">
                <button
                  type="button"
                  @click="closeModal"
                  :disabled="isSubmitting"
                  class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  :disabled="isSubmitting"
                  class="flex items-center gap-2 px-5 py-2 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 disabled:opacity-50 transition-colors"
                >
                  <Loader2 v-if="isSubmitting" class="w-4 h-4 animate-spin" />
                  {{ isSubmitting ? 'Guardando...' : (editingEntry ? 'Guardar cambios' : 'Registrar pendiente') }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ── Modal cancelar ──────────────────────────────────────────────────── -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-150"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-100"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div v-if="cancellingEntry" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div class="bg-white rounded-xl shadow-xl border-t-4 border-gold-500 p-6 w-full max-w-md">
            <div class="flex items-center justify-between mb-5">
              <h3 class="text-sm font-semibold text-gray-800">Cancelar pendiente #{{ cancellingEntry.id }}</h3>
              <button type="button" @click="closeCancel" class="text-gray-400 hover:text-gray-600 transition-colors">
                <X class="w-5 h-5" />
              </button>
            </div>

            <p class="text-xs text-gray-500 mb-4">
              {{ ENTRY_TYPE_LABELS[cancellingEntry.entry_type] }} · {{ cancellingEntry.client_detail?.name }} ·
              {{ formatCurrency(Number(cancellingEntry.value)) }}
            </p>

            <label class="block text-xs font-medium text-gray-700 mb-1">
              Justificación <span class="text-red-500">*</span>
            </label>
            <textarea
              v-model="cancelJustification"
              rows="3"
              class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-400 transition-colors"
              placeholder="Motivo de la cancelación..."
            />

            <div class="flex gap-2 justify-end pt-4">
              <button
                type="button"
                @click="closeCancel"
                :disabled="cancelLoading"
                class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100 transition-colors"
              >
                Volver
              </button>
              <button
                type="button"
                @click="confirmCancel"
                :disabled="cancelLoading || !cancelJustification.trim()"
                class="flex items-center gap-2 px-5 py-2 bg-red-600 text-white text-sm font-semibold rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                <Loader2 v-if="cancelLoading" class="w-4 h-4 animate-spin" />
                {{ cancelLoading ? 'Cancelando...' : 'Confirmar cancelación' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
