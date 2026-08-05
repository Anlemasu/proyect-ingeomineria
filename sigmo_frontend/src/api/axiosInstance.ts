import axios from 'axios'
import { toast } from 'vue-sonner'
import { useAuthStore } from '@/stores/auth.store'

const LOGIN_ENDPOINT = '/users/login/'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// FASE 4C: el token se lee del store de Pinia (memoria de ESTA pestaña),
// no de sessionStorage/localStorage directamente. useAuthStore() se llama
// dentro del interceptor (no una sola vez al importar el módulo) para
// asegurar que siempre resuelve la instancia de Pinia activa de la app
// actual. Antes esto leía localStorage en cada request — como
// localStorage se comparte entre pestañas, cerrar sesión en una pestaña
// borraba esas claves para todas, y la siguiente request de cualquier
// OTRA pestaña salía sin token y esa pestaña también quedaba deslogueada
// sin haber hecho nada.
api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
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
      // FASE 4C: se limpia a través del store (clearSession(), que ya
      // opera sobre sessionStorage — ver auth.store.ts) en vez de borrar
      // claves de localStorage a mano aquí. Esto solo afecta la sesión de
      // ESTA pestaña; otras pestañas con su propia sesión en su propio
      // sessionStorage no se enteran ni se ven tocadas.
      useAuthStore().clearSession()
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
