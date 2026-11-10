<script setup>
import { ref, computed } from 'vue'
import { useDropdown } from '../../composables/useDropdown'
import { useModelFavourites } from '../../composables/useModelFavourites'
import { useShowHidden } from '../../composables/useShowHidden'
import { useUncensoredOnly } from '../../composables/useUncensoredOnly'
import { useModelFilters } from '../../composables/useModelFilters'
import ModelFilterPanel from './ModelFilterPanel.vue'
import { PROVIDER_COLOR, TAG_LABELS, tagColor } from '../../composables/modelTags'
import { chatImageModelTakesCharacters } from '../../composables/useCharacters'

const props = defineProps({
  modelValue: { type: String, default: '' },
  models: { type: Array, default: () => [] },
  label: { type: String, required: true },
  icon: { type: String, default: '' },
  kind: { type: String, default: 'text' }, // text | image | video | audio
  loading: { type: Boolean, default: false },
  // Render the trigger as a small text button (e.g. "Try another model…")
  // instead of the labelled picker box, for one-off picks
  triggerText: { type: String, default: '' },
  allowNone: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue'])

const query = ref('')
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
const visibleModels = computed(() =>
  props.models.filter(
    m =>
      m.id === props.modelValue ||
      ((showHidden.value || !m.hidden) && (!uncensoredOnly.value || !uncensoredCount.value || m.uncensored)),
  ),
)

// Providers: Pollo ("pollo/…", billed in Pollo credits), Venice ("venice/…",
// billed to the Venice account) and OpenRouter (everything else).
const ALL_PROVIDERS = {
  pollo: { label: 'Pollo', title: 'Runs on your Pollo account (billed in Pollo credits)' },
  venice: { label: 'Venice', title: 'Runs on your Venice account (billed in Venice credit)' },
  openrouter: { label: 'OpenRouter', title: 'Runs on OpenRouter (billed in OpenRouter credits)' },
}
const providerOf = id => {
  const prefix = (id || '').split('/')[0]
  return prefix === 'pollo' || prefix === 'venice' ? prefix : 'openrouter'
}

const { filters, toggleProvider, toggleTag, clear: clearFilters, hasActive } = useModelFilters()

// Provider facet: which providers the list spans, with counts. Chips are only
// offered when more than one provider is present.
const providerCounts = computed(() => {
  const c = {}
  for (const m of visibleModels.value) {
    const p = providerOf(m.id)
    c[p] = (c[p] || 0) + 1
  }
  return c
})
const providersPresent = computed(() => Object.keys(ALL_PROVIDERS).filter(id => providerCounts.value[id]))
const showProviders = computed(() => providersPresent.value.length > 1)

// Tag facet: the capability tags present across this kind's models, with counts.
const tagCounts = computed(() => {
  const c = {}
  for (const m of visibleModels.value) for (const t of m.tags || []) c[t] = (c[t] || 0) + 1
  return c
})
const tagsPresent = computed(() =>
  Object.keys(TAG_LABELS)
    .filter(s => tagCounts.value[s])
    .map(s => ({ slug: s, label: TAG_LABELS[s], n: tagCounts.value[s], color: tagColor(s) })),
)

const selProviders = computed(() => filters[props.kind].providers)
const selTags = computed(() => filters[props.kind].tags)
// Something other than search/show-hidden is narrowing the list
const anyFilter = computed(() => hasActive(props.kind) || uncensoredOnly.value)

// Facets AND together (provider ∧ tag); within the tag facet a model needs
// only one of the selected tags. The current pick always stays.
function passesFilters(m) {
  if (m.id === props.modelValue) return true
  if (selProviders.value.length && !selProviders.value.includes(providerOf(m.id))) return false
  if (selTags.value.length && !(m.tags || []).some(t => selTags.value.includes(t))) return false
  return true
}

const searched = computed(() => {
  const faceted = visibleModels.value.filter(passesFilters)
  const q = query.value.trim().toLowerCase()
  return q ? faceted.filter(m => m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)) : faceted
})

function clearAll() {
  clearFilters(props.kind)
  uncensoredOnly.value = false
  searchInput.value?.focus()
}

// The filter menu (providers, capabilities, uncensored, show-hidden) sits in
// the pop-up behind the Filters button; the active picks also show as chips
const filtersOpen = ref(false)
const providerFacet = computed(() =>
  showProviders.value
    ? providersPresent.value.map(id => ({
        id,
        ...ALL_PROVIDERS[id],
        n: providerCounts.value[id],
        color: PROVIDER_COLOR[id],
      }))
    : [],
)
const hasFacets = computed(
  () => providerFacet.value.length || tagsPresent.value.length || uncensoredCount.value || hiddenCount.value,
)
const filterCount = computed(() => selProviders.value.length + selTags.value.length + (uncensoredOnly.value ? 1 : 0))
const activeChips = computed(() => [
  ...selProviders.value.map(id => ({
    key: `p-${id}`,
    label: ALL_PROVIDERS[id]?.label || id,
    color: PROVIDER_COLOR[id],
    off: () => toggleProvider(props.kind, id),
  })),
  ...selTags.value.map(slug => ({
    key: `t-${slug}`,
    label: TAG_LABELS[slug] || slug,
    color: tagColor(slug),
    off: () => toggleTag(props.kind, slug),
  })),
  ...(uncensoredOnly.value ? [{ key: 'unc', label: 'Uncensored', off: () => (uncensoredOnly.value = false) }] : []),
])

// Favourites keep the order they were starred in; models that have left
// the catalogue are skipped rather than shown broken
const favouriteModels = computed(() => {
  const byId = new Map(searched.value.map(m => [m.id, m]))
  return (favourites[props.kind] || []).map(id => byId.get(id)).filter(Boolean)
})
const otherModels = computed(() => searched.value.filter(m => !isFavourite(props.kind, m.id)).slice(0, 200))
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
  private: { t: 'private', cls: 'private', title: "Private: runs on Venice's own servers and nothing is stored" },
  anonymized: {
    t: 'anonymized',
    cls: 'anonymized',
    title:
      'Anonymized: Venice passes it to a third-party provider without your identity; that provider may keep the prompts and outputs',
  },
}

// Venice prices: per image, or a quote for a ~5s video at the lowest resolution
const fmtPrice = usd => `$${usd < 0.1 ? usd.toFixed(3).replace(/0$/, '') : usd.toFixed(2)}`

const colorVar = b => (b.color ? { '--b': b.color } : null)
const MAX_INLINE_BADGES = 2 // more than this and a row's badges fold up

// The little labels beside a model: warnings first, then what it can do and costs
function badges(m) {
  const kindBadges = { text: textBadges, image: imageBadges, video: videoBadges }[props.kind] || (() => [])
  const price = props.kind === 'text' ? [] : priceBadge(m)
  return [...flagBadges(m), ...price, ...kindBadges(m), ...tagBadges(m)].filter(Boolean)
}

function flagBadges(m) {
  return [
    // First, so it's the one thing you can't miss
    m.uncensored && { t: 'uncensored', title: UNCENSORED_TITLE, cls: 'uncensored' },
    PRIVACY[m.privacy],
    m.hidden && { t: 'hidden', title: m.hidden, cls: 'hidden' },
  ]
}

function textBadges(m) {
  const p = perMillion(m.prompt_price)
  const c = perMillion(m.completion_price)
  return [p && { t: p === 'free' ? 'free' : `${p}/${c}`, title: 'Input/output price per million tokens', cls: 'price' }]
}

function priceBadge(m) {
  if (!m.price) return []
  const basis = m.price.basis
  const title =
    props.kind === 'video'
      ? `Quoted price for ${basis || 'a default video'} (longer or sharper costs more)`
      : `Price per image${basis ? ` (${basis})` : ''}`
  return [{ t: fmtPrice(m.price.usd), title, cls: 'price' }]
}

function imageBadges(m) {
  return [
    m.conversational && {
      t: 'context',
      title: 'Sees the conversation (text and earlier images), like the Gemini app',
      cls: 'context',
    },
    chatImageModelTakesCharacters(m) && {
      t: 'characters',
      title: 'Can use characters (sends their reference images)',
      cls: 'characters',
    },
  ]
}
function videoBadges(m) {
  const d = m.durations
  return [d?.length && { t: `${Math.min(...d)}–${Math.max(...d)}s`, title: 'Durations', cls: 'duration' }]
}

// What each model can do, from the backend's capability tags; each tag has its own colour
const tagBadges = m =>
  (m.tags || []).map(slug => ({
    t: TAG_LABELS[slug] || slug,
    title: `Capability: ${TAG_LABELS[slug] || slug}`,
    cls: 'tag',
    color: tagColor(slug),
  }))

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

const { open, root, toggle, close } = useDropdown({
  focus: searchInput,
  onOpen() {
    query.value = ''
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true) // any scrolling ancestor moves the button
  },
  onClose() {
    filtersOpen.value = false
    window.removeEventListener('resize', place)
    window.removeEventListener('scroll', place, true)
  },
})

// A click anywhere in the pop-up but the filter menu / its button closes the menu
function closeFiltersOutside(e) {
  if (filtersOpen.value && !e.target.closest('.fpanel, .filters-btn')) filtersOpen.value = false
}

// A model, or null for none
function pick(m) {
  emit('update:modelValue', m?.id ?? '')
  close()
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    if (filtersOpen.value) filtersOpen.value = false
    else close()
  }
  if (e.key === 'Enter' && filtered.value.length) pick(filtered.value[0])
}
</script>

<template>
  <div ref="root" class="model-picker">
    <button v-if="triggerText" type="button" class="picker-trigger" :class="{ active: open }" @click="toggle">
      {{ triggerText }}
    </button>
    <button
      v-else
      type="button"
      class="picker-btn"
      :class="{ active: open }"
      :title="modelValue || 'None selected'"
      @click="toggle"
    >
      <span class="picker-icon">{{ icon }}</span>
      <span class="picker-text">
        <span class="picker-label"
          >{{ label
          }}<span
            v-if="showProviders && modelValue"
            class="provider-tag"
            :class="providerOf(modelValue)"
            :title="ALL_PROVIDERS[providerOf(modelValue)].title"
          >
            · {{ ALL_PROVIDERS[providerOf(modelValue)].label }}</span
          ></span
        >
        <span class="picker-value">
          <template v-if="loading">Loading…</template>
          <template v-else>{{ current?.name || 'None' }}</template>
          <span v-if="!loading && current?.uncensored" class="item-badge uncensored picked" :title="UNCENSORED_TITLE"
            >uncensored</span
          >
          <span
            v-if="!loading && PRIVACY[current?.privacy]"
            class="item-badge picked"
            :class="PRIVACY[current.privacy].cls"
            :title="PRIVACY[current.privacy].title"
            >{{ PRIVACY[current.privacy].t }}</span
          >
        </span>
      </span>
      <span class="chev">▾</span>
    </button>

    <div
      v-if="open"
      class="picker-pop"
      :class="{ 'filters-open': filtersOpen }"
      :style="popStyle"
      @mousedown="closeFiltersOutside"
    >
      <div class="picker-searchrow">
        <input
          ref="searchInput"
          v-model="query"
          class="picker-search"
          :placeholder="`Search ${visibleModels.length} ${label.toLowerCase()} models…`"
          @keydown="onKeydown"
        />
        <button
          v-if="hasFacets"
          type="button"
          class="filters-btn"
          :class="{ on: filtersOpen || anyFilter }"
          title="Filters"
          aria-haspopup="true"
          :aria-expanded="filtersOpen"
          @click="filtersOpen = !filtersOpen"
        >
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
          >
            <path d="M4 7h16M7 12h10M10 17h4" />
          </svg>
          <span v-if="filterCount" class="filters-n">{{ filterCount }}</span>
        </button>
      </div>
      <ModelFilterPanel
        v-if="filtersOpen && hasFacets"
        v-model:uncensored-only="uncensoredOnly"
        v-model:show-hidden="showHidden"
        :providers="providerFacet"
        :tags="tagsPresent"
        :sel-providers="selProviders"
        :sel-tags="selTags"
        :uncensored-count="uncensoredCount"
        :hidden-count="hiddenCount"
        :any-filter="anyFilter"
        @toggle-provider="id => toggleProvider(kind, id)"
        @toggle-tag="slug => toggleTag(kind, slug)"
        @clear="clearAll"
      />
      <div v-if="activeChips.length" class="picker-active">
        <button
          v-for="c in activeChips"
          :key="c.key"
          type="button"
          class="achip"
          :style="colorVar(c)"
          :title="`Remove ${c.label}`"
          @click="c.off()"
        >
          {{ c.label }} ✕
        </button>
      </div>
      <div class="picker-list">
        <template v-for="section in sections" :key="section.id">
          <div v-if="section.label" class="picker-section">{{ section.label }}</div>
          <button
            v-if="section.id === 'all' && kind !== 'text' && allowNone && !query"
            type="button"
            class="picker-item"
            :class="{ selected: !modelValue }"
            @click="pick(null)"
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
              <span
                v-if="showProviders"
                class="row-provider"
                :class="providerOf(m.id)"
                :title="ALL_PROVIDERS[providerOf(m.id)].title"
                >{{ ALL_PROVIDERS[providerOf(m.id)].label }}</span
              >
              <span class="item-badges" :class="{ collapsed: badges(m).length > MAX_INLINE_BADGES }">
                <!-- Long lists fold into coloured dots; hovering unfolds the labels -->
                <span v-if="badges(m).length > MAX_INLINE_BADGES" class="badge-dots" aria-hidden="true">
                  <span v-for="b in badges(m)" :key="b.t" class="dot" :class="b.cls" :style="colorVar(b)"></span>
                  <span class="dots-n">{{ badges(m).length }}</span>
                </span>
                <span class="badge-list">
                  <span
                    v-for="b in badges(m)"
                    :key="b.t"
                    class="item-badge"
                    :class="b.cls"
                    :style="colorVar(b)"
                    :title="b.title"
                    >{{ b.t }}</span
                  >
                </span>
              </span>
              <button
                type="button"
                class="star"
                :class="{ on: isFavourite(kind, m.id) }"
                :title="isFavourite(kind, m.id) ? 'Remove from favourites' : 'Add to favourites'"
                :aria-pressed="isFavourite(kind, m.id)"
                @click.stop="toggleFavourite(kind, m.id)"
                @keydown.enter.stop
              >
                {{ isFavourite(kind, m.id) ? '★' : '☆' }}
              </button>
            </span>
            <span class="item-id">{{ m.id }}</span>
          </div>
        </template>
        <div v-if="!filtered.length" class="picker-empty">
          <template v-if="query">No models match “{{ query }}”</template>
          <template v-else-if="anyFilter">No models match the current filters</template>
          <template v-else>No models available</template>
          <button v-if="anyFilter" type="button" class="tab-hint" @click="clearAll">Clear filters →</button>
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
  background: var(--spanel2);
  border: 1px solid var(--sborder);
  border-radius: var(--r);
  padding: 5px 10px;
  color: var(--sfg);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.12s;
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
  background: var(--spanel2);
  border: 1px solid var(--sborder);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-pop);
  overflow: hidden;
}

.picker-search {
  flex-shrink: 0;
}

.picker-search {
  width: 100%;
  border: none;
  border-bottom: 1px solid var(--sborder);
  border-radius: 0;
  padding: 9px 12px;
  background: transparent;
  box-shadow: none;
}

.provider-tag {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
}

.provider-tag.pollo {
  color: var(--p-pollo);
}

.provider-tag.venice {
  color: var(--p-venice);
}

.provider-tag.openrouter {
  color: var(--p-openrouter);
}

/* Provider colour on the closed-picker tag reused by the row provider label */
.row-provider {
  flex-shrink: 0;
  font-size: 0.62rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text2);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 0 5px;
  line-height: 1.5;
}
.row-provider.pollo {
  color: var(--p-pollo);
  border-color: color-mix(in srgb, var(--p-pollo) 45%, transparent);
}
.row-provider.venice {
  color: var(--p-venice);
  border-color: color-mix(in srgb, var(--p-venice) 45%, transparent);
}
.row-provider.openrouter {
  color: var(--p-openrouter);
  border-color: color-mix(in srgb, var(--p-openrouter) 45%, transparent);
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

/* Search + Filters button on one row; the menu itself is ModelFilterPanel */
.picker-searchrow {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
}
.picker-searchrow .picker-search {
  flex: 1;
  min-width: 0;
  border-bottom: none;
}
.filters-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin: 6px 8px 6px 0;
  padding: 0 10px;
  background: none;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text2);
  cursor: pointer;
}
.filters-btn:hover,
.filters-btn.on {
  color: var(--text);
  border-color: var(--accent);
}
.filters-n {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--accent);
}
/* Room for the menu even when only a few models are listed */
.picker-pop.filters-open {
  min-height: 330px;
}
/* The active picks, as removable chips */
.picker-active {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.achip {
  --b: var(--accent);
  padding: 2px 9px;
  border: 1px solid color-mix(in srgb, var(--b) 55%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--b) 16%, transparent);
  color: var(--b);
  font-weight: 600;
  font-size: 0.73rem;
  cursor: pointer;
}
.achip:hover {
  background: color-mix(in srgb, var(--b) 28%, transparent);
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
  background: var(--shover);
}

.picker-item.selected {
  background: var(--saccent-soft);
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

.picker-item {
  position: relative;
}
.item-badges {
  position: relative;
  flex-shrink: 0;
  margin-left: auto;
}
.badge-list {
  display: flex;
  gap: 4px;
}
/* Folded: just coloured dots (one per badge) + a count; the labels open on hover */
.item-badges.collapsed .badge-list {
  display: none;
  position: absolute;
  top: 100%;
  right: 0;
  z-index: 5;
  flex-wrap: wrap;
  justify-content: flex-end;
  width: max-content;
  max-width: 300px;
  margin-top: 2px;
  padding: 6px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.item-badges.collapsed:hover .badge-list,
.item-badges.collapsed:focus-within .badge-list {
  display: flex;
}
.badge-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--surface2);
  cursor: default;
}
.item-badges.collapsed:hover .badge-dots {
  outline: 1px solid var(--border);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.dots-n {
  margin-left: 2px;
  font-size: 0.65rem;
  color: var(--text2);
}

/* Every badge is the same pill: its hue comes from --b alone (text colour, tinted
   fill, and the folded dot), so they stay consistent whatever they say */
.item-badge {
  --b: var(--text2);
  font-size: 0.65rem;
  font-weight: 600;
  line-height: 1.5;
  padding: 1px 7px;
  border-radius: 6px;
  white-space: nowrap;
  color: var(--b);
  background: color-mix(in srgb, var(--b) 16%, transparent);
}
.dot {
  background: var(--b, var(--text2));
}
:is(.item-badge, .dot).uncensored {
  --b: #ff8a6e;
}
:is(.item-badge, .dot).private {
  --b: #4fd1a5;
}
:is(.item-badge, .dot).anonymized {
  --b: var(--text2);
}
:is(.item-badge, .dot).characters {
  --b: #e68fd0; /* pastel magenta */
}
:is(.item-badge, .dot).context {
  --b: #5fb0f0; /* pastel sky blue */
}
:is(.item-badge, .dot).duration {
  --b: #3fcabf; /* pastel teal */
}
:is(.item-badge, .dot).price {
  --b: #e8a33d;
}
:is(.item-badge, .dot).hidden {
  --b: #c9a227;
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
  transition:
    opacity 0.15s,
    color 0.15s;
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
