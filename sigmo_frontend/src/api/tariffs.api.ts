import api from './axiosInstance'
import type { Tariff } from '@/types'

export const tariffsApi = {
  list: (params?: { client?: number; vehicle_type?: number; state?: boolean }) =>
    api.get<Tariff[]>('/masters/tariffs/', { params }),

  get: (id: number) =>
    api.get<Tariff>(`/masters/tariffs/${id}/`),

  create: (data: {
    client?: number | null
    vehicle_type: number
    material_type?: number | null
    value: number
    start_date: string
  }) =>
    api.post<Tariff>('/masters/tariffs/', data),

  update: (id: number, data: { value: number }) =>
    api.patch<Tariff>(`/masters/tariffs/${id}/`, data),

  // 8B.5: elimina una tarifa personalizada de cliente (sin reemplazo) para
  // que ese cliente vuelva a usar la tarifa general — distinto de `update`,
  // que siempre cierra la vieja Y crea una nueva (RF-21).
  remove: (id: number) => api.delete(`/masters/tariffs/${id}/`),
}
