<script setup lang="ts" generic="T extends Record<string, unknown>">
import { ref, computed, watch } from 'vue'
import {
  useVueTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  FlexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/vue-table'
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from 'lucide-vue-next'

const props = defineProps<{
  columns: ColumnDef<T>[]
  data: T[]
  isLoading?: boolean
}>()

const globalFilter = ref('')
const sorting = ref<SortingState>([])
const pageSize = ref(10)
const pageIndex = ref(0)

const table = useVueTable({
  get data() { return props.data },
  get columns() { return props.columns },
  getCoreRowModel: getCoreRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  getSortedRowModel: getSortedRowModel(),
  state: {
    get globalFilter() { return globalFilter.value },
    get sorting() { return sorting.value },
    get pagination() { return { pageIndex: pageIndex.value, pageSize: pageSize.value } },
  },
  onSortingChange: (updater) => {
    sorting.value = typeof updater === 'function' ? updater(sorting.value) : updater
  },
  onGlobalFilterChange: (val) => {
    globalFilter.value = val
    pageIndex.value = 0
  },
  onPaginationChange: (updater) => {
    const next = typeof updater === 'function'
      ? updater({ pageIndex: pageIndex.value, pageSize: pageSize.value })
      : updater
    pageIndex.value = next.pageIndex
    pageSize.value = next.pageSize
  },
})

const pageCount = computed(() => table.getPageCount())

// Reset to first page when page size or data changes
watch(pageSize, () => { pageIndex.value = 0 })
watch(() => props.data, () => { pageIndex.value = 0 })
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <input
        v-model="globalFilter"
        type="text"
        placeholder="Buscar..."
        class="w-full sm:w-64 px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
      />
      <select
        v-model="pageSize"
        class="px-3 py-2 text-sm border border-gray-300 rounded-md focus:outline-none"
      >
        <option :value="10">10 por página</option>
        <option :value="25">25 por página</option>
        <option :value="50">50 por página</option>
      </select>
      <slot name="filters" />
    </div>

    <div class="border border-gray-200 rounded-lg overflow-x-auto bg-white">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 border-b border-gray-200">
          <tr>
            <th
              v-for="header in table.getHeaderGroups()[0].headers"
              :key="header.id"
              class="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider"
              :class="header.column.getCanSort() ? 'cursor-pointer select-none' : ''"
              @click="header.column.getToggleSortingHandler()?.($event)"
            >
              <div class="flex items-center gap-1">
                <FlexRender :render="header.column.columnDef.header" :props="header.getContext()" />
                <span v-if="header.column.getCanSort()">
                  <ChevronUp v-if="header.column.getIsSorted() === 'asc'" class="w-3 h-3" />
                  <ChevronDown v-else-if="header.column.getIsSorted() === 'desc'" class="w-3 h-3" />
                  <ChevronsUpDown v-else class="w-3 h-3 text-gray-400" />
                </span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="isLoading">
            <tr v-for="i in 5" :key="i" class="border-b border-gray-100">
              <td v-for="j in columns.length" :key="j" class="px-4 py-3">
                <div class="h-4 bg-gray-200 rounded animate-pulse" />
              </td>
            </tr>
          </template>
          <template v-else-if="table.getRowModel().rows.length === 0">
            <tr>
              <td :colspan="columns.length" class="px-4 py-12 text-center text-gray-400 text-sm">
                No hay registros para mostrar
              </td>
            </tr>
          </template>
          <template v-else>
            <tr
              v-for="row in table.getRowModel().rows"
              :key="row.id"
              class="border-b border-gray-100 hover:bg-gray-50 transition-colors"
            >
              <td v-for="cell in row.getVisibleCells()" :key="cell.id" class="px-4 py-3 text-gray-700">
                <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-600">
      <span>
        Página {{ pageIndex + 1 }} de {{ pageCount || 1 }}
        ({{ table.getFilteredRowModel().rows.length }} registros)
      </span>
      <div class="flex items-center gap-2">
        <button
          @click="table.previousPage()"
          :disabled="!table.getCanPreviousPage()"
          class="p-1 rounded hover:bg-gray-100 disabled:opacity-40"
        >
          <ChevronLeft class="w-4 h-4" />
        </button>
        <button
          @click="table.nextPage()"
          :disabled="!table.getCanNextPage()"
          class="p-1 rounded hover:bg-gray-100 disabled:opacity-40"
        >
          <ChevronRight class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
