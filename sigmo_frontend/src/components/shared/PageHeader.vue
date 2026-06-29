<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <div class="mb-6">
    <h1 class="text-2xl font-semibold text-gray-900">{{ title }}</h1>
    <p v-if="description" class="text-sm text-gray-500 mt-1">{{ description }}</p>
  </div>
</template>
