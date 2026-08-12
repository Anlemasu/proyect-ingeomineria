import * as XLSX from 'xlsx'

function cellText(cell: Element): string {
  return (cell.textContent ?? '').replace(/\s+/g, ' ').trim()
}

export function exportTableToExcel(table: HTMLTableElement, filenamePrefix: string, sheetName = 'Datos'): void {
  const headerRows = Array.from(table.querySelectorAll('thead tr:not([data-copy-skip])'))
  const bodyRows = Array.from(table.querySelectorAll('tbody tr:not([data-copy-skip])'))

  const rows = [...headerRows, ...bodyRows].map(row =>
    Array.from(row.querySelectorAll('th, td')).map(cellText)
  )

  const ws = XLSX.utils.aoa_to_sheet(rows)
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, sheetName)

  const today = new Date().toISOString().slice(0, 10)
  XLSX.writeFile(wb, `${filenamePrefix}_${today}.xlsx`)
}
