<script setup lang="ts">
import { ref, watch } from 'vue'

// Input numérico con estado LOCAL propio (no controlado directamente por
// `modelValue` en cada tecla) — evita el problema clásico de las celdas
// editables en tablas: si el padre re-renderiza la celda en cada `input`
// (porque `modelValue` vive en un objeto reactivo compartido), un `:value`
// controlado puede saltar el cursor al final en cada tecla. Aquí el campo
// se muestra a sí mismo (`local`) y solo AVISA al padre por evento.
const props = defineProps<{
  modelValue: number | undefined
  disabled?: boolean
}>()
const emit = defineEmits<{
  'update:modelValue': [value: number | undefined]
}>()

const local = ref<string>(props.modelValue != null ? String(props.modelValue) : '')

// Si el padre cambia el valor desde afuera (p.ej. cambió la fecha
// seleccionada y este campo se precarga con el conteo de la nueva fecha),
// sí hay que reflejarlo.
watch(() => props.modelValue, (v) => {
  local.value = v != null ? String(v) : ''
})

function onInput(e: Event) {
  const raw = (e.target as HTMLInputElement).value
  local.value = raw
  emit('update:modelValue', raw === '' ? undefined : Number(raw))
}
</script>

<template>
  <input
    type="number"
    min="0"
    step="1"
    :value="local"
    :disabled="disabled"
    @input="onInput"
    class="w-20 rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-gold-400 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed"
  />
</template>
