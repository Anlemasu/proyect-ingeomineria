<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Plus, Upload, ToggleLeft, ToggleRight, X, ChevronDown, ChevronUp, Loader2 } from 'lucide-vue-next'
import type { ColumnDef } from '@tanstack/vue-table'
import DataTable from '@/components/shared/DataTable.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import StatusBadge from '@/components/shared/StatusBadge.vue'
import { pinsApi } from '@/api/pins.api'
import { getApiErrorMessage, toastApiError } from '@/utils/handleApiError'
import { usePermissions } from '@/composables/usePermissions'
import { formatDate } from '@/utils/formatDate'
import type { PinsDumper, ImportResult } from '@/types'

const qc = useQueryClient()
const { canCreate } = usePermissions()

const showModal = ref(false)
const showImport = ref(false)
const importFile = ref<File | null>(null)
const importResult = ref<ImportResult | null>(null)
const importRejectedOpen = ref(false)
const fileError = ref('')
const previewRows = ref<string[][]>([])

const { data, isLoading } = useQuery({
  queryKey: ['pins'],
  queryFn: async () => (await pinsApi.list()).data,
})
const rows = computed(() => data.value ?? [])

const schema = toTypedSchema(z.object({
  ambiental_pin: z.string().min(1, 'El PIN es requerido').max(30).transform(s => s.trim()),
  propietary: z.string().min(1, 'El propietario es requerido').max(50).transform(s => s.trim()),
  address: z.string().min(1, 'La direccion es requerida').max(20).transform(s => s.trim()),
  phone: z.string().regex(/^\d+$/, 'Solo numeros').max(10),
  email: z.string().email('Email invalido').max(20).transform(s => s.trim()),
  plaque: z.string().min(6).max(6, 'La placa debe tener 6 caracteres').transform(s => s.trim().toUpperCase()),
  expedition_site: z.string().min(1, 'Requerido').max(20).transform(s => s.trim()),
  model: z.string().min(1, 'Requerido').max(50).transform(s => s.trim()),
  capacity: z.number({ message: 'Capacidad requerida' }).positive('Debe ser mayor a 0'),
  driver: z.string().min(1, 'El conductor es requerido').max(50).transform(s => s.trim()),
  date_register: z.string().min(1, 'La fecha es requerida'),
}))

const { handleSubmit, isSubmitting, resetForm } = useForm({ validationSchema: schema })
const { value: ambiental_pin, errorMessage: pinError } = useField<string>('ambiental_pin')
const { value: propietary, errorMessage: propietaryError } = useField<string>('propietary')
const { value: address, errorMessage: addressError } = useField<string>('address')
const { value: phone, errorMessage: phoneError } = useField<string>('phone')
const { value: email, errorMessage: emailError } = useField<string>('email')
const { value: plaque, errorMessage: plaqueError } = useField<string>('plaque')
const { value: expedition_site, errorMessage: expeditionError } = useField<string>('expedition_site')
const { value: model, errorMessage: modelError } = useField<string>('model')
const { value: capacity, errorMessage: capacityError } = useField<number>('capacity')
const { value: driver, errorMessage: driverError } = useField<string>('driver')
const { value: date_register, errorMessage: dateError } = useField<string>('date_register')

const { mutateAsync: create } = useMutation({
  mutationFn: (d: Partial<PinsDumper>) => pinsApi.create(d),
  onSuccess: () => { qc.invalidateQueries({ queryKey: ['pins'] }); toast.success('PIN registrado.') },
})

const onSubmit = handleSubmit(async (values) => {
  try {
    await create({ ...values, capacity: String(values.capacity), phone: values.phone })
    showModal.value = false
  } catch (err) {
    toastApiError(err)
  }
})

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  fileError.value = ''
  importResult.value = null
  previewRows.value = []
  if (!file) return
  if (file.size > 25 * 1024 * 1024) { fileError.value = 'El archivo no puede superar 25MB.'; return }
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['xlsx', 'csv', 'pdf'].includes(ext ?? '')) { fileError.value = 'Solo se aceptan archivos .xlsx, .csv o .pdf.'; return }
  importFile.value = file
}

const { mutate: doImport, isPending: importPending } = useMutation({
  mutationFn: (file: File) => pinsApi.importFile(file),
  onSuccess: (res) => {
    importResult.value = res.data
    qc.invalidateQueries({ queryKey: ['pins'] })
    qc.invalidateQueries({ queryKey: ['vehicles'] })
    toast.success(`Importacion completada: ${res.data.created} creados, ${res.data.updated} actualizados.`)
  },
  onError: (err) => toastApiError(err),
})

function confirmImport() {
  if (!importFile.value) return
  doImport(importFile.value)
}

const columns: ColumnDef<PinsDumper>[] = [
  { accessorKey: 'ambiental_pin', header: 'N PIN' },
  { accessorKey: 'plaque', header: 'Placa' },
  { accessorKey: 'propietary', header: 'Propietario' },
  { accessorKey: 'driver', header: 'Conductor' },
  { accessorKey: 'capacity', header: 'Capacidad' },
  { id: 'date_register', header: 'Fecha registro', cell: ({ row }) => formatDate(row.original.date_register) },
  { accessorKey: 'state', header: 'Estado', cell: ({ row }) => h(StatusBadge, { active: row.original.state }) },
]
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <PageHeader title="Pines ambientales" description="Registro y gestion de pines ambientales" />
      <div class="flex flex-wrap gap-2">
        <button v-if="canCreate('masters')" @click="showImport = true" class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">
          <Upload class="w-4 h-4" /> Importar Excel/PDF
        </button>
        <button v-if="canCreate('masters')" @click="() => { resetForm(); showModal = true }" class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600">
          <Plus class="w-4 h-4" /> Nuevo PIN
        </button>
      </div>
    </div>

    <DataTable :columns="(columns as any)" :data="(rows as any)" :is-loading="isLoading" />

    <!-- Manual Register Modal -->
    <teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl border-t-4 border-gold-500 p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
          <h2 class="text-lg font-semibold mb-4">Nuevo PIN ambiental</h2>
          <form @submit.prevent="onSubmit" class="grid grid-cols-1 sm:grid-cols-2 gap-4" novalidate>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">PIN ambiental *</label>
              <input v-model="ambiental_pin" type="text" class="w-full px-3 py-2 text-sm border rounded-md" :class="pinError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="pinError" class="mt-1 text-xs text-red-600">{{ pinError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Propietario *</label>
              <input v-model="propietary" type="text" class="w-full px-3 py-2 text-sm border rounded-md" :class="propietaryError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="propietaryError" class="mt-1 text-xs text-red-600">{{ propietaryError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Placa *</label>
              <input v-model="plaque" type="text" maxlength="6" class="w-full px-3 py-2 text-sm border rounded-md uppercase" :class="plaqueError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="plaqueError" class="mt-1 text-xs text-red-600">{{ plaqueError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Conductor *</label>
              <input v-model="driver" type="text" class="w-full px-3 py-2 text-sm border rounded-md" :class="driverError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="driverError" class="mt-1 text-xs text-red-600">{{ driverError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Direccion *</label>
              <input v-model="address" type="text" class="w-full px-3 py-2 text-sm border rounded-md" :class="addressError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="addressError" class="mt-1 text-xs text-red-600">{{ addressError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Telefono *</label>
              <input v-model="phone" type="text" inputmode="numeric" class="w-full px-3 py-2 text-sm border rounded-md" :class="phoneError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="phoneError" class="mt-1 text-xs text-red-600">{{ phoneError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Email *</label>
              <input v-model="email" type="email" class="w-full px-3 py-2 text-sm border rounded-md" :class="emailError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="emailError" class="mt-1 text-xs text-red-600">{{ emailError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Sitio de expedicion *</label>
              <input v-model="expedition_site" type="text" class="w-full px-3 py-2 text-sm border rounded-md" :class="expeditionError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="expeditionError" class="mt-1 text-xs text-red-600">{{ expeditionError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Modelo *</label>
              <input v-model="model" type="text" class="w-full px-3 py-2 text-sm border rounded-md" :class="modelError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="modelError" class="mt-1 text-xs text-red-600">{{ modelError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Capacidad *</label>
              <input v-model.number="capacity" type="number" step="0.01" min="0.01" class="w-full px-3 py-2 text-sm border rounded-md" :class="capacityError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="capacityError" class="mt-1 text-xs text-red-600">{{ capacityError }}</p>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Fecha de registro *</label>
              <input v-model="date_register" type="date" class="w-full px-3 py-2 text-sm border rounded-md" :class="dateError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="dateError" class="mt-1 text-xs text-red-600">{{ dateError }}</p>
            </div>
            <div class="col-span-2 flex justify-end gap-3 pt-2">
              <button type="button" @click="showModal = false" class="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">Cancelar</button>
              <button type="submit" :disabled="isSubmitting" class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60">
                {{ isSubmitting ? 'Guardando...' : 'Guardar' }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <!-- Import Modal -->
      <div v-if="showImport" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="!importPending && (showImport = false)" />
        <div class="relative bg-white rounded-lg shadow-xl border-t-4 border-gold-500 p-6 w-full max-w-lg mx-4 max-h-[85vh] overflow-y-auto">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-semibold">Importar pines desde Excel o PDF</h2>
            <button v-if="!importPending" @click="showImport = false" class="text-gray-400 hover:text-gray-600"><X class="w-5 h-5" /></button>
          </div>

          <!-- Loading -->
          <div v-if="importPending" class="flex flex-col items-center justify-center text-center py-10">
            <Loader2 class="w-10 h-10 text-gold-500 animate-spin mb-4" />
            <p class="text-sm font-medium text-gray-800">Importando pines...</p>
            <p v-if="importFile" class="text-xs text-gray-500 mt-1">{{ importFile.name }}</p>
            <p class="text-xs text-gray-500 mt-3 max-w-sm">
              El listado oficial trae miles de filas: esto puede tardar varios minutos.
              No cierres esta ventana ni recargues la pagina, la importacion sigue en curso.
            </p>
          </div>

          <!-- File picker -->
          <div v-else-if="!importResult" class="space-y-4">
            <div class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
              <input type="file" accept=".xlsx,.csv,.pdf" class="hidden" id="import-file" @change="onFileChange" />
              <label for="import-file" class="cursor-pointer">
                <Upload class="w-8 h-8 text-gray-400 mx-auto mb-2" />
                <p class="text-sm text-gray-600">Haz clic para seleccionar un archivo <span class="text-[#1E40AF] font-medium">.xlsx, .csv o .pdf</span></p>
                <p class="text-xs text-gray-400 mt-1">Maximo 25MB</p>
              </label>
              <p v-if="importFile" class="mt-2 text-sm font-medium text-gray-700">{{ importFile.name }}</p>
              <p v-if="fileError" class="mt-2 text-xs text-red-600">{{ fileError }}</p>
            </div>

            <div class="flex justify-end gap-3">
              <button @click="showImport = false" class="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">Cancelar</button>
              <button
                @click="confirmImport"
                :disabled="!importFile || !!fileError"
                class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60"
              >
                Confirmar importacion
              </button>
            </div>
          </div>

          <!-- Import Result -->
          <div v-else class="space-y-4">
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div class="bg-green-50 rounded-lg p-3 text-center">
                <p class="text-2xl font-bold text-green-700">{{ importResult.created }}</p>
                <p class="text-xs text-green-600">Creados</p>
              </div>
              <div class="bg-gold-50 rounded-lg p-3 text-center">
                <p class="text-2xl font-bold text-gold-800">{{ importResult.updated }}</p>
                <p class="text-xs text-gold-700">Actualizados</p>
              </div>
              <div class="bg-blue-50 rounded-lg p-3 text-center">
                <p class="text-2xl font-bold text-blue-700">{{ importResult.vehicles_synced }}</p>
                <p class="text-xs text-blue-600">Vehiculos sincronizados</p>
              </div>
              <div class="bg-red-50 rounded-lg p-3 text-center">
                <p class="text-2xl font-bold text-red-700">{{ importResult.rejected_count }}</p>
                <p class="text-xs text-red-600">Rechazados</p>
              </div>
            </div>

            <div v-if="importResult.rejected_count > 0">
              <button @click="importRejectedOpen = !importRejectedOpen" class="flex items-center gap-1 text-sm text-red-600 hover:underline">
                <component :is="importRejectedOpen ? ChevronUp : ChevronDown" class="w-4 h-4" />
                Ver {{ importResult.rejected_count }} registro(s) rechazado(s)
              </button>
              <div v-if="importRejectedOpen" class="mt-2 border border-red-200 rounded-md max-h-64 overflow-y-auto overflow-x-auto">
                <table class="w-full text-xs">
                  <thead class="bg-red-50 sticky top-0">
                    <tr>
                      <th class="px-3 py-2 text-left text-red-600">Fila</th>
                      <th class="px-3 py-2 text-left text-red-600">Placa</th>
                      <th class="px-3 py-2 text-left text-red-600">Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(r, i) in importResult.rejected" :key="i" class="border-t border-red-100">
                      <td class="px-3 py-2 whitespace-nowrap">{{ r.fila }}</td>
                      <td class="px-3 py-2 whitespace-nowrap">{{ r.placa ?? '-' }}</td>
                      <td class="px-3 py-2">{{ r.motivo }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="flex justify-end sticky bottom-0 bg-white pt-2 -mb-6 pb-6">
              <button @click="() => { showImport = false; importResult = null; importFile = null }" class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600">
                Aceptar
              </button>
            </div>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>
