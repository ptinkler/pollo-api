<!-- Instructions library (snippets + groups), shown in the Studio center pane
     (replaces the old /instructions page). Reuses InstructionEditor. -->
<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import InstructionEditor from '../chat/InstructionEditor.vue'
import { fetchInstructions } from '../../composables/useChat'
import { useChatDefaults } from '../../composables/useChatDefaults'
import { instructionColor } from '../../utils/format'
import { ALL_CHATS, defaultIcon } from '../../utils/defaults'

const emit = defineEmits(['close'])
const showToast = inject('showToast', () => {})
const { globalSettings, spaces, loadDefaults, setCurrentSpace } = useChatDefaults()

const snippets = ref([])
const groups = ref([])
const loading = ref(true)
const query = ref('')
const editing = ref(null)

const matches = item => item.name.toLowerCase().includes(query.value.trim().toLowerCase())
const shownGroups = computed(() => groups.value.filter(matches))
const shownSnippets = computed(() => snippets.value.filter(matches))
const snippetById = computed(() => new Map(snippets.value.map(s => [s.id, s])))

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
function onChanged() {
  load()
  loadDefaults()
}
onMounted(() => {
  setCurrentSpace(null)
  load()
  loadDefaults()
})
</script>

<template>
  <div class="page">
    <div class="pwrap">
      <div class="phead">
        <div>
          <h1>Instructions</h1>
          <p class="sub">Sent to the chat model word for word. A group bundles snippets that go together.</p>
        </div>
        <div class="hactions">
          <button class="ghost" @click="editing = { kind: 'group', id: null }">＋ Group</button>
          <button class="primary" @click="editing = { kind: 'snippet', id: null }">＋ Snippet</button>
          <button class="closebtn" @click="emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <input
        v-if="snippets.length || groups.length"
        v-model="query"
        type="search"
        class="search"
        placeholder="Search instructions"
      />

      <div v-if="loading" class="muted">Loading…</div>
      <template v-else>
        <div v-if="!snippets.length && !groups.length" class="empty">
          No instructions yet. Make a snippet for a tone, a format or a rule.
        </div>

        <section v-if="shownGroups.length">
          <h2>Groups</h2>
          <div class="grid">
            <button v-for="g in shownGroups" :key="g.id" class="card" @click="editing = { kind: 'group', id: g.id }">
              <h3>📦 {{ g.name }}</h3>
              <div class="members">
                <span
                  v-for="s in (g.snippet_ids || []).map(id => snippetById.get(id)).filter(Boolean)"
                  :key="s.id"
                  class="member"
                >
                  <span class="dot" :style="{ background: instructionColor(s.name) }"></span>{{ s.name }}
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
            <button
              v-for="s in shownSnippets"
              :key="s.id"
              class="card"
              @click="editing = { kind: 'snippet', id: s.id }"
            >
              <h3><span class="dot" :style="{ background: instructionColor(s.name) }"></span>{{ s.name }}</h3>
              <p class="preview">{{ s.content || 'Empty' }}</p>
              <div v-if="defaultFor('instruction', s.id).length" class="badges">
                <span v-for="b in defaultFor('instruction', s.id)" :key="b" class="badge">
                  {{ defaultIcon(b) }} {{ b }}
                </span>
              </div>
            </button>
          </div>
        </section>

        <p v-if="query && !shownGroups.length && !shownSnippets.length" class="muted">Nothing matches</p>
      </template>
    </div>

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
  margin-bottom: 16px;
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
.ghost,
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
.ghost:hover,
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.search {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--sborder);
  border-radius: 10px;
  background: var(--spanel2, var(--sbg2));
  color: var(--sfg);
  outline: none;
  margin-bottom: 16px;
}
.muted,
.empty {
  color: var(--smuted);
  font-size: 13px;
  padding: 12px 0;
}
h2 {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--sfaint);
  font-weight: 650;
  margin: 18px 0 8px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.card {
  text-align: left;
  background: var(--sbg);
  border: 1px solid var(--sborder);
  border-radius: 12px;
  padding: 12px 14px;
  cursor: pointer;
}
.card:hover {
  border-color: var(--saccent);
}
.card h3 {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 600;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.preview {
  margin-top: 6px;
  font-size: 12px;
  color: var(--smuted);
  line-height: 1.45;
  max-height: 3.2em;
  overflow: hidden;
}
.members {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.member {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--smuted);
}
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}
.badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--saccent-soft);
  color: var(--saccent);
}
</style>
