import type { AxiosError } from 'axios'
import { toast } from 'vue-sonner'
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

// El interceptor global de axiosInstance.ts ya muestra un toast para 403/500
// en TODA request — usar esto en vez de `toast.error(getApiErrorMessage(err))`
// evita el toast duplicado para esos dos status, mostrando el propio solo
// para el resto de casos (400/404/409, errores de negocio específicos, etc).
export function toastApiError(err: unknown): void {
  const e = err as AxiosError
  const status = e.response?.status
  if (status === 403 || status === 500) return
  toast.error(getApiErrorMessage(err))
}
