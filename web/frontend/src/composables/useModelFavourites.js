import { reactive } from 'vue'

// Favourite model ids per picker kind (text | image | video). Per-browser
// convenience, so localStorage is enough; shared across all pickers.
const STORE_KEY = 'chat.favourites'

function load() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY)) || {}
    return { text: raw.text || [], image: raw.image || [], video: raw.video || [] }
  } catch {
    return { text: [], image: [], video: [] }
  }
}

const favourites = reactive(load())

function save() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(favourites))
  } catch { /* storage unavailable — favourites last for this session only */ }
}

export function useModelFavourites() {
  const isFavourite = (kind, id) => favourites[kind]?.includes(id) ?? false

  function toggleFavourite(kind, id) {
    const list = favourites[kind] || (favourites[kind] = [])
    const i = list.indexOf(id)
    if (i === -1) list.push(id)
    else list.splice(i, 1)
    save()
  }

  return { favourites, isFavourite, toggleFavourite }
}
