import type { Trip } from '@/types'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate, formatTime } from '@/utils/formatDate'
import { format } from 'date-fns'

interface ColumnLite {
  key: string
  label: string
}

function escapeHtml(value: unknown): string {
  return String(value ?? '—')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function resolveDisplayValue(t: Trip, key: string, invoiceNumberMap: Record<number, string>): string {
  switch (key) {
    case 'voucher_num': return `#${t.voucher_num}`
    case 'date': return formatDate(t.date)
    case 'date_register': return formatTime(t.date_register)
    case 'client_detail.name': return t.client_detail?.name ?? '—'
    case 'origin_site_detail.name': return t.origin_site_detail?.name ?? '—'
    case 'vehicle_detail.plaque': return t.vehicle_detail?.plaque ?? '—'
    case 'vehicle_detail.dumper_detail.ambiental_pin': return t.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0'
    case 'material_type_detail.name': return t.material_type_detail?.name ?? '—'
    case 'vehicle_detail.vehicle_type_detail.name': return t.vehicle_detail?.vehicle_type_detail?.name ?? '—'
    case 'vehicle_detail.vehicle_type_detail.capacity':
      return t.vehicle_detail?.vehicle_type_detail?.capacity
        ? Number(t.vehicle_detail.vehicle_type_detail.capacity).toLocaleString('es-CO')
        : '—'
    case 'payment_detail.name': return t.payment_detail?.name ?? '—'
    case 'value': return formatCurrency(t.value)
    case 'extern_voucher_num': return t.extern_voucher_num ?? '—'
    case 'state': return t.state ? 'Activo' : 'Anulado'
    case 'invoice_number': return t.invoice != null ? (invoiceNumberMap[t.invoice] ?? `#${t.invoice}`) : '—'
    case 'certification_state': return t.certification_state === true ? 'Sí' : t.certification_state === false ? 'No' : '—'
    case 'certification_num': return t.certification_num ?? '—'
    case 'advance': return t.advance != null ? `#${t.advance}` : '—'
    case 'summary': return t.summary != null ? `#${t.summary}` : '—'
    default: return '—'
  }
}

function generateGeneralQueryHtml(
  rows: Trip[],
  columns: ColumnLite[],
  filterSummary: string,
  invoiceNumberMap: Record<number, string>,
): string {
  const now = new Date()
  const generatedAt = format(now, 'dd/MM/yyyy HH:mm')
  const numericKeys = new Set(['value', 'vehicle_detail.vehicle_type_detail.capacity'])
  const hasValueCol = columns.some(c => c.key === 'value')
  const totalValue = hasValueCol ? rows.reduce((s, t) => s + Number(t.value), 0) : 0

  const headerCells = columns
    .map(c => `<th${numericKeys.has(c.key) ? ' class="num"' : ''}>${escapeHtml(c.label)}</th>`)
    .join('')

  const bodyRows = rows.map(t => `
    <tr>${columns.map(c =>
      `<td${numericKeys.has(c.key) ? ' class="num"' : ''}>${escapeHtml(resolveDisplayValue(t, c.key, invoiceNumberMap))}</td>`,
    ).join('')}</tr>`).join('')

  const footerCells = columns.map((c, i) => {
    if (i === 0) return `<td>Total: ${rows.length} viajes</td>`
    if (c.key === 'value') return `<td class="num">${formatCurrency(totalValue)}</td>`
    return '<td></td>'
  }).join('')

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Consulta de Viajes</title>
<style>
  @media print { @page { size: A4 landscape; margin: 1cm; } }
  body { font-family: Arial, sans-serif; font-size: 10px; color: #111; margin: 0; padding: 16px; }
  .header { text-align: center; margin-bottom: 12px; }
  .header h1 { margin: 4px 0; font-size: 18px; }
  .header p { margin: 2px 0; color: #555; }
  .filters { margin-bottom: 12px; padding: 8px 12px; background: #f7f7f7; border: 1px solid #ddd; border-radius: 6px; font-size: 10px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border: 1px solid #ccc; padding: 3px 5px; text-align: left; }
  th { background: #f0f0f0; font-weight: bold; }
  td.num, th.num { text-align: right; }
  tfoot td { font-weight: bold; background: #f7f7f7; }
  .footer { margin-top: 12px; font-size: 10px; color: #666; text-align: center; }
</style>
</head>
<body>
  <div class="header">
    <h1>IGMO S.A.S.</h1>
    <p>Consulta de Viajes</p>
    <p>Generado: ${generatedAt}</p>
  </div>
  <div class="filters"><strong>Filtros aplicados:</strong> ${escapeHtml(filterSummary || 'Ninguno')}</div>
  <table>
    <thead><tr>${headerCells}</tr></thead>
    <tbody>${bodyRows || `<tr><td colspan="${columns.length}" style="text-align:center;color:#999;font-style:italic;">Sin resultados</td></tr>`}</tbody>
    <tfoot><tr>${footerCells}</tr></tfoot>
  </table>
  <div class="footer">Generado por SIGMO — ${generatedAt}</div>
</body>
</html>`
}

export function printGeneralQuery(
  rows: Trip[],
  columns: ColumnLite[],
  filterSummary: string,
  invoiceNumberMap: Record<number, string>,
): void {
  const html = generateGeneralQueryHtml(rows, columns, filterSummary, invoiceNumberMap)
  const win = window.open('', '_blank', 'width=1100,height=750')
  if (!win) return
  win.document.write(html)
  win.document.close()
  win.focus()
  setTimeout(() => {
    win.print()
    win.close()
  }, 300)
}
