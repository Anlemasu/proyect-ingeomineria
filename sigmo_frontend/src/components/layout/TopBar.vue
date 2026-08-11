<script setup lang="ts">
import { ref } from 'vue'
import { Menu, User, ChevronDown, LogOut } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth.store'
import { useSidebar } from '@/composables/useSidebar'
import { useAuth } from '@/composables/useAuth'
import { ROLE_LABELS, ROLE_COLORS } from '@/constants/roles'

const store = useAuthStore()
const { open } = useSidebar()
const { logout } = useAuth()

const menuOpen = ref(false)

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function closeMenu() {
  menuOpen.value = false
}

function handleLogout() {
  closeMenu()
  logout()
}
</script>

<template>
  <header class="h-14 bg-white border-b border-stone-200 flex items-center justify-between px-4 lg:px-6">
    <div class="flex items-center gap-3 min-w-0">
      <button
        class="text-stone-500 hover:text-stone-700 lg:hidden flex-shrink-0"
        @click="open"
      >
        <Menu class="w-6 h-6" />
      </button>
      <span class="font-semibold text-stone-800 truncate">
        <span class="sm:hidden">SIGMO</span>
        <span class="hidden sm:inline">SIGMO — Sistema Integral de Gestión Minera y Operativa</span>
      </span>
    </div>

    <div v-if="store.user" class="relative flex-shrink-0">
      <button
        class="flex items-center gap-2 pl-2 pr-1 py-1 rounded-full hover:bg-gold-50 transition-colors"
        :class="menuOpen ? 'bg-gold-50 ring-1 ring-gold-300' : ''"
        @click="toggleMenu"
      >
        <span
          class="text-xs font-medium px-2 py-1 rounded-full hidden sm:inline"
          :class="ROLE_COLORS[store.user.role] ?? 'bg-gray-100 text-gray-800'"
        >
          {{ ROLE_LABELS[store.user.role] ?? store.user.role }}
        </span>
        <span class="w-8 h-8 rounded-full bg-gold-100 text-gold-700 flex items-center justify-center">
          <User class="w-4 h-4" />
        </span>
        <ChevronDown class="w-4 h-4 text-stone-500 transition-transform" :class="menuOpen ? 'rotate-180 text-gold-600' : ''" />
      </button>

      <div
        v-if="menuOpen"
        class="fixed inset-0 z-40"
        @click="closeMenu"
      />

      <div
        v-if="menuOpen"
        class="absolute right-0 top-full mt-2 w-56 bg-white rounded-lg shadow-lg border border-stone-200 border-t-2 border-t-gold-500 z-50 py-2 overflow-hidden"
      >
        <div class="px-4 py-3 border-b border-stone-100 bg-gold-50/60 text-center">
          <p class="text-sm font-medium text-stone-800 truncate">{{ store.user.name }}</p>
          <span
            class="inline-block mt-1 text-xs font-medium px-2 py-0.5 rounded-full"
            :class="ROLE_COLORS[store.user.role] ?? 'bg-gray-100 text-gray-800'"
          >
            {{ ROLE_LABELS[store.user.role] ?? store.user.role }}
          </span>
        </div>
        <button
          class="flex items-center gap-2 w-full px-4 py-2 text-sm text-stone-600 hover:bg-gold-50 hover:text-gold-700 transition-colors"
          @click="handleLogout"
        >
          <LogOut class="w-4 h-4" />
          Cerrar sesión
        </button>
      </div>
    </div>
  </header>
</template>
