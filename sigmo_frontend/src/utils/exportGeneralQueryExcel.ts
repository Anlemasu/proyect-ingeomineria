import * as XLSX from 'xlsx'
import type { Trip } from '@/types'
import { formatDate, formatTime } from '@/utils/formatDate'

interface ColumnLite {
  key: string
  label: string
}

function resolveExportValue(t: Trip, key: string, invoiceNumberMap: Record<number, string>): string | number {
  switch (key) {
    case 'voucher_num': return t.voucher_num
    case 'date': return formatDate(t.date)
    case 'date_register': return formatTime(t.date_register)
    case 'client_detail.name': return t.client_detail?.name ?? '—'
    case 'origin_site_detail.name': return t.origin_site_detail?.name ?? '—'
    case 'vehicle_detail.plaque': return t.vehicle_detail?.plaque ?? '—'
    case 'vehicle_detail.dumper_detail.ambiental_pin': return t.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0'
    case 'material_type_detail.name': return t.material_type_detail?.name ?? '—'
    case 'vehicle_detail.vehicle_type_detail.name': return t.vehicle_detail?.vehicle_type_detail?.name ?? '—'
    case 'vehicle_detail.vehicle_type_detail.capacity': return Number(t.vehicle_detail?.vehicle_type_detail?.capacity ?? 0)
    case 'payment_detail.name': return t.payment_detail?.name ?? '—'
    case 'value': return Number(t.value)
    case 'extern_voucher_num': return t.extern_voucher_num ?? '—'
    case 'observations': return t.observations ?? '—'
    case 'state': return t.state ? 'Activo' : 'Anulado'
    case 'invoice_number': return t.invoice != null ? (invoiceNumberMap[t.invoice] ?? `#${t.invoice}`) : '—'
    case 'certification_state': return t.certification_state === true ? 'Sí' : t.certification_state === false ? 'No' : '—'
    case 'certification_num': return t.certification_num ?? '—'
    case 'advance': return t.advance != null ? `#${t.advance}` : '—'
    case 'summary': return t.summary != null ? `#${t.summary}` : '—'
    default: return '—'
  }
}

export function exportGeneralQueryExcel(rows: Trip[], columns: ColumnLite[], invoiceNumberMap: Record<number, string>): void {
  const header = columns.map(c => c.label)
  const dataRows = rows.map(t => columns.map(c => resolveExportValue(t, c.key, invoiceNumberMap)))

  const ws = XLSX.utils.aoa_to_sheet([header, ...dataRows])
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, 'Consulta de Viajes')

  const today = new Date().toISOString().slice(0, 10)
  XLSX.writeFile(wb, `Consulta_Viajes_SIGMO_${today}.xlsx`)
}
