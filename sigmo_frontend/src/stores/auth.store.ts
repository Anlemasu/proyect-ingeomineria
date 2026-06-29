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

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<User | null>(null)

  const isAuthenticated = computed(() => {
    return !!token.value && !isTokenExpired(token.value)
  })

  function initialize() {
    const stored = localStorage.getItem(TOKEN_KEY)
    if (stored && !isTokenExpired(stored)) {
      token.value = stored
    } else {
      clearSession()
    }
  }

  function login(accessToken: string, userData: User) {
    token.value = accessToken
    user.value = userData
    localStorage.setItem(TOKEN_KEY, accessToken)
  }

  function clearSession() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
  }

  function logout() {
    clearSession()
  }

  return { token, user, isAuthenticated, initialize, login, logout, clearSession }
})
