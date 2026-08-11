<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <div class="mb-6 flex items-center gap-3">
    <span class="w-1 h-8 rounded-full bg-gold-500 flex-shrink-0" />
    <div>
      <h1 class="text-2xl font-semibold text-stone-800">{{ title }}</h1>
      <p v-if="description" class="text-sm text-stone-500 mt-1">{{ description }}</p>
    </div>
  </div>
</template>
