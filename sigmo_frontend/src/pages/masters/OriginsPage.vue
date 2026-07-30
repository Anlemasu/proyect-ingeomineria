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
import { originsApi } from '@/api/origins.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { usePermissions } from '@/composables/usePermissions'
import type { OriginSite } from '@/types'

const qc = useQueryClient()
const { canCreate, canEdit } = usePermissions()

const showModal = ref(false)
const editing = ref<OriginSite | null>(null)
const confirmToggle = ref<OriginSite | null>(null)

const { data, isLoading } = useQuery({
  queryKey: ['origins'],
  queryFn: async () => (await originsApi.list()).data,
})
const rows = computed(() => data.value ?? [])

const schema = toTypedSchema(z.object({
  name: z.string().min(1, 'El nombre es requerido').max(50).transform(s => s.trim()),
}))

const { handleSubmit, isSubmitting, resetForm, setValues } = useForm({ validationSchema: schema })
const { value: name, errorMessage: nameError } = useField<string>('name')

function openCreate() { editing.value = null; resetForm(); showModal.value = true }
function openEdit(item: OriginSite) {
  editing.value = item
  setValues({ name: item.name })
  showModal.value = true
}

const { mutateAsync: create } = useMutation({
  mutationFn: (d: { name: string }) => originsApi.create(d),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['origins'] }); toast.success('Origen creado.') },
})
const { mutateAsync: update } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Partial<OriginSite> }) => originsApi.update(id, data),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['origins'] }); toast.success('Origen actualizado.') },
})
const { mutate: toggle, isPending: togglePending } = useMutation({
  mutationFn: (item: OriginSite) => originsApi.update(item.id, { state: !item.state }),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['origins'] }); confirmToggle.value = null; toast.success('Estado actualizado.') },
  onError: (err) => toast.error(getApiErrorMessage(err)),
})

const onSubmit = handleSubmit(async (values) => {
  try {
    if (editing.value) {
      await update({ id: editing.value.id, data: values })
    } else {
      await create(values)
    }
    showModal.value = false
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

const columns: ColumnDef<OriginSite>[] = [
  { accessorKey: 'name', header: 'Nombre' },
  { accessorKey: 'state', header: 'Estado', cell: ({ row }) => h(StatusBadge, { active: row.original.state }) },
  {
    id: 'actions',
    header: 'Acciones',
    cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
      canEdit('masters') ? h('button', { class: 'p-1 text-gray-500 hover:text-gold-700', onClick: () => openEdit(row.original) }, h(Pencil, { class: 'w-4 h-4' })) : null,
      canEdit('masters') ? h('button', { class: 'p-1 text-gray-500 hover:text-amber-600', onClick: () => { confirmToggle.value = row.original } },
        h(row.original.state ? ToggleRight : ToggleLeft, { class: 'w-4 h-4' })) : null,
    ].filter(Boolean)),
  },
]
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <PageHeader title="Origenes" description="Sitios de origen registrados" />
      <button v-if="canCreate('masters')" @click="openCreate" class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600">
        <Plus class="w-4 h-4" /> Nuevo origen
      </button>
    </div>

    <DataTable :columns="(columns as any)" :data="(rows as any)" :is-loading="isLoading" />

    <teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-sm mx-4">
          <h2 class="text-lg font-semibold mb-4">{{ editing ? 'Editar origen' : 'Nuevo origen' }}</h2>
          <form @submit.prevent="onSubmit" class="space-y-4" novalidate>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nombre *</label>
              <input v-model="name" type="text" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" :class="nameError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="nameError" class="mt-1 text-xs text-red-600">{{ nameError }}</p>
            </div>
            <div class="flex justify-end gap-3">
              <button type="button" @click="showModal = false" class="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">Cancelar</button>
              <button type="submit" :disabled="isSubmitting" class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60">
                {{ isSubmitting ? 'Guardando...' : 'Guardar' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </teleport>

    <ConfirmDialog
      :open="!!confirmToggle"
      :title="confirmToggle?.state ? 'Desactivar origen' : 'Activar origen'"
      :description="confirmToggle ? 'Confirmas cambiar el estado de ' + confirmToggle.name + '?' : ''"
      :loading="togglePending"
      @confirm="confirmToggle && toggle(confirmToggle)"
      @cancel="confirmToggle = null"
    />
  </div>
</template>
