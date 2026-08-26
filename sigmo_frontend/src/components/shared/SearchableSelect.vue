<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { ChevronDown, X } from 'lucide-vue-next'

interface Option {
  id: number
  name: string
}

const props = withDefaults(defineProps<{
  options: Option[]
  modelValue: number | null | undefined
  placeholder?: string
  disabled?: boolean
  clearable?: boolean
  extraActionLabel?: string
}>(), {
  placeholder: 'Seleccionar...',
  disabled: false,
  clearable: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  'extraAction': []
}>()

const open = ref(false)
// `typed` es exactamente lo que el usuario escribió — la lista se filtra con esto.
// `query` es lo que se muestra en el input, que puede incluir el sufijo autocompletado.
const typed = ref('')
const query = ref('')
const highlighted = ref(0)
const browsingAll = ref(true)
const inputEl = ref<HTMLInputElement>()
const root = ref<HTMLElement>()
const itemEls = ref<(HTMLLIElement | null)[]>([])

const COMBINING_MARKS = /[̀-ͯ]/g

function normalize(s: string) {
  return s.normalize('NFD').replace(COMBINING_MARKS, '').toLowerCase()
}

const selectedLabel = computed(() =>
  props.options.find(o => o.id === props.modelValue)?.name ?? ''
)

watch(selectedLabel, (label) => {
  if (!open.value) { query.value = label; typed.value = label }
}, { immediate: true })

const filtered = computed(() => {
  if (browsingAll.value) return props.options
  const q = normalize(typed.value.trim())
  if (!q) return props.options
  return props.options.filter(o => normalize(o.name).includes(q))
})

watch(highlighted, (idx) => {
  nextTick(() => itemEls.value[idx]?.scrollIntoView({ block: 'nearest' }))
})

// Índice a resaltar al abrir la lista: el de la opción ya seleccionada si existe,
// o ninguno (-1) si no hay nada elegido todavía — así Tab/Enter en un campo vacío
// no seleccionan por accidente el primer ítem de la lista.
function initialHighlight(list: Option[]) {
  const idx = list.findIndex(o => o.id === props.modelValue)
  return idx >= 0 ? idx : -1
}

function openList() {
  if (props.disabled) return
  open.value = true
  highlighted.value = initialHighlight(filtered.value)
}

function onFocus() {
  browsingAll.value = true
  openList()
  nextTick(() => inputEl.value?.select())
}

function onInput(e: Event) {
  const raw = (e.target as HTMLInputElement).value
  const inputType = (e as InputEvent).inputType
  const isDeleting = !!inputType && inputType.startsWith('delete')

  browsingAll.value = false
  open.value = true
  typed.value = raw
  query.value = raw

  // Al borrar (Backspace/Delete) nunca se re-completa: si no, el usuario
  // borra el sufijo sugerido y el autocompletado lo vuelve a poner,
  // dando la sensación de que no se puede borrar nada.
  if (!raw) {
    highlighted.value = -1
    return
  }
  if (isDeleting) {
    highlighted.value = 0
    return
  }

  // Autocompletado en línea: rellena con la primera coincidencia (por prefijo)
  // y deja el resto seleccionado para que la siguiente tecla lo sobrescriba.
  const q = normalize(raw)
  const match = props.options.find(o => normalize(o.name).startsWith(q))
  if (match) {
    if (match.name.length > raw.length) {
      query.value = match.name
      nextTick(() => inputEl.value?.setSelectionRange(raw.length, match.name.length))
    }
    const idx = filtered.value.findIndex(o => o.id === match.id)
    highlighted.value = idx >= 0 ? idx : 0
  } else {
    highlighted.value = 0
  }
}

function select(opt: Option) {
  emit('update:modelValue', opt.id)
  query.value = opt.name
  typed.value = opt.name
  open.value = false
}

function clear(e: Event) {
  e.stopPropagation()
  e.preventDefault()
  emit('update:modelValue', null)
  query.value = ''
  typed.value = ''
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (!open.value) { openList(); return }
    highlighted.value = Math.min(highlighted.value + 1, filtered.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const opt = filtered.value[highlighted.value]
    if (opt) select(opt)
  } else if (e.key === 'Escape') {
    open.value = false
    query.value = selectedLabel.value
    typed.value = selectedLabel.value
    inputEl.value?.blur()
  } else if (e.key === 'Tab') {
    // Igual que Enter: confirma la opción resaltada (la autocompletada o la
    // navegada con flechas) y deja que el navegador mueva el foco al siguiente
    // campo — por eso no hacemos preventDefault en ese caso.
    if (open.value) {
      const opt = filtered.value[highlighted.value]
      if (opt) {
        select(opt)
      } else if (typed.value.trim()) {
        // Hay texto escrito que no corresponde a ninguna opción (typo): no
        // dejamos avanzar con un valor inválido a medias — se queda en el
        // campo (la lista ya muestra "Sin resultados") hasta que se corrija
        // o se borre.
        e.preventDefault()
      } else {
        open.value = false
      }
    }
  }
}

function onBlur() {
  open.value = false
  const q = normalize(query.value.trim())
  const match = props.options.find(o => normalize(o.name) === q)
  if (match) {
    if (match.id !== props.modelValue) emit('update:modelValue', match.id)
    query.value = match.name
    typed.value = match.name
    return
  }
  if (!q && props.clearable) {
    if (props.modelValue != null) emit('update:modelValue', null)
    query.value = ''
    typed.value = ''
    return
  }
  query.value = selectedLabel.value
  typed.value = selectedLabel.value
}

function onOutside(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onOutside))
onUnmounted(() => document.removeEventListener('mousedown', onOutside))

defineExpose({
  focus: () => inputEl.value?.focus(),
})
</script>

<template>
  <div ref="root" class="relative">
    <div class="relative">
      <input
        ref="inputEl"
        :value="query"
        type="text"
        autocomplete="off"
        :placeholder="placeholder"
        :disabled="disabled"
        class="w-full px-3 py-2 pr-16 text-sm border rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
        :class="disabled
          ? 'border-gray-200 bg-gray-50 cursor-not-allowed text-gray-400'
          : 'border-gray-300 hover:border-gray-400 text-gray-900'"
        @focus="onFocus"
        @input="onInput"
        @keydown="onKeydown"
        @blur="onBlur"
      />
      <span class="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
        <X
          v-if="clearable && modelValue != null"
          class="w-3.5 h-3.5 text-gray-400 hover:text-gray-600 cursor-pointer"
          @mousedown.prevent="clear"
        />
        <ChevronDown class="w-4 h-4 text-gray-400 pointer-events-none" :class="open ? 'rotate-180' : ''" />
      </span>
    </div>

    <Transition
      enter-active-class="transition-all duration-100"
      enter-from-class="opacity-0 translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-75"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="open"
        class="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg"
      >
        <ul class="max-h-52 overflow-y-auto py-1">
          <li v-if="filtered.length === 0" class="px-3 py-2 text-sm text-gray-400 italic">
            Sin resultados
          </li>
          <li
            v-for="(opt, idx) in filtered"
            :key="opt.id"
            :ref="el => { itemEls[idx] = el as HTMLLIElement | null }"
            @mousedown.prevent="select(opt)"
            class="px-3 py-2 text-sm cursor-pointer transition-colors"
            :class="idx === highlighted ? 'bg-gold-50 text-gold-800 font-medium' : 'hover:bg-gold-50 text-gray-900'"
          >
            {{ opt.name }}
          </li>
          <li
            v-if="extraActionLabel"
            @mousedown.prevent="emit('extraAction'); open = false"
            class="px-3 py-2 text-sm cursor-pointer text-gold-700 hover:bg-gold-50 border-t border-gray-100 font-medium"
          >
            + {{ extraActionLabel }}
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>
