import { useAuthStore } from '@/stores/auth.store'
import { authApi } from '@/api/auth.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { useRouter } from 'vue-router'

export function useAuth() {
  const store = useAuthStore()
  const router = useRouter()

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    store.login(res.data.access, res.data.user, res.data.refresh)
    router.push('/')
  }

  async function logout() {
    // FASE 4B: se lee ANTES de limpiar el store (store.logout() lo borra).
    // Solo invalida el refresh de ESTA sesión — no toca las demás sesiones
    // del mismo usuario en otros dispositivos/navegadores (eso seguiría
    // siendo el blacklist masivo de Fase 2, que solo se dispara cuando un
    // superuser desactiva la cuenta, no aquí).
    const refreshToken = store.refreshToken
    try {
      await authApi.logout(refreshToken)
    } catch {
      // best-effort: sin conexión o backend caído, el usuario igual debe
      // poder salir de la app — no se bloquea el logout local a que el
      // backend confirme.
    } finally {
      store.logout()
      router.push('/login')
    }
  }

  return { login, logout, getApiErrorMessage }
}
