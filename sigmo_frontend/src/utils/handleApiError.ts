import type { AxiosError } from 'axios'
import type { ApiError } from '@/types'

export function getApiErrorMessage(err: unknown): string {
  const e = err as AxiosError<ApiError>
  if (!e.response) return 'Error de conexión. Verifica tu red.'
  const data = e.response.data
  if (data?.error) return data.error
  if (data?.detail) return data.detail
  const firstKey = Object.keys(data ?? {}).find(k => k !== 'error' && k !== 'detail')
  if (firstKey) {
    const val = (data as Record<string, unknown>)[firstKey]
    return Array.isArray(val) ? String(val[0]) : String(val)
  }
  switch (e.response.status) {
    case 400: return 'Datos inválidos. Revisa el formulario.'
    case 401: return 'Credenciales incorrectas.'
    case 403: return 'No tienes permisos para realizar esta acción.'
    case 404: return 'Recurso no encontrado.'
    case 429: return 'Cuenta bloqueada temporalmente. Intenta en 15 minutos.'
    case 500: return 'Error interno del servidor. Intenta de nuevo.'
    default: return 'Ocurrió un error inesperado.'
  }
}
