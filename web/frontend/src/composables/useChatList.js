import { computed, reactive, ref, watch } from 'vue'
import { deleteConversation, fetchConversations, patchConversation } from './useChat'

// The chat list: pinned and recent chats (grouped by date), search, and the
// actions on a chat. Returned reactive, so templates can bind its fields.

const DAY_MS = 24 * 60 * 60 * 1000
const SEARCH_DELAY_MS = 250

function dateGroups(conversations) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const groups = [
    { label: 'Pinned', items: [] },
    { label: 'Today', from: today, items: [] },
    { label: 'Yesterday', from: today - DAY_MS, items: [] },
    { label: 'Previous 7 days', from: today - 7 * DAY_MS, items: [] },
    { label: 'Previous 30 days', from: today - 30 * DAY_MS, items: [] },
    { label: 'Older', from: -Infinity, items: [] },
  ]
  for (const c of conversations) {
    const t = Date.parse(c.updated_at) || 0
    const group = c.pinned ? groups[0] : groups.find(g => g.from !== undefined && t >= g.from)
    group.items.push(c)
  }
  return groups.filter(g => g.items.length)
}

export function useChatList(showToast) {
  const conversations = ref([])
  const more = ref(false) // older chats beyond the list's limit
  const search = ref('')
  const searchResults = ref(null) // null = not searching
  const groups = computed(() =>
    searchResults.value ? [{ label: null, items: searchResults.value }] : dateGroups(conversations.value),
  )
  // Every shown copy of a chat (the list's and the search results')
  const copies = id => [...conversations.value, ...(searchResults.value || [])].filter(c => c.id === id)

  let searchTimer = null
  watch(search, q => {
    clearTimeout(searchTimer)
    if (!q.trim()) {
      searchResults.value = null
      return
    }
    searchTimer = setTimeout(async () => {
      try {
        const { conversations: found } = await fetchConversations(q.trim())
        if (search.value === q) searchResults.value = found
      } catch (e) {
        showToast(e.message, 'error')
      }
    }, SEARCH_DELAY_MS)
  })

  function setSearch(q) {
    search.value = q
  }

  async function load() {
    try {
      const data = await fetchConversations()
      conversations.value = data.conversations
      more.value = !!data.more
    } catch {
      /* shown elsewhere via 401 prompt */
    }
  }

  function add(conv) {
    conversations.value = [conv, ...conversations.value]
  }

  // A chat was just used: to the top, into "Today"
  function bump(id) {
    const i = conversations.value.findIndex(c => c.id === id)
    if (i === -1) return
    const [c] = conversations.value.splice(i, 1)
    c.updated_at = new Date().toISOString()
    conversations.value.unshift(c)
  }

  function setTitle(id, title) {
    for (const c of copies(id)) c.title = title
  }

  async function togglePin(c) {
    try {
      const { pinned } = await patchConversation(c.id, { pinned: !c.pinned })
      for (const x of copies(c.id)) x.pinned = pinned
      // The server lists pinned chats first; keep the rest in their order
      conversations.value = [
        ...conversations.value.filter(x => x.pinned),
        ...conversations.value.filter(x => !x.pinned),
      ]
    } catch (e) {
      showToast(`Pin failed: ${e.message}`, 'error')
    }
  }

  // The new title, or null if not renamed
  async function rename(c) {
    const title = prompt('Rename chat', c.title)
    if (!title || title === c.title) return null
    try {
      const updated = await patchConversation(c.id, { title })
      setTitle(c.id, updated.title)
      return updated.title
    } catch (e) {
      showToast(`Rename failed: ${e.message}`, 'error')
      return null
    }
  }

  // Whether it was deleted
  async function remove(c) {
    if (!confirm(`Delete “${c.title}” and its images/videos?`)) return false
    try {
      await deleteConversation(c.id)
    } catch (e) {
      showToast(`Delete failed: ${e.message}`, 'error')
      return false
    }
    conversations.value = conversations.value.filter(x => x.id !== c.id)
    if (searchResults.value) searchResults.value = searchResults.value.filter(x => x.id !== c.id)
    return true
  }

  return reactive({
    conversations,
    more,
    search,
    searchResults,
    groups,
    setSearch,
    load,
    add,
    bump,
    setTitle,
    togglePin,
    rename,
    remove,
  })
}
