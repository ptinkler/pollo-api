import { onBeforeUnmount, onMounted } from 'vue'
import { fetchChatMessage } from './useChat'

const POLL_MS = 5000

// A reply's live stream can drop — a background tab gets throttled or
// frozen, you reload, or you open it mid-reply from elsewhere. The server
// keeps working regardless, so poll such replies until they're done, plus
// any rendering video or retried image.
//
// `messages` / `streamingId`: refs of the shown chat and the reply with a
// live stream; `replace(fresh)` swaps in a fresher copy; `onFinished()` runs
// when something landed (it was billed).
export function useMessagePolling({ messages, streamingId, replace, onFinished }) {
  let timer = null

  function hasPending(m) {
    if (m.status === 'streaming') return m.id !== streamingId.value // no live stream for it
    return !!m.media?.some(x => x.status === 'pending')
  }

  async function pollOnce() {
    const pending = messages.value.filter(hasPending)
    if (!pending.length) return stop()
    let finished = false
    for (const m of pending) {
      try {
        const fresh = await fetchChatMessage(m.id)
        replace(fresh)
        finished ||= !hasPending(fresh)
      } catch {
        /* retry next tick */
      }
    }
    if (finished) onFinished()
  }

  function ensure() {
    if (timer || !messages.value.some(hasPending)) return
    timer = setInterval(pollOnce, POLL_MS)
  }

  function stop() {
    clearInterval(timer)
    timer = null
  }

  // Coming back to the tab: catch up now rather than on the next tick
  function onVisibilityChange() {
    if (document.visibilityState === 'visible' && messages.value.some(hasPending)) {
      pollOnce()
      ensure()
    }
  }

  onMounted(() => document.addEventListener('visibilitychange', onVisibilityChange))
  onBeforeUnmount(() => {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    stop()
  })

  return { ensure, stop }
}
