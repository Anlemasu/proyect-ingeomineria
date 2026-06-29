import api from './axiosInstance'
import type { PaymentMethod } from '@/types'

export const paymentMethodsApi = {
  list: () =>
    api.get<PaymentMethod[]>('/masters/payment-methods/'),

  get: (id: number) =>
    api.get<PaymentMethod>(`/masters/payment-methods/${id}/`),

  create: (data: { name: string; is_advance: boolean }) =>
    api.post<PaymentMethod>('/masters/payment-methods/', data),

  update: (id: number, data: Partial<PaymentMethod>) =>
    api.patch<PaymentMethod>(`/masters/payment-methods/${id}/`, data),
}
