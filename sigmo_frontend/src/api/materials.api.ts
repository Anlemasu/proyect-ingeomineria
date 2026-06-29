import api from './axiosInstance'
import type { MaterialType } from '@/types'

export const materialsApi = {
  list: () =>
    api.get<MaterialType[]>('/masters/material-types/'),

  get: (id: number) =>
    api.get<MaterialType>(`/masters/material-types/${id}/`),

  create: (data: { name: string; description?: string }) =>
    api.post<MaterialType>('/masters/material-types/', data),

  update: (id: number, data: Partial<MaterialType>) =>
    api.patch<MaterialType>(`/masters/material-types/${id}/`, data),
}
