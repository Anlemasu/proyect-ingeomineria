<script setup lang="ts">
import { ShieldOff } from 'lucide-vue-next'
</script>

<template>
  <div class="min-h-screen bg-[#F8FAFC] flex items-center justify-center">
    <div class="text-center">
      <ShieldOff class="w-12 h-12 text-gray-400 mx-auto mb-4" />
      <h1 class="text-xl font-semibold text-gray-800">Acceso no autorizado</h1>
      <p class="text-gray-500 text-sm mt-2">No tienes permisos para ver esta página.</p>
      <router-link to="/" class="mt-6 inline-block text-sm text-[#1E40AF] hover:underline">Volver al inicio</router-link>
    </div>
  </div>
</template>
