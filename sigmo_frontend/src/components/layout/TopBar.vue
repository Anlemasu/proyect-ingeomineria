<script setup lang="ts">
import { useAuthStore } from '@/stores/auth.store'
import { ROLE_LABELS, ROLE_COLORS } from '@/constants/roles'

const store = useAuthStore()
</script>

<template>
  <header class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6">
    <div />
    <div v-if="store.user" class="flex items-center gap-3">
      <span class="text-sm text-gray-600">{{ store.user.name }}</span>
      <span
        class="text-xs font-medium px-2 py-1 rounded-full"
        :class="ROLE_COLORS[store.user.role] ?? 'bg-gray-100 text-gray-800'"
      >
        {{ ROLE_LABELS[store.user.role] ?? store.user.role }}
      </span>
    </div>
  </header>
</template>
