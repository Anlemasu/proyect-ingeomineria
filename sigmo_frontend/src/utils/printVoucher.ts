import type { Trip } from '@/types'
import { formatCurrency } from '@/utils/formatCurrency'
import { format, parseISO } from 'date-fns'
import { openCenteredWindow } from '@/utils/openCenteredWindow'

function generateVoucherHtml(trip: Trip, pin: string, observations?: string | null): string {
  const now = new Date()
  const registerDate = trip.date_register
    ? format(parseISO(trip.date_register), 'dd/MM/yyyy')
    : format(now, 'dd/MM/yyyy')
  const printTime = format(now, 'dd/MM/yyyy HH:mm')

  const observationsRow = observations?.trim()
    ? `<div class="row obs"><span class="label">Observaciones:</span><span class="value obs-val">${observations.trim()}</span></div>`
    : ''

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Vale #${trip.voucher_num}</title>
<style>
  @media print {
    body { margin: 0; }
    .no-print { display: none; }
  }
  body {
    font-family: Arial, sans-serif;
    font-size: 12px;
    width: 80mm;
    margin: 0 auto;
    padding: 8px;
    color: #000;
  }
  .center { text-align: center; }
  .bold { font-weight: bold; }
  .large { font-size: 18px; }
  .xlarge { font-size: 28px; font-weight: bold; }
  hr { border: none; border-top: 1px dashed #000; margin: 6px 0; }
  .row { display: flex; justify-content: space-between; margin: 3px 0; }
  .label { color: #444; }
  .value { font-weight: bold; }
  .obs { align-items: flex-start; }
  .obs-val { text-align: right; max-width: 55mm; word-break: break-word; }
  .footer { font-size: 10px; color: #666; margin-top: 8px; }
</style>
</head>
<body>
  <div class="center bold large">IGMO S.A.S.</div>
  <div class="center" style="font-size:11px;">Sitio de Disposición Autorizado</div>
  <hr/>
  <div class="center bold large" style="margin:6px 0;">VALE DE INGRESO</div>
  <div class="center xlarge" style="margin:4px 0;">N° ${trip.voucher_num}</div>
  <div class="center" style="color:#555;">${registerDate}</div>
  <hr/>
  <div class="row"><span class="label">Cliente:</span><span class="value">${trip.client_detail?.name ?? '—'}</span></div>
  <div class="row"><span class="label">Placa:</span><span class="value">${trip.vehicle_detail?.plaque ?? '—'}</span></div>
  <div class="row"><span class="label">PIN Ambiental:</span><span class="value">${pin}</span></div>
  <div class="row"><span class="label">Material:</span><span class="value">${trip.material_type_detail?.name ?? '—'}</span></div>
  <div class="row"><span class="label">Tipo Vehículo:</span><span class="value">${trip.vehicle_detail?.vehicle_type_detail?.name ?? '—'}</span></div>
  <div class="row"><span class="label">Origen:</span><span class="value">${trip.origin_site_detail?.name ?? '—'}</span></div>
  <div class="row"><span class="label">Medio de Pago:</span><span class="value">${trip.payment_detail?.name ?? '—'}</span></div>
  <div class="row"><span class="label">Vale externo:</span><span class="value">${trip.extern_voucher_num ?? '—'}</span></div>
  ${observationsRow}
  <hr/>
  <div class="center footer">Generado por SIGMO — IGMO S.A.S.<br/>${printTime}</div>
</body>
</html>`
}

export function printVoucher(trip: Trip, pin: string, observations?: string | null): void {
  const html = generateVoucherHtml(trip, pin, observations)
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
