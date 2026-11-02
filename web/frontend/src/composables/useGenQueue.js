// Always-visible generation queue, backed by /api/chat/generations/active.
// It polls for the signed-in user's in-flight generations across *every* thread
// (so progress stays visible after you click away) and resolves ones it is
// already tracking to their final done/failed state. Finished items stay until
// the user clears them. Singleton module state → one poller app-wide.
import { computed, ref } from 'vue'
import { fetchActiveGenerations } from './useChat'

const LS = 'studio.genQueue'
const POLL_MS = 4000

function load() {
  try {
    return JSON.parse(localStorage.getItem(LS)) || []
  } catch {
    return []
  }
}
function persist() {
  try {
    localStorage.setItem(LS, JSON.stringify(entries.value))
  } catch {
    /* storage unavailable */
  }
}

// Each entry is a server descriptor: { media_id, message_id, conversation_id,
// conversation_title, kind, prompt, model, status, file, error, moderated }.
const entries = ref(load())
let timer = null
let starts = 0

async function poll() {
  const known = [...new Set(entries.value.map(e => e.message_id).filter(Boolean))]
  let items
  try {
    items = (await fetchActiveGenerations(known)).items || []
  } catch {
    return // offline / transient — keep the last known state
  }
  const byId = new Map(entries.value.map(e => [e.media_id, e]))
  const returned = new Set(items.map(i => i.media_id))
  const queried = new Set(known)
  for (const it of items) {
    const existing = byId.get(it.media_id)
    if (existing)
      Object.assign(existing, it) // live update (pending → done/failed)
    else if (it.status === 'pending') {
      // A generation we hadn't seen start (maybe from another thread/device).
      entries.value.push(it)
      byId.set(it.media_id, it)
    }
    // Finished items we never tracked are history — don't backfill them.
  }
  // Drop entries whose message was queried but no longer returned (deleted).
  entries.value = entries.value.filter(e => returned.has(e.media_id) || !queried.has(e.message_id))
  persist()
}

export function useGenQueue() {
  function start() {
    starts++
    if (!timer) {
      poll()
      timer = setInterval(poll, POLL_MS)
    }
  }
  function stop() {
    starts = Math.max(0, starts - 1)
    if (starts === 0 && timer) {
      clearInterval(timer)
      timer = null
    }
  }
  const refresh = poll // call after kicking off a generation for instant feedback
  function clearDone() {
    entries.value = entries.value.filter(e => e.status === 'pending')
    persist()
  }
  function clearOne(mediaId) {
    entries.value = entries.value.filter(e => e.media_id !== mediaId)
    persist()
  }
  const pending = computed(() => entries.value.filter(e => e.status === 'pending').length)
  const done = computed(() => entries.value.filter(e => e.status !== 'pending').length)
  return { entries, pending, done, start, stop, refresh, clearDone, clearOne }
}
