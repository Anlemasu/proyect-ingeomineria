export function openCenteredWindow(width: number, height: number): Window | null {
  const viewportWidth = window.outerWidth || window.innerWidth
  const viewportHeight = window.outerHeight || window.innerHeight
  const left = Math.max(0, Math.round(window.screenX + (viewportWidth - width) / 2))
  const top = Math.max(0, Math.round(window.screenY + (viewportHeight - height) / 2))
  return window.open('', '_blank', `width=${width},height=${height},left=${left},top=${top}`)
}
