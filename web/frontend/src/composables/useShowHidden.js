import { ref, watch } from 'vue'

// "Show hidden": models MODEL_INFO marks `hidden` (not enabled for this API
// key, or retired) are left out of model pickers unless this is on. One remembered
// setting shared by the chat pickers and the Generate page.
const KEY = 'models.showHidden'

function load() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

const showHidden = ref(load())
watch(showHidden, on => {
  try {
    localStorage.setItem(KEY, on ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
})

export function useShowHidden() {
  return { showHidden }
}
