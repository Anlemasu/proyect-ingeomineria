import api from './axiosInstance'
import type { OriginSite } from '@/types'

export const originsApi = {
  list: () =>
    api.get<OriginSite[]>('/masters/origin-sites/'),

  get: (id: number) =>
    api.get<OriginSite>(`/masters/origin-sites/${id}/`),

  create: (data: { name: string }) =>
    api.post<OriginSite>('/masters/origin-sites/', data),

  update: (id: number, data: Partial<OriginSite>) =>
    api.patch<OriginSite>(`/masters/origin-sites/${id}/`, data),
}
