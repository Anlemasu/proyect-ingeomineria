import api from './axiosInstance'
import type { Advance, AdvanceBalance, AdvanceCorrectValuePreview, AdvanceCorrectValueResult } from '@/types'

export const advancesApi = {
  list: (params?: { client?: number }) =>
    api.get<Advance[]>('/advances/', { params }),

  create: (data: {
    client: number
    value: number
    transfer_num: number
    date: string
    trips_quantity?: number
    proforma_number?: number
    observations?: string
  }) => api.post<Advance>('/advances/', data),

  update: (id: number, data: {
    value?: number
    transfer_num?: number
    date?: string
    proforma_number?: number | null
    observations?: string | null
  }) => api.patch<Advance>(`/advances/${id}/`, data),

  balance: (clientId: number) =>
    api.get<AdvanceBalance>(`/advances/balance/${clientId}/`),

  // { [client_id]: total deuda pendiente sin liquidar } para todos los
  // clientes en una sola consulta (usado en el resumen general de Estado de
  // Cuenta, para no pedir el balance cliente por cliente).
  pendingDebtsSummary: () =>
    api.get<Record<string, string>>('/advances/pending-debts/'),

  // Simula (sin escribir nada) el impacto de corregir `value` — qué viajes
  // quedarían como deuda pendiente si la reducción deja el saldo negativo.
  previewCorrectValue: (id: number, correctValue: number) =>
    api.post<AdvanceCorrectValuePreview>(`/advances/${id}/correct-value/preview/`, {
      correct_value: correctValue,
    }),

  // Única forma real de cambiar `value` una vez el anticipo tiene
  // movimientos (siempre, desde que se crea) — el PATCH genérico (`update`
  // arriba) lo bloquea de plano. Ver correct_active_advance_value en el
  // backend.
  correctValue: (id: number, data: { correct_value: number; justification: string }) =>
    api.post<AdvanceCorrectValueResult>(`/advances/${id}/correct-value/`, data),
}
