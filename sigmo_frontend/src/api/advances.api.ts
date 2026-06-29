import api from './axiosInstance'
import type { Advance, AdvanceBalance } from '@/types'

export const advancesApi = {
  list: (params?: { client?: number }) =>
    api.get<Advance[]>('/advances/', { params }),

  create: (data: {
    client: number
    value: number
    transfer_num: number
    date: string
    trips_quantity?: number
    proforma_number?: number
    observations?: string
  }) => api.post<Advance>('/advances/', data),

  update: (id: number, data: {
    value?: number
    transfer_num?: number
    date?: string
    proforma_number?: number | null
    observations?: string | null
  }) => api.patch<Advance>(`/advances/${id}/`, data),

  balance: (clientId: number) =>
    api.get<AdvanceBalance>(`/advances/balance/${clientId}/`),
}
