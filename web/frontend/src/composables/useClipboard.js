import { ref } from 'vue'

/**
 * Copy text to the clipboard. navigator.clipboard only exists in secure
 * contexts (HTTPS / localhost), so fall back to a hidden textarea +
 * execCommand when the app is opened over plain HTTP on the LAN.
 */
export async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch { /* permission denied — try the fallback */ }
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch { /* unsupported */ }
  document.body.removeChild(ta)
  return ok
}

/** `copiedKey` holds the key of whatever was copied last, for ~1.5s of "✓ Copied" feedback. */
export function useCopy() {
  const copiedKey = ref(null)
  let timer = null

  async function copy(text, key = 'default') {
    if (!text) return false
    const ok = await copyText(text)
    if (ok) {
      copiedKey.value = key
      clearTimeout(timer)
      timer = setTimeout(() => { copiedKey.value = null }, 1500)
    }
    return ok
  }

  return { copiedKey, copy }
}
