import { endOfMonth, parseISO, format } from 'date-fns'

export interface DateRange {
  from: string
  to: string
}

// `month` es 'yyyy-MM' (valor que entrega MonthPickerInput).
// Devuelve el mes calendario completo: del día 1 al último día del mes.
export function monthRange(month: string): DateRange {
  const from = `${month}-01`
  const to = format(endOfMonth(parseISO(from)), 'yyyy-MM-dd')
  return { from, to }
}

// `half` 1 = días 1 al 15, 2 = día 16 al último día del mes.
export function biweeklyRange(month: string, half: 1 | 2): DateRange {
  if (half === 1) return { from: `${month}-01`, to: `${month}-15` }
  const to = format(endOfMonth(parseISO(`${month}-01`)), 'yyyy-MM-dd')
  return { from: `${month}-16`, to }
}

// Quincena "actual" según el día del mes — valor por defecto del selector.
export function currentHalf(dayOfMonth: number): 1 | 2 {
  return dayOfMonth <= 15 ? 1 : 2
}
