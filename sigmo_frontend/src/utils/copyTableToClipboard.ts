function cellText(cell: Element): string {
  return (cell.textContent ?? '').replace(/\s+/g, ' ').trim()
}

export async function copyTableToClipboard(table: HTMLTableElement): Promise<void> {
  const headerRows = Array.from(table.querySelectorAll('thead tr:not([data-copy-skip])'))
  const bodyRows = Array.from(table.querySelectorAll('tbody tr:not([data-copy-skip])'))

  const lines = [...headerRows, ...bodyRows].map(row =>
    Array.from(row.querySelectorAll('th, td'))
      .map(cellText)
      .join('\t')
  )

  await navigator.clipboard.writeText(lines.join('\n'))
}
