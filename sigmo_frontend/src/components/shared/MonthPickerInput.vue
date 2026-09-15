<script setup lang="ts">
import { computed } from 'vue'
import { VueDatePicker } from '@vuepic/vue-datepicker'
import '@vuepic/vue-datepicker/dist/main.css'

// Mismo picker y mismas clases (.sigmo-dp / .sigmo-dp-input, definidas sin
// `scoped` en DatePickerInput.vue y por eso ya globales) que el selector de
// fecha normal — solo cambia `month-picker` + el formato, para que Quincenal
// y Mensual se vean con el mismo estilo que Diario/Personalizado.
const props = withDefaults(defineProps<{
  modelValue: string | null | undefined
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// Contrato: string 'yyyy-MM' (o '' vacío), igual que DatePickerInput usa 'yyyy-MM-dd'.
function onUpdate(value: string | null) {
  emit('update:modelValue', value ?? '')
}

const formats = { input: 'MM/yyyy' }
const ui = { input: 'sigmo-dp-input' }
const inputAttrs = computed(() => ({ clearable: false }))
</script>

<template>
  <VueDatePicker
    :model-value="modelValue || null"
    model-type="yyyy-MM"
    month-picker
    :formats="formats"
    :ui="ui"
    :input-attrs="inputAttrs"
    :disabled="disabled"
    placeholder="mm/aaaa"
    auto-apply
    class="sigmo-dp"
    :class="disabled && 'sigmo-dp--disabled'"
    @update:model-value="onUpdate"
  />
</template>
