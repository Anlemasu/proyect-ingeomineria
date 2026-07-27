import * as XLSX from 'xlsx'
import type { DailyReportData } from '@/types'
import { formatDate } from '@/utils/formatDate'

export function exportDailyReportExcel(date: string, data: DailyReportData): void {
  const wb = XLSX.utils.book_new()

  // ── Sheet 1: Resumen ─────────────────────────────────────────────────────
  const resumenRows: (string | number)[][] = [
    ['Reporte Diario de Operaciones — SIGMO'],
    ['Fecha', formatDate(date)],
    [],
    ['Total Viajes', data.summary.totalTrips],
    ['Total Recaudado', data.summary.totalCollected],
    ['Total Gastos', data.summary.totalExpenses],
    ['Saldo Neto', data.summary.netBalance],
    [],
    ['Medio de Pago', 'N° Viajes', 'Total (COP)'],
    ...data.summary.byPaymentMethod.map(p => [p.name, p.tripCount, p.total]),
    ['Total', data.summary.totalTrips, data.summary.totalCollected],
  ]
  const wsResumen = XLSX.utils.aoa_to_sheet(resumenRows)
  XLSX.utils.book_append_sheet(wb, wsResumen, 'Resumen')

  // ── Sheet 2: Viajes ──────────────────────────────────────────────────────
  const viajesHeader = [
    'N° Vale', 'Fecha registro', 'Cliente', 'Placa', 'PIN Ambiental', 'Origen',
    'Tipo Material', 'Tipo Vehículo', 'Valor', 'Medio de Pago',
    'N° Vale Externo', 'N° Factura', 'Estado',
  ]
  const viajesRows = data.trips.map(t => [
    t.voucher_num,
    formatDate(t.date_register),
    t.client_detail?.name ?? '—',
    t.vehicle_detail?.plaque ?? '—',
    t.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0',
    t.origin_site_detail?.name ?? '—',
    t.material_type_detail?.name ?? '—',
    t.vehicle_detail?.vehicle_type_detail?.name ?? '—',
    Number(t.value),
    t.payment_detail?.name ?? '—',
    t.extern_voucher_num ?? '—',
    t.invoice ?? '—',
    t.state ? 'Activo' : 'Anulado',
  ])
  const wsViajes = XLSX.utils.aoa_to_sheet([viajesHeader, ...viajesRows])
  XLSX.utils.book_append_sheet(wb, wsViajes, 'Viajes')

  // ── Sheet 3: Gastos ──────────────────────────────────────────────────────
  const gastosHeader = ['Fecha', 'Descripción', 'Valor', 'Usuario']
  const gastosRows = data.expenses.map(e => [
    formatDate(e.date),
    e.description,
    Number(e.value),
    `#${e.user}`,
  ])
  const totalGastos = data.expenses.reduce((s, e) => s + Number(e.value), 0)
  const wsGastos = XLSX.utils.aoa_to_sheet([
    gastosHeader,
    ...gastosRows,
    ['', 'Total', totalGastos, ''],
  ])
  XLSX.utils.book_append_sheet(wb, wsGastos, 'Gastos')

  // ── Sheet 4: Anticipos Consumidos ────────────────────────────────────────
  const anticiposHeader = ['Cliente', 'Anticipo ID', 'Valor Descontado', 'N° Viaje asociado']
  const anticiposRows = data.advancesConsumed.map(t => [
    t.client_detail?.name ?? '—',
    t.advance ?? '—',
    Number(t.value),
    t.voucher_num,
  ])
  const totalAnticipos = data.advancesConsumed.reduce((s, t) => s + Number(t.value), 0)
  const wsAnticipos = XLSX.utils.aoa_to_sheet([
    anticiposHeader,
    ...anticiposRows,
    ['', 'Total', totalAnticipos, ''],
  ])
  XLSX.utils.book_append_sheet(wb, wsAnticipos, 'Anticipos Consumidos')

  XLSX.writeFile(wb, `Reporte_Diario_SIGMO_${date}.xlsx`)
}
