import api from './axiosInstance'
import type { Invoice } from '@/types'

// 8B.6: crear la factura y asociarle los viajes seleccionados ahora es UNA
// sola request (antes era un POST /invoices/ + N PATCH /trips/<id>/ en
// paralelo, sin ninguna transacción en común entre ellos — si uno de los
// PATCH fallaba a mitad de camino, quedaba una factura con solo un
// subconjunto de viajes asociados). `create` sigue aceptando solo
// `number` para el caso de uso que no factura viajes (ej. la factura
// "SIN FACTURA" de DashboardPage.vue).
interface InvoiceAssignmentResponse extends Invoice {
  trip_ids_assigned: number[]
}

export const invoicesApi = {
  list: () => api.get<Invoice[]>('/invoices/'),
  create: (data: { number: string; trip_ids?: number[] }) =>
    api.post<InvoiceAssignmentResponse>('/invoices/', data),
  assignTripsToExistingInvoice: (data: { invoice_id: number; trip_ids: number[] }) =>
    api.post<InvoiceAssignmentResponse>('/invoices/', data),
  detail: (id: number) => api.get<Invoice>(`/invoices/${id}/`),
}
