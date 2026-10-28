<!--
  Unified Studio shell (overhaul). Thin orchestrator: it owns the shared
  catalogue + composer settings, wires useStudio()'s state/behaviour to the
  presentational panes (sidebar / feed+composer / inspector), and holds the
  icon sprite. All logic lives in useStudio; all markup in the child
  components. Route: /studio — runs alongside the existing app during the build.
-->
<script setup>
import { ref, reactive, computed, provide, inject, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { useComposerSettings, MODES } from '../composables/useComposerSettings'
import { useStudio } from '../composables/useStudio'
import { fmtCost } from '../utils/format'
import StudioSidebar from '../components/studio/StudioSidebar.vue'
import StudioInspector from '../components/studio/StudioInspector.vue'
import StudioComposer from '../components/studio/StudioComposer.vue'
import StudioFeed from '../components/studio/StudioFeed.vue'
import StudioSpace from '../components/studio/StudioSpace.vue'
import StudioMedia from '../components/studio/StudioMedia.vue'
import StudioSettings from '../components/studio/StudioSettings.vue'
import MediaLightbox from '../components/chat/MediaLightbox.vue'
import CharacterEditor from '../components/characters/CharacterEditor.vue'
import InstructionEditor from '../components/chat/InstructionEditor.vue'
import SpaceSettingsDialog from '../components/chat/SpaceSettingsDialog.vue'
import ImportChatsModal from '../components/chat/ImportChatsModal.vue'
import '../components/studio/studio.css'

const router = useRouter()
const { logout } = useAuth()

async function onSignOut() {
  try {
    await logout()
  } catch {
    /* ignore */
  }
  window.location.href = '/'
}

const showToast = inject('showToast', (m, t) => console.warn(`[${t}] ${m}`))

const models = reactive({ text: [], image: [], video: [] })
provide('chatModels', models) // ChatMessage's "Try another model"
const settings = useComposerSettings(models)
provide('composerSettings', settings) // read by the inspector's model/options sections
const { mode, currentMode } = settings

const studio = useStudio({ models, settings, showToast })
const {
  modelsLoading,
  threads,
  spaces,
  active,
  activeTitle,
  messages,
  sending,
  draft,
  lightbox,
  attachments,
  uploading,
  addFiles,
  removeAttachment,
  lastAssistantId,
  canSend,
  loadModels,
  loadLists,
  openThread,
  newThread,
  send,
  retry,
  editMessage,
  resendMessage,
  switchBranch,
  forkFrom,
  regenerateMedia,
  pinMedia,
  stop,
  deleteExchange,
  useImage,
  useText,
  toggleFav,
  renameThread,
  removeThread,
  moveThread,
  addSpace,
  renameSpace,
  removeSpace,
  // instructions
  instructions,
  instructionGroups,
  instructionIds,
  instructionGroupIds,
  instructionSummary,
  setInstructions,
  setGroups,
  onInstructionsChanged,
  editingInstruction,
  loadInstructions,
  inheritedDefaults,
  hiddenInherited,
  pausedInstructionIds,
  setDefaultHidden,
  setPaused,
  loadDefaults,
  globalSettings,
  // characters
  characters,
  characterIds,
  charEditor,
  characterNames,
  characterSupport,
  loadCharacters,
  setCharacters,
  editCharacter,
  newCharacter,
  onCharacterSaved,
  onCharacterDeleted,
  spend,
} = studio

const spendLabel = computed(() => {
  const s = spend.value
  if (!s) return ''
  const usd = (s.usd || 0) + (s.inherited_usd || 0)
  const cr = (s.credits || 0) + (s.inherited_credits || 0)
  const parts = []
  if (usd) parts.push(fmtCost(usd))
  if (cr) parts.push(`${cr} cr`)
  return parts.join(' · ')
})

const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const search = ref('')
const favOnly = ref(false)
const centerView = ref('thread') // 'thread' | 'space' | 'media' | 'settings'
const spaceSettings = ref(null) // a space | 'new' | 'global' | null (closed)
const importOpen = ref(false)
function onSpacesChanged() {
  loadDefaults()
  loadLists()
}
function onImported() {
  loadLists()
  loadDefaults()
}
const activeSpace = ref(null)
const spaceThreads = computed(() => threads.value.filter(t => t.space_id === activeSpace.value?.id))

function openSpace(space) {
  activeSpace.value = space
  centerView.value = 'space'
}
async function deleteSpaceView(space) {
  await removeSpace(space)
  if (activeSpace.value?.id === space.id) centerView.value = 'thread'
}

// ── Theme (System / Light / Dark) ────────────────────────────────────────
const THEME_KEY = 'studio.theme'
const readTheme = () => {
  try {
    return localStorage.getItem(THEME_KEY) || 'system'
  } catch {
    return 'system'
  }
}
const theme = ref(readTheme())
const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
const systemDark = ref(mq ? mq.matches : true)
mq?.addEventListener?.('change', e => (systemDark.value = e.matches))
const dataTheme = computed(() => (theme.value === 'system' ? (systemDark.value ? 'dark' : 'light') : theme.value))
function setTheme(t) {
  theme.value = t
  try {
    localStorage.setItem(THEME_KEY, t)
  } catch {
    /* storage unavailable */
  }
}

function openThreadView(id) {
  centerView.value = 'thread'
  openThread(id)
}
function newThreadView() {
  centerView.value = 'thread'
  newThread()
}

function goInstructions() {
  router.push({ name: 'instructions' })
}

onMounted(() => {
  loadLists()
  loadModels()
  loadInstructions()
  loadCharacters()
  loadDefaults()
})
</script>

<template>
  <div class="studio" :data-theme="dataTheme">
    <StudioSidebar
      v-model:collapsed="leftCollapsed"
      v-model:search="search"
      v-model:favourites="favOnly"
      :threads="threads"
      :spaces="spaces"
      :active="centerView === 'thread' ? active : null"
      @open="openThreadView"
      @new="newThreadView"
      @favourite="toggleFav"
      @rename="renameThread"
      @delete="removeThread"
      @settings="centerView = 'settings'"
      @open-space="openSpace"
      @add-space="addSpace"
      @rename-space="renameSpace"
      @delete-space="deleteSpaceView"
      @move="moveThread"
      @media="centerView = 'media'"
      @space-settings="spaceSettings = $event"
    />

    <main class="center">
      <StudioSettings
        v-if="centerView === 'settings'"
        :theme="theme"
        @set-theme="setTheme"
        @close="centerView = 'thread'"
        @navigate="router.push({ name: $event })"
        @sign-out="onSignOut"
        @defaults="spaceSettings = 'global'"
        @import="importOpen = true"
      />

      <StudioSpace
        v-else-if="centerView === 'space' && activeSpace"
        :space="activeSpace"
        :threads="spaceThreads"
        @open="openThreadView"
        @new="newThreadView"
        @close="centerView = 'thread'"
      />

      <StudioMedia v-else-if="centerView === 'media'" @close="centerView = 'thread'" />

      <template v-else>
        <div class="top">
          <div class="ttitle">{{ activeTitle }}</div>
          <div class="spacer"></div>
          <span v-if="spendLabel" class="spend" title="Spent in this thread">{{ spendLabel }}</span>
          <button class="iconbtn" title="Inspector" @click="rightCollapsed = !rightCollapsed">
            <svg class="ic"><use href="#s-cog" /></svg>
          </button>
        </div>

        <StudioFeed
          :messages="messages"
          :active="active"
          :sending="sending"
          :last-assistant-id="lastAssistantId"
          @retry="retry"
          @edit="editMessage"
          @resend="resendMessage"
          @branch="switchBranch"
          @use-image="useImage"
          @use-text="useText"
          @regenerate="regenerateMedia"
          @pin="pinMedia"
          @delete="deleteExchange"
          @fork="forkFrom"
          @open-chat="openThreadView"
          @stop="stop"
          @open-media="lightbox = $event"
        />

        <StudioComposer
          v-model:draft="draft"
          v-model:mode="mode"
          :modes="MODES"
          :hint="currentMode.hint"
          :sending="sending"
          :can-send="canSend"
          :attachments="attachments"
          :uploading="uploading"
          @send="send"
          @files="addFiles"
          @remove="removeAttachment"
        />
      </template>
    </main>

    <StudioInspector
      v-model:collapsed="rightCollapsed"
      :models="models"
      :models-loading="modelsLoading"
      :instructions="{
        list: instructions,
        groups: instructionGroups,
        snippetIds: instructionIds,
        groupIds: instructionGroupIds,
        summary: instructionSummary,
        inheritedSnippets: inheritedDefaults.instruction,
        inheritedGroups: inheritedDefaults.instruction_group,
        hiddenSnippets: hiddenInherited.instruction,
        hiddenGroups: hiddenInherited.instruction_group,
        pausedSnippets: pausedInstructionIds.snippets,
        pausedGroups: pausedInstructionIds.groups,
      }"
      :characters="{
        list: characters,
        ids: characterIds,
        names: characterNames,
        support: characterSupport,
        inherited: inheritedDefaults.character,
        hidden: hiddenInherited.character,
      }"
      @update:snippet-ids="setInstructions"
      @update:group-ids="setGroups"
      @manage="goInstructions"
      @edit-instruction="editingInstruction = $event"
      @instr-hide="setDefaultHidden($event, true)"
      @instr-unhide="setDefaultHidden($event, false)"
      @instr-pause="setPaused($event, true)"
      @instr-resume="setPaused($event, false)"
      @update:character-ids="setCharacters"
      @edit-character="editCharacter"
      @create-character="newCharacter()"
      @char-hide="setDefaultHidden({ kind: 'character', id: $event }, true)"
      @char-unhide="setDefaultHidden({ kind: 'character', id: $event }, false)"
    />

    <MediaLightbox :item="lightbox" @close="lightbox = null" @use-image="useImage" />

    <CharacterEditor
      :open="charEditor.open"
      :character="charEditor.character"
      :conversation-id="charEditor.conversationId"
      :seed="charEditor.seed"
      show-defaults
      @close="charEditor.open = false"
      @saved="onCharacterSaved"
      @deleted="onCharacterDeleted"
    />

    <InstructionEditor
      :target="editingInstruction"
      :instructions="instructions"
      :groups="instructionGroups"
      @close="editingInstruction = null"
      @changed="onInstructionsChanged"
    />

    <SpaceSettingsDialog
      :target="spaceSettings"
      :global-settings="globalSettings"
      :characters="characters"
      :instructions="instructions"
      :groups="instructionGroups"
      @close="spaceSettings = null"
      @changed="onSpacesChanged"
    />

    <ImportChatsModal :visible="importOpen" @close="importOpen = false" @imported="onImported" />
  </div>

  <svg width="0" height="0" class="sprite" aria-hidden="true">
    <symbol id="s-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></symbol>
    <symbol id="s-chev" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></symbol>
    <symbol id="s-chevL" viewBox="0 0 24 24"><path d="m15 6-6 6 6 6" /></symbol>
    <symbol id="s-search" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </symbol>
    <symbol id="s-chat" viewBox="0 0 24 24">
      <path d="M20.5 11.5a7.5 7.5 0 0 1-10.9 6.7L4.5 19.5l1.3-5A7.5 7.5 0 1 1 20.5 11.5z" />
    </symbol>
    <symbol id="s-folder" viewBox="0 0 24 24">
      <path d="M4 7.5a2 2 0 0 1 2-2h3.2l1.8 2H18a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
    </symbol>
    <symbol id="s-star" viewBox="0 0 24 24">
      <path d="M12 4.5l2.2 4.5 4.9.5-3.7 3.3 1.1 4.8L12 15.7l-4.5 2.4 1.1-4.8L4.9 9.5l4.9-.5z" />
    </symbol>
    <symbol id="s-cog" viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.5M12 18.5V21M5 5l1.8 1.8M17.2 17.2 19 19M3 12h2.5M18.5 12H21M5 19l1.8-1.8M17.2 6.8 19 5" />
    </symbol>
    <symbol id="s-spark" viewBox="0 0 24 24">
      <path d="M12 3.5l1.5 5L18.5 10l-5 1.5L12 16.5l-1.5-5L5.5 10l5-1.5z" />
    </symbol>
    <symbol id="s-pencil" viewBox="0 0 24 24"><path d="M4 20h4l10-10-4-4L4 16z M13.5 6.5l4 4" /></symbol>
    <symbol id="s-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" /></symbol>
    <symbol id="s-clip" viewBox="0 0 24 24">
      <path d="M21 11l-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 6" />
    </symbol>
    <symbol id="s-image" viewBox="0 0 24 24">
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="M5 17l4.5-4.5L13 16l2.5-2.5L19 17" />
    </symbol>
  </svg>
</template>

<style scoped>
.studio {
  position: fixed;
  inset: 0;
  display: flex;
  overflow: hidden;
  background: var(--sbg2);
  color: var(--sfg);
  font-size: 13.5px;
}
.center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.top {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--sborder2);
}
.ttitle {
  font-weight: 600;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.top .spacer {
  flex: 1;
}
.iconbtn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
}
.iconbtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.spend {
  font-size: 12px;
  color: var(--smuted);
  padding: 3px 9px;
  border: 1px solid var(--sborder);
  border-radius: 7px;
}
.sprite {
  position: absolute;
}
</style>
