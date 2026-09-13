<script setup lang="ts">
import { computed } from 'vue'
import { formatCurrency } from '@/utils/formatCurrency'
import type { TripsByClientRow } from '@/types'

const props = defineProps<{
  rows: TripsByClientRow[]
  isLoading?: boolean
  // Si se pasa (ej. "16rem"), la tabla queda acotada a ese alto con su propio
  // scroll vertical y encabezado/total fijos — para no obligar a desplazarse
  // por todo el contenedor (KPIs, desglose por pago, etc.) cuando hay muchos
  // clientes, como en el drawer de detalle de un cierre. Sin este prop la
  // tabla crece libremente (comportamiento original, usado en Dashboard y
  // Reporte Diario, donde el scroll de la página ya resuelve listas largas).
  maxHeight?: string
}>()

const totals = computed(() => ({
  trips: props.rows.reduce((s, r) => s + r.trips_count, 0),
  value: props.rows.reduce((s, r) => s + Number(r.total_value), 0),
  volume: props.rows.reduce((s, r) => s + Number(r.total_volume), 0),
}))

function volume(v: number | string): string {
  return Number(v).toLocaleString('es-CO')
}
</script>

<template>
  <div
    class="overflow-x-auto"
    :style="maxHeight ? { maxHeight, overflowY: 'auto' } : undefined"
  >
    <table class="w-full text-sm">
      <thead>
        <tr
          class="bg-gray-50 border-b border-gray-100"
          :class="maxHeight ? 'sticky top-0 z-10' : ''"
        >
          <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cliente</th>
          <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Viajes</th>
          <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Total (COP)</th>
          <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Volumen m³</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-50">
        <tr v-if="isLoading">
          <td colspan="4" class="px-4 py-4"><div class="h-4 bg-gray-200 rounded animate-pulse" /></td>
        </tr>
        <tr v-else-if="rows.length === 0">
          <td colspan="4" class="px-4 py-6 text-center text-xs text-gray-400">Sin viajes registrados.</td>
        </tr>
        <tr v-for="r in rows" :key="r.client" class="hover:bg-gray-50">
          <td class="px-4 py-3 text-gray-700">{{ r.client_name }}</td>
          <td class="px-4 py-3 text-right text-gray-700">{{ r.trips_count }}</td>
          <td class="px-4 py-3 text-right font-semibold text-gray-900">{{ formatCurrency(r.total_value) }}</td>
          <td class="px-4 py-3 text-right text-gray-700">{{ volume(r.total_volume) }}</td>
        </tr>
      </tbody>
      <tfoot v-if="rows.length > 0">
        <tr
          class="bg-gray-50 border-t-2 border-gray-200"
          :class="maxHeight ? 'sticky bottom-0 z-10' : ''"
        >
          <td class="px-4 py-3 text-xs font-semibold text-gray-600">Total</td>
          <td class="px-4 py-3 text-right text-xs font-semibold text-gray-600">{{ totals.trips }}</td>
          <td class="px-4 py-3 text-right text-sm font-bold text-gray-900">{{ formatCurrency(totals.value) }}</td>
          <td class="px-4 py-3 text-right text-xs font-semibold text-gray-600">{{ volume(totals.volume) }}</td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>
