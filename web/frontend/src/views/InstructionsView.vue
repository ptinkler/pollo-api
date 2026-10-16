<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import InstructionEditor from '../components/chat/InstructionEditor.vue'
import { fetchInstructions } from '../composables/useChat'
import { useChatDefaults } from '../composables/useChatDefaults'
import { instructionColor } from '../utils/format'
import { ALL_CHATS, defaultIcon } from '../utils/defaults'

// Every instruction snippet and group, like the Characters page: each opens
// in InstructionEditor. Badges say where it's a default.
const showToast = inject('showToast', () => {})
const { globalSettings, spaces, loadDefaults, setCurrentSpace } = useChatDefaults()

const snippets = ref([])
const groups = ref([])
const loading = ref(true)
const query = ref('')
const editing = ref(null) // { kind, id } in the editor

const matches = item => item.name.toLowerCase().includes(query.value.trim().toLowerCase())
const shownGroups = computed(() => groups.value.filter(matches))
const shownSnippets = computed(() => snippets.value.filter(matches))
const snippetById = computed(() => new Map(snippets.value.map(s => [s.id, s])))

// Where an item is a default: "All chats" and/or space names
function defaultFor(kind, id) {
  const field = `default_${kind}_ids`
  return [
    ...(globalSettings.value[field].includes(id) ? [ALL_CHATS] : []),
    ...spaces.value.filter(s => s[field].includes(id)).map(s => s.name),
  ]
}

async function load() {
  try {
    const data = await fetchInstructions()
    snippets.value = data.instructions
    groups.value = data.groups || []
  } catch (e) {
    showToast(`Couldn't load instructions: ${e.message}`, 'error')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  setCurrentSpace(null) // no chat in context here: "Default for" offers all chats only
  load()
  loadDefaults()
})

function onChanged() {
  load()
  loadDefaults()
}
</script>

<template>
  <div class="instructions-view">
    <header class="page-header">
      <div>
        <h1>Instructions</h1>
        <p class="sub">Sent to the chat model word for word. A group bundles snippets that go together.</p>
      </div>
      <div class="new-btns">
        <button class="btn btn-secondary" @click="editing = { kind: 'group', id: null }">＋ Group</button>
        <button class="btn btn-primary" @click="editing = { kind: 'snippet', id: null }">＋ Snippet</button>
      </div>
    </header>

    <input
      v-if="snippets.length || groups.length"
      v-model="query"
      type="search"
      class="search"
      placeholder="Search instructions"
      aria-label="Search instructions"
    />

    <div v-if="loading" class="loading"><p>Loading...</p></div>

    <template v-else>
      <div v-if="!snippets.length && !groups.length" class="empty-state">
        <h3>No instructions yet</h3>
        <p>Make a snippet for a tone, a format or a rule. The chat model can save them too.</p>
      </div>

      <section v-if="shownGroups.length">
        <h2>Groups</h2>
        <div class="grid">
          <button v-for="g in shownGroups" :key="g.id" class="card" @click="editing = { kind: 'group', id: g.id }">
            <h3>
              <span class="title">📦 {{ g.name }}</span>
            </h3>
            <div class="members">
              <span
                v-for="s in (g.snippet_ids || []).map(id => snippetById.get(id)).filter(Boolean)"
                :key="s.id"
                class="member"
              >
                <span class="dot" :style="{ background: instructionColor(s.name) }"></span
                ><span class="title">{{ s.name }}</span>
              </span>
              <span v-if="!g.snippet_ids?.length" class="muted">No snippets</span>
            </div>
            <div v-if="defaultFor('instruction_group', g.id).length" class="badges">
              <span v-for="b in defaultFor('instruction_group', g.id)" :key="b" class="badge">
                {{ defaultIcon(b) }} {{ b }}
              </span>
            </div>
          </button>
        </div>
      </section>

      <section v-if="shownSnippets.length">
        <h2>Snippets</h2>
        <div class="grid">
          <button v-for="s in shownSnippets" :key="s.id" class="card" @click="editing = { kind: 'snippet', id: s.id }">
            <h3>
              <span class="dot" :style="{ background: instructionColor(s.name) }"></span
              ><span class="title">{{ s.name }}</span>
            </h3>
            <p class="preview">{{ s.content || 'Empty' }}</p>
            <div v-if="defaultFor('instruction', s.id).length" class="badges">
              <span v-for="b in defaultFor('instruction', s.id)" :key="b" class="badge">
                {{ defaultIcon(b) }} {{ b }}
              </span>
            </div>
          </button>
        </div>
      </section>

      <p v-if="query && !shownGroups.length && !shownSnippets.length" class="muted none">Nothing matches</p>
    </template>

    <InstructionEditor
      :target="editing"
      :instructions="snippets"
      :groups="groups"
      @close="editing = null"
      @changed="onChanged"
    />
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
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

.new-btns {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.search {
  width: 100%;
  max-width: 360px;
  padding: 8px 12px;
  border-radius: 8px;
  margin-bottom: 8px;
}

section {
  margin-top: 18px;
}

h2 {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text2);
  margin-bottom: 10px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  color: var(--text);
  text-align: left;
  font: inherit;
  cursor: pointer;
  transition: border-color 0.2s;
  min-width: 0;
}

.card:hover {
  border-color: var(--accent);
}

.card h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.95rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dot {
  flex-shrink: 0;
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.card h3 .dot {
  margin-right: 0;
}

.preview {
  font-size: 0.8rem;
  color: var(--text2);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-line;
}

.members {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 0.8rem;
  color: var(--text2);
}

.member {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.badge {
  font-size: 0.7rem;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(108, 92, 231, 0.18);
  color: var(--accent2);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted {
  font-size: 0.8rem;
  color: var(--text2);
}

.none {
  margin-top: 16px;
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
}
</style>
