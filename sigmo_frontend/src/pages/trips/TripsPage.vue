<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { toast } from 'vue-sonner'

import {
  Eye, RefreshCw, Printer, AlertTriangle,
  CheckCircle, Pencil, Info,
} from 'lucide-vue-next'

import PageHeader       from '@/components/shared/PageHeader.vue'
import SearchableSelect from '@/components/shared/SearchableSelect.vue'
import CurrencyInput    from '@/components/shared/CurrencyInput.vue'

import { clientsApi }        from '@/api/clients.api'
import { originsApi }        from '@/api/origins.api'
import { materialsApi }      from '@/api/materials.api'
import { vehicleTypesApi, vehiclesApi } from '@/api/vehicles.api'
import { paymentMethodsApi } from '@/api/paymentMethods.api'
import { advancesApi }       from '@/api/advances.api'
import { tariffsApi }        from '@/api/tariffs.api'
import { pinsApi }           from '@/api/pins.api'
import { tripsApi }          from '@/api/trips.api'

import { useAuthStore }       from '@/stores/auth.store'
import { todayBogota, formatDate } from '@/utils/formatDate'
import { formatCurrency }     from '@/utils/formatCurrency'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { printVoucher }       from '@/utils/printVoucher'
import type { Trip } from '@/types'

// ── Auth ───────────────────────────────────────────────────────────────────────
const authStore   = useAuthStore()
const queryClient = useQueryClient()
const isSuperuser   = computed(() => authStore.user?.role === 'superuser')
const canChangeDate = computed(() =>
  authStore.user?.role === 'superuser' || authStore.user?.role === 'commercial_admin'
)

// ── Queries para selects del formulario ───────────────────────────────────────
const { data: clientsData } = useQuery({
  queryKey: ['clients'],
  queryFn: () => clientsApi.list({ state: 'true' }).then(r => r.data),
})
const { data: originsData, refetch: refetchOrigins } = useQuery({
  queryKey: ['origins'],
  queryFn: () => originsApi.list().then(r => r.data),
})
const { data: materialsData } = useQuery({
  queryKey: ['materials'],
  queryFn: () => materialsApi.list().then(r => r.data),
})
const { data: vehicleTypesData } = useQuery({
  queryKey: ['vehicle-types'],
  queryFn: () => vehicleTypesApi.list().then(r => r.data),
})
const { data: paymentsData } = useQuery({
  queryKey: ['payments'],
  queryFn: () => paymentMethodsApi.list().then(r => r.data),
})

const clientOptions      = computed(() => (clientsData.value ?? []).filter(c => c.state).map(c => ({ id: c.id, name: c.name })))
const originOptions      = computed(() => (originsData.value ?? []).filter(o => o.state).map(o => ({ id: o.id, name: o.name })))
const materialOptions    = computed(() => (materialsData.value ?? []).filter(m => m.state).map(m => ({ id: m.id, name: m.name })))
const vehicleTypeOptions = computed(() => (vehicleTypesData.value ?? []).filter(v => v.state).map(v => ({ id: v.id, name: v.name })))
const paymentList        = computed(() => (paymentsData.value ?? []).filter(p => p.state))

// ── Query viajes de hoy ────────────────────────────────────────────────────────
const today = todayBogota()

const { data: todayTripsData, isLoading: tripsLoading, refetch: refetchTrips } = useQuery({
  queryKey: ['trips', 'today'],
  queryFn: () => tripsApi.list({ date: today }).then(r => r.data),
  refetchInterval: 30_000,
})

const todayTrips  = computed(() => todayTripsData.value ?? [])
const totalActive = computed(() => todayTrips.value.filter(t => t.state).length)
const totalValue  = computed(() =>
  todayTrips.value.filter(t => t.state).reduce((sum, t) => sum + parseFloat(t.value), 0),
)

// ── VeeValidate + Zod ─────────────────────────────────────────────────────────
const schema = toTypedSchema(z.object({
  client:             z.number({ message: 'El cliente es requerido' }),
  origin_site:        z.number({ message: 'El origen es requerido' }),
  material_type:      z.number({ message: 'El tipo de material es requerido' }),
  vehicle_type:       z.number({ message: 'El tipo de vehículo es requerido' }),
  payment:            z.number({ message: 'El medio de pago es requerido' }),
  advance:            z.number().nullable().optional(),
  value:              z.number({ message: 'El valor es requerido' }).positive('Debe ser mayor a cero'),
  date:               z.string().min(1, 'La fecha es requerida'),
  extern_voucher_num: z.string().max(20).optional(),
  observations:       z.string().max(500).optional(),
}))

const { handleSubmit, isSubmitting, resetForm, setFieldValue } = useForm({
  validationSchema: schema,
  initialValues: {
    client:             undefined as number | undefined,
    origin_site:        undefined as number | undefined,
    material_type:      undefined as number | undefined,
    vehicle_type:       undefined as number | undefined,
    payment:            undefined as number | undefined,
    advance:            null as number | null,
    value:              undefined as number | undefined,
    date:               today,
    extern_voucher_num: '',
    observations:       '',
  },
})

// ── Bindings reactivos de campos ──────────────────────────────────────────────
const { value: clientId,      errorMessage: clientError }      = useField<number | undefined>('client')
const { value: originId,      errorMessage: originError }      = useField<number | undefined>('origin_site')
const { value: materialId,    errorMessage: materialError }    = useField<number | undefined>('material_type')
const { value: vehicleTypeId, errorMessage: vehicleTypeError } = useField<number | undefined>('vehicle_type')
const { value: paymentId,     errorMessage: paymentError }     = useField<number | undefined>('payment')
const { value: tripValue,     errorMessage: valueError }       = useField<number | undefined>('value')
const { value: tripDate,      errorMessage: dateError }        = useField<string>('date')
const { value: externVoucher, errorMessage: externError }      = useField<string | undefined>('extern_voucher_num')
const { value: observations,  errorMessage: observationsError }= useField<string | undefined>('observations')

// ── Estado placa — solo lookup de PIN (Fix: placa nunca bloquea el formulario) ──
// El vehículo (Vehicle.id) se resuelve en onSubmit:
//   1. GET /api/masters/vehicles/?plaque=PLACA — si existe usamos su id
//   2. Si no, POST /api/masters/vehicles/ — requiere permisos de maestros;
//      para cashier el backend devuelve 403 y se muestra toast, no se bloquea visualmente
const plateInput = ref('')
const pinDisplay = ref('')   // Fix 4: '0' cuando placa ingresada pero sin PIN registrado
const pinFound   = ref(false)
const pinLoading = ref(false)
const pinTimer   = ref<ReturnType<typeof setTimeout> | null>(null)

function onPlateInput(e: Event) {
  const raw = (e.target as HTMLInputElement).value
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
    .slice(0, 6)
  plateInput.value = raw
  ;(e.target as HTMLInputElement).value = raw

  if (pinTimer.value) clearTimeout(pinTimer.value)

  if (!raw) {
    pinDisplay.value = ''
    pinFound.value   = false
    return
  }
  pinTimer.value = setTimeout(() => lookupPin(raw), 400)
}

async function lookupPin(plate: string) {
  pinLoading.value = true
  pinFound.value   = false
  pinDisplay.value = ''
  try {
    const res   = await pinsApi.list({ plaque: plate })
    const exact = res.data.find(p => p.plaque === plate && p.state)
    if (exact) {
      pinDisplay.value = exact.ambiental_pin
      pinFound.value   = true
    } else {
      // Fix 4: "0" cuando no hay PIN registrado para esta placa
      pinDisplay.value = '0'
      pinFound.value   = false
    }
  } finally {
    pinLoading.value = false
  }
}

// ── Tarifa automática ─────────────────────────────────────────────────────────
type TariffMode = 'client' | 'general' | 'manual' | null
const tariffMode    = ref<TariffMode>(null)
const tariffLoading = ref(false)
const valueEditable = ref(false)

async function fetchTariff() {
  if (!clientId.value || !vehicleTypeId.value) return
  tariffLoading.value = true
  valueEditable.value = false
  try {
    const clientRes = await tariffsApi.list({
      client:       clientId.value,
      vehicle_type: vehicleTypeId.value,
      state:        true,
    })
    if (clientRes.data.length > 0) {
      setFieldValue('value', parseFloat(clientRes.data[0].value))
      tariffMode.value = 'client'
      return
    }
    const generalRes    = await tariffsApi.list({ vehicle_type: vehicleTypeId.value, state: true })
    const generalTariff = generalRes.data.find(t => !t.client)
    if (generalTariff) {
      setFieldValue('value', parseFloat(generalTariff.value))
      tariffMode.value = 'general'
      return
    }
    setFieldValue('value', undefined)
    tariffMode.value    = 'manual'
    valueEditable.value = true
  } finally {
    tariffLoading.value = false
  }
}

watch([clientId, vehicleTypeId], ([c, v]) => {
  if (c && v) fetchTariff()
  else { tariffMode.value = null; valueEditable.value = false }
})

// ── Saldo total de anticipos del cliente ──────────────────────────────────────
const { data: clientBalanceData } = useQuery({
  queryKey: computed(() => ['advance-balance', clientId.value]),
  queryFn: () => clientId.value
    ? advancesApi.balance(clientId.value).then(r => r.data)
    : Promise.resolve(null),
  enabled: computed(() => !!clientId.value),
})
const clientBalance = computed(() => clientBalanceData.value?.balance ?? null)

// ── Pago con anticipo — Fix 3: auto-selección, sin dropdown ───────────────────
// RF-31: un cliente solo tiene un anticipo activo (saldo > 0) a la vez.
// El anticipo se selecciona automáticamente; el usuario nunca lo elige manualmente.
const selectedPayment  = computed(() => paymentList.value.find(p => p.id === paymentId.value) ?? null)
const isAdvancePayment = computed(() => selectedPayment.value?.is_advance === true)

const { data: advancesData } = useQuery({
  queryKey: computed(() => ['advances', clientId.value]),
  queryFn: () => clientId.value
    ? advancesApi.list({ client: clientId.value }).then(r => r.data)
    : Promise.resolve([]),
  enabled: computed(() => !!clientId.value),
})

// El anticipo activo es el primero con saldo > 0
const activeAdvance   = computed(() =>
  (advancesData.value ?? []).find(a => (a.available_balance ?? 0) > 0) ?? null
)
const advanceBalance  = computed(() => activeAdvance.value?.available_balance ?? null)
const hasActiveAdvance = computed(() => activeAdvance.value !== null)

// Cuando el pago cambia a tipo anticipo (o el anticipo activo cambia), auto-asignar
watch([activeAdvance, isAdvancePayment], ([advance, isAdvance]) => {
  if (isAdvance) {
    setFieldValue('advance', advance?.id ?? null)
  } else {
    setFieldValue('advance', null)
  }
})

watch(paymentId, () => {
  forceSubmit.value   = false
  justification.value = ''
})

const balanceSufficient = computed(() => {
  if (!isAdvancePayment.value) return true
  if (!hasActiveAdvance.value) return false            // sin anticipo disponible → bloquear
  return (advanceBalance.value ?? 0) >= (tripValue.value ?? 0)
})

const forceSubmit   = ref(false)
const justification = ref('')

const canSubmit = computed(() => {
  if (isAdvancePayment.value) {
    if (!hasActiveAdvance.value) return false          // sin anticipo, siempre bloqueado
    if (!balanceSufficient.value) {
      return isSuperuser.value && forceSubmit.value && justification.value.trim().length > 0
    }
  }
  return true
})

// ── Modal crear origen ────────────────────────────────────────────────────────
const showCreateOrigin    = ref(false)
const newOriginName       = ref('')
const createOriginLoading = ref(false)

async function createOrigin() {
  const name = newOriginName.value.trim()
  if (!name) return
  createOriginLoading.value = true
  try {
    const res = await originsApi.create({ name })
    await refetchOrigins()
    setFieldValue('origin_site', res.data.id)
    showCreateOrigin.value = false
    newOriginName.value    = ''
    toast.success(`Origen "${name}" creado`)
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  } finally {
    createOriginLoading.value = false
  }
}

// ── Drawer detalle ────────────────────────────────────────────────────────────
const detailTrip = ref<Trip | null>(null)

// ── Envío del formulario ──────────────────────────────────────────────────────
const onSubmit = handleSubmit(async (values) => {
  const plate = plateInput.value.trim()
  if (!plate) {
    toast.error('Ingrese la placa del vehículo')
    return
  }
  if (!canSubmit.value) return

  // Resolver Vehicle.id: buscar por placa exacta o crear si no existe.
  // Si el rol no tiene permiso para crear vehículos (cashier → 403), se muestra toast.
  let vehicleId: number
  try {
    const vehiclesRes = await vehiclesApi.list({ plaque: plate })
    const exact       = vehiclesRes.data.find(v => v.plaque === plate)
    if (exact) {
      vehicleId = exact.id
    } else {
      const newVehicle = await vehiclesApi.create({
        plaque:       plate,
        vehicle_type: values.vehicle_type,
      })
      vehicleId = newVehicle.data.id
    }
  } catch {
    toast.error('Vehículo no registrado y sin permisos para crearlo. Contacte al administrador.')
    return
  }

  try {
    const payload = {
      client:             values.client,
      origin_site:        values.origin_site,
      material_type:      values.material_type,
      vehicle:            vehicleId,
      payment:            values.payment,
      advance:            values.advance ?? null,
      value:              values.value,
      date:               values.date,
      extern_voucher_num: values.extern_voucher_num?.trim() || null,
      observations:       values.observations?.trim() || null,
      ...(forceSubmit.value && justification.value.trim()
        ? { force: true, justification: justification.value.trim() }
        : {}),
    }

    const res  = await tripsApi.create(payload)
    const trip = res.data

    toast.success(`Viaje #${trip.voucher_num} registrado correctamente`)

    // PIN viene del formulario (pinDisplay), no del response backend (puede omitir dumper_detail)
    printVoucher(trip, pinDisplay.value || '0', values.observations?.trim() || null)

    queryClient.invalidateQueries({ queryKey: ['trips', 'today'] })
    queryClient.invalidateQueries({ queryKey: ['advance-balance', values.client] })
    queryClient.invalidateQueries({ queryKey: ['advances', values.client] })
    queryClient.invalidateQueries({ queryKey: ['cash-closing-today'] })

    resetForm()

    plateInput.value    = ''
    pinDisplay.value    = ''
    pinFound.value      = false
    tariffMode.value    = null
    valueEditable.value = false
    forceSubmit.value   = false
    justification.value = ''

  } catch (err: unknown) {
    const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data
    if (data?.saldo_disponible !== undefined) {
      // El panel de saldo ya muestra la información — no duplicar con toast
    } else {
      toast.error(getApiErrorMessage(err))
    }
  }
})
</script>

<template>
  <div class="space-y-6">
    <PageHeader title="Registro de Viajes" subtitle="Módulo principal de operación diaria" />

    <!-- ── FORMULARIO DE REGISTRO ─────────────────────────────────────────── -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm">
      <div class="px-6 py-4 border-b border-gray-100">
        <h2 class="text-sm font-semibold text-gray-800">Nuevo Viaje</h2>
      </div>

      <form @submit.prevent="onSubmit" class="p-6">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-5">

          <!-- 1. Cliente -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Cliente <span class="text-red-500">*</span>
            </label>
            <SearchableSelect
              :options="clientOptions"
              v-model="clientId"
              placeholder="Buscar cliente..."
              :clearable="true"
            />
            <p v-if="clientError" class="mt-1 text-xs text-red-500">{{ clientError }}</p>
            <div v-if="clientId && clientBalance !== null" class="mt-1.5">
              <span
                class="text-xs font-medium"
                :class="clientBalance > 0 ? 'text-green-600' : 'text-red-500'"
              >
                Saldo disponible: {{ formatCurrency(clientBalance) }}
              </span>
            </div>
          </div>

          <!-- 2. Origen -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Origen del material <span class="text-red-500">*</span>
            </label>
            <SearchableSelect
              :options="originOptions"
              v-model="originId"
              placeholder="Buscar origen..."
              extra-action-label="Crear origen"
              @extra-action="showCreateOrigin = true"
            />
            <p v-if="originError" class="mt-1 text-xs text-red-500">{{ originError }}</p>
          </div>

          <!-- Fecha -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Fecha <span class="text-red-500">*</span>
            </label>
            <input
              v-model="tripDate"
              type="date"
              :readonly="!canChangeDate"
              class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
              :class="canChangeDate
                ? 'border-gray-300 bg-white'
                : 'border-gray-200 bg-gray-50 text-gray-600 cursor-default'"
            />
            <p v-if="!canChangeDate" class="mt-1 text-xs text-gray-400">Solo el día actual</p>
            <p v-if="dateError" class="mt-1 text-xs text-red-500">{{ dateError }}</p>
          </div>

          <!-- 3. Placa -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Placa del vehículo <span class="text-red-500">*</span>
            </label>
            <div class="relative">
              <input
                :value="plateInput"
                @input="onPlateInput"
                type="text"
                maxlength="6"
                placeholder="ABC123"
                class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 font-mono uppercase tracking-widest"
              />
              <div v-if="pinLoading" class="absolute right-3 top-2.5">
                <RefreshCw class="w-4 h-4 text-gray-400 animate-spin" />
              </div>
            </div>
          </div>

          <!-- 4. PIN Ambiental (informativo, auto-completado) -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">PIN Ambiental</label>
            <input
              :value="pinDisplay"
              type="text"
              readonly
              placeholder="Auto-completado por placa"
              class="w-full px-3 py-2 text-sm border border-gray-200 rounded-md bg-gray-50 text-gray-600 cursor-default font-mono"
            />
            <div v-if="plateInput && !pinLoading" class="mt-1.5">
              <span v-if="pinFound" class="inline-flex items-center gap-1.5 text-xs text-green-600 font-medium">
                <CheckCircle class="w-3.5 h-3.5" /> PIN vigente
              </span>
              <span v-else class="inline-flex items-center gap-1.5 text-xs text-amber-500 font-medium">
                <AlertTriangle class="w-3.5 h-3.5" /> Sin PIN registrado
              </span>
            </div>
          </div>

          <!-- 5. Tipo de material -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Tipo de material <span class="text-red-500">*</span>
            </label>
            <SearchableSelect
              :options="materialOptions"
              v-model="materialId"
              placeholder="Buscar material..."
            />
            <p v-if="materialError" class="mt-1 text-xs text-red-500">{{ materialError }}</p>
          </div>

          <!-- 6. Tipo de vehículo — siempre dropdown manual -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Tipo de vehículo <span class="text-red-500">*</span>
            </label>
            <SearchableSelect
              :options="vehicleTypeOptions"
              v-model="vehicleTypeId"
              placeholder="Buscar tipo de vehículo..."
            />
            <p v-if="vehicleTypeError" class="mt-1 text-xs text-red-500">{{ vehicleTypeError }}</p>
          </div>

          <!-- 7. Valor del servicio -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Valor del servicio <span class="text-red-500">*</span>
            </label>
            <div class="flex items-center gap-2">
              <CurrencyInput
                v-model="tripValue"
                :readonly="(tariffMode === 'client' || tariffMode === 'general') && !valueEditable"
                :placeholder="tariffMode === 'manual' || tariffMode === null ? 'Ingrese el valor' : ''"
              />
              <button
                v-if="tariffMode === 'client' || tariffMode === 'general'"
                type="button"
                @click="valueEditable = !valueEditable"
                class="shrink-0 p-1.5 rounded text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
                :title="valueEditable ? 'Usar tarifa' : 'Editar manualmente'"
              >
                <Pencil class="w-3.5 h-3.5" />
              </button>
            </div>
            <div class="mt-1.5 h-4">
              <span v-if="tariffLoading" class="text-xs text-gray-400">Buscando tarifa...</span>
              <span v-else-if="tariffMode === 'client'" class="inline-flex items-center gap-1 text-xs text-gold-700 font-medium">
                <Info class="w-3 h-3" /> Tarifa del cliente
              </span>
              <span v-else-if="tariffMode === 'general'" class="inline-flex items-center gap-1 text-xs text-gray-500 font-medium">
                <Info class="w-3 h-3" /> Tarifa general
              </span>
              <span v-else-if="tariffMode === 'manual'" class="text-xs text-amber-500 font-medium">Ingreso manual</span>
            </div>
            <p v-if="valueError" class="mt-1 text-xs text-red-500">{{ valueError }}</p>
          </div>

          <!-- 8. Medio de pago -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">
              Medio de pago <span class="text-red-500">*</span>
            </label>
            <SearchableSelect
              :options="paymentList"
              v-model="paymentId"
              placeholder="Buscar medio de pago..."
            />
            <p v-if="paymentError" class="mt-1 text-xs text-red-500">{{ paymentError }}</p>
          </div>

          <!-- 9. Vale externo -->
          <div>
            <label class="block text-xs font-medium text-gray-700 mb-1.5">N° Vale externo</label>
            <input
              v-model="externVoucher"
              type="text"
              maxlength="20"
              placeholder="Opcional"
              class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
            />
            <p v-if="externError" class="mt-1 text-xs text-red-500">{{ externError }}</p>
          </div>

          <!-- 10. Observaciones -->
          <div class="lg:col-span-2">
            <label class="block text-xs font-medium text-gray-700 mb-1.5">Observaciones</label>
            <textarea
              v-model="observations"
              rows="2"
              maxlength="500"
              placeholder="Observaciones opcionales (máx. 500 caracteres)"
              class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 resize-none"
            />
            <p v-if="observationsError" class="mt-1 text-xs text-red-500">{{ observationsError }}</p>
          </div>
        </div>

        <!-- Fix 3: panel de anticipo — info automática, sin dropdown -->
        <div v-if="isAdvancePayment" class="mt-5">
          <!-- Sin cliente seleccionado -->
          <div
            v-if="!clientId"
            class="flex items-center gap-2 px-4 py-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-sm"
          >
            <AlertTriangle class="w-4 h-4 shrink-0" />
            <span>Selecciona un cliente para verificar el anticipo disponible</span>
          </div>

          <!-- Sin anticipo activo -->
          <div
            v-else-if="!hasActiveAdvance"
            class="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm"
          >
            <AlertTriangle class="w-4 h-4 shrink-0" />
            <span>Sin anticipo disponible para este cliente. No se puede registrar con anticipo.</span>
          </div>

          <!-- Anticipo activo con saldo suficiente -->
          <div
            v-else-if="balanceSufficient"
            class="flex items-center gap-2 px-4 py-3 rounded-lg bg-green-50 border border-green-200 text-green-700 text-sm"
          >
            <CheckCircle class="w-4 h-4 shrink-0" />
            <span>
              Anticipo activo: <strong>#{{ activeAdvance!.id }}</strong> —
              Saldo: <strong>{{ formatCurrency(advanceBalance ?? 0) }}</strong>
            </span>
          </div>

          <!-- Anticipo activo con saldo insuficiente -->
          <div v-else class="px-4 py-3 rounded-lg bg-red-50 border border-red-200">
            <div class="flex items-start gap-2 text-red-700 text-sm">
              <AlertTriangle class="w-4 h-4 shrink-0 mt-0.5" />
              <div class="space-y-1">
                <p class="font-semibold">Saldo insuficiente — Anticipo #{{ activeAdvance!.id }}</p>
                <p>Saldo disponible: <strong>{{ formatCurrency(advanceBalance ?? 0) }}</strong></p>
                <p>Valor del viaje: <strong>{{ formatCurrency(tripValue ?? 0) }}</strong></p>
                <p>Diferencia: <strong>{{ formatCurrency((tripValue ?? 0) - (advanceBalance ?? 0)) }}</strong></p>
              </div>
            </div>
            <!-- Override exclusivo para superusuario -->
            <div v-if="isSuperuser" class="mt-3 pt-3 border-t border-red-200">
              <label class="flex items-center gap-2 text-sm text-red-700 cursor-pointer select-none">
                <input v-model="forceSubmit" type="checkbox" class="rounded border-red-300" />
                <span class="font-medium">Forzar registro (requiere justificación)</span>
              </label>
              <textarea
                v-if="forceSubmit"
                v-model="justification"
                rows="2"
                placeholder="Justificación obligatoria..."
                class="mt-2 w-full px-3 py-2 text-sm border border-red-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
              />
            </div>
          </div>
        </div>

        <!-- Botón enviar -->
        <div class="mt-6 flex items-center justify-end pt-4 border-t border-gray-100">
          <button
            type="submit"
            :disabled="isSubmitting || !canSubmit"
            class="px-6 py-2.5 bg-gold-500 text-stone-900 text-sm font-semibold rounded-lg hover:bg-gold-600 active:bg-gold-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 transition-colors shadow-sm"
          >
            <RefreshCw v-if="isSubmitting" class="w-4 h-4 animate-spin" />
            {{ isSubmitting ? 'Registrando...' : 'Registrar Viaje' }}
          </button>
        </div>
      </form>
    </div>

    <!-- Modal crear origen -->
    <Teleport to="body">
      <div v-if="showCreateOrigin" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
        <div class="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm">
          <h3 class="text-sm font-semibold text-gray-800 mb-4">Nuevo origen de material</h3>
          <input
            v-model="newOriginName"
            type="text"
            placeholder="Nombre del origen"
            class="w-full px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
            @keydown.enter.prevent="createOrigin"
            autofocus
          />
          <div class="mt-4 flex gap-2 justify-end">
            <button
              type="button"
              @click="showCreateOrigin = false; newOriginName = ''"
              class="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 rounded-lg hover:bg-gray-100"
            >Cancelar</button>
            <button
              type="button"
              @click="createOrigin"
              :disabled="!newOriginName.trim() || createOriginLoading"
              class="px-4 py-2 bg-gold-500 text-stone-900 text-sm font-medium rounded-lg hover:bg-gold-600 disabled:opacity-50"
            >
              {{ createOriginLoading ? 'Creando...' : 'Crear origen' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── TABLA VIAJES DE HOY ────────────────────────────────────────────── -->
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 class="text-sm font-semibold text-gray-800">Viajes de hoy — {{ today }}</h2>
          <p class="text-xs text-gray-500 mt-0.5">Actualización automática cada 30 segundos</p>
        </div>
        <button
          type="button"
          @click="refetchTrips()"
          class="p-2 rounded-lg text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
          title="Actualizar ahora"
        >
          <RefreshCw class="w-4 h-4" :class="tripsLoading ? 'animate-spin text-gold-600' : ''" />
        </button>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-gray-50 border-b border-gray-100">
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">N° Vale</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Fecha</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Cliente</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Placa</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">PIN</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Material</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Vehículo</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Valor</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Pago</th>
              <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Acciones</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-if="tripsLoading && todayTrips.length === 0">
              <td colspan="10" class="px-4 py-10 text-center text-xs text-gray-400">
                <RefreshCw class="w-4 h-4 animate-spin inline-block mr-2" />Cargando...
              </td>
            </tr>
            <tr v-else-if="todayTrips.length === 0">
              <td colspan="10" class="px-4 py-10 text-center text-xs text-gray-400">
                Sin viajes registrados hoy
              </td>
            </tr>
            <tr
              v-for="trip in todayTrips"
              :key="trip.id"
              class="hover:bg-gray-50 transition-colors"
              :class="!trip.state ? 'opacity-40' : ''"
            >
              <td class="px-4 py-3">
                <span class="font-mono font-bold text-gold-800">#{{ trip.voucher_num }}</span>
              </td>
              <td class="px-4 py-3 text-gray-600 text-xs">{{ formatDate(trip.date_register) }}</td>
              <td class="px-4 py-3 font-medium text-gray-900 max-w-[160px] truncate">
                {{ trip.client_detail?.name ?? '—' }}
              </td>
              <td class="px-4 py-3 font-mono text-gray-800 tracking-wider">{{ trip.vehicle_detail?.plaque ?? '—' }}</td>
              <td class="px-4 py-3 text-gray-500 text-xs">{{ trip.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0' }}</td>
              <td class="px-4 py-3 text-gray-700 text-xs">{{ trip.material_type_detail?.name ?? '—' }}</td>
              <td class="px-4 py-3 text-gray-700 text-xs">{{ trip.vehicle_detail?.vehicle_type_detail?.name ?? '—' }}</td>
              <td class="px-4 py-3 text-right font-semibold text-gray-900">{{ formatCurrency(trip.value) }}</td>
              <td class="px-4 py-3 text-gray-600 text-xs">{{ trip.payment_detail?.name ?? '—' }}</td>
              <td class="px-4 py-3">
                <div class="flex items-center gap-0.5">
                  <button
                    type="button"
                    @click="detailTrip = trip"
                    class="p-1.5 rounded text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
                    title="Ver detalle"
                  >
                    <Eye class="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    @click="printVoucher(trip, trip.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0', null)"
                    class="p-1.5 rounded text-gray-400 hover:text-gold-700 hover:bg-gold-50 transition-colors"
                    title="Reimprimir vale"
                  >
                    <Printer class="w-4 h-4" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
          <tfoot v-if="todayTrips.length > 0">
            <tr class="bg-gray-50 border-t-2 border-gray-200">
              <td colspan="7" class="px-4 py-3 text-xs font-semibold text-gray-600">
                Total del día: {{ totalActive }} viaje{{ totalActive !== 1 ? 's' : '' }}
              </td>
              <td class="px-4 py-3 text-right text-sm font-bold text-gray-900">
                {{ formatCurrency(totalValue) }}
              </td>
              <td colspan="2"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>

    <!-- Drawer detalle de viaje -->
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-150"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div v-if="detailTrip" class="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/30" @click="detailTrip = null" />
          <Transition
            enter-active-class="transition-all duration-200"
            enter-from-class="opacity-0 scale-95"
            enter-to-class="opacity-100 scale-100"
          >
            <div v-if="detailTrip" class="relative bg-white w-full max-w-md lg:max-w-xl max-h-[85vh] rounded-xl shadow-2xl flex flex-col overflow-hidden">
              <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between shrink-0">
                <div>
                  <h3 class="text-sm font-semibold text-gray-800">Vale #{{ detailTrip.voucher_num }}</h3>
                  <p class="text-xs text-gray-500 mt-0.5">{{ formatDate(detailTrip.date_register) }}</p>
                </div>
                <button type="button" @click="detailTrip = null" class="text-gray-400 hover:text-gray-600 text-lg leading-none">✕</button>
              </div>
              <div class="p-6 space-y-4 flex-1 overflow-y-auto text-sm">
                <div v-if="!detailTrip.state" class="px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
                  ⚠ Viaje anulado
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">Cliente</p>
                    <p class="font-medium text-gray-900">{{ detailTrip.client_detail?.name ?? '—' }}</p>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">Fecha</p>
                    <p class="font-medium text-gray-900">{{ formatDate(detailTrip.date_register) }}</p>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">Placa</p>
                    <p class="font-mono font-bold text-gray-900">{{ detailTrip.vehicle_detail?.plaque ?? '—' }}</p>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">PIN Ambiental</p>
                    <p class="font-medium text-gray-900">{{ detailTrip.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0' }}</p>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">Material</p>
                    <p class="font-medium text-gray-900">{{ detailTrip.material_type_detail?.name ?? '—' }}</p>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">Tipo vehículo</p>
                    <p class="font-medium text-gray-900">{{ detailTrip.vehicle_detail?.vehicle_type_detail?.name ?? '—' }}</p>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">Origen</p>
                    <p class="font-medium text-gray-900">{{ detailTrip.origin_site_detail?.name ?? '—' }}</p>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-0.5">Medio de pago</p>
                    <p class="font-medium text-gray-900">{{ detailTrip.payment_detail?.name ?? '—' }}</p>
                  </div>
                  <div class="col-span-2">
                    <p class="text-xs text-gray-500 mb-0.5">Valor del servicio</p>
                    <p class="text-2xl font-bold text-gray-900">{{ formatCurrency(detailTrip.value) }}</p>
                  </div>
                  <div v-if="detailTrip.extern_voucher_num" class="col-span-2">
                    <p class="text-xs text-gray-500 mb-0.5">Vale externo</p>
                    <p class="font-medium text-gray-900">{{ detailTrip.extern_voucher_num }}</p>
                  </div>
                </div>
              </div>
              <div class="px-6 py-4 border-t border-gray-100 shrink-0">
                <button
                  type="button"
                  @click="printVoucher(detailTrip!, detailTrip!.vehicle_detail?.dumper_detail?.ambiental_pin ?? '0', null)"
                  class="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-gold-500 text-stone-900 text-sm font-medium rounded-lg hover:bg-gold-600 transition-colors"
                >
                  <Printer class="w-4 h-4" /> Reimprimir Vale
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
