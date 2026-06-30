import api from './axiosInstance'
import type { AuditLogEntry } from '@/types'

export interface AuditListParams {
  user?: number
  action?: string
  model?: string
  date_from?: string
  date_to?: string
}

export const auditApi = {
  list: (params?: AuditListParams) =>
    api.get<AuditLogEntry[]>('/audit/', { params }),
}
