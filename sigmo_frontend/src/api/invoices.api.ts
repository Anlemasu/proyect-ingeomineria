import api from './axiosInstance'
import type { Invoice } from '@/types'

export const invoicesApi = {
  list: () => api.get<Invoice[]>('/invoices/'),
  create: (data: { number: string }) => api.post<Invoice>('/invoices/', data),
  detail: (id: number) => api.get<Invoice>(`/invoices/${id}/`),
}
