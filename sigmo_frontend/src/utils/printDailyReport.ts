import type { DailyReportData } from '@/types'
import { formatCurrency } from '@/utils/formatCurrency'
import { formatDate } from '@/utils/formatDate'
import { format } from 'date-fns'

function escapeHtml(value: unknown): string {
  return String(value ?? '—')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function generateDailyReportHtml(date: string, data: DailyReportData): string {
  const now = new Date()
  const generatedAt = format(now, 'dd/MM/yyyy HH:mm')

  const summaryBoxes = `
    <div class="summary-row">
      <div class="summary-box">
        <span class="summary-label">Total Viajes</span>
        <span class="summary-value">${data.summary.totalTrips}</span>
      </div>
      <div class="summary-box">
        <span class="summary-label">Total Recaudado</span>
        <span class="summary-value green">${formatCurrency(data.summary.totalCollected)}</span>
      </div>
      <div class="summary-box">
        <span class="summary-label">Total Gastos</span>
        <span class="summary-value red">${formatCurrency(data.summary.totalExpenses)}</span>
      </div>
      <div class="summary-box">
        <span class="summary-label">Saldo Neto</span>
        <span class="summary-value ${data.summary.netBalance >= 0 ? 'blue' : 'red'}">${formatCurrency(data.summary.netBalance)}</span>
      </div>
    </div>`

  const paymentRows = data.summary.byPaymentMethod.map(p => `
    <tr>
      <td>${escapeHtml(p.name)}</td>
      <td class="num">${p.tripCount}</td>
      <td class="num">${formatCurrency(p.total)}</td>
    </tr>`).join('')

  const paymentTable = `
    <table>
      <thead><tr><th>Medio de Pago</th><th class="num">N° Viajes</th><th class="num">Total (COP)</th></tr></thead>
      <tbody>${paymentRows || '<tr><td colspan="3" class="empty">Sin viajes registrados</td></tr>'}</tbody>
      <tfoot><tr>
        <td>Total</td>
        <td class="num">${data.summary.totalTrips}</td>
        <td class="num">${formatCurrency(data.summary.totalCollected)}</td>
      </tr></tfoot>
    </table>`

  const tripRows = data.trips.map(t => `
    <tr>
      <td>${t.voucher_num}</td>
      <td>${formatDate(t.date_register)}</td>
      <td>${escapeHtml(t.client_detail?.name)}</td>
      <td>${escapeHtml(t.vehicle_detail?.plaque)}</td>
      <td>${escapeHtml(t.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0')}</td>
      <td>${escapeHtml(t.origin_site_detail?.name)}</td>
      <td>${escapeHtml(t.material_type_detail?.name)}</td>
      <td>${escapeHtml(t.vehicle_detail?.vehicle_type_detail?.name)}</td>
      <td class="num">${formatCurrency(t.value)}</td>
      <td>${escapeHtml(t.payment_detail?.name)}</td>
      <td>${escapeHtml(t.extern_voucher_num ?? '—')}</td>
      <td>${escapeHtml(t.invoice ?? '—')}</td>
      <td>${t.state ? 'Activo' : 'Anulado'}</td>
    </tr>`).join('')

  const tripsTable = `
    <table>
      <thead><tr>
        <th>N° Vale</th><th>Fecha registro</th><th>Cliente</th><th>Placa</th><th>PIN Ambiental</th>
        <th>Origen</th><th>Tipo Material</th><th>Tipo Vehículo</th><th class="num">Valor</th>
        <th>Medio de Pago</th><th>N° Vale Externo</th><th>N° Factura</th><th>Estado</th>
      </tr></thead>
      <tbody>${tripRows || '<tr><td colspan="13" class="empty">No se registraron viajes para esta fecha.</td></tr>'}</tbody>
    </table>`

  const expenseRows = data.expenses.map(e => `
    <tr>
      <td>${formatDate(e.date)}</td>
      <td>${escapeHtml(e.description)}</td>
      <td class="num">${formatCurrency(e.value)}</td>
      <td>#${e.user}</td>
    </tr>`).join('')

  const totalExpenses = data.expenses.reduce((s, e) => s + Number(e.value), 0)

  const expensesTable = `
    <table>
      <thead><tr><th>Fecha</th><th>Descripción</th><th class="num">Valor</th><th>Usuario</th></tr></thead>
      <tbody>${expenseRows || '<tr><td colspan="4" class="empty">No se registraron gastos para esta fecha.</td></tr>'}</tbody>
      <tfoot><tr><td colspan="2">Total</td><td class="num">${formatCurrency(totalExpenses)}</td><td></td></tr></tfoot>
    </table>`

  const advanceRows = data.advancesConsumed.map(t => `
    <tr>
      <td>${escapeHtml(t.client_detail?.name)}</td>
      <td>#${t.advance}</td>
      <td class="num">${formatCurrency(t.value)}</td>
      <td>#${t.voucher_num}</td>
    </tr>`).join('')

  const totalAdvances = data.advancesConsumed.reduce((s, t) => s + Number(t.value), 0)

  const advancesTable = `
    <table>
      <thead><tr><th>Cliente</th><th>Anticipo ID</th><th class="num">Valor Descontado</th><th>N° Viaje asociado</th></tr></thead>
      <tbody>${advanceRows || '<tr><td colspan="4" class="empty">No se consumieron anticipos en esta fecha.</td></tr>'}</tbody>
      <tfoot><tr><td colspan="2">Total</td><td class="num">${formatCurrency(totalAdvances)}</td><td></td></tr></tfoot>
    </table>`

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Reporte Diario ${date}</title>
<style>
  @media print {
    @page { size: A4 landscape; margin: 1cm; }
  }
  body { font-family: Arial, sans-serif; font-size: 11px; color: #111; margin: 0; padding: 16px; }
  .header { text-align: center; margin-bottom: 16px; }
  .header h1 { margin: 4px 0; font-size: 18px; }
  .header p { margin: 2px 0; color: #555; }
  h2 { font-size: 13px; margin: 20px 0 8px; border-bottom: 2px solid #333; padding-bottom: 4px; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
  th, td { border: 1px solid #ccc; padding: 4px 6px; text-align: left; }
  th { background: #f0f0f0; font-weight: bold; }
  td.num, th.num { text-align: right; }
  tfoot td { font-weight: bold; background: #f7f7f7; }
  .empty { text-align: center; color: #999; font-style: italic; }
  .summary-row { display: flex; gap: 12px; margin-bottom: 12px; }
  .summary-box { flex: 1; border: 1px solid #ccc; border-radius: 6px; padding: 10px; text-align: center; }
  .summary-label { display: block; font-size: 10px; color: #666; text-transform: uppercase; }
  .summary-value { display: block; font-size: 18px; font-weight: bold; margin-top: 4px; }
  .summary-value.green { color: #15803d; }
  .summary-value.red { color: #b91c1c; }
  .summary-value.blue { color: #1d4ed8; }
  .footer { margin-top: 16px; font-size: 10px; color: #666; text-align: center; }
</style>
</head>
<body>
  <div class="header">
    <h1>IGMO S.A.S.</h1>
    <p>Reporte Diario de Operaciones</p>
    <p>Fecha: ${formatDate(date)}</p>
  </div>

  ${summaryBoxes}

  <h2>Desglose por medio de pago</h2>
  ${paymentTable}

  <h2>Viajes del día (${data.trips.length})</h2>
  ${tripsTable}

  <h2>Gastos del día (${data.expenses.length})</h2>
  ${expensesTable}

  <h2>Anticipos consumidos (${data.advancesConsumed.length})</h2>
  ${advancesTable}

  <div class="footer">Generado por SIGMO — ${generatedAt}</div>
</body>
</html>`
}

export function printDailyReport(date: string, data: DailyReportData): void {
  const html = generateDailyReportHtml(date, data)
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
