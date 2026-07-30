<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
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
const search = ref('')
const searchInput = ref<HTMLInputElement>()
const root = ref<HTMLElement>()

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return props.options
  return props.options.filter(o => o.name.toLowerCase().includes(q))
})

const selectedLabel = computed(() =>
  props.options.find(o => o.id === props.modelValue)?.name ?? ''
)

function select(id: number) {
  emit('update:modelValue', id)
  open.value = false
  search.value = ''
}

function clear(e: Event) {
  e.stopPropagation()
  emit('update:modelValue', null)
}

function toggle() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) {
    nextTick(() => searchInput.value?.focus())
  } else {
    search.value = ''
  }
}

function onOutside(e: MouseEvent) {
  if (root.value && !root.value.contains(e.target as Node)) {
    open.value = false
    search.value = ''
  }
}

onMounted(() => document.addEventListener('mousedown', onOutside))
onUnmounted(() => document.removeEventListener('mousedown', onOutside))
</script>

<template>
  <div ref="root" class="relative">
    <button
      type="button"
      @click="toggle"
      :disabled="disabled"
      class="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm border rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-gold-400 transition-colors"
      :class="disabled
        ? 'border-gray-200 bg-gray-50 cursor-not-allowed text-gray-400'
        : 'border-gray-300 hover:border-gray-400 text-gray-900'"
    >
      <span :class="selectedLabel ? '' : 'text-gray-400'">
        {{ selectedLabel || placeholder }}
      </span>
      <span class="flex items-center gap-1 shrink-0">
        <X
          v-if="clearable && modelValue != null"
          class="w-3.5 h-3.5 text-gray-400 hover:text-gray-600"
          @click="clear"
        />
        <ChevronDown class="w-4 h-4 text-gray-400" :class="open ? 'rotate-180' : ''" />
      </span>
    </button>

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
        <div class="p-2 border-b border-gray-100">
          <input
            ref="searchInput"
            v-model="search"
            type="text"
            placeholder="Buscar..."
            class="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-gold-400"
          />
        </div>
        <ul class="max-h-52 overflow-y-auto py-1">
          <li v-if="filtered.length === 0" class="px-3 py-2 text-sm text-gray-400 italic">
            Sin resultados
          </li>
          <li
            v-for="opt in filtered"
            :key="opt.id"
            @click="select(opt.id)"
            class="px-3 py-2 text-sm cursor-pointer hover:bg-gold-50 transition-colors"
            :class="modelValue === opt.id ? 'bg-gold-50 font-medium text-gold-800' : 'text-gray-900'"
          >
            {{ opt.name }}
          </li>
          <li
            v-if="extraActionLabel"
            @click="emit('extraAction'); open = false; search = ''"
            class="px-3 py-2 text-sm cursor-pointer text-gold-700 hover:bg-gold-50 border-t border-gray-100 font-medium"
          >
            + {{ extraActionLabel }}
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>
