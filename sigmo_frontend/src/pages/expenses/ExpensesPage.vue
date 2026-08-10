<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'
import { Pencil, Loader2, X, Ban } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'

import PageHeader from '@/components/shared/PageHeader.vue'
import DataTable from '@/components/shared/DataTable.vue'
import CurrencyInput from '@/components/shared/CurrencyInput.vue'
import { expensesApi } from '@/api/expenses.api'
import type { Expense } from '@/types'
import { usePermissions } from '@/composables/usePermissions'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, todayBogota } from '@/utils/formatDate'
import { getApiErrorMessage } from '@/utils/handleApiError'

const { canCreate, canEdit } = usePermissions()
const queryClient = useQueryClient()

// ── Today's date helper ───────────────────────────────────────────────────────
const todayISO = todayBogota()

// ── Filter state ──────────────────────────────────────────────────────────────
type FilterMode = 'today' | 'specific' | 'range'
const filterMode = ref<FilterMode>('today')
const filterDate = ref(todayISO)
const filterFrom = ref(todayISO)
const filterTo = ref(todayISO)

const queryParams = computed(() => {
  if (filterMode.value === 'today') return { date: todayISO }
  if (filterMode.value === 'specific') return { date: filterDate.value }
  return { date_from: filterFrom.value, date_to: filterTo.value }
})

// ── List query ────────────────────────────────────────────────────────────────
const { data: expensesData, isLoading } = useQuery({
  queryKey: computed(() => ['expenses', queryParams.value]),
  queryFn: () => expensesApi.list(queryParams.value).then(r => r.data),
})

const expenses = computed(() => expensesData.value ?? [])
// Igual que en Trips (totalActive): los gastos anulados no cuentan en el
// total, aunque siguen listados con trazabilidad.
const totalValue = computed(() =>
  expenses.value.filter(e => e.state).reduce((sum, e) => sum + Number(e.value), 0)
)

// ── Create form ───────────────────────────────────────────────────────────────
const createSchema = toTypedSchema(z.object({
  description: z.string().min(1, 'La descripción es requerida').transform(s => s.trim()),
  value: z.number({ error: 'El valor es requerido' }).positive('El valor debe ser mayor a cero'),
  date: z.string().min(1, 'La fecha es requerida'),
}))

const { handleSubmit: handleCreate, resetForm, isSubmitting } = useForm({
  validationSchema: createSchema,
  initialValues: { description: '', value: undefined as unknown as number, date: todayISO },
})

const { value: description, errorMessage: descriptionError } = useField<string>('description')
const { value: value, errorMessage: valueError } = useField<number>('value')
const { value: date, errorMessage: dateError } = useField<string>('date')

const { mutateAsync: createExpense } = useMutation({
  mutationFn: expensesApi.create,
})

const onCreateSubmit = handleCreate(async (values) => {
  try {
    await createExpense(values)
    toast.success('Gasto registrado correctamente.')
    resetForm()
    queryClient.invalidateQueries({ queryKey: ['expenses'] })
    queryClient.invalidateQueries({ queryKey: ['cash-closing-today'] })
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

// ── Edit modal ────────────────────────────────────────────────────────────────
const editingExpense = ref<Expense | null>(null)

const editSchema = toTypedSchema(z.object({
  description: z.string().min(1, 'La descripción es requerida').transform(s => s.trim()),
  value: z.number({ error: 'El valor es requerido' }).positive('El valor debe ser mayor a cero'),
  date: z.string().min(1, 'La fecha es requerida'),
}))

const { handleSubmit: handleEdit, setValues: setEditValues, isSubmitting: isEditSubmitting } = useForm({
  validationSchema: editSchema,
  initialValues: { description: '', value: undefined as unknown as number, date: todayISO },
})

const { value: editDescription, errorMessage: editDescriptionError } = useField<string>('description')
const { value: editValue, errorMessage: editValueError } = useField<number>('value')
const { value: editDate, errorMessage: editDateError } = useField<string>('date')

function openEdit(expense: Expense) {
  editingExpense.value = expense
  setEditValues({
    description: expense.description,
    value: Number(expense.value),
    date: expense.date,
  })
}

function closeEdit() {
  editingExpense.value = null
}

const { mutateAsync: updateExpense } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Partial<{ description: string; value: number; date: string }> }) =>
    expensesApi.update(id, data),
})

const onEditSubmit = handleEdit(async (values) => {
  if (!editingExpense.value) return
  try {
    await updateExpense({ id: editingExpense.value.id, data: values })
    toast.success('Gasto actualizado correctamente.')
    closeEdit()
    queryClient.invalidateQueries({ queryKey: ['expenses'] })
    queryClient.invalidateQueries({ queryKey: ['cash-closing-today'] })
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

// ── Anulación ─────────────────────────────────────────────────────────────────
const annulExpense = ref<Expense | null>(null)
const annulJustification = ref('')
const annulLoading = ref(false)

function openAnnul(expense: Expense) {
  annulExpense.value = expense
  annulJustification.value = ''
}

function closeAnnul() {
  annulExpense.value = null
}

async function confirmAnnul() {
  if (!annulExpense.value) return
  if (!annulJustification.value.trim()) {
    toast.error('Debe justificar la anulación')
    return
  }
  annulLoading.value = true
  try {
    await expensesApi.update(annulExpense.value.id, {
      state: false,
      justification: annulJustification.value.trim(),
    })
    toast.success(`Gasto #${annulExpense.value.id} anulado`)
    closeAnnul()
    queryClient.invalidateQueries({ queryKey: ['expenses'] })
    queryClient.invalidateQueries({ queryKey: ['cash-closing-today'] })
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  } finally {
    annulLoading.value = false
  }
}

// ── Table columns ─────────────────────────────────────────────────────────────
const columns: ColumnDef<Expense>[] = [
  {
    accessorKey: 'date',
    header: 'Fecha',
    cell: ({ row }) => formatDate(row.original.date),
  },
  {
    accessorKey: 'description',
    header: 'Descripción',
    cell: ({ row }) => h('span', {
      class: ['max-w-xs truncate block', row.original.state ? '' : 'line-through text-gray-400'],
    }, row.original.description),
  },
  {
    accessorKey: 'value',
    header: 'Valor',
    cell: ({ row }) => h('span', { class: 'font-medium text-gray-900' }, formatCurrency(Number(row.original.value))),
  },
  {
    id: 'state',
    header: 'Estado',
    enableSorting: false,
    cell: ({ row }) => row.original.state
      ? h('span', { class: 'text-xs text-gray-400' }, '—')
      : h('span', { class: 'text-xs font-medium text-red-600 bg-red-50 px-2 py-0.5 rounded' }, 'Anulado'),
  },
  {
    id: 'actions',
    header: 'Acciones',
    enableSorting: false,
    cell: ({ row }) => {
      if (!canEdit('expenses') || !row.original.state) return null
      return h('div', { class: 'flex items-center gap-1' }, [
        h('button', {
          type: 'button',
          title: 'Editar gasto',
          class: 'p-1.5 rounded-lg text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors',
          onClick: () => openEdit(row.original),
        }, h(Pencil, { class: 'w-4 h-4' })),
        h('button', {
          type: 'button',
          title: 'Anular gasto',
          class: 'p-1.5 rounded-lg text-gray-400 hover:text-red-700 hover:bg-red-50 transition-colors',
          onClick: () => openAnnul(row.original),
        }, h(Ban, { class: 'w-4 h-4' })),
      ])
    },
  },
]
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="Gastos"
      subtitle="Registro y consulta de gastos operativos"
    />

    <!-- ── Registration form ──────────────────────────────────────────────── -->
    <div v-if="canCreate('expenses')" class="bg-white rounded-xl border border-gray-200 shadow-sm">
      <div class="px-6 py-4 border-b border-gray-100">
        <h2 class="text-sm font-semibold text-gray-800">Registrar gasto</h2>
      </div>
      <form @submit.prevent="onCreateSubmit" class="p-6">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <!-- Descripción -->
          <div class="md:col-span-1">
            <label class="block text-xs font-medium text-gray-700 mb-1">
              Descripción <span class="text-red-500">*</span>
            </label>
            <input
              v-model="description"
              type="text"
              placeholder="Combustible, mantenimiento..."
              class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
              :class="descriptionError ? 'border-red-400 bg-red-50' : 'border-gray-300'"
            />
            <p v-if="descriptionError" class="mt-1 text-xs text-red-500">{{ descriptionError }}</p>
          </div>

          <!-- Valor -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">
              Valor <span class="text-red-500">*</span>
            </label>
            <CurrencyInput
              v-model="value"
              :class="valueError ? 'border-red-400 bg-red-50' : ''"
            />
            <p v-if="valueError" class="mt-1 text-xs text-red-500">{{ valueError }}</p>
          </div>

          <!-- Fecha -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1">
              Fecha <span class="text-red-500">*</span>
            </label>
            <input
              v-model="date"
              type="date"
              class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
              :class="dateError ? 'border-red-400 bg-red-50' : 'border-gray-300'"
            />
            <p v-if="dateError" class="mt-1 text-xs text-red-500">{{ dateError }}</p>
          </div>
        </div>

        <div class="mt-4 flex justify-end">
          <button
            type="submit"
            :disabled="isSubmitting"
            class="flex items-center gap-2 px-5 py-2.5 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Loader2 v-if="isSubmitting" class="w-4 h-4 animate-spin" />
            {{ isSubmitting ? 'Registrando...' : 'Registrar Gasto' }}
          </button>
        </div>
      </form>
    </div>

    <!-- ── Expenses list ───────────────────────────────────────────────────── -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm">
      <div class="px-6 py-4 border-b border-gray-100">
        <h2 class="text-sm font-semibold text-gray-800">Gastos registrados</h2>
      </div>

      <!-- Filter bar -->
      <div class="px-6 py-4 border-b border-gray-100 flex flex-wrap items-end gap-4">
        <!-- Mode toggle -->
        <div class="flex rounded-lg border border-gray-200 overflow-hidden text-xs font-medium">
          <button
            v-for="(label, mode) in { today: 'Hoy', specific: 'Fecha específica', range: 'Rango de fechas' }"
            :key="mode"
            type="button"
            @click="filterMode = mode as FilterMode"
            class="px-3 py-2 transition-colors"
            :class="filterMode === mode
              ? 'bg-gold-500 text-stone-900'
              : 'text-gray-600 hover:bg-gray-50'"
          >
            {{ label }}
          </button>
        </div>

        <!-- Specific date -->
        <div v-if="filterMode === 'specific'">
          <label class="block text-xs text-gray-500 mb-1">Fecha</label>
          <input
            v-model="filterDate"
            type="date"
            class="px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
          />
        </div>

        <!-- Date range -->
        <template v-if="filterMode === 'range'">
          <div>
            <label class="block text-xs text-gray-500 mb-1">Desde</label>
            <input
              v-model="filterFrom"
              type="date"
              class="px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-500 mb-1">Hasta</label>
            <input
              v-model="filterTo"
              type="date"
              class="px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
            />
          </div>
        </template>
      </div>

      <!-- DataTable -->
      <div class="p-6">
        <DataTable :columns="columns" :data="expenses" :isLoading="isLoading" />

        <!-- Footer totals -->
        <div v-if="expenses.length > 0" class="mt-3 flex justify-between items-center px-1 text-sm">
          <span class="text-gray-500">
            {{ expenses.length }} {{ expenses.length === 1 ? 'gasto' : 'gastos' }}
          </span>
          <span class="font-semibold text-gray-900">
            Total: <span class="text-red-600">{{ formatCurrency(totalValue) }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- ── Edit modal ──────────────────────────────────────────────────────── -->
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
          v-if="editingExpense"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
        >
          <div class="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div class="flex items-center justify-between mb-5">
              <h3 class="text-sm font-semibold text-gray-800">Editar gasto</h3>
              <button
                type="button"
                @click="closeEdit"
                class="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X class="w-5 h-5" />
              </button>
            </div>

            <form @submit.prevent="onEditSubmit" class="space-y-4">
              <!-- Descripción -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">
                  Descripción <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="editDescription"
                  type="text"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
                  :class="editDescriptionError ? 'border-red-400 bg-red-50' : 'border-gray-300'"
                />
                <p v-if="editDescriptionError" class="mt-1 text-xs text-red-500">{{ editDescriptionError }}</p>
              </div>

              <!-- Valor -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">
                  Valor <span class="text-red-500">*</span>
                </label>
                <CurrencyInput
                  v-model="editValue"
                  :class="editValueError ? 'border-red-400 bg-red-50' : ''"
                />
                <p v-if="editValueError" class="mt-1 text-xs text-red-500">{{ editValueError }}</p>
              </div>

              <!-- Fecha -->
              <div>
                <label class="block text-xs font-medium text-gray-700 mb-1">
                  Fecha <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="editDate"
                  type="date"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
                  :class="editDateError ? 'border-red-400 bg-red-50' : 'border-gray-300'"
                />
                <p v-if="editDateError" class="mt-1 text-xs text-red-500">{{ editDateError }}</p>
              </div>

              <div class="flex gap-2 justify-end pt-2">
                <button
                  type="button"
                  @click="closeEdit"
                  :disabled="isEditSubmitting"
                  class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  :disabled="isEditSubmitting"
                  class="flex items-center gap-2 px-5 py-2 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 disabled:opacity-50 transition-colors"
                >
                  <Loader2 v-if="isEditSubmitting" class="w-4 h-4 animate-spin" />
                  {{ isEditSubmitting ? 'Guardando...' : 'Guardar cambios' }}
                </button>
              </div>
            </form>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ── Annul modal ─────────────────────────────────────────────────────── -->
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
          v-if="annulExpense"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
        >
          <div class="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
            <div class="flex items-center justify-between mb-5">
              <h3 class="text-sm font-semibold text-gray-800">
                Anular Gasto #{{ annulExpense.id }}
              </h3>
              <button
                type="button"
                @click="closeAnnul"
                class="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X class="w-5 h-5" />
              </button>
            </div>

            <p class="text-xs text-gray-500 mb-4">
              {{ annulExpense.description }} · {{ formatCurrency(Number(annulExpense.value)) }}
            </p>

            <label class="block text-xs font-medium text-gray-700 mb-1">
              Justificación <span class="text-red-500">*</span>
            </label>
            <textarea
              v-model="annulJustification"
              rows="3"
              class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-400 transition-colors"
              placeholder="Motivo de la anulación..."
            />

            <div class="flex gap-2 justify-end pt-4">
              <button
                type="button"
                @click="closeAnnul"
                :disabled="annulLoading"
                class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100 transition-colors"
              >
                Cancelar
              </button>
              <button
                type="button"
                @click="confirmAnnul"
                :disabled="annulLoading || !annulJustification.trim()"
                class="flex items-center gap-2 px-5 py-2 bg-red-600 text-white text-sm font-semibold rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                <Loader2 v-if="annulLoading" class="w-4 h-4 animate-spin" />
                {{ annulLoading ? 'Anulando...' : 'Confirmar anulación' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
