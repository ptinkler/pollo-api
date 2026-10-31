<!-- Characters library, shown in the Studio center pane (replaces the old
     /characters page). Reuses CharacterEditor; Studio-styled. -->
<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
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
  if (!confirm(`Delete “${c.name}” and its images?`)) return
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
          <button class="primary" @click="edit(null)">＋ New character</button>
          <button class="closebtn" @click="emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <div v-if="loading" class="muted">Loading…</div>
      <template v-else>
        <div v-if="!saved.length" class="empty">No saved characters yet. Create one here, or save one from a chat.</div>
        <div v-else class="grid">
          <button v-for="c in saved" :key="c.id" class="card" @click="edit(c)">
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
          <h2>Chat-only characters</h2>
          <p class="sub">Made inside a chat; deleted with it unless you save them.</p>
          <div v-for="c in adhoc" :key="c.id" class="arow">
            <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" class="mini" />
            <span v-else class="mini blank">👤</span>
            <button class="link" @click="edit(c)">{{ c.name }}</button>
            <button class="chat-link" @click="router.push(`/studio/${c.conversation_id}`)">
              in “{{ c.conversation_title || 'a chat' }}”
            </button>
            <span class="spacer"></span>
            <button class="small" @click="promote(c)">⭐ Save</button>
            <button class="small danger" @click="remove(c)">Delete</button>
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
.page {
  flex: 1;
  overflow-y: auto;
  padding: 32px 22px;
}
.pwrap {
  max-width: 820px;
  margin: 0 auto;
}
.phead {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
h1 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
}
.sub {
  font-size: 13px;
  color: var(--smuted);
  margin-top: 6px;
  line-height: 1.5;
  max-width: 560px;
}
.hactions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.primary {
  padding: 8px 14px;
  border: none;
  border-radius: 9px;
  background: var(--saccent);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}
.closebtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
}
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.muted,
.empty {
  color: var(--smuted);
  font-size: 13px;
  padding: 20px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 14px;
}
.card {
  text-align: left;
  padding: 0;
  background: var(--sbg);
  border: 1px solid var(--sborder);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
}
.card:hover {
  border-color: var(--saccent);
}
.thumb {
  aspect-ratio: 1;
  background: var(--sbg2);
  display: grid;
  place-items: center;
  font-size: 2.5rem;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.info {
  padding: 10px 12px;
}
.info h3 {
  font-size: 14px;
  font-weight: 600;
}
.desc {
  font-size: 12px;
  color: var(--smuted);
  margin: 4px 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  font-size: 11px;
  color: var(--sfaint);
}
.adhoc {
  margin-top: 28px;
}
h2 {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}
.arow {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--sborder2);
}
.mini {
  width: 30px;
  height: 30px;
  border-radius: 7px;
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
}
.chat-link {
  background: none;
  border: none;
  color: var(--smuted);
  cursor: pointer;
  font-size: 12px;
}
.chat-link:hover {
  color: var(--saccent);
}
.spacer {
  flex: 1;
}
.small {
  padding: 5px 10px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  background: none;
  color: var(--sfg);
  cursor: pointer;
  font-size: 12px;
}
.small:hover {
  background: var(--shover);
}
.small.danger:hover {
  color: var(--sdanger, #e5484d);
  border-color: var(--sdanger, #e5484d);
}
</style>
