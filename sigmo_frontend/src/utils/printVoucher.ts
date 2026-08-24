import type { Trip } from '@/types'
import { format, parseISO } from 'date-fns'
import { openCenteredWindow } from '@/utils/openCenteredWindow'

// Datos fijos del sitio de disposición (visibles en el formato físico).
// Ajustar aquí si cambian las resoluciones, el registro o el nombre del sitio.
const SITE_NAME = 'SAN ANTONIO'
const SITE_DESCRIPTION = 'SITIO DE DISPOSICIÓN FINAL DE RESIDUOS DE\nCONSTRUCCIÓN Y DEMOLICIÓN'
const SITE_LICENSES = [
  'RESOLUCIÓN 0836 DEL 16 DE JULIO DE 2015 DE ANLA',
  'RESOLUCIÓN 1110 DEL 12 DE SEPTIEMBRE DE 2017 DE ANLA',
  'REGISTRO SDA PIN 9730',
  'REGISTRO PROVEEDOR IDU N°.654 -2022',
]

function generateVoucherHtml(
  trip: Trip,
  pin: string,
  observations?: string | null,
  posInvoice?: string | number | null,
): string {
  // NOTA: se asume que `trip.date_register` es un datetime ISO completo (fecha + hora),
  // ya que el formato físico muestra "Fecha" y "Hora" como campos separados.
  // Si en tu modelo Trip la hora viene en otro campo, reemplaza `registerTime` por ese valor.
  const registerDateObj = trip.date_register ? parseISO(trip.date_register) : new Date()
  const registerDate = format(registerDateObj, 'd/MM/yyyy')
  const registerTime = format(registerDateObj, 'HH:mm')

  // NOTA: "Factura POS" no existe en el tipo Trip mostrado; se recibe como parámetro
  // opcional. Cambia el origen del dato (p. ej. trip.pos_invoice) según tu modelo real.
  const posInvoiceValue = posInvoice != null && posInvoice !== '' ? String(posInvoice) : '0'

  // QR con el número de vale, generado vía API pública (requiere conexión a internet
  // en el navegador que imprime). Si prefieres generarlo localmente, sustituye `qrSrc`
  // por un data:URL producido con una librería como `qrcode`.
  const qrData = encodeURIComponent(`VALE ${trip.voucher_num} - IGMO S.A.S.`)
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&margin=0&data=${qrData}`

  const field = (label: string, value: string) => `
    <div class="field">
      <div class="field-label">${label}</div>
      <div class="field-value">${value}</div>
    </div>`

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Vale #${trip.voucher_num}</title>
<style>
  /* Página física: 5x7 pulgadas, márgenes de 6.35mm en todos los lados */
  @page { size: 5in 7in; margin: 6.35mm; }
  @media print {
    body { margin: 0; }
    .no-print { display: none; }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    font-family: Arial, Helvetica, sans-serif;
    color: #000;
    width: 12.497cm;
    height: 7.011cm;
    margin: 0 auto;
    padding: 0;
    font-size: 7.5px;
    line-height: 1.15;
    overflow: hidden;
  }
  .header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 2mm 2mm 1mm;
  }
  .header-logo { width: 14mm; height: auto; object-fit: contain; }
  .header-title { text-align: center; flex: 1; }
  .header-title .site-name { font-size: 11px; font-weight: bold; margin: 0; }
  .header-title .site-desc {
    font-size: 6.5px;
    font-weight: bold;
    margin: 1px 0 0;
    white-space: pre-line;
  }
  .header-comprobante { text-align: center; width: 26mm; }
  .header-comprobante .label { font-size: 6.5px; color: #333; margin-bottom: 1mm; }
  .header-comprobante .num-box {
    border: 1px solid #888;
    color: #c00;
    font-size: 15px;
    font-weight: bold;
    padding: 1mm 0;
  }
  .header-comprobante .caption { font-size: 6.5px; margin-top: 1mm; }
  .licenses { padding: 0 2mm; font-size: 5.5px; color: #333; }
  .licenses .lic-title {
    display: inline-block;
    width: 20mm;
    vertical-align: top;
  }
  .licenses .lic-list { display: inline-block; }
  .licenses .lic-list div { margin: 0.3mm 0; }
  .body { display: flex; padding: 1mm 2mm 2mm; gap: 2mm; }
  .fields-col { flex: 1.6; }
  .field { display: flex; border: 1px solid #000; margin-bottom: -1px; }
  .field-label {
    flex: 0 0 26mm;
    font-weight: bold;
    border-right: 1px solid #000;
    padding: 0.6mm 1mm;
  }
  .field-value { flex: 1; padding: 0.6mm 1mm; }
  .obs-box {
    border: 1px solid #000;
    min-height: 8mm;
    padding: 0.6mm 1mm;
    margin-top: 1mm;
    font-weight: bold;
    font-size: 6.5px;
  }
  .qr-col {
    flex: 0 0 18mm;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
  }
  .qr-col img { width: 16mm; height: 16mm; margin-top: 1mm; }
  .stamps-col { flex: 0 0 24mm; display: flex; flex-direction: column; gap: 0.8mm; }
  .stamp-box {
    border: 1px solid #000;
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #aaa;
    font-size: 6px;
  }
</style>
</head>
<body>
  <div class="header">
    <img class="header-logo" src="/logo_transparente.png" alt="Ingeominería" />
    <div class="header-title">
      <p class="site-name">${SITE_NAME}</p>
      <p class="site-desc">${SITE_DESCRIPTION}</p>
    </div>
    <div class="header-comprobante">
      <div class="label">Comprobante de ingreso</div>
      <div class="num-box">${trip.voucher_num}</div>
      <div class="caption">vale por 1 viaje</div>
    </div>
  </div>
  <div class="licenses">
    <span class="lic-title">Licencias y registros:</span>
    <span class="lic-list">
      ${SITE_LICENSES.map((l) => `<div>${l}</div>`).join('')}
    </span>
  </div>
  <div class="body">
    <div class="fields-col">
      ${field('Fecha:', registerDate)}
      ${field('Hora', registerTime)}
      ${field('Placa Vehículo', trip.vehicle_detail?.plaque ?? '—')}
      ${field('PIN', pin)}
      ${field('Empresa Generadora', trip.client_detail?.name ?? '—')}
      ${field('Origen Material', trip.origin_site_detail?.name ?? '—')}
      ${field('Vale Externo', trip.extern_voucher_num ?? '—')}
      ${field('Tipo Material', trip.material_type_detail?.name ?? '—')}
      ${field('Tipo Vehículo', trip.vehicle_detail?.vehicle_type_detail?.name ?? '—')}
      ${field('Factura POS', posInvoiceValue)}
      <div class="obs-box">${observations?.trim() ? observations.trim() : ''}</div>
    </div>
    <div class="qr-col">
      <img src="${qrSrc}" alt="QR" />
    </div>
    <div class="stamps-col">
      <div class="stamp-box">CAJAS</div>
      <div class="stamp-box">PATIO</div>
      <div class="stamp-box">PORTERÍA</div>
    </div>
  </div>
</body>
</html>`
}

export function printVoucher(
  trip: Trip,
  pin: string,
  observations?: string | null,
  posInvoice?: string | number | null,
): void {
  const html = generateVoucherHtml(trip, pin, observations, posInvoice)
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