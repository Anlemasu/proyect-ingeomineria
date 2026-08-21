import { onBeforeUnmount, reactive } from 'vue'

export interface ResizableColumnDef {
  id: string
  width: number
  minWidth?: number
}

/**
 * Anchos de columna ajustables por arrastre (estilo Excel/Access) para tablas
 * HTML planas que no pasan por @tanstack/vue-table. Se usa junto a un
 * <colgroup> — cada <col> toma su ancho de `widths[id]` y gobierna toda la
 * columna (requiere `table-layout: fixed` en el <table>).
 */
export function useResizableColumns(columns: ResizableColumnDef[], storageKey: string) {
  const defaults: Record<string, number> = {}
  const minWidths: Record<string, number> = {}
  for (const c of columns) {
    defaults[c.id] = c.width
    minWidths[c.id] = c.minWidth ?? 60
  }

  function load(): Record<string, number> {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? '{}')
      return { ...defaults, ...stored }
    } catch {
      return { ...defaults }
    }
  }

  const widths = reactive<Record<string, number>>(load())

  function persist() {
    localStorage.setItem(storageKey, JSON.stringify(widths))
  }

  let dragId: string | null = null
  let startX = 0
  let startWidth = 0

  function clientXOf(e: MouseEvent | TouchEvent): number {
    return 'touches' in e ? (e.touches[0]?.clientX ?? startX) : e.clientX
  }

  function onMove(e: MouseEvent | TouchEvent) {
    if (!dragId) return
    const delta = clientXOf(e) - startX
    widths[dragId] = Math.max(minWidths[dragId] ?? 60, Math.round(startWidth + delta))
  }
  function onEnd() {
    if (!dragId) return
    dragId = null
    persist()
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onEnd)
    window.removeEventListener('touchmove', onMove)
    window.removeEventListener('touchend', onEnd)
  }

  function startResize(id: string, e: MouseEvent | TouchEvent) {
    e.preventDefault()
    e.stopPropagation()
    dragId = id
    startX = clientXOf(e)
    startWidth = widths[id] ?? defaults[id] ?? 120
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onEnd)
    window.addEventListener('touchmove', onMove, { passive: false })
    window.addEventListener('touchend', onEnd)
  }

  function resetWidth(id: string) {
    widths[id] = defaults[id]
    persist()
  }

  onBeforeUnmount(() => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onEnd)
    window.removeEventListener('touchmove', onMove)
    window.removeEventListener('touchend', onEnd)
  })

  return { widths, startResize, resetWidth }
}
