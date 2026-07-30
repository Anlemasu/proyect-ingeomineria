<script setup lang="ts">
import { ref, watch } from 'vue'
import { formatCurrency } from '@/utils/formatCurrency'

const props = withDefaults(defineProps<{
  modelValue: number | null | undefined
  placeholder?: string
  disabled?: boolean
  readonly?: boolean
}>(), {
  placeholder: '$ 0',
  disabled: false,
  readonly: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: number | null | undefined] }>()

const display = ref(props.modelValue != null ? formatCurrency(props.modelValue) : '')

watch(() => props.modelValue, (val) => {
  display.value = val != null ? formatCurrency(val) : ''
})

function onInput(e: Event) {
  if (props.readonly || props.disabled) return
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
    :readonly="readonly || disabled"
    :disabled="disabled"
    class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
    :class="[
      disabled ? 'bg-gray-50 text-gray-400 cursor-not-allowed border-gray-200' :
      readonly ? 'bg-gray-50 text-gray-700 border-gray-300 cursor-default' :
                 'bg-white text-gray-900 border-gray-300'
    ]"
    :placeholder="placeholder"
    @input="onInput"
  />
</template>
