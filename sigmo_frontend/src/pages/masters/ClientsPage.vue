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
import { clientsApi } from '@/api/clients.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { usePermissions } from '@/composables/usePermissions'
import type { Client } from '@/types'

const qc = useQueryClient()
const { canCreate, canEdit } = usePermissions()

const showModal = ref(false)
const editingClient = ref<Client | null>(null)
const confirmToggle = ref<Client | null>(null)
const nitDuplicate = ref('')
const nitCheckTimeout = ref<ReturnType<typeof setTimeout> | null>(null)

const { data: clients, isLoading } = useQuery({
  queryKey: ['clients'],
  queryFn: async () => {
    const res = await clientsApi.list()
    return res.data
  },
})

const allClients = computed(() => clients.value ?? [])

const schema = toTypedSchema(z.object({
  nit: z.string()
    .min(1, 'El NIT es requerido')
    .max(15, 'Maximo 15 caracteres')
    .regex(/^[\d-]+$/, 'Solo se permiten numeros y guiones')
    .transform(s => s.trim()),
  name: z.string().min(1, 'El nombre es requerido').max(50).transform(s => s.trim()),
  abrev_name: z.string().min(1, 'La abreviacion es requerida').max(20).transform(s => s.trim()),
  address: z.string().min(1, 'La direccion es requerida').max(20).transform(s => s.trim()),
  phone: z.string().regex(/^\d{10}$/, 'El telefono debe tener exactamente 10 digitos'),
  city: z.string().max(20).optional().transform(s => s?.trim() || null),
  facturation_name: z.string().max(50).optional().transform(s => s?.trim() || null),
  email: z.string().email('Email invalido').optional().or(z.literal('')).transform(s => s?.trim() || null),
  validate_certification: z.boolean().optional(),  // ← quita el .default(false)
}))

const { handleSubmit, isSubmitting, resetForm, setValues } = useForm({ validationSchema: schema })
const { value: nit, errorMessage: nitError } = useField<string>('nit')
const { value: name, errorMessage: nameError } = useField<string>('name')
const { value: abrev_name, errorMessage: abrevError } = useField<string>('abrev_name')
const { value: address, errorMessage: addressError } = useField<string>('address')
const { value: phone, errorMessage: phoneError } = useField<string>('phone')
const { value: city } = useField<string>('city')
const { value: facturation_name } = useField<string>('facturation_name')
const { value: email, errorMessage: emailError } = useField<string>('email')
const { value: validate_certification } = useField<boolean>('validate_certification')

function openCreate() {
  editingClient.value = null
  resetForm()
  nitDuplicate.value = ''
  showModal.value = true
}

function openEdit(client: Client) {
  editingClient.value = client
  nitDuplicate.value = ''
  setValues({
    nit: client.nit,
    name: client.name,
    abrev_name: client.abrev_name,
    address: client.address,
    phone: String(client.phone),
    city: client.city ?? '',
    facturation_name: client.facturation_name ?? '',
    email: client.email ?? '',
    validate_certification: client.validate_certification ?? false,
  })
  showModal.value = true
}

function checkNit(val: string) {
  if (!val || editingClient.value) return
  if (nitCheckTimeout.value) clearTimeout(nitCheckTimeout.value)
  nitCheckTimeout.value = setTimeout(async () => {
    try {
      const res = await clientsApi.list({ nit: val })
      const found = res.data.find((c: Client) => 
        c.nit === val.replace(/-/g, '').replace(/ /g, '')
      )
      nitDuplicate.value = found ? `Ya existe un cliente con este NIT: ${found.name}` : ''
    } catch {
      nitDuplicate.value = ''
    }
  }, 500)
}

const { mutateAsync: createClient } = useMutation({
  mutationFn: (data: Partial<Client>) => clientsApi.create(data),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['clients'] })
    toast.success('Cliente creado correctamente.')
  },
})

const { mutateAsync: updateClient } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Partial<Client> }) => clientsApi.update(id, data),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['clients'] })
    toast.success('Cliente actualizado correctamente.')
  },
})

const { mutate: toggleClient, isPending: togglePending } = useMutation({
  mutationFn: (client: Client) => clientsApi.update(client.id, { state: !client.state }),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['clients'] })
    confirmToggle.value = null
    toast.success('Estado actualizado.')
  },
  onError: (err) => { toast.error(getApiErrorMessage(err)) },
})

const onSubmit = handleSubmit(async (values) => {
  if (nitDuplicate.value) return
  try {
    if (editingClient.value) {
      const { nit: _n, ...rest } = values
      await updateClient({ id: editingClient.value.id, data: rest })
    } else {
      await createClient(values)
    }
    showModal.value = false
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

const columns: ColumnDef<Client>[] = [
  { accessorKey: 'nit', header: 'NIT' },
  { accessorKey: 'name', header: 'Nombre empresa' },
  { accessorKey: 'abrev_name', header: 'Abreviacion' },
  { accessorKey: 'phone', header: 'Telefono' },
  { accessorKey: 'city', header: 'Ciudad' },
  {
    accessorKey: 'state',
    header: 'Estado',
    cell: ({ row }) => h(StatusBadge, { active: row.original.state }),
  },
  {
    id: 'actions',
    header: 'Acciones',
    cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
      canEdit('clients') ? h('button', {
        class: 'p-1 text-gray-500 hover:text-blue-600',
        title: 'Editar',
        onClick: () => openEdit(row.original),
      }, h(Pencil, { class: 'w-4 h-4' })) : null,
      canEdit('clients') ? h('button', {
        class: 'p-1 text-gray-500 hover:text-amber-600',
        title: row.original.state ? 'Desactivar' : 'Activar',
        onClick: () => { confirmToggle.value = row.original },
      }, h(row.original.state ? ToggleRight : ToggleLeft, { class: 'w-4 h-4' })) : null,
    ].filter(Boolean)),
  },
]
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <PageHeader title="Clientes" description="Gestion de clientes del sistema" />
      <button
        v-if="canCreate('clients')"
        @click="openCreate"
        class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[#1E40AF] rounded-md hover:bg-blue-700"
      >
        <Plus class="w-4 h-4" />
        Nuevo cliente
      </button>
    </div>

    <DataTable :columns="(columns as any)" :data="(allClients as any)" :is-loading="isLoading" />

    <teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <h2 class="text-lg font-semibold mb-5">
            {{ editingClient ? 'Editar cliente' : 'Nuevo cliente' }}
          </h2>
          <form @submit.prevent="onSubmit" class="space-y-4" novalidate>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">NIT *</label>
                <input
                  v-model="nit"
                  type="text"
                  :disabled="!!editingClient"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                  :class="(nitError || nitDuplicate) ? 'border-red-400' : 'border-gray-300'"
                  @blur="checkNit(nit ?? '')"
                />
                <p v-if="nitError" class="mt-1 text-xs text-red-600">{{ nitError }}</p>
                <p v-else-if="nitDuplicate" class="mt-1 text-xs text-red-600">{{ nitDuplicate }}</p>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Nombre empresa *</label>
                <input v-model="name" type="text" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" :class="nameError ? 'border-red-400' : 'border-gray-300'" />
                <p v-if="nameError" class="mt-1 text-xs text-red-600">{{ nameError }}</p>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Abreviacion *</label>
                <input v-model="abrev_name" type="text" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" :class="abrevError ? 'border-red-400' : 'border-gray-300'" />
                <p v-if="abrevError" class="mt-1 text-xs text-red-600">{{ abrevError }}</p>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Direccion *</label>
                <input v-model="address" type="text" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" :class="addressError ? 'border-red-400' : 'border-gray-300'" />
                <p v-if="addressError" class="mt-1 text-xs text-red-600">{{ addressError }}</p>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Telefono *</label>
                <input v-model="phone" type="text" inputmode="numeric" maxlength="10" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" :class="phoneError ? 'border-red-400' : 'border-gray-300'" />
                <p v-if="phoneError" class="mt-1 text-xs text-red-600">{{ phoneError }}</p>
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Ciudad</label>
                <input v-model="city" type="text" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none" />
              </div>
              <div class="col-span-2">
                <label class="block text-sm font-medium text-gray-700 mb-1">Empresa a facturar</label>
                <input v-model="facturation_name" type="text" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none" />
              </div>
              <div class="col-span-2">
                <label class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input v-model="email" type="email" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none" :class="emailError ? 'border-red-400' : 'border-gray-300'" />
                <p v-if="emailError" class="mt-1 text-xs text-red-600">{{ emailError }}</p>
              </div>
              <div class="col-span-2 flex items-center gap-2">
                <input v-model="validate_certification" type="checkbox" id="cert" class="w-4 h-4 rounded border-gray-300" />
                <label for="cert" class="text-sm text-gray-700">Validar certificacion</label>
              </div>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button type="button" @click="showModal = false" class="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">
                Cancelar
              </button>
              <button
                type="submit"
                :disabled="isSubmitting || !!nitDuplicate"
                class="px-4 py-2 text-sm font-medium text-white bg-[#1E40AF] rounded-md hover:bg-blue-700 disabled:opacity-60"
              >
                {{ isSubmitting ? 'Guardando...' : 'Guardar' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </teleport>

    <ConfirmDialog
      :open="!!confirmToggle"
      :title="confirmToggle?.state ? 'Desactivar cliente' : 'Activar cliente'"
      :description="confirmToggle ? 'Confirmas cambiar el estado del cliente ' + confirmToggle.name + '?' : ''"
      :loading="togglePending"
      @confirm="confirmToggle && toggleClient(confirmToggle)"
      @cancel="confirmToggle = null"
    />
  </div>
</template>
