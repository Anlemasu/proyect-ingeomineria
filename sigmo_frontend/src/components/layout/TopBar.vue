<script setup lang="ts">
import { Menu } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth.store'
import { useSidebar } from '@/composables/useSidebar'
import { ROLE_LABELS, ROLE_COLORS } from '@/constants/roles'

const store = useAuthStore()
const { open } = useSidebar()
</script>

<template>
  <header class="h-14 bg-white border-b border-stone-200 flex items-center justify-between px-4 lg:px-6">
    <button
      class="text-stone-500 hover:text-stone-700 lg:hidden"
      @click="open"
    >
      <Menu class="w-6 h-6" />
    </button>
    <div v-if="store.user" class="flex items-center gap-3">
      <span class="text-sm text-gray-600 hidden sm:inline">{{ store.user.name }}</span>
      <span
        class="text-xs font-medium px-2 py-1 rounded-full"
        :class="ROLE_COLORS[store.user.role] ?? 'bg-gray-100 text-gray-800'"
      >
        {{ ROLE_LABELS[store.user.role] ?? store.user.role }}
      </span>
    </div>
  </header>
</template>
