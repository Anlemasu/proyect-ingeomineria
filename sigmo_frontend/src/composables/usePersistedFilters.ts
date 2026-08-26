import { reactive, ref, watch, type Ref } from 'vue'

/**
 * Ref respaldado en localStorage — mismo valor por defecto en la primera
 * visita, pero recuerda el último valor elegido en visitas siguientes (p. ej.
 * un filtro de fecha o cliente en una tabla) para no perderlo al recargar o
 * navegar entre páginas.
 */
export function usePersistedRef<T>(key: string, defaultValue: T): Ref<T> {
  function load(): T {
    try {
      const raw = localStorage.getItem(key)
      return raw !== null ? (JSON.parse(raw) as T) : defaultValue
    } catch {
      return defaultValue
    }
  }

  const state = ref(load()) as Ref<T>

  watch(state, (value) => {
    localStorage.setItem(key, JSON.stringify(value))
  })

  return state
}

/**
 * Variante de usePersistedRef para un grupo de filtros relacionados
 * (p. ej. { user, action, date_from, date_to }) que conviene guardar juntos
 * bajo una sola llave. Los campos nuevos que se agreguen a `defaults` en el
 * futuro no rompen lo ya guardado: se completan con su valor por defecto.
 */
export function usePersistedFilters<T extends object>(key: string, defaults: T): T {
  function load(): T {
    try {
      const stored = JSON.parse(localStorage.getItem(key) ?? 'null')
      return stored ? { ...defaults, ...stored } : { ...defaults }
    } catch {
      return { ...defaults }
    }
  }

  const state = reactive(load()) as T

  watch(state, () => {
    localStorage.setItem(key, JSON.stringify(state))
  }, { deep: true })

  return state
}
