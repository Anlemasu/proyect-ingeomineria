import api from './axiosInstance'
import type { Certificate } from '@/types'

// Mismo patrón que invoices.api.ts: crear el certificado y asociarle los
// viajes seleccionados es una sola request atómica (ver 8B.6 en el backend).
interface CertificateAssignmentResponse extends Certificate {
  trip_ids_assigned: number[]
}

export const certificatesApi = {
  list: () => api.get<Certificate[]>('/certificates/'),
  create: (data: { number: string; trip_ids?: number[] }) =>
    api.post<CertificateAssignmentResponse>('/certificates/', data),
  assignTripsToExistingCertificate: (data: { certificate_id: number; trip_ids: number[] }) =>
    api.post<CertificateAssignmentResponse>('/certificates/', data),
  detail: (id: number) => api.get<Certificate>(`/certificates/${id}/`),
}
