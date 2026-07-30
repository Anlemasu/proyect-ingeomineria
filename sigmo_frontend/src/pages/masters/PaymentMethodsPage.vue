<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Plus, Pencil, ToggleLeft, ToggleRight } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'
import DataTable from '@/components/shared/DataTable.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import StatusBadge from '@/components/shared/StatusBadge.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { usePermissions } from '@/composables/usePermissions'
import type { PaymentMethod } from '@/types'

const qc = useQueryClient()
const { canCreate, canEdit } = usePermissions()

const showModal = ref(false)
const editing = ref<PaymentMethod | null>(null)
const confirmToggle = ref<PaymentMethod | null>(null)

const { data, isLoading } = useQuery({
  queryKey: ['payment-methods'],
  queryFn: async () => (await paymentMethodsApi.list()).data,
})
const rows = computed(() => data.value ?? [])

const schema = toTypedSchema(z.object({
  name: z.string().min(1, 'El nombre es requerido').max(20).transform(s => s.trim()),
  is_advance: z.boolean().optional(),
}))

const { handleSubmit, resetForm, setValues, isSubmitting } = useForm({
  validationSchema: schema,
  initialValues: {
    name: '',
    is_advance: false,
  }
})

const { value: name, errorMessage: nameError } = useField<string>('name')
const { value: is_advance } = useField<boolean>('is_advance')

function openCreate() { editing.value = null; resetForm(); showModal.value = true }
function openEdit(item: PaymentMethod) {
  editing.value = item
  setValues({ name: item.name, is_advance: item.is_advance })
  showModal.value = true
}

const { mutateAsync: create } = useMutation({
  mutationFn: (d: { name: string; is_advance: boolean }) => paymentMethodsApi.create(d),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['payment-methods'] }); toast.success('Medio de pago creado.') },
})
const { mutateAsync: update } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Partial<PaymentMethod> }) => paymentMethodsApi.update(id, data),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['payment-methods'] }); toast.success('Medio de pago actualizado.') },
})
const { mutate: toggle, isPending: togglePending } = useMutation({
  mutationFn: (item: PaymentMethod) => paymentMethodsApi.update(item.id, { state: !item.state }),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['payment-methods'] }); confirmToggle.value = null; toast.success('Estado actualizado.') },
  onError: (err) => toast.error(getApiErrorMessage(err)),
})

const onSubmit = handleSubmit(async (values) => {
  try {
    if (editing.value) {
      const { is_advance: _ia, ...rest } = values
      await update({ id: editing.value.id, data: rest })
    } else {
      await create({ 
        name: values.name, 
        is_advance: values.is_advance ?? false  // ← garantiza boolean
      })
    }
    showModal.value = false
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

const columns: ColumnDef<PaymentMethod>[] = [
  { accessorKey: 'name', header: 'Nombre' },
  {
    accessorKey: 'is_advance',
    header: 'Tipo',
    cell: ({ row }) => h('span', {
      class: row.original.is_advance
        ? 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800'
        : 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800',
    }, row.original.is_advance ? 'Tipo anticipo' : 'Pago directo'),
  },
  { accessorKey: 'state', header: 'Estado', cell: ({ row }) => h(StatusBadge, { active: row.original.state }) },
  {
    id: 'actions',
    header: 'Acciones',
    cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
      canEdit('masters') ? h('button', { class: 'p-1 text-gray-500 hover:text-blue-600', onClick: () => openEdit(row.original) }, h(Pencil, { class: 'w-4 h-4' })) : null,
      canEdit('masters') ? h('button', { class: 'p-1 text-gray-500 hover:text-amber-600', onClick: () => { confirmToggle.value = row.original } },
        h(row.original.state ? ToggleRight : ToggleLeft, { class: 'w-4 h-4' })) : null,
    ].filter(Boolean)),
  },
]
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <PageHeader title="Medios de pago" description="Gestion de medios de pago disponibles" />
      <button v-if="canCreate('masters')" @click="openCreate" class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[#1E40AF] rounded-md hover:bg-blue-700">
        <Plus class="w-4 h-4" /> Nuevo medio de pago
      </button>
    </div>

    <DataTable :columns="(columns as any)" :data="(rows as any)" :is-loading="isLoading" />

    <teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
          <h2 class="text-lg font-semibold mb-4">{{ editing ? 'Editar medio de pago' : 'Nuevo medio de pago' }}</h2>
          <form @submit.prevent="onSubmit" class="space-y-4" novalidate>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nombre *</label>
              <input v-model="name" type="text" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" :class="nameError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="nameError" class="mt-1 text-xs text-red-600">{{ nameError }}</p>
            </div>
            <div v-if="!editing" class="flex items-center gap-2">
              <input v-model="is_advance" type="checkbox" id="is_advance" class="w-4 h-4 rounded border-gray-300" />
              <label for="is_advance" class="text-sm text-gray-700">Es tipo anticipo</label>
            </div>
            <div v-if="editing" class="bg-gray-50 rounded-md p-3 text-sm text-gray-600">
              Tipo: <span class="font-medium">{{ editing.is_advance ? 'Tipo anticipo' : 'Pago directo' }}</span>
              <p class="text-xs text-gray-400 mt-1">El tipo no se puede cambiar una vez creado.</p>
            </div>
            <div class="flex justify-end gap-3">
              <button type="button" @click="showModal = false" class="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">Cancelar</button>
              <button type="submit" :disabled="isSubmitting" class="px-4 py-2 text-sm font-medium text-white bg-[#1E40AF] rounded-md hover:bg-blue-700 disabled:opacity-60">
                {{ isSubmitting ? 'Guardando...' : 'Guardar' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </teleport>

    <ConfirmDialog
      :open="!!confirmToggle"
      :title="confirmToggle?.state ? 'Desactivar medio de pago' : 'Activar medio de pago'"
      :description="confirmToggle ? 'Confirmas cambiar el estado de ' + confirmToggle.name + '?' : ''"
      :loading="togglePending"
      @confirm="confirmToggle && toggle(confirmToggle)"
      @cancel="confirmToggle = null"
    />
  </div>
</template>
