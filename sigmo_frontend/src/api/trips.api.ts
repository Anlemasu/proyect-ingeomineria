import api from './axiosInstance'
import type { Trip } from '@/types'

export const tripsApi = {
  list: (params?: {
    client?: number
    date_from?: string
    date_to?: string
    date?: string
    state?: boolean
    invoice?: number
  }) => api.get<Trip[]>('/trips/', { params }),

  patch: (id: number, data: {
    invoice?: number | null
    invoice_pos?: number | null
    state?: boolean
    justification?: string
  }) => api.patch<Trip>(`/trips/${id}/`, data),
}
