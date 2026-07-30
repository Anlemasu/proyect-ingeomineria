import { format, parseISO } from 'date-fns'

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  try {
    return format(parseISO(dateStr), 'dd/MM/yyyy')
  } catch {
    return dateStr
  }
}

export function toISODate(date: Date): string {
  return format(date, 'yyyy-MM-dd')
}

// Extrae y formatea la hora de un datetime ISO 8601.
// Entrada: "2026-06-29T14:35:22.123456Z" — Salida: "14:35"
// Fuerza America/Bogota porque el backend serializa en UTC y el dispositivo
// del usuario puede estar en cualquier zona horaria.
export function formatTime(isoDatetime: string | null | undefined): string {
  if (!isoDatetime) return '—'
  try {
    const date = new Date(isoDatetime)
    if (isNaN(date.getTime())) return '—'
    return date.toLocaleTimeString('es-CO', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'America/Bogota',
    })
  } catch {
    return '—'
  }
}
