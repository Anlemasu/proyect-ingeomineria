import type { Trip } from '@/types'
import { formatCurrency } from '@/utils/formatCurrency'
import { format, parseISO } from 'date-fns'
import { openCenteredWindow } from '@/utils/openCenteredWindow'

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function row(label: string, value: string): string {
  return `<div class="row"><span class="label">${escapeHtml(label)}:</span><span class="value">${escapeHtml(value)}</span></div>`
}

function generateAdjustmentHtml(trip: Trip): string {
  const printTime = format(new Date(), 'dd/MM/yyyy HH:mm')
  const tripDate = trip.date ? format(parseISO(trip.date), 'dd/MM/yyyy') : '—'

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Ajuste — Vale #${trip.voucher_num}</title>
<style>
  @media print {
    body { margin: 0; }
    .no-print { display: none; }
  }
  body {
    font-family: Arial, sans-serif;
    font-size: 13px;
    width: 90mm;
    margin: 0 auto;
    padding: 10px;
    color: #000;
  }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  .large { font-size: 18px; }
  hr { border: none; border-top: 1px dashed #000; margin: 8px 0; }
  .row { display: flex; justify-content: space-between; gap: 8px; margin: 4px 0; }
  .label { color: #444; }
  .value { font-weight: bold; text-align: right; max-width: 60mm; word-break: break-word; }
  .footer { font-size: 10px; color: #666; margin-top: 10px; }
</style>
</head>
<body>
  <div class="center bold large">IGMO S.A.S.</div>
  <div class="center bold" style="margin:6px 0;">COMPROBANTE DE AJUSTE — VALE N° ${trip.voucher_num}</div>
  <hr/>
  ${row('Fecha del viaje', tripDate)}
  ${row('Cliente', trip.client_detail?.name ?? '—')}
  ${row('Placa', trip.vehicle_detail?.plaque ?? '—')}
  ${row('Material', trip.material_type_detail?.name ?? '—')}
  ${row('Origen', trip.origin_site_detail?.name ?? '—')}
  ${row('Medio de pago', trip.payment_detail?.name ?? '—')}
  ${row('Valor', formatCurrency(trip.value))}
  ${row('Vale externo', trip.extern_voucher_num ?? '—')}
  ${row('Estado', trip.state ? 'Activo' : 'Anulado')}
  ${row('Observaciones', trip.observations ?? '—')}
  <hr/>
  <div class="center footer">Generado por SIGMO — IGMO S.A.S.<br/>${printTime}</div>
</body>
</html>`
}

export function printAdjustmentRecord(trip: Trip): void {
  const html = generateAdjustmentHtml(trip)
  const win = openCenteredWindow(window.screen.availWidth, window.screen.availHeight)
  if (!win) return
  win.document.write(html)
  win.document.close()
  win.focus()
  setTimeout(() => {
    win.print()
    win.close()
  }, 300)
}
