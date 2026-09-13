import * as XLSX from 'xlsx'
import type { DailySummary } from '@/types'
import { formatDate } from '@/utils/formatDate'

/**
 * Exporta el detalle de un cierre de caja (el que se ve en el drawer del
 * histórico) a un libro Excel con tres hojas:
 *   - "Resumen": fecha, estado, volumen, valor promedio, gastos e ingresos.
 *   - "Desglose por pago": total por medio de pago.
 *   - "Viajes por cliente": conteo, valor total y volumen m³ por cliente
 *     (calculado en vivo por el backend desde los viajes activos del cierre).
 */
export function exportCashClosingDetailExcel(summary: DailySummary): void {
  const wb = XLSX.utils.book_new()

  const revenue = summary.payment_details.reduce((s, p) => s + Number(p.total), 0)

  // ── Hoja 1: Resumen ─────────────────────────────────────────────────────
  const resumenRows: (string | number)[][] = [
    ['Cierre de Caja — SIGMO'],
    [],
    ['Fecha', formatDate(summary.date)],
    ['Estado', summary.state === 'closed' ? 'Cerrado' : 'Revertido'],
    ['Total viajes', summary.total_trips],
    ['Volumen total m³', Number(summary.total_volume)],
    ['Valor promedio', Number(summary.avg_trip_value)],
    ['Gastos', Number(summary.total_expenses)],
    ['Total ingresos', revenue],
  ]
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(resumenRows), 'Resumen')

  // ── Hoja 2: Desglose por pago ───────────────────────────────────────────
  const pagoHeader = ['Medio de Pago', 'Total (COP)']
  const pagoRows = summary.payment_details.map(p => [p.payment_method_name, Number(p.total)])
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([pagoHeader, ...pagoRows, ['Total', revenue]]),
    'Desglose por pago',
  )

  // ── Hoja 3: Viajes por cliente ─────────────────────────────────────────
  const clienteHeader = ['Cliente', 'N° Viajes', 'Total (COP)', 'Volumen m³']
  const clientes = summary.client_details ?? []
  const clienteRows = clientes.map(r => [
    r.client_name,
    r.trips_count,
    Number(r.total_value),
    Number(r.total_volume),
  ])
  const totalTrips = clientes.reduce((s, r) => s + r.trips_count, 0)
  const totalValue = clientes.reduce((s, r) => s + Number(r.total_value), 0)
  const totalVolume = clientes.reduce((s, r) => s + Number(r.total_volume), 0)
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      clienteHeader,
      ...clienteRows,
      ['Total', totalTrips, totalValue, totalVolume],
    ]),
    'Viajes por cliente',
  )

  XLSX.writeFile(wb, `Cierre_Caja_${summary.date}.xlsx`)
}
