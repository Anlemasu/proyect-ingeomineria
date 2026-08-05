import { format, parseISO } from 'date-fns'

// Si trae componente de hora (datetime ISO, p.ej. date_register) hay que
// forzar America/Bogota antes de extraer el día — mismo motivo que
// formatTime: el backend serializa en UTC y el dispositivo puede estar en
// cualquier zona horaria, así que el día calendario "crudo" puede no
// coincidir con el día en Bogotá. Si es una fecha pura (sin hora, p.ej.
// Trip.date/Expense.date) no hay nada que convertir: el string ya es el
// día calendario correcto tal como lo guardó el backend.
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  try {
    if (dateStr.includes('T')) {
      const date = new Date(dateStr)
      if (isNaN(date.getTime())) return dateStr
      return date.toLocaleDateString('es-CO', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        timeZone: 'America/Bogota',
      })
    }
    return format(parseISO(dateStr), 'dd/MM/yyyy')
  } catch {
    return dateStr
  }
}

// Fecha "de hoy" en zona horaria Bogotá, como string yyyy-MM-dd. A
// diferencia de format(new Date(), 'yyyy-MM-dd'), no depende de la zona
// horaria configurada en el dispositivo del usuario — evita que un
// dispositivo en otra zona (p.ej. UTC) calcule "hoy" como el día siguiente
// cerca de la medianoche de Bogotá.
export function todayBogota(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/Bogota' })
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
