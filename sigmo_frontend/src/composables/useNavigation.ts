import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth.store'
import { navigation, type NavItem, type NavLeaf, type NavGroup } from '@/constants/navigation'

export function useNavigation() {
  const store = useAuthStore()

  const visibleNav = computed<NavItem[]>(() => {
    const role = store.user?.role
    if (!role) return []

    return navigation.reduce<NavItem[]>((acc, item) => {
      if (item.type === 'leaf') {
        if (item.roles.includes(role)) acc.push(item)
      } else {
        const visibleChildren = item.children.filter(child => child.roles.includes(role))
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
    for (const item of navigation) {
      if (item.type === 'leaf' && item.path === path) return item.roles.includes(role)
      if (item.type === 'group') {
        const child = item.children.find(c => c.path === path)
        if (child) return child.roles.includes(role)
      }
    }
    return false
  }

  return { visibleNav, isLeafVisible }
}
