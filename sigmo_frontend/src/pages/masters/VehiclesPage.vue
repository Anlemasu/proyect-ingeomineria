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
import SearchableSelect from '@/components/shared/SearchableSelect.vue'
import StatusBadge from '@/components/shared/StatusBadge.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import { vehicleTypesApi, vehiclesApi } from '@/api/vehicles.api'
import { pinsApi } from '@/api/pins.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { usePermissions } from '@/composables/usePermissions'
import type { VehicleType, Vehicle, PinsDumper } from '@/types'

const qc = useQueryClient()
const { canCreate, canEdit } = usePermissions()

const activeTab = ref<'types' | 'vehicles'>('types')

// ── Vehicle Types ─────────────────────────────────────────────────────────────
const showTypeModal = ref(false)
const editingType = ref<VehicleType | null>(null)
const confirmToggleType = ref<VehicleType | null>(null)

const { data: typesData, isLoading: typesLoading } = useQuery({
  queryKey: ['vehicle-types'],
  queryFn: async () => (await vehicleTypesApi.list()).data,
})
const types = computed(() => typesData.value ?? [])

const typeSchema = toTypedSchema(z.object({
  name: z.string().min(1, 'El nombre es requerido').max(20).transform(s => s.trim()),
  capacity: z.number({ message: 'Capacidad requerida' }).positive('Debe ser mayor a 0'),
  description: z.string().optional().transform(s => s?.trim() || undefined),
}))

const { handleSubmit: handleTypeSubmit, isSubmitting: typeSubmitting, resetForm: resetTypeForm, setValues: setTypeValues } = useForm({ validationSchema: typeSchema })
const { value: typeName, errorMessage: typeNameError } = useField<string>('name')
const { value: typeCapacity, errorMessage: typeCapacityError } = useField<number>('capacity')
const { value: typeDescription } = useField<string>('description')

function openCreateType() { editingType.value = null; resetTypeForm(); showTypeModal.value = true }
function openEditType(t: VehicleType) {
  editingType.value = t
  setTypeValues({ name: t.name, capacity: parseFloat(t.capacity), description: t.description ?? '' })
  showTypeModal.value = true
}

const { mutateAsync: createType } = useMutation({
  mutationFn: (d: { name: string; capacity: number; description?: string }) => vehicleTypesApi.create(d),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['vehicle-types'] }); toast.success('Tipo creado.') },
})
const { mutateAsync: updateType } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Partial<VehicleType> }) => vehicleTypesApi.update(id, data),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['vehicle-types'] }); toast.success('Tipo actualizado.') },
})
const { mutate: toggleType, isPending: toggleTypePending } = useMutation({
  mutationFn: (t: VehicleType) => vehicleTypesApi.update(t.id, { state: !t.state }),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['vehicle-types'] }); confirmToggleType.value = null; toast.success('Estado actualizado.') },
  onError: (err) => toast.error(getApiErrorMessage(err)),
})

const onTypeSubmit = handleTypeSubmit(async (values) => {
  try {
    const payload = { name: values.name, capacity: values.capacity, description: values.description }
    if (editingType.value) {
      await updateType({ id: editingType.value.id, data: { ...payload, capacity: String(values.capacity) } })
    } else {
      await createType(payload)
    }
    showTypeModal.value = false
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

const typeColumns: ColumnDef<VehicleType>[] = [
  { accessorKey: 'name', header: 'Nombre' },
  { accessorKey: 'capacity', header: 'Capacidad (m3)' },
  { accessorKey: 'description', header: 'Descripcion' },
  { accessorKey: 'state', header: 'Estado', cell: ({ row }) => h(StatusBadge, { active: row.original.state }) },
  {
    id: 'actions',
    header: 'Acciones',
    cell: ({ row }) => h('div', { class: 'flex items-center gap-2' }, [
      canEdit('masters') ? h('button', { class: 'p-1 text-gray-500 hover:text-gold-700', onClick: () => openEditType(row.original) }, h(Pencil, { class: 'w-4 h-4' })) : null,
      canEdit('masters') ? h('button', { class: 'p-1 text-gray-500 hover:text-amber-600', onClick: () => { confirmToggleType.value = row.original } },
        h(row.original.state ? ToggleRight : ToggleLeft, { class: 'w-4 h-4' })) : null,
    ].filter(Boolean)),
  },
]

// ── Vehicles ──────────────────────────────────────────────────────────────────
const showVehicleModal = ref(false)

const { data: vehiclesData, isLoading: vehiclesLoading } = useQuery({
  queryKey: ['vehicles'],
  queryFn: async () => (await vehiclesApi.list()).data,
})
const vehicles = computed(() => vehiclesData.value ?? [])

const { data: pinsData } = useQuery({
  queryKey: ['pins'],
  queryFn: async () => (await pinsApi.list()).data,
})
const activePins = computed(() => (pinsData.value ?? []).filter((p: PinsDumper) => p.state))
const activeTypes = computed(() => types.value.filter((t: VehicleType) => t.state))
const pinOptions = computed(() => activePins.value.map(p => ({ id: p.id, name: `${p.plaque} - ${p.ambiental_pin}` })))

const vehicleSchema = toTypedSchema(z.object({
  plaque: z.string().min(6, 'La placa debe tener 6 caracteres').max(6, 'La placa debe tener 6 caracteres').transform(s => s.trim().toUpperCase()),
  vehicle_type: z.number({ message: 'Selecciona un tipo' }),
  dumper: z.number().nullable().optional(),
}))

const { handleSubmit: handleVehicleSubmit, isSubmitting: vehicleSubmitting, resetForm: resetVehicleForm } = useForm({ validationSchema: vehicleSchema })
const { value: plaque, errorMessage: plaqueError } = useField<string>('plaque')
const { value: vehicleType, errorMessage: vehicleTypeError } = useField<number>('vehicle_type')
const { value: dumper } = useField<number | null>('dumper')

const { mutateAsync: createVehicle } = useMutation({
  mutationFn: (d: { plaque: string; vehicle_type: number; dumper?: number | null }) => vehiclesApi.create(d),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['vehicles'] }); toast.success('Vehiculo registrado.') },
})

const onVehicleSubmit = handleVehicleSubmit(async (values) => {
  try {
    await createVehicle(values)
    showVehicleModal.value = false
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

const vehicleColumns: ColumnDef<Vehicle>[] = [
  { accessorKey: 'plaque', header: 'Placa' },
  { id: 'type', header: 'Tipo', cell: ({ row }) => row.original.vehicle_type_detail?.name ?? '-' },
  { id: 'pin', header: 'PIN asociado', cell: ({ row }) => row.original.dumper_detail?.ambiental_pin ?? '-' },
  { id: 'driver', header: 'Conductor', cell: ({ row }) => row.original.dumper_detail?.driver ?? '-' },
]
</script>

<template>
  <div>
    <PageHeader title="Vehiculos" description="Tipos de vehiculo y vehiculos registrados" />

    <div class="flex gap-1 mb-6 border-b border-gray-200 overflow-x-auto">
      <button
        v-for="tab in [{ key: 'types', label: 'Tipos de vehiculo' }, { key: 'vehicles', label: 'Vehiculos' }]"
        :key="tab.key"
        @click="activeTab = tab.key as 'types' | 'vehicles'"
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap"
        :class="activeTab === tab.key ? 'border-[#1E40AF] text-[#1E40AF]' : 'border-transparent text-gray-500 hover:text-gray-700'"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Vehicle Types Tab -->
    <div v-if="activeTab === 'types'">
      <div class="flex justify-end mb-4">
        <button v-if="canCreate('masters')" @click="openCreateType" class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600">
          <Plus class="w-4 h-4" /> Nuevo tipo
        </button>
      </div>
      <DataTable :columns="(typeColumns as any)" :data="(types as any)" :is-loading="typesLoading" />
    </div>

    <!-- Vehicles Tab -->
    <div v-if="activeTab === 'vehicles'">
      <div class="flex justify-end mb-4">
        <button v-if="canCreate('masters')" @click="() => { resetVehicleForm(); showVehicleModal = true }" class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600">
          <Plus class="w-4 h-4" /> Nuevo vehiculo
        </button>
      </div>
      <DataTable :columns="(vehicleColumns as any)" :data="(vehicles as any)" :is-loading="vehiclesLoading" />
    </div>

    <!-- Type Modal -->
    <teleport to="body">
      <div v-if="showTypeModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showTypeModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl border-t-4 border-gold-500 p-6 w-full max-w-md mx-4">
          <h2 class="text-lg font-semibold mb-4">{{ editingType ? 'Editar tipo' : 'Nuevo tipo de vehiculo' }}</h2>
          <form @submit.prevent="onTypeSubmit" class="space-y-4" novalidate>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nombre *</label>
              <input v-model="typeName" type="text" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" :class="typeNameError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="typeNameError" class="mt-1 text-xs text-red-600">{{ typeNameError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Capacidad en m3 *</label>
              <input v-model.number="typeCapacity" type="number" step="0.01" min="0.01" class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400" :class="typeCapacityError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="typeCapacityError" class="mt-1 text-xs text-red-600">{{ typeCapacityError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Descripcion</label>
              <textarea v-model="typeDescription" rows="2" class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none resize-none" />
            </div>
            <div class="flex justify-end gap-3">
              <button type="button" @click="showTypeModal = false" class="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">Cancelar</button>
              <button type="submit" :disabled="typeSubmitting" class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60">
                {{ typeSubmitting ? 'Guardando...' : 'Guardar' }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <div v-if="showVehicleModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showVehicleModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl border-t-4 border-gold-500 p-6 w-full max-w-md mx-4">
          <h2 class="text-lg font-semibold mb-4">Nuevo vehiculo</h2>
          <form @submit.prevent="onVehicleSubmit" class="space-y-4" novalidate>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Placa *</label>
              <input v-model="plaque" type="text" maxlength="6" class="w-full px-3 py-2 text-sm border rounded-md uppercase focus:outline-none focus:ring-2 focus:ring-gold-400" :class="plaqueError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="plaqueError" class="mt-1 text-xs text-red-600">{{ plaqueError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Tipo de vehiculo *</label>
              <SearchableSelect :options="activeTypes" v-model="vehicleType" placeholder="Buscar tipo de vehículo..." />
              <p v-if="vehicleTypeError" class="mt-1 text-xs text-red-600">{{ vehicleTypeError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">PIN asociado (opcional)</label>
              <SearchableSelect :options="pinOptions" v-model="dumper" placeholder="Sin PIN" clearable />
            </div>
            <div class="flex justify-end gap-3">
              <button type="button" @click="showVehicleModal = false" class="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">Cancelar</button>
              <button type="submit" :disabled="vehicleSubmitting" class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60">
                {{ vehicleSubmitting ? 'Guardando...' : 'Guardar' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </teleport>

    <ConfirmDialog
      :open="!!confirmToggleType"
      :title="confirmToggleType?.state ? 'Desactivar tipo' : 'Activar tipo'"
      :description="confirmToggleType ? 'Confirmas cambiar el estado de ' + confirmToggleType.name + '?' : ''"
      :loading="toggleTypePending"
      @confirm="confirmToggleType && toggleType(confirmToggleType)"
      @cancel="confirmToggleType = null"
    />
  </div>
</template>
