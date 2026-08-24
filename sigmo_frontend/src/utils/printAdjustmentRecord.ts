import type { Trip } from '@/types'
import { format, parseISO } from 'date-fns'
import { openCenteredWindow } from '@/utils/openCenteredWindow'

// Datos fijos del sitio de disposición (visibles en el formato físico).
// Idénticos a los de printVoucher.ts — ajustar en ambos archivos si cambian.
const SITE_NAME = 'SAN ANTONIO'
const SITE_DESCRIPTION = 'SITIO DE DISPOSICIÓN FINAL DE RESIDUOS DE\nCONSTRUCCIÓN Y DEMOLICIÓN'
const SITE_LICENSES = [
  'RESOLUCIÓN 0836 DEL 16 DE JULIO DE 2015 DE ANLA',
  'RESOLUCIÓN 1110 DEL 12 DE SEPTIEMBRE DE 2017 DE ANLA',
  'REGISTRO SDA PIN 9730',
  'REGISTRO PROVEEDOR IDU N°.654 -2022',
]

// --- Presupuesto de alto fijo del vale (siempre 12.497cm x 7.011cm) ---
// Mismos números que printVoucher.ts, para que ambos comprobantes se vean
// exactamente iguales de tamaño y proporciones.
const BODY_TOTAL_MM = 70.11 // 7.011cm
const HEADER_MM = 11
const LICENSES_MM = 6.5
const BODY_ROW_MM = BODY_TOTAL_MM - HEADER_MM - LICENSES_MM // 52.61mm
const BODY_PAD_TOP_MM = 1
const BODY_PAD_BOTTOM_MM = 2
const BODY_CONTENT_MM = BODY_ROW_MM - BODY_PAD_TOP_MM - BODY_PAD_BOTTOM_MM // 49.61mm

const FIELD_FONT_PX = 7
const FIELD_LINE_HEIGHT_RATIO = 1.05
const PX_TO_MM = 25.4 / 96
const TEXT_LINE_MM = FIELD_FONT_PX * FIELD_LINE_HEIGHT_RATIO * PX_TO_MM // ≈1.94mm
const FIELD_OVERHEAD_MM = 1.0 // padding (0.3mm x2) + borde de cada renglón
const GAP_BEFORE_OBSERVACIONES_MM = 0.5

// Mismo patrón de líneas que printVoucher.ts (1 línea la mayoría, Empresa
// Generadora 4 líneas, Origen Material 2 líneas).
const FIELD_LINES = [1, 1, 1, 1, 4, 2, 1, 1, 1, 1]
const OBSERVACIONES_LINES = 5

const FIELD_ROW_HEIGHTS_MM = FIELD_LINES.map((n) => FIELD_OVERHEAD_MM + n * TEXT_LINE_MM)
const FIELD_ROWS_SUM_MM = FIELD_ROW_HEIGHTS_MM.reduce((a, b) => a + b, 0)
const OBSERVACIONES_ROW_HEIGHT_MM = BODY_CONTENT_MM - FIELD_ROWS_SUM_MM
const FIELDS_COL_ROWS = `${FIELD_ROW_HEIGHTS_MM.map((h) => `${h.toFixed(2)}mm`).join(' ')} ${OBSERVACIONES_ROW_HEIGHT_MM.toFixed(2)}mm`

// Misma información que printVoucher.ts: recibe los mismos datos externos al
// Trip (pin, observaciones, factura POS) para poder reimprimir exactamente
// el mismo vale después de corregir un valor.
function generateAdjustmentHtml(
  trip: Trip,
  pin: string,
  observations?: string | null,
  posInvoice?: string | number | null,
): string {
  // NOTA: igual que en printVoucher.ts, se asume que `trip.date_register` es
  // un datetime ISO completo (fecha + hora). Si en tu Trip real el campo se
  // llama distinto (p. ej. `trip.date`), ajusta esta línea.
  const registerDateObj = trip.date_register ? parseISO(trip.date_register) : new Date()
  const registerDate = format(registerDateObj, 'd/MM/yyyy')
  const registerTime = format(registerDateObj, 'HH:mm')

  const posInvoiceValue = posInvoice != null && posInvoice !== '' ? String(posInvoice) : '0'

  // QR con el número de vale (misma API pública que printVoucher.ts, requiere
  // conexión a internet en el navegador que imprime).
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
<title>Ajuste — Vale #${trip.voucher_num}</title>
<style>
  /* Página física idéntica a printVoucher.ts: hoja 5x7in horizontal (ancho
     7in x alto 5in), márgenes de 6.35mm, columna única de 12.497cm x 7.011cm. */
  @page { size: 7in 5in; margin: 6.35mm; }
  @media print {
    body { margin: 0; }
    .no-print { display: none; }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; padding: 0; }
  body {
    font-family: Arial, Helvetica, sans-serif;
    color: #000;
    width: 12.497cm;
    height: 7.011cm;
    font-size: 7.5px;
    line-height: 1.15;
    display: grid;
    grid-template-rows: ${HEADER_MM}mm ${LICENSES_MM}mm ${BODY_ROW_MM.toFixed(2)}mm;
  }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1mm 2mm 0.5mm;
    overflow: hidden;
  }
  .header-logo { height: 8.5mm; width: auto; max-width: 16mm; object-fit: contain; }
  .header-title { text-align: center; flex: 1; }
  .header-title .site-name { font-size: 9px; font-weight: bold; margin: 0; }
  .header-title .site-desc {
    font-size: 5.5px;
    font-weight: bold;
    margin: 0.5px 0 0;
    white-space: pre-line;
  }
  .header-comprobante { text-align: center; width: 22mm; }
  .header-comprobante .label { font-size: 5.5px; color: #333; margin-bottom: 0.4mm; }
  .header-comprobante .num-box {
    border: 1px solid #888;
    color: #c00;
    font-size: 12px;
    font-weight: bold;
    padding: 0.4mm 0;
  }
  .header-comprobante .caption { font-size: 5.5px; margin-top: 0.4mm; }
  .licenses { padding: 0.3mm 2mm; font-size: 5px; color: #333; overflow: hidden; }
  .licenses .lic-title {
    display: inline-block;
    width: 18mm;
    vertical-align: top;
  }
  .licenses .lic-list { display: inline-block; }
  .licenses .lic-list div { margin: 0.15mm 0; }
  .body {
    display: grid;
    grid-template-columns: 1fr 42mm;
    column-gap: 1.5mm;
    padding: 1mm 2mm 2mm;
    min-height: 0;
  }
  .fields-col {
    display: grid;
    grid-template-rows: ${FIELDS_COL_ROWS};
    min-height: 0;
  }
  .field {
    display: flex;
    border: 1px solid #000;
    margin-bottom: -1px;
    min-height: 0;
    font-size: ${FIELD_FONT_PX}px;
    line-height: ${FIELD_LINE_HEIGHT_RATIO};
  }
  .field-label {
    flex: 0 0 24mm;
    font-weight: bold;
    border-right: 1px solid #000;
    padding: 0.3mm 1mm;
  }
  .field-value {
    flex: 1;
    min-width: 0;
    padding: 0.3mm 1mm;
    overflow: hidden;
    white-space: normal;
    word-break: break-word;
  }
  .bottom-row { display: flex; gap: 1.5mm; margin-top: ${GAP_BEFORE_OBSERVACIONES_MM}mm; min-height: 0; }
  .obs-box {
    flex: 1;
    border: 1px solid #000;
    padding: 0.3mm 1mm;
    font-weight: bold;
    font-size: ${FIELD_FONT_PX}px;
    line-height: ${FIELD_LINE_HEIGHT_RATIO};
    overflow: hidden;
  }
  .qr-box {
    flex: 0 0 18mm;
    border: 1px solid #000;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .qr-box img { width: 88%; height: 88%; object-fit: contain; }
  .stamps-col {
    display: grid;
    grid-template-rows: repeat(3, 1fr);
    gap: 0.8mm;
    min-height: 0;
  }
  .stamp-box {
    border: 1px solid #000;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #aaa;
    font-size: 7px;
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
      <div class="label">Comprobante de ajuste</div>
      <div class="num-box">${trip.voucher_num}</div>
      <div class="caption">ajuste de vale</div>
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
      <div class="bottom-row">
        <div class="obs-box">${observations?.trim() ? observations.trim() : ''}</div>
        <div class="qr-box">
          <img src="${qrSrc}" alt="QR" />
        </div>
      </div>
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

export function printAdjustmentRecord(
  trip: Trip,
  pin: string,
  observations?: string | null,
  posInvoice?: string | number | null,
): void {
  const html = generateAdjustmentHtml(trip, pin, observations, posInvoice)
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