<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { RouterLink } from 'vue-router'
import CharacterEditor from '../components/characters/CharacterEditor.vue'
import { fetchCharacters, promoteCharacter, deleteCharacter, characterAvatar } from '../composables/useCharacters'

const showToast = inject('showToast', () => {})

const characters = ref([])
const loading = ref(true)
const editing = ref(null) // character being edited
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
  <div class="characters-view">
    <header class="page-header">
      <div>
        <h1>Characters</h1>
        <p class="sub">
          Reusable characters for chats and generations. Their description goes into the prompt and their images are
          sent as references, so they look the same every time.
        </p>
      </div>
      <button class="btn btn-primary" @click="edit(null)">＋ New character</button>
    </header>

    <div v-if="loading" class="loading"><p>Loading...</p></div>

    <template v-else>
      <div v-if="!saved.length" class="empty-state">
        <h3>No saved characters yet</h3>
        <p>Create one here, or make one from an image in a chat and save it.</p>
      </div>
      <div v-else class="grid">
        <div v-for="c in saved" :key="c.id" class="card" @click="edit(c)">
          <div class="thumb">
            <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" loading="lazy" />
            <span v-else>👤</span>
          </div>
          <div class="info">
            <h3>{{ c.name }}</h3>
            <p class="desc">{{ c.description || 'No description' }}</p>
            <span class="meta">{{ c.images.length }} image{{ c.images.length !== 1 ? 's' : '' }}</span>
          </div>
        </div>
      </div>

      <section v-if="adhoc.length" class="adhoc">
        <h2>Chat-only characters</h2>
        <p class="sub">Made inside a chat; they're deleted with it unless you save them.</p>
        <div class="adhoc-list">
          <div v-for="c in adhoc" :key="c.id" class="adhoc-row">
            <img v-if="characterAvatar(c)" :src="characterAvatar(c)" alt="" class="mini" />
            <span v-else class="mini blank">👤</span>
            <button class="link name" @click="edit(c)">{{ c.name }}</button>
            <RouterLink :to="{ name: 'chat-conversation', params: { id: c.conversation_id } }" class="chat-link">
              in “{{ c.conversation_title || 'a chat' }}”
            </RouterLink>
            <span class="spacer"></span>
            <button class="btn btn-secondary small" @click="promote(c)">⭐ Save</button>
            <button class="btn btn-danger small" @click="remove(c)">Delete</button>
          </div>
        </div>
      </section>
    </template>

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
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.page-header h1 {
  font-size: 1.5rem;
}

.sub {
  font-size: 0.85rem;
  color: var(--text2);
  margin-top: 4px;
  line-height: 1.45;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s;
}

.card:hover {
  border-color: var(--accent);
}

.thumb {
  aspect-ratio: 1;
  background: var(--surface2);
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
  font-size: 0.95rem;
}

.desc {
  font-size: 0.8rem;
  color: var(--text2);
  margin: 4px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  font-size: 0.72rem;
  color: var(--text2);
}

.adhoc {
  margin-top: 32px;
}

.adhoc h2 {
  font-size: 1.1rem;
}

.adhoc-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.adhoc-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--surface);
  border: 1px dashed var(--border);
  border-radius: 10px;
  font-size: 0.88rem;
}

.mini {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  object-fit: cover;
}

.mini.blank {
  display: grid;
  place-items: center;
  background: var(--surface2);
}

.link {
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.chat-link {
  color: var(--text2);
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spacer {
  flex: 1;
}

.btn.small {
  padding: 6px 12px;
  font-size: 0.8rem;
}

.empty-state {
  text-align: center;
  padding: 48px 16px;
  color: var(--text2);
}

.empty-state h3 {
  color: var(--text);
  margin-bottom: 6px;
}

@media (max-width: 640px) {
  .page-header {
    flex-direction: column;
  }

  .adhoc-row {
    flex-wrap: wrap;
  }
}
</style>
