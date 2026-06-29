<script setup lang="ts">
import { ref } from 'vue'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Eye, EyeOff, Loader2 } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth.store'
import { authApi } from '@/api/auth.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { useRouter } from 'vue-router'

const router = useRouter()
const store = useAuthStore()

const schema = toTypedSchema(z.object({
  username: z.string().min(1, 'El usuario es requerido').transform(s => s.trim()),
  password: z.string().min(8, 'La contraseña debe tener al menos 8 caracteres'),
}))

const { handleSubmit, isSubmitting } = useForm({ validationSchema: schema })
const { value: username, errorMessage: usernameError } = useField<string>('username')
const { value: password, errorMessage: passwordError } = useField<string>('password')

const showPassword = ref(false)
const serverError = ref('')

const onSubmit = handleSubmit(async (values) => {
  serverError.value = ''
  try {
    const res = await authApi.login(values.username, values.password)
    store.login(res.data.access, res.data.user)
    router.push('/')
  } catch (err: unknown) {
    const e = err as { response?: { status?: number } }
    if (e?.response?.status === 429) {
      serverError.value = 'Cuenta bloqueada temporalmente. Intenta en 15 minutos.'
    } else if (e?.response?.status === 401) {
      serverError.value = getApiErrorMessage(err)
    } else {
      serverError.value = getApiErrorMessage(err)
    }
  }
})
</script>

<template>
  <div class="min-h-screen bg-[#F8FAFC] flex items-center justify-center px-4">
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-8 w-full max-w-sm">
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-[#1E40AF]">SIGMO</h1>
        <p class="text-gray-500 text-sm mt-1">Sistema de Información de Gestión Minera</p>
      </div>

      <form @submit.prevent="onSubmit" class="space-y-5" novalidate>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Usuario</label>
          <input
            v-model="username"
            type="text"
            autocomplete="username"
            class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            :class="usernameError ? 'border-red-400' : 'border-gray-300'"
            placeholder="Ingresa tu usuario"
          />
          <p v-if="usernameError" class="mt-1 text-xs text-red-600">{{ usernameError }}</p>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Contraseña</label>
          <div class="relative">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              class="w-full px-3 py-2 pr-10 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              :class="passwordError ? 'border-red-400' : 'border-gray-300'"
              placeholder="Ingresa tu contraseña"
            />
            <button
              type="button"
              tabindex="-1"
              class="absolute inset-y-0 right-3 flex items-center text-gray-400 hover:text-gray-600"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" class="w-4 h-4" />
              <Eye v-else class="w-4 h-4" />
            </button>
          </div>
          <p v-if="passwordError" class="mt-1 text-xs text-red-600">{{ passwordError }}</p>
        </div>

        <div v-if="serverError" class="bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700">
          {{ serverError }}
        </div>

        <button
          type="submit"
          :disabled="isSubmitting"
          class="w-full flex items-center justify-center gap-2 py-2.5 px-4 text-sm font-medium text-white bg-[#1E40AF] rounded-md hover:bg-blue-700 disabled:opacity-60 transition-colors"
        >
          <Loader2 v-if="isSubmitting" class="w-4 h-4 animate-spin" />
          {{ isSubmitting ? 'Iniciando sesión...' : 'Iniciar sesión' }}
        </button>
      </form>
    </div>
  </div>
</template>
