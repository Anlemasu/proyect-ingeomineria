import { useAuthStore } from '@/stores/auth.store'
import { authApi } from '@/api/auth.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { useRouter } from 'vue-router'

export function useAuth() {
  const store = useAuthStore()
  const router = useRouter()

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    store.login(res.data.access, res.data.user)
    router.push('/')
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // best-effort
    } finally {
      store.logout()
      router.push('/login')
    }
  }

  return { login, logout, getApiErrorMessage }
}
