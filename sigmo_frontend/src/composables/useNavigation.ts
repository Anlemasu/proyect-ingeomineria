import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth.store'
import { navigation, getAllowedRoles, type NavItem, type NavGroup } from '@/constants/navigation'

export function useNavigation() {
  const store = useAuthStore()

  const visibleNav = computed<NavItem[]>(() => {
    const role = store.user?.role
    if (!role) return []

    return navigation.reduce<NavItem[]>((acc, item) => {
      if (item.type === 'leaf') {
        if (item.enabled !== false && item.roles.includes(role)) acc.push(item)
      } else {
        const visibleChildren = item.children.filter(
          child => child.enabled !== false && child.roles.includes(role),
        )
        if (visibleChildren.length > 0) {
          acc.push({ ...item, children: visibleChildren } as NavGroup)
        }
      }
      return acc
    }, [])
  })

  function isLeafVisible(path: string): boolean {
    const role = store.user?.role
    if (!role) return false
    return getAllowedRoles(path)?.includes(role) ?? false
  }

  return { visibleNav, isLeafVisible }
}
