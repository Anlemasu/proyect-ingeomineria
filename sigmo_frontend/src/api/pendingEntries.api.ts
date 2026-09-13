import api from './axiosInstance'
import type { PendingEntry, PendingEntryType, PendingEntryStatus } from '@/types'

export const pendingEntriesApi = {
  list: (params?: { client?: number; entry_type?: PendingEntryType; status?: PendingEntryStatus }) =>
    api.get<PendingEntry[]>('/pending-entries/', { params }),

  create: (data: {
    entry_type: PendingEntryType
    client: number
    value: number
    date: string
    payment_method?: number | null
    observations?: string
  }) => api.post<PendingEntry>('/pending-entries/', data),

  update: (id: number, data: {
    client?: number
    value?: number
    date?: string
    payment_method?: number | null
    observations?: string | null
  }) => api.patch<PendingEntry>(`/pending-entries/${id}/`, data),

  cancel: (id: number, data: { justification: string }) =>
    api.post<PendingEntry>(`/pending-entries/${id}/cancel/`, data),
}
