import api from './axiosInstance'
import type { Vehicle, VehicleType } from '@/types'

export const vehicleTypesApi = {
  list: () =>
    api.get<VehicleType[]>('/masters/vehicle-types/'),

  get: (id: number) =>
    api.get<VehicleType>(`/masters/vehicle-types/${id}/`),

  create: (data: { name: string; capacity: number; description?: string }) =>
    api.post<VehicleType>('/masters/vehicle-types/', data),

  update: (id: number, data: Partial<VehicleType>) =>
    api.patch<VehicleType>(`/masters/vehicle-types/${id}/`, data),
}

export const vehiclesApi = {
  list: (params?: { plaque?: string }) =>
    api.get<Vehicle[]>('/masters/vehicles/', { params }),

  create: (data: { plaque: string; vehicle_type: number; dumper?: number | null }) =>
    api.post<Vehicle>('/masters/vehicles/', data),
}
