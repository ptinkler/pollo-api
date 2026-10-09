<script setup>
import { ref, computed, nextTick, onBeforeUnmount } from 'vue'
import { useModelFavourites } from '../../composables/useModelFavourites'
import { useShowHidden } from '../../composables/useShowHidden'
import { useUncensoredOnly } from '../../composables/useUncensoredOnly'
import { chatImageModelTakesCharacters } from '../../composables/useCharacters'

const props = defineProps({
  modelValue: { type: String, default: '' },
  models: { type: Array, default: () => [] },
  label: { type: String, required: true },
  icon: { type: String, default: '' },
  kind: { type: String, default: 'text' },  // text | image | video
  loading: { type: Boolean, default: false },
  // Render the trigger as a small text button (e.g. "Try another model…")
  // instead of the labelled picker box, for one-off picks
  triggerText: { type: String, default: '' },
  allowNone: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const query = ref('')
const root = ref(null)
const searchInput = ref(null)

const current = computed(() => props.models.find(m => m.id === props.modelValue))

const { favourites, isFavourite, toggleFavourite } = useModelFavourites()

// Hidden models (not enabled for this API key, or retired) only show behind "Show
// hidden" — except the current pick, so the picker never loses it
const { showHidden } = useShowHidden()
const hiddenCount = computed(() => props.models.filter(m => m.hidden).length)
// "Uncensored only" narrows the list the same way (the current pick always stays)
const { uncensoredOnly } = useUncensoredOnly()
const uncensoredCount = computed(() => props.models.filter(m => m.uncensored && (showHidden.value || !m.hidden)).length)
const visibleModels = computed(() => props.models.filter(m => m.id === props.modelValue || (
  (showHidden.value || !m.hidden) && (!uncensoredOnly.value || !uncensoredCount.value || m.uncensored))))

// ── Provider tabs: Pollo ("pollo/…", billed in Pollo credits), Venice
// ("venice/…", billed to the Venice account) and OpenRouter. Only shown when
// the catalogue has more than one; each tab only when it has models.
const ALL_PROVIDERS = {
  pollo: { label: 'Pollo', title: 'Runs on your Pollo account (billed in Pollo credits)' },
  venice: { label: 'Venice', title: 'Runs on your Venice account (billed in Venice credit)' },
  openrouter: { label: 'OpenRouter', title: 'Runs on OpenRouter (billed in OpenRouter credits)' },
}
const providerOf = (id) => {
  const prefix = (id || '').split('/')[0]
  return prefix === 'pollo' || prefix === 'venice' ? prefix : 'openrouter'
}
const PROVIDERS = computed(() => Object.fromEntries(
  Object.entries(ALL_PROVIDERS).filter(([id]) => visibleModels.value.some(m => providerOf(m.id) === id))))
const showTabs = computed(() => Object.keys(PROVIDERS.value).length > 1)
const tab = ref(Object.keys(ALL_PROVIDERS)[0])

const searched = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q
    ? visibleModels.value.filter(m => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q))
    : visibleModels.value
})
const matches = computed(() =>
  showTabs.value ? searched.value.filter(m => providerOf(m.id) === tab.value) : searched.value)
const tabCounts = computed(() => {
  const counts = Object.fromEntries(Object.keys(ALL_PROVIDERS).map(id => [id, 0]))
  for (const m of searched.value) counts[providerOf(m.id)]++
  return counts
})
// Where a search that found nothing here does find something
const otherTab = computed(() =>
  Object.keys(PROVIDERS.value).find(id => id !== tab.value && tabCounts.value[id]) || null)

// Favourites keep the order they were starred in; models that have left
// the catalogue are skipped rather than shown broken
const favouriteModels = computed(() => {
  const byId = new Map(matches.value.map(m => [m.id, m]))
  return (favourites[props.kind] || []).map(id => byId.get(id)).filter(Boolean)
})
const otherModels = computed(() =>
  matches.value.filter(m => !isFavourite(props.kind, m.id)).slice(0, 200))
const filtered = computed(() => [...favouriteModels.value, ...otherModels.value])

const sections = computed(() => {
  const out = []
  if (favouriteModels.value.length) out.push({ id: 'fav', label: '★ Favourites', models: favouriteModels.value })
  // Only label the main list when there's a favourites list to tell it apart from
  out.push({ id: 'all', label: favouriteModels.value.length ? 'All models' : '', models: otherModels.value })
  return out
})

function perMillion(price) {
  const n = Number(price)
  if (!price || Number.isNaN(n)) return null
  if (n === 0) return 'free'
  const v = n * 1e6
  return `$${v < 1 ? v.toFixed(2) : v.toFixed(v < 10 ? 1 : 0)}`
}

const UNCENSORED_TITLE = 'Uncensored: the provider marks this model as having no content filtering'

// Venice's privacy levels
const PRIVACY = {
  private: { t: '🔒 private', cls: 'private',
    title: 'Private: runs on Venice\'s own servers and nothing is stored' },
  anonymized: { t: 'anonymized', cls: 'anonymized',
    title: 'Anonymized: Venice passes it to a third-party provider without your identity; that provider may keep the prompts and outputs' },
}

// Venice prices: per image, or a quote for a ~5s video at the lowest resolution
const fmtPrice = (usd) => `$${usd < 0.1 ? usd.toFixed(3).replace(/0$/, '') : usd.toFixed(2)}`

function badges(m) {
  const out = []
  // First, so it's the one thing you can't miss
  if (m.uncensored) out.push({ t: '🔞 uncensored', title: UNCENSORED_TITLE, cls: 'uncensored' })
  if (PRIVACY[m.privacy]) out.push(PRIVACY[m.privacy])
  if (m.hidden) out.push({ t: 'hidden', title: m.hidden })
  if (props.kind === 'text') {
    if (m.input_modalities?.includes('image')) out.push({ t: 'vision', title: 'Accepts images' })
    if (m.supports_tools) out.push({ t: 'tools', title: 'Can create images/videos in Auto mode' })
    const p = perMillion(m.prompt_price)
    const c = perMillion(m.completion_price)
    if (p) out.push({ t: p === 'free' ? 'free' : `${p}/${c}`, title: 'Input/output price per million tokens' })
  } else if (m.price) {
    out.push({ t: fmtPrice(m.price.usd), title: props.kind === 'video'
      ? `Quoted price for ${m.price.basis || 'a default video'} (longer or sharper costs more)`
      : `Price per image${m.price.basis ? ` (${m.price.basis})` : ''}` })
  }
  if (props.kind === 'image') {
    if (m.conversational) out.push({ t: 'context', title: 'Sees the conversation (text and earlier images), like the Gemini app' })
    else if (m.input_modalities?.includes('image')) out.push({ t: 'edits', title: 'Takes reference images (tends to edit them)' })
    if (chatImageModelTakesCharacters(m)) out.push({ t: '👤', title: 'Can use characters (sends their reference images)' })
  } else if (props.kind === 'video') {
    const FAMILY = {
      reference: 'refs→vid', frames: 'first+last', angles: 'multi-angle',
      video: 'vid→vid', motion: 'motion', upscale: 'upscale',
    }
    if (FAMILY[m.family]) out.push({ t: FAMILY[m.family], title: m.family_hint })
    else if (m.frame_images?.includes('first_frame')) out.push({ t: 'img→vid', title: 'Can animate an image' })
    if (m.durations?.length) out.push({ t: `${Math.min(...m.durations)}–${Math.max(...m.durations)}s`, title: 'Durations' })
    if (m.generate_audio) out.push({ t: 'audio', title: 'Can generate audio' })
  }
  return out
}

function onDocClick(e) {
  if (root.value && !root.value.contains(e.target)) close()
}

// The pop-up is position: fixed, placed next to its button, so a scrolling
// or narrow container (the chat sidebar) can't clip it. It opens upwards
// when there's more room above, and never runs off the window.
const popStyle = ref({})
function place() {
  if (!root.value) return
  const r = root.value.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const width = Math.min(420, vw - 16)
  const left = Math.max(8, Math.min(r.left, vw - width - 8))
  const below = vh - r.bottom - 14
  const above = r.top - 14
  const up = below < 320 && above > below
  popStyle.value = {
    left: `${left}px`,
    width: `${width}px`,
    maxHeight: `${Math.max(180, up ? above : below)}px`,
    ...(up ? { bottom: `${vh - r.top + 6}px` } : { top: `${r.bottom + 6}px` }),
  }
}

async function toggle() {
  if (open.value) return close()
  open.value = true
  query.value = ''
  // Open on the tab holding the current pick, so it's in view
  if (props.modelValue) tab.value = providerOf(props.modelValue)
  else if (!PROVIDERS.value[tab.value]) tab.value = Object.keys(PROVIDERS.value)[0] || tab.value
  place()
  document.addEventListener('mousedown', onDocClick)
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)   // any scrolling ancestor moves the button
  await nextTick()
  searchInput.value?.focus()
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onDocClick)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
}

function pick(m) {
  emit('update:modelValue', m.id)
  close()
}

function onKeydown(e) {
  if (e.key === 'Escape') close()
  if (e.key === 'Enter' && filtered.value.length) pick(filtered.value[0])
}

onBeforeUnmount(close)
</script>

<template>
  <div ref="root" class="model-picker">
    <button v-if="triggerText" type="button" class="picker-trigger" :class="{ active: open }" @click="toggle">
      {{ triggerText }}
    </button>
    <button v-else type="button" class="picker-btn" :class="{ active: open }" @click="toggle" :title="modelValue || 'None selected'">
      <span class="picker-icon">{{ icon }}</span>
      <span class="picker-text">
        <span class="picker-label">{{ label }}<span
          v-if="showTabs && modelValue" class="provider-tag" :class="providerOf(modelValue)"
          :title="ALL_PROVIDERS[providerOf(modelValue)].title"> · {{ ALL_PROVIDERS[providerOf(modelValue)].label }}</span></span>
        <span class="picker-value">
          <template v-if="loading">Loading…</template>
          <template v-else>{{ current?.name || modelValue || 'None' }}</template>
          <span v-if="!loading && current?.uncensored" class="item-badge uncensored picked" :title="UNCENSORED_TITLE">🔞 uncensored</span>
          <span v-if="!loading && PRIVACY[current?.privacy]" class="item-badge picked" :class="PRIVACY[current.privacy].cls"
                :title="PRIVACY[current.privacy].title">{{ PRIVACY[current.privacy].t }}</span>
        </span>
      </span>
      <span class="chev">▾</span>
    </button>

    <div v-if="open" class="picker-pop" :style="popStyle">
      <input
        ref="searchInput"
        v-model="query"
        class="picker-search"
        :placeholder="`Search ${visibleModels.length} ${label.toLowerCase()} models…`"
        @keydown="onKeydown"
      />
      <div v-if="showTabs" class="picker-tabs" role="tablist">
        <button
          v-for="(p, id) in PROVIDERS"
          :key="id"
          type="button"
          role="tab"
          class="picker-tab"
          :class="[id, { active: tab === id }]"
          :aria-selected="tab === id"
          :title="p.title"
          @click="tab = id; searchInput?.focus()"
        >{{ p.label }} <span class="tab-count">{{ tabCounts[id] }}</span></button>
      </div>
      <label v-if="uncensoredCount" class="show-hidden uncensored-only" title="Only list models marked uncensored">
        <input v-model="uncensoredOnly" type="checkbox" @change="searchInput?.focus()" />
        🔞 Uncensored only ({{ uncensoredCount }})
      </label>
      <label v-if="hiddenCount" class="show-hidden" title="Models left out of the list: not enabled for this API key, or retired">
        <input v-model="showHidden" type="checkbox" @change="searchInput?.focus()" />
        Show hidden ({{ hiddenCount }})
      </label>
      <div class="picker-list">
        <template v-for="section in sections" :key="section.id">
          <div v-if="section.label" class="picker-section">{{ section.label }}</div>
          <button
            v-if="section.id === 'all' && kind !== 'text' && allowNone && !query"
            type="button"
            class="picker-item"
            :class="{ selected: !modelValue }"
            @click="emit('update:modelValue', ''); close()"
          >
            <span class="item-name">None</span>
            <span class="item-id">Disable {{ kind }} generation</span>
          </button>
          <div
            v-for="m in section.models"
            :key="m.id"
            role="button"
            tabindex="0"
            class="picker-item"
            :class="{ selected: m.id === modelValue }"
            @click="pick(m)"
            @keydown.enter.prevent="pick(m)"
          >
            <span class="item-row">
              <span class="item-name">{{ m.name }}</span>
              <span class="item-badges">
                <span v-for="b in badges(m)" :key="b.t" class="item-badge" :class="b.cls" :title="b.title">{{ b.t }}</span>
              </span>
              <button
                type="button"
                class="star"
                :class="{ on: isFavourite(kind, m.id) }"
                :title="isFavourite(kind, m.id) ? 'Remove from favourites' : 'Add to favourites'"
                :aria-pressed="isFavourite(kind, m.id)"
                @click.stop="toggleFavourite(kind, m.id)"
                @keydown.enter.stop"
              >{{ isFavourite(kind, m.id) ? '★' : '☆' }}</button>
            </span>
            <span class="item-id">{{ m.id }}</span>
          </div>
        </template>
        <div v-if="!filtered.length" class="picker-empty">
          No {{ showTabs ? ALL_PROVIDERS[tab].label + ' ' : '' }}models match “{{ query }}”
          <button v-if="showTabs && otherTab" type="button" class="tab-hint" @click="tab = otherTab">
            {{ tabCounts[otherTab] }} match{{ tabCounts[otherTab] === 1 ? '' : 'es' }} in {{ ALL_PROVIDERS[otherTab].label }} →
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-picker {
  position: relative;
  min-width: 0;
}

.picker-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 6px 10px;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s;
}

.picker-trigger {
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 10px;
  color: var(--text);
  font-size: 0.78rem;
  cursor: pointer;
}

.picker-trigger:hover,
.picker-trigger.active {
  border-color: var(--accent);
}

.picker-btn:hover,
.picker-btn.active {
  border-color: var(--accent);
}

.picker-icon {
  font-size: 1rem;
}

.picker-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.picker-label {
  font-size: 0.65rem;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.picker-value {
  font-size: 0.85rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chev {
  color: var(--text2);
  font-size: 0.75rem;
}

.picker-pop {
  position: fixed;
  z-index: 100;
  width: min(420px, 92vw);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.picker-search,
.picker-tabs,
.show-hidden {
  flex-shrink: 0;
}

.picker-search {
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--border);
  border-radius: 0;
  padding: 10px 12px;
  background: var(--surface);
}

.picker-tabs {
  display: flex;
  gap: 4px;
  padding: 6px 6px 0;
  border-bottom: 1px solid var(--border);
}

.picker-tab {
  flex: 1;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 6px 8px 8px;
  color: var(--text2);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
}

.picker-tab:hover {
  color: var(--text);
}

.picker-tab.active.pollo {
  color: var(--accent2);
  border-bottom-color: var(--accent2);
}

.picker-tab.active.venice {
  color: #e8a33d;
  border-bottom-color: #e8a33d;
}

.picker-tab.active.openrouter {
  color: var(--text);
  border-bottom-color: var(--text);
}

.tab-count {
  font-weight: 400;
  font-size: 0.7rem;
  opacity: 0.7;
}

.provider-tag {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
}

.provider-tag.pollo {
  color: var(--accent2);
}

.provider-tag.venice {
  color: #e8a33d;
}

.tab-hint {
  display: block;
  margin: 8px auto 0;
  background: none;
  border: none;
  color: var(--accent2);
  font-size: 0.8rem;
  cursor: pointer;
}

.uncensored-only {
  color: #ff8a6e;
}

.show-hidden {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 0.75rem;
  color: var(--text2);
  cursor: pointer;
}

.picker-list {
  max-height: 360px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 4px;
}

.picker-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  background: none;
  border: none;
  border-radius: 8px;
  padding: 7px 10px;
  color: var(--text);
  cursor: pointer;
  text-align: left;
}

.picker-item:hover {
  background: var(--surface2);
}

.picker-item.selected {
  background: rgba(108, 92, 231, 0.18);
}

.item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.item-name {
  font-size: 0.87rem;
}

.item-id {
  font-size: 0.72rem;
  color: var(--text2);
  font-family: monospace;
}

.item-badges {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  margin-left: auto;
}

.item-badge {
  font-size: 0.65rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface2);
  color: var(--accent2);
}

.item-badge.uncensored {
  background: rgba(225, 112, 85, 0.18);
  color: #ff8a6e;
  font-weight: 600;
}

.item-badge.private {
  background: rgba(0, 184, 148, 0.16);
  color: #4fd1a5;
}

.item-badge.anonymized {
  color: var(--text2);
}

.item-badge.picked {
  margin-left: 6px;
  vertical-align: middle;
}

.picker-section {
  padding: 8px 10px 4px;
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text2);
}

.picker-section:not(:first-child) {
  margin-top: 4px;
  border-top: 1px solid var(--border);
  padding-top: 10px;
}

.star {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text2);
  font-size: 1rem;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.45;
  transition: opacity 0.15s, color 0.15s;
}

.picker-item:hover .star,
.star:focus-visible {
  opacity: 1;
}

.star:hover {
  color: var(--yellow);
}

.star.on {
  color: var(--yellow);
  opacity: 1;
}

.picker-empty {
  padding: 16px;
  text-align: center;
  color: var(--text2);
  font-size: 0.85rem;
}
</style>
