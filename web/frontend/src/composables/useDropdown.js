import { nextTick, onBeforeUnmount, ref } from 'vue'

// A pop-up's open state, closed by any mousedown outside `root` (bind it to
// the element holding both the button and the pop-up) and on unmount.
// `onOpen` / `onClose` run as it opens / closes; `focus` (a template ref) is
// focused once it's open.
export function useDropdown({ onOpen, onClose, focus } = {}) {
  const open = ref(false)
  const root = ref(null)

  function onDocDown(e) {
    if (root.value && !root.value.contains(e.target)) close()
  }

  async function show() {
    if (open.value) return
    open.value = true
    onOpen?.()
    document.addEventListener('mousedown', onDocDown)
    await nextTick()
    focus?.value?.focus()
  }

  function close() {
    if (!open.value) return
    open.value = false
    document.removeEventListener('mousedown', onDocDown)
    onClose?.()
  }

  const toggle = () => (open.value ? close() : show())

  onBeforeUnmount(close)
  return { open, root, show, close, toggle }
}
