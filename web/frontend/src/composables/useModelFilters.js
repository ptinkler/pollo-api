import { reactive } from 'vue'

// Per-kind model-picker filters: which providers and capability tags the list
// is narrowed to. Multi-select; an empty list means "all". A per-browser
// convenience (like favourites / uncensored-only), so localStorage is enough
// and it's shared across every picker of the same kind.
const KEY = 'models.filters'

function blank() {
  return { providers: [], tags: [] }
}

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY)) || {}
    const one = x => ({ providers: x?.providers || [], tags: x?.tags || [] })
    return { text: one(raw.text), image: one(raw.image), video: one(raw.video), audio: one(raw.audio) }
  } catch {
    return { text: blank(), image: blank(), video: blank(), audio: blank() }
  }
}

const filters = reactive(load())

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(filters))
  } catch {
    /* storage unavailable — filters last for this session only */
  }
}

function toggleIn(list, value) {
  const i = list.indexOf(value)
  if (i === -1) list.push(value)
  else list.splice(i, 1)
}

export function useModelFilters() {
  const toggleProvider = (kind, id) => {
    toggleIn(filters[kind].providers, id)
    save()
  }
  const toggleTag = (kind, slug) => {
    toggleIn(filters[kind].tags, slug)
    save()
  }
  const clear = kind => {
    filters[kind].providers.splice(0)
    filters[kind].tags.splice(0)
    save()
  }
  const hasActive = kind => filters[kind].providers.length > 0 || filters[kind].tags.length > 0

  return { filters, toggleProvider, toggleTag, clear, hasActive }
}
