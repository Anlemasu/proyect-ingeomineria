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

// FASE 4C: la sesión se persiste en sessionStorage, NO en localStorage.
// localStorage se comparte entre TODAS las pestañas del mismo origen —
// con múltiples sesiones simultáneas permitidas (una pestaña puede tener
// al usuario X logueado y otra al Y, o dos sesiones distintas del mismo
// usuario), guardar la sesión ahí hacía que cerrar sesión en una pestaña
// borrara literalmente las claves que las demás pestañas también leían,
// "cerrándoles la sesión" sin que ellas hubieran hecho nada.
// sessionStorage resuelve esto porque el navegador le da una copia
// completamente aislada a cada pestaña (aunque sea el mismo origen) —
// nada que escriba la pestaña A es visible para la B — y a la vez
// sobrevive un F5 dentro de la MISMA pestaña, que es lo que pedía la
// Fase 4 (Bug 1).
const storage = sessionStorage

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(storage.getItem(TOKEN_KEY))
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
  // desde storage junto con el token.
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
    const storedToken = storage.getItem(TOKEN_KEY)
    const storedUser = storage.getItem(USER_KEY)

    if (storedToken && !isTokenExpired(storedToken) && storedUser) {
      try {
        const parsedUser = JSON.parse(storedUser) as User
        token.value = storedToken
        user.value = parsedUser
        refreshToken.value = storage.getItem(REFRESH_KEY)
      } catch {
        // storage corrupto/manipulado: mejor arrancar sin sesión que con
        // un usuario a medias.
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
    storage.setItem(TOKEN_KEY, accessToken)
    storage.setItem(USER_KEY, JSON.stringify(userData))
    storage.setItem(REFRESH_KEY, refresh)
  }

  // 8A.3: usado por el refresh silencioso (axiosInstance.ts) para renovar
  // el access token (y el refresh rotado) sin pasar por login() completo,
  // que exige `userData` — algo que la respuesta de refresh no trae (no
  // vuelve a autenticar contra credenciales, solo renueva tokens de una
  // sesión que ya existía, así que `user` se deja intacto).
  function setTokens(accessToken: string, refresh?: string) {
    token.value = accessToken
    storage.setItem(TOKEN_KEY, accessToken)
    if (refresh) {
      refreshToken.value = refresh
      storage.setItem(REFRESH_KEY, refresh)
    }
  }

  function clearSession() {
    token.value = null
    user.value = null
    refreshToken.value = null
    storage.removeItem(TOKEN_KEY)
    storage.removeItem(USER_KEY)
    storage.removeItem(REFRESH_KEY)
  }

  function logout() {
    clearSession()
  }

  return { token, user, refreshToken, isAuthenticated, isInitializing, initialize, login, logout, clearSession, setTokens }
})
