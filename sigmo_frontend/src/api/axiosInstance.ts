import axios from 'axios'
import { toast } from 'vue-sonner'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sigmo_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!error.response) {
      toast.error('Error de conexión. Verifica tu red.')
      return Promise.reject(error)
    }
    const status = error.response.status
    if (status === 401) {
      localStorage.removeItem('sigmo_token')
      toast.error('Sesión expirada. Inicia sesión nuevamente.')
      window.location.href = '/login'
    } else if (status === 403) {
      toast.error('No tienes permisos para realizar esta acción.')
    } else if (status === 500) {
      toast.error('Error interno del servidor. Intenta de nuevo.')
    }
    return Promise.reject(error)
  }
)

export default api
