<script setup lang="ts">
import { Toaster } from 'vue-sonner'
import { Loader2 } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth.store'

// FASE 4 (BUG 1): red de seguridad para que el router nunca resuelva una
// ruta protegida contra un store todavía sin rehidratar. Mismo look que
// LoginPage.vue (gradiente + Loader2) para no introducir un patrón visual
// nuevo.
const authStore = useAuthStore()
</script>

<template>
  <div
    v-if="authStore.isInitializing"
    class="min-h-screen flex items-center justify-center bg-[radial-gradient(ellipse_at_center,_#ffffff_0%,_#f5f5f4_100%)]"
  >
    <Loader2 class="w-8 h-8 text-gold-500 animate-spin" />
  </div>
  <router-view v-else />
  <Toaster position="top-right" richColors />
</template>
