import api from './axiosInstance'
import type { Client } from '@/types'

export const clientsApi = {
  list: (params?: { name?: string; nit?: string; state?: string }) =>
    api.get<Client[]>('/clients/', { params }),

  get: (id: number) =>
    api.get<Client>(`/clients/${id}/`),

  create: (data: Partial<Client>) =>
    api.post<Client>('/clients/', data),

  update: (id: number, data: Partial<Client>) =>
    api.patch<Client>(`/clients/${id}/`, data),
}
