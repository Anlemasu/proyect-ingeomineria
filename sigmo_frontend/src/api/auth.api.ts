import api from './axiosInstance'
import type { LoginResponse } from '@/types'

// 8A.3: el refresh de token (POST /users/token/refresh/) NO se expone acá
// — vive directamente en axiosInstance.ts, que es quien lo dispara desde
// el interceptor de respuesta. Ponerlo en este archivo crearía un ciclo de
// imports (auth.api.ts ya importa `api` desde axiosInstance.ts).
export const authApi = {
  login: (username: string, password: string) =>
    api.post<LoginResponse>('/users/login/', { username, password }),

  // FASE 4B: manda el refresh token de ESTA sesión para que el backend lo
  // invalide (blacklist individual, Fase 2) — sin esto el logout solo
  // limpiaba el frontend y el token seguía siendo válido hasta expirar
  // solo. Es opcional a propósito: si por lo que sea no hay un refresh
  // guardado, el logout local igual debe poder seguir su curso.
  logout: (refreshToken?: string | null) =>
    api.post('/users/logout/', refreshToken ? { refresh: refreshToken } : {}),

  changePassword: (current_password: string, new_password: string, confirm_password: string) =>
    api.post('/users/change-password/', { current_password, new_password, confirm_password }),
}
