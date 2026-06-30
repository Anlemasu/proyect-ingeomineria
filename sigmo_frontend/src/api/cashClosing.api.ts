import api from './axiosInstance'
import type { DailySummary, TodaySummary } from '@/types'

export const cashClosingApi = {
  today: () =>
    api.get<TodaySummary>('/cash-closing/today/'),

  close: () =>
    api.post<DailySummary>('/cash-closing/close/'),

  list: () =>
    api.get<DailySummary[]>('/cash-closing/'),
}
