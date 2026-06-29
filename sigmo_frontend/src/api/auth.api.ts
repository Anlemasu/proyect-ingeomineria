import api from './axiosInstance'
import type { LoginResponse } from '@/types'

export const authApi = {
  login: (username: string, password: string) =>
    api.post<LoginResponse>('/users/login/', { username, password }),

  logout: () =>
    api.post('/users/logout/'),

  changePassword: (current_password: string, new_password: string, confirm_password: string) =>
    api.post('/users/change-password/', { current_password, new_password, confirm_password }),
}
