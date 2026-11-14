<script setup>
import { computed, ref } from 'vue'
import { characterAvatar } from '../../composables/useCharacters'
import { defaultIcon, defaultTitle as fromTitle } from '../../utils/defaults'
import PickDialog from '../PickDialog.vue'

// Attached characters as chips, plus a dialog to pick more (a grid of
// pictures: names aren't unique, so a chat's own "Linh" and a library "Linh"
// are told apart by face and badge). Editing and creating happen in
// CharacterEditor; this only emits 'edit' / 'create'.
const props = defineProps({
  modelValue: { type: Array, default: () => [] }, // attached character ids
  characters: { type: Array, default: () => [] }, // what can be attached
  allowCreate: { type: Boolean, default: true },
  createLabel: { type: String, default: '＋ New character' },
  // Attached by the chat's defaults: [{ id, from }] — shown, but changed in the defaults, not here
  inherited: { type: Array, default: () => [] },
  // Defaults switched off in this chat: [{ id, from }] — offered in the menu to switch back on
  hidden: { type: Array, default: () => [] },
})
// 'hide' / 'unhide': a default character's id, switched off / on in this chat only
const emit = defineEmits(['update:modelValue', 'edit', 'create', 'hide', 'unhide'])

const open = ref(false)
const close = () => (open.value = false)
const toggle = () => (open.value = !open.value)

const byId = computed(() => new Map(props.characters.map(c => [c.id, c])))
const inheritedIds = computed(() => [...props.inherited, ...props.hidden].map(x => x.id))
const hiddenItems = computed(() =>
  props.hidden.map(x => byId.value.get(x.id) && { ...byId.value.get(x.id), from: x.from }).filter(Boolean),
)

function unhide(c) {
  emit('unhide', c.id)
}
const fromDefaults = computed(() =>
  props.inherited.map(x => byId.value.get(x.id) && { ...byId.value.get(x.id), from: x.from }).filter(Boolean),
)
const attached = computed(() =>
  props.modelValue
    .filter(id => !inheritedIds.value.includes(id))
    .map(id => byId.value.get(id))
    .filter(Boolean),
)
const available = computed(() =>
  props.characters.filter(c => !props.modelValue.includes(c.id) && !inheritedIds.value.includes(c.id)),
)

function attach(c) {
  emit('update:modelValue', [...props.modelValue, c.id])
}

function detach(c) {
  emit(
    'update:modelValue',
    props.modelValue.filter(id => id !== c.id),
  )
}

function create() {
  close()
  emit('create')
}

// Every character as a card: in use (own, or from the defaults) or not
const card = (c, on, from) => ({
  key: `${from ? 'd' : ''}${c.id}`,
  id: c.id,
  name: c.name,
  sub: c.description || '',
  img: characterAvatar(c) || null,
  badge: c.adhoc ? 'This chat' : 'Library',
  from: from ? `${defaultIcon(from)} ${fromTitle(from)}` : undefined,
  on,
  kind: from ? 'default' : 'own',
})
const cards = computed(() => [
  ...attached.value.map(c => card(c, true)),
  ...fromDefaults.value.map(c => card(c, true, c.from)),
  ...hiddenItems.value.map(c => card(c, false, c.from)),
  ...available.value.map(c => card(c, false)),
])
function onToggle(item) {
  const c = byId.value.get(item.id)
  if (!c) return
  if (item.kind === 'default') return item.on ? emit('hide', c.id) : unhide(c)
  return item.on ? detach(c) : attach(c)
}
</script>

<template>
  <div class="char-picker">
    <div class="chips">
      <span
        v-for="c in fromDefaults"
        :key="`d${c.id}`"
        class="chip inherited"
        :title="`${c.name} · ${fromTitle(c.from)}`"
      >
        <button class="chip-main" @click="emit('edit', c)">
          <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" />
          <span v-else class="avatar-blank">👤</span>
          {{ c.name }}
        </button>
        <span class="chip-src">{{ defaultIcon(c.from) }}</span>
        <button class="chip-x" :title="`Hide ${c.name} in this chat`" @click="emit('hide', c.id)">✕</button>
      </span>
      <span
        v-for="c in attached"
        :key="c.id"
        class="chip"
        :class="{ adhoc: c.adhoc }"
        :title="(c.adhoc ? 'This chat only — ' : '') + (c.description || c.name)"
      >
        <button class="chip-main" @click="emit('edit', c)">
          <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" />
          <span v-else class="avatar-blank">👤</span>
          {{ c.name }}
        </button>
        <button class="chip-x" :title="`Detach ${c.name}`" @click="detach(c)">✕</button>
      </span>
      <button class="add" @click="toggle">
        {{ attached.length || fromDefaults.length ? '＋' : '＋ Add character' }}
      </button>
    </div>

    <PickDialog
      :open="open"
      title="Characters"
      :items="cards"
      empty="No characters yet"
      search-placeholder="Search characters"
      @toggle="onToggle"
      @close="close"
    >
      <template v-if="allowCreate" #actions>
        <button type="button" class="btn btn-secondary" @click="create">{{ createLabel }}</button>
      </template>
    </PickDialog>
  </div>
</template>

<style scoped>
.char-picker {
  position: relative;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
  font-size: 0.8rem;
  overflow: hidden;
}

.chip.adhoc {
  border-style: dashed;
}

/* Attached by the chat's defaults: no ✕ — the icon says where from */
.chip.inherited {
  background: transparent;
}

.chip-src {
  flex-shrink: 0;
  padding: 0 0 0 2px;
  font-size: 0.7rem;
  opacity: 0.75;
}

.chip-main {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px 3px 3px;
  background: none;
  border: none;
  color: var(--text);
  cursor: pointer;
  font: inherit;
}

.chip img,
.avatar-blank {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  display: inline-grid;
  place-items: center;
  font-size: 0.7rem;
  background: var(--surface);
}

.chip-x {
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  padding: 0 8px 0 2px;
  font-size: 0.7rem;
}

.chip-x:hover {
  color: var(--text);
}

.add {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px dashed var(--border);
  background: none;
  color: var(--text2);
  cursor: pointer;
  font-size: 0.8rem;
}

.add:hover {
  color: var(--text);
  border-color: var(--accent);
}
</style>
