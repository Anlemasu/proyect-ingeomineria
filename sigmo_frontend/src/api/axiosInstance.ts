import axios from 'axios'
import { toast } from 'vue-sonner'

const TOKEN_KEY = 'sigmo_token'
const USER_KEY = 'sigmo_user'
const REFRESH_KEY = 'sigmo_refresh'
const LOGIN_ENDPOINT = '/users/login/'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
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
    const isLoginRequest = (error.config?.url ?? '').endsWith(LOGIN_ENDPOINT)

    // FASE 4 (BUG 2): un 401 de /users/login/ es "credenciales
    // incorrectas" — no hay ninguna sesión todavía que pueda "expirar".
    // Antes esta rama trataba ese 401 igual que cualquier otro (limpiaba
    // el token y forzaba window.location.href = '/login'), lo que
    // recargaba la página antes de que LoginPage.vue alcanzara a mostrar
    // el mensaje real del backend. Se deja pasar el error tal cual para
    // que lo maneje el propio formulario de login.
    //
    // El bloqueo por intentos fallidos (RF-03) no pasa por aquí: el
    // backend lo devuelve como 429, no 401, así que nunca entra a este
    // `if` ni al de abajo — ya le llega íntegro a LoginPage.vue.
    if (status === 401 && isLoginRequest) {
      return Promise.reject(error)
    }

    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      localStorage.removeItem(REFRESH_KEY)
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
