<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { toast } from 'vue-sonner'
import { useForm, useField } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import { z } from 'zod'
import { Plus, Pencil, ToggleLeft, ToggleRight, KeyRound, Eye, EyeOff } from 'lucide-vue-next'
import type { AxiosError } from 'axios'
import type { ColumnDef } from '@tanstack/vue-table'
import DataTable from '@/components/shared/DataTable.vue'
import PageHeader from '@/components/shared/PageHeader.vue'
import StatusBadge from '@/components/shared/StatusBadge.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import { usersApi } from '@/api/users.api'
import { getApiErrorMessage } from '@/utils/handleApiError'
import { useAuthStore } from '@/stores/auth.store'
import type { User, UserRole } from '@/types'

// ── Store ────────────────────────────────────────────────────────────────────
const authStore = useAuthStore()
const qc = useQueryClient()

// ── Modal state ──────────────────────────────────────────────────────────────
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showResetModal = ref(false)
const editingUser = ref<User | null>(null)
const resetTargetUser = ref<User | null>(null)
const confirmToggle = ref<User | null>(null)

// ── Password visibility toggles ──────────────────────────────────────────────
const showPassword = ref(false)
const showConfirmPassword = ref(false)
const showResetPassword = ref(false)
const showResetConfirmPassword = ref(false)

// ── Roles ────────────────────────────────────────────────────────────────────
const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'superuser', label: 'Superusuario' },
  { value: 'commercial_admin', label: 'Administrador Comercial' },
  { value: 'cashier', label: 'Operador de Caja' },
  { value: 'accountant', label: 'Contador' },
  { value: 'auditor', label: 'Auditor' },
]

const ROLE_BADGE: Record<UserRole, string> = {
  superuser: 'bg-purple-100 text-purple-700',
  commercial_admin: 'bg-blue-100 text-blue-700',
  cashier: 'bg-green-100 text-green-700',
  accountant: 'bg-amber-100 text-amber-700',
  auditor: 'bg-gray-100 text-gray-700',
}

const ROLE_LABEL: Record<UserRole, string> = {
  superuser: 'Superusuario',
  commercial_admin: 'Adm. Comercial',
  cashier: 'Cajero',
  accountant: 'Contador',
  auditor: 'Auditor',
}

// ── Password validation (mirrors backend: min 8, uppercase, digit) ────────────
const passwordRules = z.string()
  .min(8, 'Mínimo 8 caracteres')
  .refine(v => /[A-Z]/.test(v), 'Debe contener al menos una mayúscula')
  .refine(v => /\d/.test(v), 'Debe contener al menos un número')

// ── Create schema ────────────────────────────────────────────────────────────
const createSchema = toTypedSchema(z.object({
  name: z.string().min(1, 'El nombre es requerido').max(30).transform(s => s.trim()),
  email: z.string().email('Email inválido').max(30).transform(s => s.trim()),
  username: z.string().min(1, 'El usuario es requerido').max(30)
    .regex(/^\S+$/, 'El usuario no debe contener espacios')
    .transform(s => s.trim()),
  password: passwordRules,
  password_confirm: z.string(),
  role: z.enum(['superuser', 'commercial_admin', 'cashier', 'accountant', 'auditor'], {
    required_error: 'El rol es requerido',
  }),
}).refine(data => data.password === data.password_confirm, {
  message: 'Las contraseñas no coinciden',
  path: ['password_confirm'],
}))

// ── Edit schema ──────────────────────────────────────────────────────────────
const editSchema = toTypedSchema(z.object({
  name: z.string().min(1, 'El nombre es requerido').max(30).transform(s => s.trim()),
  email: z.string().email('Email inválido').max(30).transform(s => s.trim()),
  username: z.string().min(1, 'El usuario es requerido').max(30)
    .regex(/^\S+$/, 'El usuario no debe contener espacios')
    .transform(s => s.trim()),
}))

// ── Reset password schema ────────────────────────────────────────────────────
const resetSchema = toTypedSchema(z.object({
  password: passwordRules,
  password_confirm: z.string(),
}).refine(data => data.password === data.password_confirm, {
  message: 'Las contraseñas no coinciden',
  path: ['password_confirm'],
}))

// ── Create form ───────────────────────────────────────────────────────────────
const {
  handleSubmit: handleCreateSubmit,
  isSubmitting: isCreating,
  resetForm: resetCreateForm,
  setFieldError: setCreateFieldError,
} = useForm({ validationSchema: createSchema })

const { value: createName, errorMessage: createNameError } = useField<string>('name')
const { value: createEmail, errorMessage: createEmailError } = useField<string>('email')
const { value: createUsername, errorMessage: createUsernameError } = useField<string>('username')
const { value: createPassword, errorMessage: createPasswordError } = useField<string>('password')
const { value: createPasswordConfirm, errorMessage: createPasswordConfirmError } = useField<string>('password_confirm')
const { value: createRole, errorMessage: createRoleError } = useField<UserRole>('role')

// ── Edit form ─────────────────────────────────────────────────────────────────
const {
  handleSubmit: handleEditSubmit,
  isSubmitting: isEditing,
  resetForm: resetEditForm,
  setValues: setEditValues,
  setFieldError: setEditFieldError,
} = useForm({ validationSchema: editSchema })

const { value: editName, errorMessage: editNameError } = useField<string>('name')
const { value: editEmail, errorMessage: editEmailError } = useField<string>('email')
const { value: editUsername, errorMessage: editUsernameError } = useField<string>('username')

// ── Reset password form ────────────────────────────────────────────────────────
const {
  handleSubmit: handleResetSubmit,
  isSubmitting: isResetting,
  resetForm: resetResetForm,
} = useForm({ validationSchema: resetSchema })

const { value: resetPassword, errorMessage: resetPasswordError } = useField<string>('password')
const { value: resetPasswordConfirm, errorMessage: resetPasswordConfirmError } = useField<string>('password_confirm')

// ── Query ─────────────────────────────────────────────────────────────────────
const { data: users, isLoading } = useQuery({
  queryKey: ['users'],
  queryFn: async () => {
    const res = await usersApi.list()
    return res.data
  },
})

const allUsers = computed(() => users.value ?? [])

// ── Mutations ─────────────────────────────────────────────────────────────────
const { mutateAsync: createUser } = useMutation({
  mutationFn: (data: Parameters<typeof usersApi.create>[0]) => usersApi.create(data),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['users'] })
    toast.success('Usuario creado correctamente.')
  },
})

const { mutateAsync: updateUser } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: Parameters<typeof usersApi.update>[1] }) =>
    usersApi.update(id, data),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['users'] })
    toast.success('Usuario actualizado correctamente.')
  },
})

const { mutate: toggleUser, isPending: togglePending } = useMutation({
  mutationFn: (user: User) => usersApi.update(user.id, { state: !user.state }),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['users'] })
    confirmToggle.value = null
    toast.success('Estado actualizado.')
  },
  onError: (err) => { toast.error(getApiErrorMessage(err)) },
})

const { mutateAsync: resetUserPassword } = useMutation({
  mutationFn: ({ id, data }: { id: number; data: { new_password: string } }) =>
    usersApi.resetPassword(id, data),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ['users'] })
    toast.success('Contraseña restablecida correctamente.')
  },
})

// ── Helpers ───────────────────────────────────────────────────────────────────
function getFieldErrors(err: unknown): Record<string, string> {
  const e = err as AxiosError<Record<string, unknown>>
  if (!e.response?.data) return {}
  const data = e.response.data
  const out: Record<string, string> = {}
  for (const key of Object.keys(data)) {
    const val = data[key]
    out[key] = Array.isArray(val) ? String(val[0]) : String(val)
  }
  return out
}

// ── Open modals ───────────────────────────────────────────────────────────────
function openCreate() {
  resetCreateForm()
  showPassword.value = false
  showConfirmPassword.value = false
  showCreateModal.value = true
}

function openEdit(user: User) {
  editingUser.value = user
  resetEditForm()
  setEditValues({ name: user.name, email: user.email, username: user.username })
  showEditModal.value = true
}

function openReset(user: User) {
  resetTargetUser.value = user
  resetResetForm()
  showResetPassword.value = false
  showResetConfirmPassword.value = false
  showResetModal.value = true
}

// ── Submit handlers ───────────────────────────────────────────────────────────
const onCreateSubmit = handleCreateSubmit(async (values) => {
  try {
    await createUser({
      name: values.name,
      email: values.email,
      username: values.username,
      password: values.password,
      role: values.role as UserRole,
    })
    showCreateModal.value = false
  } catch (err) {
    const fieldErrors = getFieldErrors(err)
    if (fieldErrors.email) setCreateFieldError('email', fieldErrors.email)
    else if (fieldErrors.username) setCreateFieldError('username', fieldErrors.username)
    else toast.error(getApiErrorMessage(err))
  }
})

const onEditSubmit = handleEditSubmit(async (values) => {
  if (!editingUser.value) return
  try {
    await updateUser({ id: editingUser.value.id, data: { name: values.name, email: values.email, username: values.username } })
    showEditModal.value = false
  } catch (err) {
    const fieldErrors = getFieldErrors(err)
    if (fieldErrors.username) setEditFieldError('username', fieldErrors.username)
    else if (fieldErrors.email) setEditFieldError('email', fieldErrors.email)
    else toast.error(getApiErrorMessage(err))
  }
})

const onResetSubmit = handleResetSubmit(async (values) => {
  if (!resetTargetUser.value) return
  try {
    await resetUserPassword({ id: resetTargetUser.value.id, data: { new_password: values.password } })
    showResetModal.value = false
  } catch (err) {
    toast.error(getApiErrorMessage(err))
  }
})

// ── Table columns ─────────────────────────────────────────────────────────────
const columns: ColumnDef<User>[] = [
  { accessorKey: 'name', header: 'Nombre' },
  { accessorKey: 'username', header: 'Usuario' },
  { accessorKey: 'email', header: 'Email' },
  {
    accessorKey: 'role',
    header: 'Rol',
    cell: ({ row }) => h('span', {
      class: `inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ROLE_BADGE[row.original.role as UserRole] ?? 'bg-gray-100 text-gray-700'}`,
    }, ROLE_LABEL[row.original.role as UserRole] ?? row.original.role_display),
  },
  {
    accessorKey: 'state',
    header: 'Estado',
    cell: ({ row }) => h(StatusBadge, { active: row.original.state }),
  },
  {
    id: 'actions',
    header: 'Acciones',
    cell: ({ row }) => {
      const u = row.original
      const isSelf = authStore.user?.id === u.id
      return h('div', { class: 'flex items-center gap-2' }, [
        h('button', {
          class: 'p-1 text-gray-500 hover:text-gold-700',
          title: 'Editar',
          onClick: () => openEdit(u),
        }, h(Pencil, { class: 'w-4 h-4' })),
        h('button', {
          class: 'p-1 text-gray-500 hover:text-amber-600',
          title: 'Restablecer contraseña',
          onClick: () => openReset(u),
        }, h(KeyRound, { class: 'w-4 h-4' })),
        isSelf
          ? h('button', {
              class: 'p-1 text-gray-300 cursor-not-allowed',
              title: 'No puedes desactivar tu propia cuenta.',
              disabled: true,
            }, h(u.state ? ToggleRight : ToggleLeft, { class: 'w-4 h-4' }))
          : h('button', {
              class: 'p-1 text-gray-500 hover:text-amber-600',
              title: u.state ? 'Desactivar' : 'Activar',
              onClick: () => { confirmToggle.value = u },
            }, h(u.state ? ToggleRight : ToggleLeft, { class: 'w-4 h-4' })),
      ])
    },
  },
]
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex flex-wrap items-center justify-between gap-3 mb-6">
      <PageHeader title="Usuarios" description="Gestión de usuarios del sistema" />
      <button
        @click="openCreate"
        class="flex items-center gap-2 px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600"
      >
        <Plus class="w-4 h-4" />
        Nuevo usuario
      </button>
    </div>

    <DataTable :columns="(columns as any)" :data="(allUsers as any)" :is-loading="isLoading" />

    <!-- ── CREATE MODAL ─────────────────────────────────────────────────────── -->
    <teleport to="body">
      <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showCreateModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <h2 class="text-lg font-semibold mb-5">Nuevo usuario</h2>
          <form @submit.prevent="onCreateSubmit" class="space-y-4" novalidate>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nombre completo *</label>
              <input v-model="createName" type="text"
                class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                :class="createNameError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="createNameError" class="mt-1 text-xs text-red-600">{{ createNameError }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Correo electrónico *</label>
              <input v-model="createEmail" type="email"
                class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                :class="createEmailError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="createEmailError" class="mt-1 text-xs text-red-600">{{ createEmailError }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nombre de usuario *</label>
              <input v-model="createUsername" type="text" autocomplete="off"
                class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                :class="createUsernameError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="createUsernameError" class="mt-1 text-xs text-red-600">{{ createUsernameError }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Contraseña temporal *</label>
              <div class="relative">
                <input v-model="createPassword"
                  :type="showPassword ? 'text' : 'password'"
                  autocomplete="new-password"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 pr-10"
                  :class="createPasswordError ? 'border-red-400' : 'border-gray-300'" />
                <button type="button" @click="showPassword = !showPassword"
                  class="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600">
                  <EyeOff v-if="showPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>
              <p v-if="createPasswordError" class="mt-1 text-xs text-red-600">{{ createPasswordError }}</p>
              <p class="mt-1 text-xs text-gray-400">Mínimo 8 caracteres, una mayúscula y un número.</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Confirmar contraseña *</label>
              <div class="relative">
                <input v-model="createPasswordConfirm"
                  :type="showConfirmPassword ? 'text' : 'password'"
                  autocomplete="new-password"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 pr-10"
                  :class="createPasswordConfirmError ? 'border-red-400' : 'border-gray-300'" />
                <button type="button" @click="showConfirmPassword = !showConfirmPassword"
                  class="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600">
                  <EyeOff v-if="showConfirmPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>
              <p v-if="createPasswordConfirmError" class="mt-1 text-xs text-red-600">{{ createPasswordConfirmError }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Rol *</label>
              <select v-model="createRole"
                class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                :class="createRoleError ? 'border-red-400' : 'border-gray-300'">
                <option value="" disabled>Selecciona un rol</option>
                <option v-for="opt in ROLE_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <p v-if="createRoleError" class="mt-1 text-xs text-red-600">{{ createRoleError }}</p>
            </div>

            <div class="flex justify-end gap-3 pt-2">
              <button type="button" @click="showCreateModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">
                Cancelar
              </button>
              <button type="submit" :disabled="isCreating"
                class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60">
                {{ isCreating ? 'Guardando...' : 'Crear usuario' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </teleport>

    <!-- ── EDIT MODAL ──────────────────────────────────────────────────────── -->
    <teleport to="body">
      <div v-if="showEditModal && editingUser" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showEditModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
          <h2 class="text-lg font-semibold mb-5">Editar usuario</h2>
          <form @submit.prevent="onEditSubmit" class="space-y-4" novalidate>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nombre completo *</label>
              <input v-model="editName" type="text"
                class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                :class="editNameError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="editNameError" class="mt-1 text-xs text-red-600">{{ editNameError }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Correo electrónico *</label>
              <input v-model="editEmail" type="email"
                class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                :class="editEmailError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="editEmailError" class="mt-1 text-xs text-red-600">{{ editEmailError }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nombre de usuario *</label>
              <input v-model="editUsername" type="text" autocomplete="off"
                class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
                :class="editUsernameError ? 'border-red-400' : 'border-gray-300'" />
              <p v-if="editUsernameError" class="mt-1 text-xs text-red-600">{{ editUsernameError }}</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Rol</label>
              <span :class="`inline-flex items-center px-2.5 py-1 rounded text-xs font-medium ${ROLE_BADGE[editingUser.role as UserRole] ?? 'bg-gray-100 text-gray-700'}`">
                {{ editingUser.role_display }}
              </span>
              <p class="mt-1 text-xs text-gray-400">El rol no puede modificarse después de la creación.</p>
            </div>

            <div class="flex justify-end gap-3 pt-2">
              <button type="button" @click="showEditModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">
                Cancelar
              </button>
              <button type="submit" :disabled="isEditing"
                class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60">
                {{ isEditing ? 'Guardando...' : 'Guardar cambios' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </teleport>

    <!-- ── RESET PASSWORD MODAL ────────────────────────────────────────────── -->
    <teleport to="body">
      <div v-if="showResetModal && resetTargetUser" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showResetModal = false" />
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
          <h2 class="text-lg font-semibold mb-1">Restablecer contraseña</h2>
          <p class="text-sm text-gray-500 mb-5">
            Establecer nueva contraseña temporal para
            <span class="font-medium text-gray-700">{{ resetTargetUser.username }}</span>
          </p>
          <form @submit.prevent="onResetSubmit" class="space-y-4" novalidate>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Nueva contraseña temporal *</label>
              <div class="relative">
                <input v-model="resetPassword"
                  :type="showResetPassword ? 'text' : 'password'"
                  autocomplete="new-password"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 pr-10"
                  :class="resetPasswordError ? 'border-red-400' : 'border-gray-300'" />
                <button type="button" @click="showResetPassword = !showResetPassword"
                  class="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600">
                  <EyeOff v-if="showResetPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>
              <p v-if="resetPasswordError" class="mt-1 text-xs text-red-600">{{ resetPasswordError }}</p>
              <p class="mt-1 text-xs text-gray-400">Mínimo 8 caracteres, una mayúscula y un número.</p>
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">Confirmar contraseña *</label>
              <div class="relative">
                <input v-model="resetPasswordConfirm"
                  :type="showResetConfirmPassword ? 'text' : 'password'"
                  autocomplete="new-password"
                  class="w-full px-3 py-2 text-sm border rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 pr-10"
                  :class="resetPasswordConfirmError ? 'border-red-400' : 'border-gray-300'" />
                <button type="button" @click="showResetConfirmPassword = !showResetConfirmPassword"
                  class="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600">
                  <EyeOff v-if="showResetConfirmPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>
              <p v-if="resetPasswordConfirmError" class="mt-1 text-xs text-red-600">{{ resetPasswordConfirmError }}</p>
            </div>

            <div class="flex justify-end gap-3 pt-2">
              <button type="button" @click="showResetModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50">
                Cancelar
              </button>
              <button type="submit" :disabled="isResetting"
                class="px-4 py-2 text-sm font-medium text-stone-900 bg-gold-500 rounded-md hover:bg-gold-600 disabled:opacity-60">
                {{ isResetting ? 'Restableciendo...' : 'Restablecer' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </teleport>

    <!-- ── CONFIRM TOGGLE ─────────────────────────────────────────────────── -->
    <ConfirmDialog
      :open="!!confirmToggle"
      :title="confirmToggle?.state ? 'Desactivar usuario' : 'Reactivar usuario'"
      :description="confirmToggle?.state
        ? `¿Desactivar a ${confirmToggle?.name}? No podrá iniciar sesión hasta ser reactivado.`
        : `¿Reactivar a ${confirmToggle?.name}? Podrá iniciar sesión nuevamente.`"
      :loading="togglePending"
      @confirm="confirmToggle && toggleUser(confirmToggle)"
      @cancel="confirmToggle = null"
    />
  </div>
</template>
