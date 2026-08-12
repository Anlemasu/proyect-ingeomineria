import axios, { type AxiosRequestConfig } from 'axios'
import { toast } from 'vue-sonner'
import { useAuthStore } from '@/stores/auth.store'
import type { RefreshResponse } from '@/types'

const LOGIN_ENDPOINT = '/users/login/'
const REFRESH_ENDPOINT = '/users/token/refresh/'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// 8A.3: refresh silencioso. Sin precedente en el proyecto — primera vez
// que se introduce un patrón de "un solo refresh en vuelo, el resto
// espera". `isRefreshing` evita que varias requests que expiran casi al
// mismo tiempo (ej. varias llamadas paralelas de vue-query) disparen cada
// una su propio POST /token/refresh/ — la primera que detecta el 401
// dispara el refresh; las demás solo se encolan en `refreshSubscribers` y
// se reintentan todas juntas cuando ese único refresh resuelve.
// Cada suscriptor recibe el token nuevo si el refresh tuvo éxito, o `null`
// si falló — así ninguna request en cola se queda esperando para siempre
// (una promesa que nunca resuelve ni rechaza) cuando el refresh token
// también resulta inválido.
let isRefreshing = false
let refreshSubscribers: Array<(newToken: string | null) => void> = []

function subscribeTokenRefresh(cb: (newToken: string | null) => void) {
  refreshSubscribers.push(cb)
}

function notifySubscribers(newToken: string | null) {
  refreshSubscribers.forEach((cb) => cb(newToken))
  refreshSubscribers = []
}

// 9.7B: `message` es opcional — cuando el backend manda un motivo específico
// en el cuerpo del 401 (ej. ActiveUserJWTAuthentication: "Tu cuenta ha sido
// desactivada...", o "...contraseña fue actualizada...") se muestra ese en
// vez del genérico. Sin mensaje específico (ej. token expirado por tiempo,
// sin refresh token disponible), se mantiene el genérico de siempre.
function forceSessionExpired(message?: string) {
  useAuthStore().clearSession()
  toast.error(message || 'Sesión expirada. Inicia sesión nuevamente.')
  window.location.href = '/login'
}

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
  async (error) => {
    if (!error.response) {
      toast.error('Error de conexión. Verifica tu red.')
      return Promise.reject(error)
    }
    const status = error.response.status
    const url = error.config?.url ?? ''
    const isLoginRequest = url.endsWith(LOGIN_ENDPOINT)
    const isRefreshRequest = url.endsWith(REFRESH_ENDPOINT)

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

    // 8A.3: la propia llamada de refresh fallando (401 = refresh token
    // inválido/expirado/blacklisteado; o cualquier otro error) no debe
    // reintentar refrescarse a sí misma — sería un loop infinito. Se deja
    // pasar el rechazo tal cual: el único responsable de limpiar la
    // sesión, avisar a la cola de requests en espera, y redirigir a
    // login es el catch del sitio que disparó el refresh (más abajo) —
    // así ese manejo ocurre una sola vez, sea cual sea el motivo por el
    // que el refresh falló.
    if (isRefreshRequest) {
      return Promise.reject(error)
    }

    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean }
    const authStore = useAuthStore()
    // 9.7B: se lee ANTES de intentar el refresh silencioso — es el 401
    // original (ej. de ActiveUserJWTAuthentication) el que trae el motivo
    // específico. Si el refresh también falla más abajo (ej. porque
    // desactivar al usuario blacklisteó su refresh token), el error de esa
    // llamada de refresh ya no trae este mensaje amigable, así que se
    // captura acá y se reutiliza en el catch del refresh.
    const specificMessage: string | undefined = error.response?.data?.detail

    if (status === 401 && !originalRequest._retry && authStore.refreshToken) {
      // 8A.3: refresh silencioso — antes de este fix, CUALQUIER 401
      // (incluido uno legítimo por access token expirado, con el refresh
      // token todavía vigente) desconectaba al usuario de inmediato,
      // perdiendo lo que estuviera a mitad de capturar. Se marca
      // `_retry` para que, si el reintento con el token nuevo también
      // 401ea, no se vuelva a intentar refrescar en loop — ahí sí es una
      // sesión realmente inválida.
      originalRequest._retry = true

      if (isRefreshing) {
        // Ya hay un refresh en curso disparado por otra request (ej. dos
        // llamadas paralelas de vue-query expirando casi al mismo
        // tiempo) — esta solo se encola y espera su resultado, sin
        // disparar un segundo POST /token/refresh/ redundante.
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh((newToken) => {
            if (newToken) {
              resolve(api(originalRequest))
            } else {
              reject(error)
            }
          })
        })
      }

      isRefreshing = true
      try {
        // Llamada directa con `api` (no vía auth.api.ts): auth.api.ts
        // importa este módulo para obtener el cliente axios, así que
        // importar authApi.refresh aquí crearía un ciclo de imports
        // entre los dos archivos.
        const { data } = await api.post<RefreshResponse>(REFRESH_ENDPOINT, {
          refresh: authStore.refreshToken,
        })
        authStore.setTokens(data.access, data.refresh)
        isRefreshing = false
        // Avisa a cualquier request que se haya encolado MIENTRAS este
        // refresh estaba en curso. Esta misma request (la que disparó el
        // refresh) no pasa por la cola — se reintenta directo abajo.
        notifySubscribers(data.access)
        return api(originalRequest)
      } catch (refreshError) {
        // Cubre TODO fallo del refresh (401, red, 500, lo que sea):
        // única vez que se limpia isRefreshing, se avisa a la cola (con
        // null, para que cada request encolada se rechace en vez de
        // quedar esperando para siempre) y se fuerza el logout.
        isRefreshing = false
        notifySubscribers(null)
        forceSessionExpired(specificMessage)
        return Promise.reject(refreshError)
      }
    }

    if (status === 401) {
      // FASE 4C: se limpia a través del store (clearSession(), que ya
      // opera sobre sessionStorage — ver auth.store.ts) en vez de borrar
      // claves de localStorage a mano aquí. Esto solo afecta la sesión de
      // ESTA pestaña; otras pestañas con su propia sesión en su propio
      // sessionStorage no se enteran ni se ven tocadas.
      forceSessionExpired(specificMessage)
    } else if (status === 403) {
      // Se usa el mensaje específico del backend si viene uno (ej. "Solo el
      // Superusuador puede revertir un cierre de caja.") — el interceptor es
      // el único responsable de avisar en 403, así que los `catch` de cada
      // página ya no deben mostrar su propio toast para este status.
      const data = error.response?.data as Record<string, unknown> | undefined
      const specific = (data?.error as string | undefined) ?? (data?.detail as string | undefined)
      toast.error(specific || 'No tienes permisos para realizar esta acción.')
    } else if (status === 500) {
      toast.error('Error interno del servidor. Intenta de nuevo.')
    }
    return Promise.reject(error)
  }
)

export default api
