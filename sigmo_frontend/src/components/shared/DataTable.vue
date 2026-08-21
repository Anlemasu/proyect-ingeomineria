<script setup lang="ts" generic="T">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import {
  useVueTable,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  FlexRender,
  type ColumnDef,
  type SortingState,
  type ColumnSizingState,
} from '@tanstack/vue-table'
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight, Copy, FileSpreadsheet } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { copyTableToClipboard } from '@/utils/copyTableToClipboard'
import { exportTableToExcel } from '@/utils/exportTableToExcel'

const props = defineProps<{
  columns: ColumnDef<T>[]
  data: T[]
  isLoading?: boolean
  exportFilename?: string
}>()

const globalFilter = ref('')
const sorting = ref<SortingState>([])
const pageSize = ref(10)
const pageIndex = ref(0)

// ── Ancho de columnas ajustable (persistido por ruta + set de columnas) ─────
const route = useRoute()
function deriveColumnId(c: ColumnDef<T>, idx: number): string {
  if ('id' in c && c.id) return c.id
  if ('accessorKey' in c && typeof c.accessorKey === 'string') return c.accessorKey
  if (typeof c.header === 'string') return c.header
  return `col_${idx}`
}
const storageKey = computed(() =>
  `sigmo_dt_colw:${route.path}:${props.columns.map((c, i) => deriveColumnId(c, i)).join('|')}`
)
function loadColumnSizing(): ColumnSizingState {
  try {
    return JSON.parse(localStorage.getItem(storageKey.value) ?? '{}')
  } catch {
    return {}
  }
}
const columnSizing = ref<ColumnSizingState>(loadColumnSizing())
watch(storageKey, () => { columnSizing.value = loadColumnSizing() })

let persistTimer: ReturnType<typeof setTimeout> | undefined
function persistColumnSizing() {
  clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    localStorage.setItem(storageKey.value, JSON.stringify(columnSizing.value))
  }, 250)
}
onBeforeUnmount(() => {
  clearTimeout(persistTimer)
  localStorage.setItem(storageKey.value, JSON.stringify(columnSizing.value))
})

const table = useVueTable({
  get data() { return props.data },
  get columns() { return props.columns },
  defaultColumn: { size: 150, minSize: 80 },
  enableColumnResizing: true,
  columnResizeMode: 'onChange',
  getCoreRowModel: getCoreRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
  getSortedRowModel: getSortedRowModel(),
  state: {
    get globalFilter() { return globalFilter.value },
    get sorting() { return sorting.value },
    get pagination() { return { pageIndex: pageIndex.value, pageSize: pageSize.value } },
    get columnSizing() { return columnSizing.value },
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
  onColumnSizingChange: (updater) => {
    columnSizing.value = typeof updater === 'function' ? updater(columnSizing.value) : updater
    persistColumnSizing()
  },
})

const pageCount = computed(() => table.getPageCount())

// Reset to first page when page size or data changes
watch(pageSize, () => { pageIndex.value = 0 })
watch(() => props.data, () => { pageIndex.value = 0 })

const tableEl = ref<HTMLTableElement | null>(null)
async function handleCopy() {
  if (!tableEl.value) return
  try {
    await copyTableToClipboard(tableEl.value)
    toast.success('Tabla copiada al portapapeles')
  } catch {
    toast.error('No se pudo copiar la tabla')
  }
}

function handleExportExcel() {
  if (!tableEl.value) return
  try {
    exportTableToExcel(tableEl.value, props.exportFilename ?? 'Export_SIGMO')
    toast.success('Tabla exportada a Excel')
  } catch {
    toast.error('No se pudo exportar la tabla')
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-3">
      <input
        v-model="globalFilter"
        type="text"
        placeholder="Buscar..."
        class="w-full sm:w-64 px-3 py-2 text-sm border border-stone-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400 focus:border-gold-400"
      />
      <select
        v-model="pageSize"
        class="px-3 py-2 text-sm border border-stone-300 rounded-md focus:outline-none focus:ring-2 focus:ring-gold-400"
      >
        <option :value="10">10 por página</option>
        <option :value="25">25 por página</option>
        <option :value="50">50 por página</option>
      </select>
      <slot name="filters" />
      <button
        type="button"
        @click="handleCopy"
        class="ml-auto flex items-center gap-1.5 px-3 py-2 text-sm text-stone-600 border border-stone-300 rounded-md hover:bg-gold-50 hover:border-gold-300 hover:text-gold-700 transition-colors"
        title="Copiar tabla al portapapeles"
      >
        <Copy class="w-4 h-4" />Copiar
      </button>
      <button
        type="button"
        @click="handleExportExcel"
        class="flex items-center gap-1.5 px-3 py-2 text-sm text-stone-600 border border-stone-300 rounded-md hover:bg-gold-50 hover:border-gold-300 hover:text-gold-700 transition-colors"
        title="Exportar tabla a Excel"
      >
        <FileSpreadsheet class="w-4 h-4" />Exportar Excel
      </button>
    </div>

    <div class="border border-stone-200 rounded-lg overflow-auto bg-white max-h-[65vh]">
      <table ref="tableEl" class="w-full text-sm">
        <thead class="bg-gold-50 border-b-2 border-gold-200 sticky top-0 z-10">
          <tr class="divide-x divide-gold-200/70">
            <th
              v-for="header in table.getHeaderGroups()[0].headers"
              :key="header.id"
              :style="{ width: header.getSize() + 'px', minWidth: header.getSize() + 'px' }"
              class="relative px-4 py-3 text-left text-xs font-semibold text-stone-700 uppercase tracking-wider"
              :class="header.column.getCanSort() ? 'cursor-pointer select-none' : ''"
              @click="header.column.getToggleSortingHandler()?.($event)"
            >
              <div class="flex items-center gap-1 pr-2.5 min-w-0">
                <span class="truncate min-w-0">
                  <FlexRender :render="header.column.columnDef.header" :props="header.getContext()" />
                </span>
                <span v-if="header.column.getCanSort()" class="shrink-0">
                  <ChevronUp v-if="header.column.getIsSorted() === 'asc'" class="w-3 h-3 text-gold-700" />
                  <ChevronDown v-else-if="header.column.getIsSorted() === 'desc'" class="w-3 h-3 text-gold-700" />
                  <ChevronsUpDown v-else class="w-3 h-3 text-stone-400" />
                </span>
              </div>
              <div
                v-if="header.column.getCanResize()"
                class="absolute top-0 right-0 z-20 h-full w-2.5 cursor-col-resize touch-none select-none"
                :class="header.column.getIsResizing() ? 'bg-gold-500' : 'hover:bg-gold-400/80'"
                title="Arrastra para ajustar el ancho — doble clic para restablecer"
                @mousedown.stop="header.getResizeHandler()($event)"
                @touchstart.stop="header.getResizeHandler()($event)"
                @click.stop
                @dblclick.stop="header.column.resetSize()"
              />
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-if="isLoading">
            <tr v-for="i in 5" :key="i" class="border-b border-stone-100">
              <td v-for="j in columns.length" :key="j" class="px-4 py-3">
                <div class="h-4 bg-stone-200 rounded animate-pulse" />
              </td>
            </tr>
          </template>
          <template v-else-if="table.getRowModel().rows.length === 0">
            <tr>
              <td :colspan="columns.length" class="px-4 py-12 text-center text-stone-400 text-sm">
                No hay registros para mostrar
              </td>
            </tr>
          </template>
          <template v-else>
            <tr
              v-for="row in table.getRowModel().rows"
              :key="row.id"
              class="border-b border-stone-100 divide-x divide-stone-100 hover:bg-gold-50/50 transition-colors"
            >
              <td
                v-for="cell in row.getVisibleCells()"
                :key="cell.id"
                :style="{ width: cell.column.getSize() + 'px', minWidth: cell.column.getSize() + 'px' }"
                class="px-4 py-3 text-stone-700 whitespace-nowrap overflow-hidden text-ellipsis"
              >
                <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-2 text-sm text-stone-600">
      <span>
        Página {{ pageIndex + 1 }} de {{ pageCount || 1 }}
        ({{ table.getFilteredRowModel().rows.length }} registros)
      </span>
      <div class="flex items-center gap-2">
        <button
          @click="table.previousPage()"
          :disabled="!table.getCanPreviousPage()"
          class="p-1 rounded hover:bg-gold-100 hover:text-gold-700 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-stone-600"
        >
          <ChevronLeft class="w-4 h-4" />
        </button>
        <button
          @click="table.nextPage()"
          :disabled="!table.getCanNextPage()"
          class="p-1 rounded hover:bg-gold-100 hover:text-gold-700 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-stone-600"
        >
          <ChevronRight class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
