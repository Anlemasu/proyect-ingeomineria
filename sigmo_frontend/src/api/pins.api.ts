import api from './axiosInstance'
import type { PinsDumper, ImportResult } from '@/types'

export const pinsApi = {
  list: (params?: { plaque?: string }) =>
    api.get<PinsDumper[]>('/masters/pins/', { params }),

  create: (data: Partial<PinsDumper>) =>
    api.post<PinsDumper>('/masters/pins/', data),

  update: (id: number, data: Partial<PinsDumper>) =>
    api.patch<PinsDumper>(`/masters/pins/${id}/`, data),

  importFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ImportResult>('/masters/pins/import/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
