import { inject, provide, ref } from 'vue'

// Sidebar sections folded away (per browser). The chat page provides the
// state; each section's heading reads and toggles it.
const FOLD_KEY = 'chat.folded'
const FOLDED = Symbol('folded')

function load() {
  try {
    return new Set(JSON.parse(localStorage.getItem(FOLD_KEY)) || [])
  } catch {
    return new Set()
  }
}

export function provideFolded() {
  const folded = ref(load())

  function toggleFold(key) {
    const next = new Set(folded.value)
    if (!next.delete(key)) next.add(key)
    folded.value = next
    try {
      localStorage.setItem(FOLD_KEY, JSON.stringify([...next]))
    } catch {
      /* storage unavailable */
    }
  }

  const state = { isFolded: key => folded.value.has(key), toggleFold }
  provide(FOLDED, state)
  return state
}

export function useFolded() {
  return inject(FOLDED)
}
