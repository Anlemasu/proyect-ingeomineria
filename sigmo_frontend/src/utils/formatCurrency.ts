export function formatCurrency(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '$ 0'
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return '$ 0'
  return '$ ' + num.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}
