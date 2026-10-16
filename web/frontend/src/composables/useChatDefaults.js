import { computed, ref } from 'vue'
import { fetchSettings, updateSettings, fetchSpaces, updateSpace } from './useChat'
import { ALL_CHATS } from '../utils/defaults'

// Shared, app-wide state for the two "settings buckets": the global defaults
// (every chat) and each space's own defaults (stacked on top for chats in that
// space). They apply live — a chat uses its defaults plus what's attached to
// it — so `inherited` is what the chat in context gets from them. A module-level singleton so the chat view and
// the characters page read/toggle the same state.
//
// `kind` is one of 'character' | 'instruction' | 'instruction_group'; the
// matching bucket field is `default_${kind}_ids`.

const EMPTY = () => ({ default_character_ids: [], default_instruction_ids: [], default_instruction_group_ids: [] })

const globalSettings = ref(EMPTY())
const spaces = ref([])
const currentSpaceId = ref(null) // the space of the chat currently in context (set by ChatView)
let loaded = false // whether the buckets have been fetched at least once

const key = kind => `default_${kind}_ids`

export function useChatDefaults() {
  const currentSpace = computed(() => spaces.value.find(s => s.id === currentSpaceId.value) || null)
  const spaceById = id => spaces.value.find(s => s.id === id) || null

  // What the chat in context gets from its defaults, per kind: [{ id, from }],
  // `from` naming the bucket ("All chats" wins when an id is in both)
  const inherited = computed(() => {
    const out = {}
    for (const kind of ['character', 'instruction', 'instruction_group']) {
      const seen = new Map()
      for (const id of globalSettings.value[key(kind)]) seen.set(id, ALL_CHATS)
      for (const id of currentSpace.value?.[key(kind)] || []) if (!seen.has(id)) seen.set(id, currentSpace.value.name)
      out[kind] = [...seen].map(([id, from]) => ({ id, from }))
    }
    return out
  })

  async function loadDefaults() {
    try {
      globalSettings.value = { ...EMPTY(), ...(await fetchSettings()) }
    } catch {
      /* 401 handled elsewhere */
    }
    try {
      spaces.value = (await fetchSpaces()).spaces || []
    } catch {
      /* 401 handled elsewhere */
    }
    loaded = true
  }

  // Load once — for views (character editor, media view) that show the toggles
  // without otherwise needing the buckets, so membership shows correctly.
  async function ensureLoaded() {
    if (!loaded) await loadDefaults()
  }

  const inGlobal = (kind, id) => globalSettings.value[key(kind)].includes(id)
  const inSpace = (kind, id) => !!currentSpace.value && currentSpace.value[key(kind)].includes(id)

  function toggled(ids, id) {
    return ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id]
  }

  // Toggles re-read the current bucket from the server before writing, so a
  // stale local copy can never clobber it (the editor may be open in a view
  // that hadn't loaded the buckets).
  async function toggleGlobal(kind, id) {
    const latest = { ...EMPTY(), ...(await fetchSettings()) }
    globalSettings.value = await updateSettings({ ...bucketLists(latest), [key(kind)]: toggled(latest[key(kind)], id) })
  }

  async function toggleSpace(kind, id) {
    const sid = currentSpaceId.value
    if (sid == null) return
    const fresh = (await fetchSpaces()).spaces || []
    spaces.value = fresh
    const space = fresh.find(s => s.id === sid)
    if (!space) return
    const updated = await updateSpace(space.id, {
      name: space.name,
      ...bucketLists(space),
      [key(kind)]: toggled(space[key(kind)], id),
    })
    const i = spaces.value.findIndex(s => s.id === space.id)
    if (i !== -1) spaces.value.splice(i, 1, updated)
  }

  // Where an item is a default: { global, spaceIds }
  function membership(kind, id) {
    return {
      global: globalSettings.value[key(kind)].includes(id),
      spaceIds: spaces.value.filter(s => s[key(kind)].includes(id)).map(s => s.id),
    }
  }

  // Make an item a default exactly where `want` says ({ global, spaceIds }),
  // writing only the buckets that change — each re-read first, as above
  async function setMembership(kind, id, want) {
    const latest = { ...EMPTY(), ...(await fetchSettings()) }
    if (latest[key(kind)].includes(id) !== want.global) {
      const ids = toggled(latest[key(kind)], id)
      globalSettings.value = await updateSettings({ ...bucketLists(latest), [key(kind)]: ids })
    }
    const fresh = (await fetchSpaces()).spaces || []
    for (const space of fresh) {
      if (space[key(kind)].includes(id) === want.spaceIds.includes(space.id)) continue
      const updated = await updateSpace(space.id, {
        name: space.name,
        ...bucketLists(space),
        [key(kind)]: toggled(space[key(kind)], id),
      })
      fresh.splice(fresh.indexOf(space), 1, updated)
    }
    spaces.value = [...fresh]
  }

  // Global ∪ current-space default ids for a kind (de-duped), for seeding
  function defaultIds(kind) {
    const ids = [...globalSettings.value[key(kind)], ...(currentSpace.value ? currentSpace.value[key(kind)] : [])]
    return [...new Set(ids)]
  }

  function setCurrentSpace(id) {
    currentSpaceId.value = id ?? null
  }

  return {
    globalSettings,
    spaces,
    currentSpace,
    currentSpaceId,
    spaceById,
    inherited,
    loadDefaults,
    ensureLoaded,
    inGlobal,
    inSpace,
    toggleGlobal,
    toggleSpace,
    membership,
    setMembership,
    defaultIds,
    setCurrentSpace,
  }
}

// Just the three id-lists of a bucket (drops name/timestamps)
function bucketLists(b) {
  return {
    default_character_ids: b.default_character_ids,
    default_instruction_ids: b.default_instruction_ids,
    default_instruction_group_ids: b.default_instruction_group_ids,
  }
}
