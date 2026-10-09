import { ref, watch } from 'vue'

// "Uncensored only": narrow the chat model pickers to models their provider
// marks uncensored (Venice). One remembered setting shared by every picker.
const KEY = 'models.uncensoredOnly'

function load() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

const uncensoredOnly = ref(load())
watch(uncensoredOnly, on => {
  try {
    localStorage.setItem(KEY, on ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
})

export function useUncensoredOnly() {
  return { uncensoredOnly }
}
