import type { DailySummary } from '@/types'
import { formatCurrency } from '@/utils/formatCurrency'

/**
 * Copia al portapapeles, en texto separado por tabulaciones (pegable
 * directamente en Excel/Sheets), las DOS tablas del detalle de un cierre de
 * caja: "Desglose por medio de pago" y "Viajes por cliente".
 *
 * Se arma desde los datos en vez de leer el DOM (a diferencia de
 * copyTableToClipboard) porque el desglose por medio de pago del drawer no
 * se renderiza como <table> HTML — así ambos bloques quedan en un solo
 * copiado, uno debajo del otro.
 */
export async function copyCashClosingDetail(summary: DailySummary): Promise<void> {
  const revenue = summary.payment_details.reduce((s, p) => s + Number(p.total), 0)

  const paymentLines = [
    'Desglose por medio de pago',
    ['Medio de Pago', 'Total (COP)'].join('\t'),
    ...summary.payment_details.map(p => [p.payment_method_name, formatCurrency(p.total)].join('\t')),
    ['Total', formatCurrency(revenue)].join('\t'),
  ]

  const clients = summary.client_details ?? []
  const totals = clients.reduce(
    (acc, r) => ({
      trips: acc.trips + r.trips_count,
      value: acc.value + Number(r.total_value),
      volume: acc.volume + Number(r.total_volume),
    }),
    { trips: 0, value: 0, volume: 0 },
  )
  const clientLines = [
    'Viajes por cliente',
    ['Cliente', 'N° Viajes', 'Total (COP)', 'Volumen m³'].join('\t'),
    ...clients.map(r => [
      r.client_name,
      String(r.trips_count),
      formatCurrency(r.total_value),
      String(Number(r.total_volume)),
    ].join('\t')),
    ['Total', String(totals.trips), formatCurrency(totals.value), String(totals.volume)].join('\t'),
  ]

  const text = [...paymentLines, '', ...clientLines].join('\n')
  await navigator.clipboard.writeText(text)
}
