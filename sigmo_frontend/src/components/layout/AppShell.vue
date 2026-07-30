<script setup lang="ts">
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
import { useSidebar } from '@/composables/useSidebar'

const { collapsed } = useSidebar()
</script>

<template>
  <div class="flex min-h-screen bg-[#F8FAFC]">
    <Sidebar />
    <div
      class="flex-1 flex flex-col min-w-0 transition-all duration-300"
      :class="collapsed ? 'lg:ml-16' : 'lg:ml-60'"
    >
      <TopBar />
      <main class="flex-1 p-4 lg:p-6 min-w-0">
        <router-view />
      </main>
    </div>
  </div>
</template>
