<script setup lang="ts">
import { computed } from 'vue'
import { VueDatePicker } from '@vuepic/vue-datepicker'
import '@vuepic/vue-datepicker/dist/main.css'

const props = withDefaults(defineProps<{
  modelValue: string | null | undefined
  placeholder?: string
  disabled?: boolean
  readonly?: boolean
  error?: boolean
  min?: string
  max?: string
  clearable?: boolean
}>(), {
  placeholder: 'dd/mm/aaaa',
  disabled: false,
  readonly: false,
  error: false,
  clearable: true,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

// El input nativo type="date" siempre entrega/recibe un string 'yyyy-MM-dd'
// (o '' cuando está vacío). model-type mantiene ese mismo contrato para no
// afectar nada del formato que ya consumen los formularios y el backend.
function onUpdate(value: string | null) {
  emit('update:modelValue', value ?? '')
}

// :readonly en los usos existentes solo bloqueaba la edición manteniendo el
// campo visible con estilo "deshabilitado"; el datepicker no distingue
// readonly de disabled, así que lo tratamos igual.
const isDisabled = computed(() => props.disabled || props.readonly)

function toDate(value: string | undefined) {
  return value ? new Date(`${value}T00:00:00`) : undefined
}
const minDate = computed(() => toDate(props.min))
const maxDate = computed(() => toDate(props.max))

// La v14 de vue-datepicker agrupa casi todo en props anidadas — un `format`,
// `enable-time-picker` o `clearable` de nivel raíz (API de versiones viejas)
// no existen y quedan como atributos HTML inertes sin avisar de nada.
const timeConfig = { enableTimePicker: false }
const formats = { input: 'dd/MM/yyyy' }
const ui = { input: 'sigmo-dp-input' }
const inputAttrs = computed(() => ({ clearable: props.clearable && !isDisabled.value }))
</script>

<template>
  <VueDatePicker
    :model-value="modelValue || null"
    model-type="yyyy-MM-dd"
    :formats="formats"
    :time-config="timeConfig"
    :ui="ui"
    :input-attrs="inputAttrs"
    :disabled="isDisabled"
    :placeholder="placeholder"
    :min-date="minDate"
    :max-date="maxDate"
    auto-apply
    text-input
    :class="['sigmo-dp', error && 'sigmo-dp--error', isDisabled && 'sigmo-dp--disabled']"
    @update:model-value="onUpdate"
  />
</template>

<style>
.sigmo-dp {
  --dp-primary-color: #FBB903;
  --dp-primary-text-color: #1f2937;
  --dp-border-radius: 0.375rem;
  --dp-font-family: 'Inter', sans-serif;
  --dp-font-size: 0.875rem;
  --dp-input-padding: 0.5rem 0.75rem;
  width: 100%;
}

.sigmo-dp-input {
  border-color: #d1d5db;
}
.sigmo-dp-input:hover {
  border-color: #9ca3af;
}
.sigmo-dp-input:focus {
  --dp-border-color-focus: #FCC419;
  box-shadow: 0 0 0 2px rgba(252, 196, 25, 0.5);
}

.sigmo-dp--error .sigmo-dp-input {
  border-color: #f87171 !important;
  background-color: #fef2f2;
}

.sigmo-dp--disabled .sigmo-dp-input {
  border-color: #e5e7eb !important;
  background-color: #f9fafb !important;
  color: #4b5563 !important;
  cursor: default !important;
}
</style>
