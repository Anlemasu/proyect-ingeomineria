import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types'

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(payload)
  } catch {
    return null
  }
}

function isTokenExpired(token: string): boolean {
  const payload = decodeJwtPayload(token)
  if (!payload || typeof payload.exp !== 'number') return true
  return Date.now() / 1000 > payload.exp
}

const TOKEN_KEY = 'sigmo_token'
const USER_KEY = 'sigmo_user'
const REFRESH_KEY = 'sigmo_refresh'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(null)
  // FASE 4B: se persiste para poder mandarlo en el logout y que el
  // backend lo invalide (blacklist, Fase 2) — antes de este fix el
  // frontend nunca lo guardaba en ningún lado, así que el logout nunca
  // tenía nada que enviarle al backend y el refresh token seguía siendo
  // válido hasta expirar solo (hasta 1 día).
  const refreshToken = ref<string | null>(null)

  // FASE 4 (BUG 1): antes de este fix, initialize() solo restauraba el
  // token — nunca el usuario/rol — así que tras un F5 store.user quedaba
  // en null hasta el próximo login. Las guardas de router.beforeEach
  // comparan contra store.user, así que con user=null la condición
  // `allowedRoles && store.user && ...` daba false y dejaba pasar
  // cualquier ruta. No existe un endpoint /me en el backend (se revisó
  // antes de implementar esto — ver resumen de la fase), así que en vez
  // de validar contra el servidor en cada arranque, se persiste el mismo
  // objeto `user` que el login ya trae (LoginResponse.user) y se restaura
  // desde localStorage junto con el token.
  //
  // isInitializing empieza en true y App.vue no renderiza rutas
  // protegidas mientras lo esté. Hoy initialize() es 100% síncrono (no
  // hay llamada de red), así que para cuando el router resuelve la
  // primera navegación esta bandera ya está en false — no se ve ningún
  // spinner en la práctica. Se deja como bandera explícita (en vez de
  // asumir que "siempre es síncrono") para no depender de un orden de
  // ejecución implícito y para no tener que cambiar este contrato si en
  // el futuro initialize() pasa a validar el token contra el backend.
  const isInitializing = ref(true)

  const isAuthenticated = computed(() => {
    return !!token.value && !isTokenExpired(token.value)
  })

  function initialize() {
    const storedToken = localStorage.getItem(TOKEN_KEY)
    const storedUser = localStorage.getItem(USER_KEY)

    if (storedToken && !isTokenExpired(storedToken) && storedUser) {
      try {
        const parsedUser = JSON.parse(storedUser) as User
        token.value = storedToken
        user.value = parsedUser
        refreshToken.value = localStorage.getItem(REFRESH_KEY)
      } catch {
        // localStorage corrupto/manipulado: mejor arrancar sin sesión que
        // con un usuario a medias.
        clearSession()
      }
    } else {
      clearSession()
    }

    isInitializing.value = false
  }

  function login(accessToken: string, userData: User, refresh: string) {
    token.value = accessToken
    user.value = userData
    refreshToken.value = refresh
    localStorage.setItem(TOKEN_KEY, accessToken)
    localStorage.setItem(USER_KEY, JSON.stringify(userData))
    localStorage.setItem(REFRESH_KEY, refresh)
  }

  function clearSession() {
    token.value = null
    user.value = null
    refreshToken.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(REFRESH_KEY)
  }

  function logout() {
    clearSession()
  }

  return { token, user, refreshToken, isAuthenticated, isInitializing, initialize, login, logout, clearSession }
})
