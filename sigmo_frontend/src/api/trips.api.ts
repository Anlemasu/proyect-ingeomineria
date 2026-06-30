import api from './axiosInstance'
import type { Trip } from '@/types'

export interface TripCreateData {
  client: number
  origin_site: number
  material_type: number
  vehicle: number
  payment: number
  advance?: number | null
  value: number
  date: string
  extern_voucher_num?: string | null
  force?: boolean
}

export const tripsApi = {
  list: (params?: {
    client?: number
    date_from?: string
    date_to?: string
    date?: string
    state?: boolean
    invoice?: number
  }) => api.get<Trip[]>('/trips/', { params }),

  detail: (id: number) =>
    api.get<Trip>(`/trips/${id}/`),

  create: (data: TripCreateData) =>
    api.post<Trip>('/trips/', data),

  patch: (id: number, data: {
    invoice?: number | null
    invoice_pos?: number | null
    state?: boolean
    justification?: string
    payment?: number
    client?: number
    origin_site?: number
    material_type?: number
    vehicle?: number
    advance?: number | null
    value?: number
    date?: string
    extern_voucher_num?: string | null
  }) => api.patch<Trip>(`/trips/${id}/`, data),
}
