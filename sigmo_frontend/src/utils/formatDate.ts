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
