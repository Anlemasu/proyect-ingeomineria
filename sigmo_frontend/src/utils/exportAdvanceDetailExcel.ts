import * as XLSX from 'xlsx'
import type { Advance, Trip } from '@/types'
import { formatDate } from '@/utils/formatDate'

/**
 * Exporta el detalle completo de un anticipo a un libro Excel con tres hojas:
 *   - "Anticipo": datos de cabecera + saldo disponible en vivo.
 *   - "Movimientos": todos los AdvanceMovement (ingresos y egresos, incluidas
 *     las reversiones de viajes anulados) — historial completo, sin filtrar.
 *   - "Viajes": los viajes ACTIVOS registrados contra el anticipo (state=true),
 *     que es lo que hoy consume saldo. Mismo criterio que la tabla en pantalla.
 *
 * `trips` debe venir ya filtrado a los que se quieren en la hoja "Viajes"
 * (el caller aplica el filtro state=true).
 */
export function exportAdvanceDetailExcel(advance: Advance, trips: Trip[]): void {
  const wb = XLSX.utils.book_new()

  const totalDiscounted = trips.reduce((s, t) => s + Number(t.value), 0)

  // ── Hoja 1: Anticipo ─────────────────────────────────────────────────────
  const anticipoRows: (string | number)[][] = [
    ['Detalle de Anticipo — SIGMO'],
    [],
    ['N° Anticipo', advance.id],
    ['Cliente', advance.client_detail?.name ?? '—'],
    ['NIT', advance.client_detail?.nit ?? '—'],
    ['Fecha', formatDate(advance.date)],
    ['Valor del anticipo', Number(advance.value)],
    ['N° Consignación', advance.transfer_num],
    ['N° Proforma', advance.proforma_number ?? '—'],
    ['Saldo disponible', advance.available_balance],
    ['Observaciones', advance.observations ?? '—'],
    [],
    ['N° de viajes activos', trips.length],
    ['Total descontado (viajes activos)', totalDiscounted],
  ]
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(anticipoRows), 'Anticipo')

  // ── Hoja 2: Movimientos ──────────────────────────────────────────────────
  const movHeader = ['Fecha', 'Tipo', 'Monto', 'N° Viajes', 'Descripción', 'Viaje N°']
  const movs = [...(advance.movements ?? [])].sort(
    (a, b) => b.date.localeCompare(a.date) || b.id - a.id,
  )
  const movRows = movs.map(m => [
    formatDate(m.date),
    m.type_movement === 'ingreso' ? 'Ingreso' : 'Egreso',
    Number(m.amount),
    m.trips_quantity,
    m.description ?? '—',
    m.trip ?? '—',
  ])
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([movHeader, ...movRows]),
    'Movimientos',
  )

  // ── Hoja 3: Viajes ───────────────────────────────────────────────────────
  const viajesHeader = [
    'N° Vale', 'Fecha', 'Cliente', 'Placa', 'Tipo Vehículo', 'Origen',
    'Tipo Material', 'Valor', 'Medio de Pago', 'Estado',
  ]
  const viajesRows = trips.map(t => [
    t.voucher_num,
    formatDate(t.date),
    t.client_detail?.name ?? '—',
    t.vehicle_detail?.plaque ?? '—',
    t.vehicle_detail?.vehicle_type_detail?.name ?? '—',
    t.origin_site_detail?.name ?? '—',
    t.material_type_detail?.name ?? '—',
    Number(t.value),
    t.payment_detail?.name ?? '—',
    t.state ? 'Activo' : 'Anulado',
  ])
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      viajesHeader,
      ...viajesRows,
      ['', '', '', '', '', '', 'Total', totalDiscounted, '', ''],
    ]),
    'Viajes',
  )

  const slug = advance.client_detail?.abrev_name || 'cliente'
  XLSX.writeFile(wb, `Anticipo_${advance.id}_${slug}.xlsx`)
}
