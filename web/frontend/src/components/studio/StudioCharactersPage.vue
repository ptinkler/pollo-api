<!-- Characters library, shown in the Studio center pane (replaces the old
     /characters page). Reuses CharacterEditor; Studio-styled. -->
<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { confirmDialog } from '../../composables/useDialog'
import CharacterEditor from '../characters/CharacterEditor.vue'
import { fetchCharacters, promoteCharacter, deleteCharacter, characterAvatar } from '../../composables/useCharacters'

const emit = defineEmits(['close'])
const router = useRouter()
const showToast = inject('showToast', () => {})

const characters = ref([])
const loading = ref(true)
const editing = ref(null)
const editorOpen = ref(false)

const saved = computed(() => characters.value.filter(c => !c.adhoc))
const adhoc = computed(() => characters.value.filter(c => c.adhoc))

async function load() {
  try {
    characters.value = await fetchCharacters({ includeAdhoc: true })
  } catch (e) {
    showToast(`Couldn't load characters: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
}
function edit(c) {
  editing.value = c
  editorOpen.value = true
}
function onSaved(c) {
  const i = characters.value.findIndex(x => x.id === c.id)
  const keep = i === -1 ? {} : { conversation_title: characters.value[i].conversation_title }
  if (i === -1) characters.value.push(c)
  else characters.value.splice(i, 1, { ...keep, ...c })
  if (editing.value?.id === c.id) editing.value = characters.value.find(x => x.id === c.id)
}
function onDeleted(id) {
  characters.value = characters.value.filter(c => c.id !== id)
}
async function promote(c) {
  try {
    onSaved(await promoteCharacter(c.id))
    showToast(`${c.name} saved`, 'success')
  } catch (e) {
    showToast(`Couldn't save: ${e.message}`, 'error')
  }
}
async function remove(c) {
  if (
    !(await confirmDialog({
      title: `Delete “${c.name}”?`,
      message: 'Its images are deleted too.',
      confirmLabel: 'Delete',
      danger: true,
    }))
  )
    return
  try {
    await deleteCharacter(c.id)
    onDeleted(c.id)
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error')
  }
}
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="pwrap">
      <div class="phead">
        <div>
          <h1>Characters</h1>
          <p class="sub">
            Reusable characters for chats and generations: their description goes into the prompt and their images are
            sent as references, so they look the same every time.
          </p>
        </div>
        <div class="hactions">
          <button class="btn btn-primary" @click="edit(null)">
            <svg class="ic"><use href="#s-plus" /></svg> New character
          </button>
          <button class="btn" @click="emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <div v-if="loading" class="muted">Loading…</div>
      <template v-else>
        <div v-if="!saved.length" class="empty">No saved characters yet. Create one here, or save one from a chat.</div>
        <div v-else class="grid">
          <button v-for="c in saved" :key="c.id" class="gcard card" @click="edit(c)">
            <div class="thumb">
              <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" loading="lazy" />
              <span v-else>👤</span>
            </div>
            <div class="info">
              <h3>{{ c.name }}</h3>
              <p class="desc">{{ c.description || 'No description' }}</p>
              <span class="meta">{{ c.images.length }} image{{ c.images.length !== 1 ? 's' : '' }}</span>
            </div>
          </button>
        </div>

        <section v-if="adhoc.length" class="adhoc">
          <h2 class="sect">Chat-only characters</h2>
          <p class="sub">Made inside a chat; deleted with it unless you save them.</p>
          <div v-for="c in adhoc" :key="c.id" class="arow">
            <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" class="mini" />
            <span v-else class="mini blank">👤</span>
            <button class="link" @click="edit(c)">{{ c.name }}</button>
            <a class="chat-link" :href="`/${c.conversation_id}`" @click.prevent="router.push(`/${c.conversation_id}`)">
              in “{{ c.conversation_title || 'a chat' }}”
            </a>
            <span class="spacer"></span>
            <button class="btn btn-sm" @click="promote(c)">Save</button>
            <button class="btn btn-sm btn-danger-quiet" @click="remove(c)">Delete</button>
          </div>
        </section>
      </template>
    </div>

    <CharacterEditor
      :open="editorOpen"
      :character="editing"
      @close="editorOpen = false"
      @saved="onSaved"
      @deleted="onDeleted"
    />
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
}
.card {
  padding: 0;
  overflow: hidden;
}
.thumb {
  aspect-ratio: 1;
  background: var(--sbg2);
  display: grid;
  place-items: center;
  font-size: 2.2rem;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.info {
  padding: 8px 10px 10px;
}
.info h3 {
  font-size: 13.5px;
  font-weight: 600;
}
.desc {
  font-size: 12px;
  color: var(--smuted);
  margin: 2px 0 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  font-size: 11px;
  color: var(--sfaint);
}
.adhoc {
  margin-top: 8px;
}
.adhoc .sub {
  margin: 0 0 4px;
}
.arow {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid var(--sborder2);
  font-size: 13px;
}
.mini {
  width: 28px;
  height: 28px;
  border-radius: var(--r-sm);
  object-fit: cover;
}
.mini.blank {
  display: grid;
  place-items: center;
  background: var(--sbg2);
}
.link {
  background: none;
  border: none;
  color: var(--sfg);
  cursor: pointer;
  font-weight: 500;
  font-size: 13px;
  padding: 0;
}
.link:hover {
  color: var(--saccent);
}
.chat-link {
  text-decoration: none;
  background: none;
  border: none;
  color: var(--smuted);
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}
.chat-link:hover {
  color: var(--saccent);
}
.spacer {
  flex: 1;
}
</style>
