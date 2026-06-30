<script setup lang="ts">
import { ref, computed } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { Save, History, X } from 'lucide-vue-next'
import PageHeader from '@/components/shared/PageHeader.vue'
import CurrencyInput from '@/components/shared/CurrencyInput.vue'
import { tariffsApi } from '@/api/tariffs.api'
import { clientsApi } from '@/api/clients.api'
import { vehicleTypesApi } from '@/api/vehicles.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { usePermissions } from '@/composables/usePermissions'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate } from '@/utils/formatDate'
import { toISODate } from '@/utils/formatDate'
import type { Client, VehicleType, Tariff } from '@/types'

const qc = useQueryClient()
const { canEdit } = usePermissions()

const { data: clientsData } = useQuery({
  queryKey: ['clients'],
  queryFn: async () => (await clientsApi.list({ state: 'true' })).data,
})
const { data: typesData } = useQuery({
  queryKey: ['vehicle-types'],
  queryFn: async () => (await vehicleTypesApi.list()).data,
})
const { data: tariffsData, isLoading } = useQuery({
  queryKey: ['tariffs'],
  queryFn: async () => (await tariffsApi.list()).data,
})

const activeClients = computed(() => (clientsData.value ?? []).filter((c: Client) => c.state))
const activeTypes = computed(() => (typesData.value ?? []).filter((t: VehicleType) => t.state))
const tariffs = computed(() => tariffsData.value ?? [])

// current active tariff per (client, vehicle_type)
function getCurrentTariff(clientId: number | null, typeId: number): Tariff | undefined {
  return tariffs.value.find(
    (t: Tariff) => t.client === clientId && t.vehicle_type === typeId && t.state
  )
}

// Cell edit state: key = `${clientId}-${typeId}`
const editValues = ref<Record<string, number | null>>({})
const dirtyKeys = ref<Set<string>>(new Set())

function cellKey(clientId: number | null, typeId: number) {
  return `${clientId ?? 'general'}-${typeId}`
}

function getCellValue(clientId: number | null, typeId: number): number | null {
  const key = cellKey(clientId, typeId)
  if (key in editValues.value) return editValues.value[key]
  const t = getCurrentTariff(clientId, typeId)
  return t ? parseFloat(t.value) : null
}

function setCellValue(clientId: number | null, typeId: number, val: number | null | undefined) {
  const key = cellKey(clientId, typeId)
  editValues.value[key] = val ?? null
  dirtyKeys.value.add(key)
}

const saving = ref(false)

const { mutateAsync: createTariff } = useMutation({
  mutationFn: (d: Parameters<typeof tariffsApi.create>[0]) => tariffsApi.create(d),
})
const { mutateAsync: updateTariff } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: { value: number } }) => tariffsApi.update(id, data),
})

async function saveAll() {
  if (!dirtyKeys.value.size) return
  saving.value = true
  const today = toISODate(new Date())
  let errors = 0
  for (const key of dirtyKeys.value) {
    const [clientPart, typePart] = key.split('-')
    const clientId = clientPart === 'general' ? null : parseInt(clientPart)
    const typeId = parseInt(typePart)
    const val = editValues.value[key]
    if (!val || val <= 0) continue
    try {
      const existing = getCurrentTariff(clientId, typeId)
      if (existing) {
        await updateTariff({ id: existing.id, data: { value: val } })
      } else {
        await createTariff({ client: clientId, vehicle_type: typeId, value: val, start_date: today })
      }
    } catch {
      errors++
    }
  }
  await qc.invalidateQueries({ queryKey: ['tariffs'] })
  editValues.value = {}
  dirtyKeys.value.clear()
  saving.value = false
  if (errors === 0) {
    toast.success('Tarifas guardadas correctamente.')
  } else {
    toast.error(`${errors} tarifa(s) no se pudieron guardar.`)
  }
}

// History drawer
const historyDrawer = ref<{ open: boolean; clientId: number | null; clientName: string }>({ open: false, clientId: null, clientName: '' })
const historyTariffs = computed(() => {
  if (historyDrawer.value.clientId === null) return []
  return tariffs.value.filter((t: Tariff) => t.client === historyDrawer.value.clientId).sort(
    (a: Tariff, b: Tariff) => (b.start_date ?? '').localeCompare(a.start_date ?? '')
  )
})

function openHistory(client: Client) {
  historyDrawer.value = { open: true, clientId: client.id, clientName: client.name }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <PageHeader title="Tarifas" description="Tarifas por cliente y tipo de vehiculo" />
      <button
        v-if="canEdit('masters') && dirtyKeys.size > 0"
        @click="saveAll"
        :disabled="saving"
        class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[#1E40AF] rounded-md hover:bg-blue-700 disabled:opacity-60"
      >
        <Save class="w-4 h-4" />
        {{ saving ? 'Guardando...' : 'Guardar cambios' }}
      </button>
    </div>

    <div v-if="isLoading" class="text-center py-12 text-gray-400">Cargando tarifas...</div>
    <div v-else class="bg-white border border-gray-200 rounded-lg overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase sticky left-0 bg-gray-50">Cliente</th>
            <th v-for="t in activeTypes" :key="t.id" class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase whitespace-nowrap">
              {{ t.name }}
            </th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Historial</th>
          </tr>
        </thead>
        <tbody>
          <!-- General row -->
          <tr class="border-b border-gray-100 bg-blue-50">
            <td class="px-4 py-3 font-medium text-gray-800 sticky left-0 bg-blue-50">Tarifa general</td>
            <td v-for="t in activeTypes" :key="t.id" class="px-4 py-2">
              <CurrencyInput
                v-if="canEdit('masters')"
                :model-value="getCellValue(null, t.id)"
                @update:model-value="(val) => setCellValue(null, t.id, val)"
                class="w-36"
              />
              <span v-else>{{ formatCurrency(getCellValue(null, t.id)) }}</span>
            </td>
            <td class="px-4 py-3"></td>
          </tr>
          <!-- Per client rows -->
          <tr v-for="client in activeClients" :key="client.id" class="border-b border-gray-100 hover:bg-gray-50">
            <td class="px-4 py-3 text-gray-700 sticky left-0 bg-white">{{ client.name }}</td>
            <td v-for="t in activeTypes" :key="t.id" class="px-4 py-2">
              <CurrencyInput
                v-if="canEdit('masters')"
                :model-value="getCellValue(client.id, t.id)"
                @update:model-value="(val) => setCellValue(client.id, t.id, val)"
                class="w-36"
              />
              <span v-else>{{ formatCurrency(getCellValue(client.id, t.id)) }}</span>
            </td>
            <td class="px-4 py-3">
              <button @click="openHistory(client)" class="p-1 text-gray-400 hover:text-blue-600" title="Ver historial">
                <History class="w-4 h-4" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- History Drawer -->
    <teleport to="body">
      <div v-if="historyDrawer.open" class="fixed inset-0 z-50 flex justify-end">
        <div class="absolute inset-0 bg-black/40" @click="historyDrawer.open = false" />
        <div class="relative bg-white w-full max-w-lg h-full overflow-y-auto shadow-xl">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 class="text-lg font-semibold">Historial de tarifas</h2>
            <button @click="historyDrawer.open = false" class="p-1 text-gray-400 hover:text-gray-600">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="px-6 py-4">
            <p class="text-sm text-gray-500 mb-4">Cliente: <span class="font-medium text-gray-800">{{ historyDrawer.clientName }}</span></p>
            <table class="w-full text-sm">
              <thead class="text-xs text-gray-500 uppercase">
                <tr>
                  <th class="text-left py-2">Tipo vehiculo</th>
                  <th class="text-left py-2">Valor</th>
                  <th class="text-left py-2">Inicio</th>
                  <th class="text-left py-2">Fin</th>
                  <th class="text-left py-2">Estado</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in historyTariffs" :key="t.id" class="border-b border-gray-100">
                  <td class="py-2">{{ t.vehicle_type_name }}</td>
                  <td class="py-2">{{ formatCurrency(parseFloat(t.value)) }}</td>
                  <td class="py-2">{{ formatDate(t.start_date) }}</td>
                  <td class="py-2">{{ t.end_date ? formatDate(t.end_date) : '-' }}</td>
                  <td class="py-2">
                    <span :class="t.state ? 'text-green-600' : 'text-gray-400'">{{ t.state ? 'Activa' : 'Cerrada' }}</span>
                  </td>
                </tr>
                <tr v-if="historyTariffs.length === 0">
                  <td colspan="5" class="py-6 text-center text-gray-400">Sin historial de tarifas</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>
