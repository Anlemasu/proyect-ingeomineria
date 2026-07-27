<script setup lang="ts">
import Sidebar from './Sidebar.vue'
import TopBar from './TopBar.vue'
</script>

<template>
  <div class="flex min-h-screen bg-[#F8FAFC]">
    <Sidebar />
    <div class="flex-1 flex flex-col min-w-0">
      <TopBar />
      <main class="flex-1 p-6 min-w-0">
        <router-view />
      </main>
    </div>
  </div>
</template>
