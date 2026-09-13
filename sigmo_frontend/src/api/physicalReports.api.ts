import api from './axiosInstance'
import type { PhysicalReportSummary, PhysicalReportDetail, PhysicalCountEntry, PhysicalCountClosure, BulkEntryResult } from '@/types'

export const physicalReportsApi = {
  // Anticipos abiertos con viajes pendientes por confirmar (vista principal).
  // `date` calcula 'cumulative_entered'/'remaining' a esa fecha y agrega
  // 'day_count'/'day_editable' (para el campo inline de la tabla).
  list: (params?: { date?: string }) =>
    api.get<PhysicalReportSummary[]>('/physical-reports/', { params }),

  // Anticipos con el conteo físico cerrado (vista "Cerrados", para reabrir).
  listClosed: (params?: { date?: string }) =>
    api.get<PhysicalReportSummary[]>('/physical-reports/closed/', { params }),

  detail: (advanceId: number, params?: { date?: string }) =>
    api.get<PhysicalReportDetail>(`/physical-reports/${advanceId}/`, { params }),

  registerEntry: (advanceId: number, data: { date: string; count: number; justification?: string }) =>
    api.post<PhysicalCountEntry>(`/physical-reports/${advanceId}/entries/`, data),

  // Botón único "Guardar todos" de la tabla principal: una fecha, varios
  // anticipos. Cada fila se procesa independiente — ver BulkEntryResult.
  bulkRegisterEntries: (date: string, entries: { advance: number; count: number }[]) =>
    api.post<BulkEntryResult[]>('/physical-reports/bulk-entries/', { date, entries }),

  setQuota: (advanceId: number, quantity: number) =>
    api.post<{ advance: number; expected_trips_quantity: number }>(
      `/physical-reports/${advanceId}/quota/`, { quantity },
    ),

  close: (advanceId: number) =>
    api.post<PhysicalCountClosure>(`/physical-reports/${advanceId}/close/`),

  undoClose: (advanceId: number) =>
    api.post<PhysicalCountClosure>(`/physical-reports/${advanceId}/undo-close/`),

  reopen: (advanceId: number, justification: string) =>
    api.post<PhysicalCountClosure>(`/physical-reports/${advanceId}/reopen/`, { justification }),
}
