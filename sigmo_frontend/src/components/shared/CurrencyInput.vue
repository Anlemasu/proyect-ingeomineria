<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatCurrency } from '@/utils/formatCurrency'

const props = defineProps<{ modelValue: number | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: number | null] }>()

const display = ref(props.modelValue != null ? formatCurrency(props.modelValue) : '')

watch(() => props.modelValue, (val) => {
  display.value = val != null ? formatCurrency(val) : ''
})

function onInput(e: Event) {
  const raw = (e.target as HTMLInputElement).value.replace(/[^0-9]/g, '')
  const num = raw ? parseInt(raw, 10) : null
  emit('update:modelValue', num)
  display.value = num != null ? formatCurrency(num) : ''
}
</script>

<template>
  <input
    :value="display"
    type="text"
    inputmode="numeric"
    class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
    @input="onInput"
    placeholder="$ 0"
  />
</template>
