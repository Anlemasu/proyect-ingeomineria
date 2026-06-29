import { useAuthStore } from '@/stores/auth.store'
import { PERMISSIONS, type PermissionModule, type PermissionAction } from '@/constants/permissions'
import { useNavigation } from '@/composables/useNavigation'

export function usePermissions() {
  const store = useAuthStore()
  const { isLeafVisible } = useNavigation()

  function hasRole(...roles: string[]): boolean {
    return !!store.user && roles.includes(store.user.role)
  }

  function can(module: PermissionModule, action: PermissionAction): boolean {
    if (!store.user) return false
    return (PERMISSIONS[module][action] as readonly string[]).includes(store.user.role)
  }

  function canView(module: PermissionModule) { return can(module, 'view') }
  function canCreate(module: PermissionModule) { return can(module, 'create') }
  function canEdit(module: PermissionModule) { return can(module, 'edit') }
  function canDelete(module: PermissionModule) { return can(module, 'delete') }

  function canAccess(path: string): boolean {
    return isLeafVisible(path)
  }

  return { hasRole, can, canView, canCreate, canEdit, canDelete, canAccess }
}
