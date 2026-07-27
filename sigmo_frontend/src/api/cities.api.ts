import api from './axiosInstance'
import type { City } from '@/types'

export const citiesApi = {
  list: () =>
    api.get<City[]>('/masters/cities/'),

  get: (id: number) =>
    api.get<City>(`/masters/cities/${id}/`),

  create: (data: { name: string }) =>
    api.post<City>('/masters/cities/', data),

  update: (id: number, data: Partial<City>) =>
    api.patch<City>(`/masters/cities/${id}/`, data),
}
