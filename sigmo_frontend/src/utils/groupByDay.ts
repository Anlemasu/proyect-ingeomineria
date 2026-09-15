import type { Trip, Expense, DailyReportBreakdownRow } from '@/types'

/**
 * Subtotales por día para reportes de rango (quincenal/mensual): agrupa
 * viajes ACTIVOS y gastos por su campo `date`, igual criterio que usa
 * DailyReportPage para los totales generales del reporte.
 */
export function groupByDay(trips: Trip[], expenses: Expense[]): DailyReportBreakdownRow[] {
  const map = new Map<string, DailyReportBreakdownRow>()

  function rowFor(date: string): DailyReportBreakdownRow {
    let row = map.get(date)
    if (!row) {
      row = { date, tripsCount: 0, totalCollected: 0, totalExpenses: 0, netBalance: 0 }
      map.set(date, row)
    }
    return row
  }

  for (const t of trips) {
    if (!t.state) continue
    const row = rowFor(t.date)
    row.tripsCount += 1
    row.totalCollected += Number(t.value)
  }
  for (const e of expenses) {
    rowFor(e.date).totalExpenses += Number(e.value)
  }

  const rows = [...map.values()]
  for (const row of rows) row.netBalance = row.totalCollected - row.totalExpenses
  return rows.sort((a, b) => a.date.localeCompare(b.date))
}
