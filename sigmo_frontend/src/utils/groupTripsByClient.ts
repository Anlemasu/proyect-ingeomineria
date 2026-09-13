import type { Trip, TripsByClientRow } from '@/types'

/**
 * Agrupa viajes ACTIVOS (state=true) por cliente: conteo, valor total y
 * volumen m³ (capacidad del tipo de vehículo del viaje — misma métrica que
 * usa el backend para el volumen del cierre de caja).
 *
 * Ordena por cantidad de viajes desc y, a igualdad, por nombre de cliente.
 * Mismo formato que devuelve el backend en TodaySummary.trips_by_client /
 * DailySummary.client_details, para poder renderizar la tabla con el mismo
 * componente sin importar el origen de los datos.
 */
export function groupTripsByClient(trips: Trip[]): TripsByClientRow[] {
  const map = new Map<number, TripsByClientRow>()
  for (const t of trips) {
    if (!t.state) continue
    const id = t.client_detail?.id ?? -1
    const row = map.get(id) ?? {
      client: id,
      client_name: t.client_detail?.name ?? '—',
      trips_count: 0,
      total_value: 0,
      total_volume: 0,
    }
    row.trips_count += 1
    row.total_value = Number(row.total_value) + Number(t.value)
    row.total_volume =
      Number(row.total_volume) + Number(t.vehicle_detail?.vehicle_type_detail?.capacity ?? 0)
    map.set(id, row)
  }
  return [...map.values()].sort(
    (a, b) => b.trips_count - a.trips_count || a.client_name.localeCompare(b.client_name),
  )
}
