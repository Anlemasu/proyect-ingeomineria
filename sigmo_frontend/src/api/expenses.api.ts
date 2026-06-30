import api from './axiosInstance'
import type { Expense } from '@/types'

export interface ExpenseListParams {
  date?: string
  date_from?: string
  date_to?: string
}

export interface ExpensePayload {
  description: string
  value: number
  date: string
}

export const expensesApi = {
  list: (params?: ExpenseListParams) => api.get<Expense[]>('/expenses/', { params }),
  create: (data: ExpensePayload) => api.post<Expense>('/expenses/', data),
  detail: (id: number) => api.get<Expense>(`/expenses/${id}/`),
  update: (id: number, data: Partial<ExpensePayload>) => api.patch<Expense>(`/expenses/${id}/`, data),
}
