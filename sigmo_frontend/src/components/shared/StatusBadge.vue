<script setup lang="ts">
defineProps<{ active: boolean }>()
</script>

<template>
  <span
    class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
    :class="active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'"
  >
    {{ active ? 'Activo' : 'Inactivo' }}
  </span>
</template>
