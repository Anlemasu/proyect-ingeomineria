<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { LogOut, ChevronLeft, ChevronRight, ChevronDown } from 'lucide-vue-next'
import { useAuth } from '@/composables/useAuth'
import { useNavigation } from '@/composables/useNavigation'
import type { NavItem, NavLeaf, NavGroup } from '@/constants/navigation'

const route = useRoute()
const { logout } = useAuth()
const { visibleNav } = useNavigation()

const collapsed = ref(false)

// Track which groups are open
const openGroups = ref<Set<string>>(new Set())

function isLeafActive(path: string): boolean {
  return route.path === path
}

function isGroupActive(group: NavGroup): boolean {
  return group.children.some(child => isLeafActive(child.path))
}

function toggleGroup(label: string) {
  if (openGroups.value.has(label)) {
    openGroups.value.delete(label)
  } else {
    openGroups.value.add(label)
  }
  // Trigger reactivity
  openGroups.value = new Set(openGroups.value)
}

// Auto-expand group containing current active route on load and route change
function autoExpand() {
  for (const item of visibleNav.value) {
    if (item.type === 'group' && isGroupActive(item)) {
      openGroups.value.add(item.label)
    }
  }
  openGroups.value = new Set(openGroups.value)
}

autoExpand()
watch(() => route.path, autoExpand)

// When sidebar collapses, don't close groups (remember state)
const sidebarWidth = computed(() => collapsed.value ? 'w-16' : 'w-60')
</script>

<template>
  <aside
    class="flex flex-col min-h-screen bg-slate-800 transition-all duration-300 flex-shrink-0"
    :class="sidebarWidth"
  >
    <!-- Logo -->
    <div
      class="flex items-center border-b border-slate-700 transition-all duration-300"
      :class="collapsed ? 'p-4 justify-center' : 'px-5 py-4'"
    >
      <span class="text-white font-bold text-lg flex-shrink-0">S</span>
      <span v-if="!collapsed" class="text-white font-bold text-lg ml-0.5">IGMO</span>
    </div>

    <!-- Nav -->
    <nav class="flex-1 py-3 overflow-y-auto overflow-x-hidden">
      <template v-for="item in visibleNav" :key="item.type === 'leaf' ? item.path : item.label">

        <!-- Leaf item -->
        <router-link
          v-if="item.type === 'leaf'"
          :to="(item as NavLeaf).path"
          :title="collapsed ? item.label : undefined"
          class="flex items-center gap-3 mx-2 px-3 py-2 rounded-md text-sm transition-colors"
          :class="isLeafActive((item as NavLeaf).path)
            ? 'bg-blue-600 text-white'
            : 'text-slate-300 hover:bg-slate-700 hover:text-white'"
        >
          <component :is="item.icon" class="w-4 h-4 flex-shrink-0" />
          <span v-if="!collapsed" class="truncate">{{ item.label }}</span>
        </router-link>

        <!-- Group item -->
        <div v-else>
          <button
            :title="collapsed ? item.label : undefined"
            class="flex items-center gap-3 w-full mx-2 px-3 py-2 rounded-md text-sm transition-colors"
            :class="[
              isGroupActive(item as NavGroup) && !openGroups.has(item.label)
                ? 'text-blue-400'
                : 'text-slate-300 hover:bg-slate-700 hover:text-white',
              'w-[calc(100%-16px)]',
            ]"
            @click="toggleGroup(item.label)"
          >
            <component :is="item.icon" class="w-4 h-4 flex-shrink-0" />
            <span v-if="!collapsed" class="flex-1 text-left truncate">{{ item.label }}</span>
            <ChevronDown
              v-if="!collapsed"
              class="w-3.5 h-3.5 flex-shrink-0 transition-transform duration-200"
              :class="openGroups.has(item.label) ? 'rotate-180' : ''"
            />
          </button>

          <!-- Children (always show if collapsed, as flat icons; show animated if expanded) -->
          <div
            v-if="!collapsed"
            class="overflow-hidden transition-all duration-200"
            :style="openGroups.has(item.label)
              ? `max-height: ${(item as NavGroup).children.length * 44}px`
              : 'max-height: 0px'"
          >
            <router-link
              v-for="child in (item as NavGroup).children"
              :key="child.path"
              :to="child.path"
              class="flex items-center gap-3 mx-2 pl-9 pr-3 py-2 rounded-md text-sm transition-colors"
              :class="isLeafActive(child.path)
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:bg-slate-700 hover:text-white'"
            >
              <component :is="child.icon" class="w-3.5 h-3.5 flex-shrink-0" />
              <span class="truncate">{{ child.label }}</span>
            </router-link>
          </div>

          <!-- Collapsed children: show as icon-only items below group -->
          <template v-if="collapsed && openGroups.has(item.label)">
            <router-link
              v-for="child in (item as NavGroup).children"
              :key="child.path"
              :to="child.path"
              :title="child.label"
              class="flex items-center justify-center mx-2 px-3 py-2 rounded-md text-sm transition-colors"
              :class="isLeafActive(child.path)
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:bg-slate-700 hover:text-white'"
            >
              <component :is="child.icon" class="w-3.5 h-3.5" />
            </router-link>
          </template>
        </div>

      </template>
    </nav>

    <!-- Bottom: collapse toggle + logout -->
    <div class="border-t border-slate-700 p-2 space-y-1">
      <button
        @click="logout"
        :title="collapsed ? 'Cerrar sesión' : undefined"
        class="flex items-center gap-3 w-full px-3 py-2 rounded-md text-sm text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
        :class="collapsed ? 'justify-center' : ''"
      >
        <LogOut class="w-4 h-4 flex-shrink-0" />
        <span v-if="!collapsed">Cerrar sesión</span>
      </button>

      <button
        @click="collapsed = !collapsed"
        :title="collapsed ? 'Expandir menú' : 'Colapsar menú'"
        class="flex items-center gap-3 w-full px-3 py-2 rounded-md text-sm text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
        :class="collapsed ? 'justify-center' : ''"
      >
        <ChevronLeft v-if="!collapsed" class="w-4 h-4" />
        <ChevronRight v-else class="w-4 h-4" />
        <span v-if="!collapsed" class="text-xs">Colapsar</span>
      </button>
    </div>
  </aside>
</template>
