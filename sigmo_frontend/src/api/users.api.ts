import api from "./axiosInstance";
import type { User, UserRole } from '@/types'

export interface CreateUserPayload {
  name: string
  email: string
  username: string
  password: string
  role: UserRole
}

export interface UpdateUserPayload {
  name?: string
  email?: string
  username?: string
  state?: boolean
}

export interface ResetPasswordPayload {
  new_password: string
}

export const usersApi = {
  list: () => api.get<User[]>('/users/'),
  create: (data: CreateUserPayload) => api.post<User>('/users/', data),
  detail: (id: number) => api.get<User>(`/users/${id}/`),
  update: (id: number, data: UpdateUserPayload) => api.patch<User>(`/users/${id}/`, data),
  resetPassword: (id: number, data: ResetPasswordPayload) =>
    api.post<{ message: string }>(`/users/${id}/reset-password/`, data),
}
