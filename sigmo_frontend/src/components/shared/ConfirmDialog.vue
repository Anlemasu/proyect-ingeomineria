<script setup lang="ts">
defineProps<{
  open: boolean
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<template>
  <teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/50" @click="emit('cancel')" />
      <div class="relative bg-white rounded-lg shadow-xl p-6 max-w-md w-full mx-4">
        <h2 class="text-lg font-semibold text-gray-900">{{ title }}</h2>
        <p v-if="description" class="mt-2 text-sm text-gray-600">{{ description }}</p>
        <div class="mt-6 flex justify-end gap-3">
          <button
            @click="emit('cancel')"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            {{ cancelLabel ?? 'Cancelar' }}
          </button>
          <button
            @click="emit('confirm')"
            :disabled="loading"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-800 rounded-md hover:bg-blue-700 disabled:opacity-60"
          >
            {{ loading ? 'Procesando...' : (confirmLabel ?? 'Confirmar') }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>
