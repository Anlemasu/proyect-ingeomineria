import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const collapsed = ref(false)
const isMobileOpen = ref(false)

function open() {
  isMobileOpen.value = true
}

function close() {
  isMobileOpen.value = false
}

function toggle() {
  isMobileOpen.value = !isMobileOpen.value
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value
}

let autoCloseBound = false

export function useSidebar() {
  const route = useRoute()

  if (!autoCloseBound) {
    autoCloseBound = true
    watch(() => route.fullPath, () => close())
  }

  return { collapsed, isMobileOpen, open, close, toggle, toggleCollapsed }
}
