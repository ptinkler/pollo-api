<!--
  Unified Studio shell (overhaul). Thin orchestrator: it owns the shared
  catalogue + composer settings, wires useStudio()'s state/behaviour to the
  presentational panes (sidebar / feed+composer / inspector), and holds the
  icon sprite. All logic lives in useStudio; all markup in the child
  components. Route: /studio — runs alongside the existing app during the build.
-->
<script setup>
import { ref, reactive, computed, provide, inject, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { useComposerSettings, MODES } from '../composables/useComposerSettings'
import { useStudio } from '../composables/useStudio'
import { fmtCost } from '../utils/format'
import StudioSidebar from '../components/studio/StudioSidebar.vue'
import StudioInspector from '../components/studio/StudioInspector.vue'
import StudioComposer from '../components/studio/StudioComposer.vue'
import StudioFeed from '../components/studio/StudioFeed.vue'
import StudioGenerations from '../components/studio/StudioGenerations.vue'
import GenerationGrid from '../components/studio/GenerationGrid.vue'
import GenerationModal from '../components/studio/GenerationModal.vue'
import { chatMediaUrl, chatMediaPreviewUrl } from '../composables/useChat'
import StudioSpace from '../components/studio/StudioSpace.vue'
import StudioMedia from '../components/studio/StudioMedia.vue'
import StudioUsage from '../components/studio/StudioUsage.vue'
import StudioCharactersPage from '../components/studio/StudioCharactersPage.vue'
import StudioInstructionsPage from '../components/studio/StudioInstructionsPage.vue'
import StudioRequestLog from '../components/studio/StudioRequestLog.vue'
import StudioSettings from '../components/studio/StudioSettings.vue'
import StudioTools from '../components/studio/StudioTools.vue'
import MediaLightbox from '../components/chat/MediaLightbox.vue'
import CharacterEditor from '../components/characters/CharacterEditor.vue'
import InstructionEditor from '../components/chat/InstructionEditor.vue'
import SpaceSettingsDialog from '../components/chat/SpaceSettingsDialog.vue'
import ImportChatsModal from '../components/chat/ImportChatsModal.vue'
import '../components/studio/studio.css'

const router = useRouter()
const route = useRoute()
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
  activeKind,
  favourites,
  loadFavourites,
  favouriteMedia,
  setThreadKind,
  attachments,
  uploading,
  addFiles,
  removeAttachment,
  lastAssistantId,
  canSend,
  loadModels,
  loadLists,
  loadStatus,
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
  balances,
} = studio

const fmtCredits = v => (v == null ? '—' : Math.round(v).toLocaleString())
const fmtBal = v => (v == null ? '—' : `$${v.toFixed(2)}`)

// Every thread has two views: the chat conversation and its generations
// gallery. A thread's `kind` ('chat' | 'gallery') only picks which it opens on,
// unless the URL pins a tab (/studio/:id/chat|gallery).
const threadView = ref('chat')
watch(
  activeKind,
  k => {
    if (!route.params.view) threadView.value = k
  },
  { immediate: true },
)

// The generation shown in the big-view card modal, and whether its message is
// in the open thread (so manage actions — regenerate/delete — are available).
const galleryItem = ref(null)
const galleryManage = ref(false)
function openGeneration(item) {
  galleryItem.value = item
  galleryManage.value = true
}
async function onGalleryFavourite(item) {
  await favouriteMedia({ id: item.message_id }, { mediaId: item.id, favourite: !item.favourite })
}
function regenerateFromModal(item) {
  const msg = messages.value.find(m => m.id === item.message_id)
  if (msg) regenerateMedia(msg, { mediaId: item.id })
  galleryItem.value = null
}
async function deleteFromModal(item) {
  const msg = messages.value.find(m => m.id === item.message_id)
  galleryItem.value = null
  if (msg) await deleteExchange(msg)
}

// Favourites: the cross-thread gallery of starred generations.
const favItems = computed(() =>
  (favourites.value || []).map(i => ({
    ...i,
    url: chatMediaUrl(i.conversation_id, i.file),
    preview:
      i.kind === 'image' ? chatMediaPreviewUrl(i.conversation_id, i.file) : chatMediaUrl(i.conversation_id, i.file),
  })),
)
function openFavourite(item) {
  galleryItem.value = item
  galleryManage.value = false
}
async function onFavUnstar(item) {
  await favouriteMedia({ id: item.message_id }, { mediaId: item.id, favourite: false })
  if (galleryItem.value?.id === item.id) galleryItem.value = null
}
function openThreadFromModal(convId) {
  galleryItem.value = null
  openThreadView(convId)
}

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
const navFilter = ref('all') // list filter: 'all' | 'chat' | 'gallery' (Favourites is its own route)
const centerView = ref('thread') // 'thread' | 'space' | 'media' | 'settings' | 'favourites' — derived from the route
// The sidebar shows Favourites as active when its route is open.
const sidebarFilter = computed(() => (centerView.value === 'favourites' ? 'favourites' : navFilter.value))
function onFilter(f) {
  if (f === 'favourites') router.push('/favourites')
  else {
    navFilter.value = f
    if (centerView.value === 'favourites') goThread()
  }
}
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

function ensureSpace(spaceId) {
  const found = spaces.value.find(s => s.id === Number(spaceId))
  if (found) activeSpace.value = found
}
// The space may not be loaded yet on a cold deep-link; bind it once lists load.
watch(spaces, () => {
  if (route.name === 'studio-space') ensureSpace(route.params.spaceId)
})

function openSpace(space) {
  router.push(`/space/${space.id}`)
}
async function deleteSpaceView(space) {
  await removeSpace(space)
  if (activeSpace.value?.id === space.id) goThread()
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

// ── Navigation: center panes are real routes so the back button works ──────
let pendingKind = 'chat' // the kind a brand-new thread (/) opens on
function goThread() {
  router.push(active.value ? `/${active.value}` : '/')
}
function goSettings() {
  router.push('/settings')
}
function goTools() {
  router.push('/tools')
}
function goMedia() {
  router.push('/media')
}
function openThreadView(id) {
  router.push(`/${id}`)
}
function newThreadView(kind = 'chat') {
  pendingKind = kind
  if (route.name === 'studio')
    newThread(kind) // already on the home route: just reset
  else router.push('/')
}
function setThreadView(v) {
  if (active.value) router.push(`/${active.value}/${v}`)
  else threadView.value = v // unsaved new thread has no id to route
}
function goInstructions() {
  router.push('/instructions')
}
// Settings "Tools" links → in-Studio panes.
const STUDIO_PANE_PATH = {
  usage: '/usage',
  characters: '/characters',
  instructions: '/instructions',
  'request-log': '/requests',
}
function onSettingsNavigate(dest) {
  const path = STUDIO_PANE_PATH[dest]
  if (path) router.push(path)
  else router.push({ name: dest })
}

// Which center pane each route name shows (threads handled separately below).
const PANE_FOR_ROUTE = {
  'studio-settings': 'settings',
  'studio-tools': 'tools',
  'studio-media': 'media',
  'studio-usage': 'usage',
  'studio-characters': 'characters',
  'studio-instructions': 'instructions',
  'studio-requests': 'requests',
  'studio-favourites': 'favourites',
  'studio-space': 'space',
}
// Drive the center pane + active thread from the current route.
async function syncFromRoute() {
  const pane = PANE_FOR_ROUTE[route.name]
  if (pane) {
    centerView.value = pane
    if (pane === 'usage')
      loadStatus() // refresh balances when opening usage
    else if (pane === 'favourites') loadFavourites()
    else if (pane === 'space') ensureSpace(route.params.spaceId)
    return
  }
  // studio-thread (/:id[/:view]) or studio (/ = new thread)
  centerView.value = 'thread'
  const id = route.params.id || null
  if (!id) {
    newThread(pendingKind)
    pendingKind = 'chat'
    return
  }
  // A thread that fails to load (stale URL) falls back to home.
  if (id !== active.value && !(await openThread(id))) {
    router.replace('/')
    return
  }
  if (route.params.view === 'chat' || route.params.view === 'gallery') threadView.value = route.params.view
}
watch(() => route.fullPath, syncFromRoute)

// When a thread appears/changes outside navigation (first send on a new thread,
// or a fork), reflect its id in the URL so the address bar and back button stay
// correct. replace (not push) so back doesn't land on the empty /studio.
watch(active, id => {
  if (id && centerView.value === 'thread' && route.params.id !== id) router.replace(`/${id}`)
})

onMounted(() => {
  loadLists()
  loadModels()
  loadStatus() // which providers are configured + refresh their balances (Pollo/OpenRouter/Venice)
  loadInstructions()
  loadCharacters()
  loadDefaults()
  syncFromRoute()
})
</script>

<template>
  <div class="studio" :data-theme="dataTheme">
    <StudioSidebar
      v-model:collapsed="leftCollapsed"
      v-model:search="search"
      :filter="sidebarFilter"
      :threads="threads"
      :spaces="spaces"
      :active="centerView === 'thread' ? active : null"
      @update:filter="onFilter"
      @open="openThreadView"
      @new="newThreadView"
      @pin="toggleFav"
      @rename="renameThread"
      @delete="removeThread"
      @settings="goSettings"
      @open-space="openSpace"
      @add-space="addSpace"
      @rename-space="renameSpace"
      @delete-space="deleteSpaceView"
      @move="moveThread"
      @media="goMedia"
      @tools="goTools"
      @space-settings="spaceSettings = $event"
    />

    <main class="center">
      <StudioSettings
        v-if="centerView === 'settings'"
        :theme="theme"
        @set-theme="setTheme"
        @close="goThread"
        @navigate="onSettingsNavigate"
        @sign-out="onSignOut"
      />

      <StudioTools
        v-else-if="centerView === 'tools'"
        @close="goThread"
        @navigate="onSettingsNavigate"
        @defaults="spaceSettings = 'global'"
        @import="importOpen = true"
      />

      <StudioSpace
        v-else-if="centerView === 'space' && activeSpace"
        :space="activeSpace"
        :threads="spaceThreads"
        @open="openThreadView"
        @new="newThreadView"
        @close="goThread"
      />

      <StudioMedia v-else-if="centerView === 'media'" @close="goThread" />

      <StudioUsage
        v-else-if="centerView === 'usage'"
        :balances="balances"
        @close="goThread"
        @refresh="loadStatus"
        @manage-keys="goSettings"
      />

      <StudioCharactersPage v-else-if="centerView === 'characters'" @close="goThread" />

      <StudioInstructionsPage v-else-if="centerView === 'instructions'" @close="goThread" />

      <StudioRequestLog v-else-if="centerView === 'requests'" @close="goThread" />

      <template v-else-if="centerView === 'favourites'">
        <div class="top">
          <div class="ttitle">Favourites</div>
          <div class="spacer"></div>
          <span class="gcount">{{ favItems.length }} starred</span>
        </div>
        <GenerationGrid
          :items="favItems"
          empty="No favourites yet — star a generation to add it here."
          @open="openFavourite"
          @favourite="onFavUnstar"
        />
      </template>

      <template v-else>
        <div class="top">
          <div class="ttitle">{{ activeTitle }}</div>
          <div class="vtoggle">
            <button :class="{ on: threadView === 'chat' }" @click="setThreadView('chat')">Chat</button>
            <button :class="{ on: threadView === 'gallery' }" @click="setThreadView('gallery')">Gallery</button>
          </div>
          <button
            class="kindswitch"
            :data-on="activeKind === 'gallery' ? 'gallery' : 'chat'"
            :title="`Opens on ${activeKind === 'gallery' ? 'Gallery' : 'Chat'} by default — click to switch`"
            @click="setThreadKind(activeKind === 'gallery' ? 'chat' : 'gallery')"
          >
            <span class="knob"></span>
            <span class="kopt"
              ><svg class="ic"><use href="#s-chat" /></svg
            ></span>
            <span class="kopt"
              ><svg class="ic"><use href="#s-image" /></svg
            ></span>
          </button>
          <div class="spacer"></div>
          <span v-if="spendLabel" class="spend" title="Spent in this thread">{{ spendLabel }}</span>
          <span class="bal pollo" title="Pollo credits remaining — click for usage" @click="router.push('/usage')">
            Pollo <b>{{ fmtCredits(balances.pollo) }}</b>
          </span>
          <span class="bal" title="OpenRouter balance remaining">
            OpenRouter <b>{{ fmtBal(balances.openrouter) }}</b>
          </span>
          <span class="bal venice" title="Venice balance remaining">
            Venice <b>{{ fmtBal(balances.venice) }}</b>
          </span>
          <button class="iconbtn" title="Inspector" @click="rightCollapsed = !rightCollapsed">
            <svg class="ic"><use href="#s-cog" /></svg>
          </button>
        </div>

        <StudioFeed
          v-if="threadView === 'chat'"
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
        <StudioGenerations
          v-else
          :messages="messages"
          :conv-id="active"
          @open="openGeneration"
          @favourite="onGalleryFavourite"
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

    <GenerationModal
      :item="galleryItem"
      :can-manage="galleryManage"
      @close="galleryItem = null"
      @favourite="galleryManage ? onGalleryFavourite($event) : onFavUnstar($event)"
      @use-image="useImage"
      @regenerate="regenerateFromModal"
      @delete="deleteFromModal"
      @open-thread="openThreadFromModal"
    />

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
    <symbol id="s-pin" viewBox="0 0 24 24">
      <path d="M9 3h6l-1 6 3 3v2H7v-2l3-3-1-6zM12 14v7" />
    </symbol>
    <symbol id="s-download" viewBox="0 0 24 24">
      <path d="M12 4v10m0 0 4-4m-4 4-4-4M5 19h14" />
    </symbol>
    <symbol id="s-refresh" viewBox="0 0 24 24">
      <path d="M20 11a8 8 0 1 0-.9 4.5M20 5v5h-5" />
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
.bal {
  font-size: 12px;
  color: var(--smuted);
  padding: 3px 9px;
  border: 1px solid var(--sborder);
  border-radius: 7px;
  white-space: nowrap;
}
.bal b {
  color: var(--sfg);
  font-weight: 600;
}
.bal.pollo {
  cursor: pointer;
}
.bal.pollo:hover {
  border-color: var(--saccent);
}
.vtoggle {
  display: inline-flex;
  gap: 2px;
  background: var(--sbg2);
  border: 1px solid var(--sborder);
  border-radius: 7px;
  padding: 2px;
}
.vtoggle button {
  font-size: 12px;
  padding: 3px 10px;
  border: 0;
  background: transparent;
  color: var(--smuted);
  border-radius: 5px;
  cursor: pointer;
}
.vtoggle button.on {
  background: var(--shover);
  color: var(--sfg);
}
/* Sliding switch for the thread's default view: chat ◄► gallery */
.kindswitch {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 58px;
  height: 28px;
  padding: 3px;
  border: 1px solid var(--sborder);
  border-radius: 999px;
  background: var(--sbg2);
  cursor: pointer;
}
.kindswitch:hover {
  border-color: var(--saccent);
}
.kindswitch .knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 24px;
  height: 20px;
  border-radius: 999px;
  /* A bright thumb so the active icon (accent, below) reads clearly in both
     themes — white-on-accent washed out at this size. */
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
  transition: transform 0.16s ease;
}
.kindswitch[data-on='gallery'] .knob {
  transform: translateX(24px);
}
.kindswitch .kopt {
  position: relative;
  z-index: 1;
  flex: 1;
  display: grid;
  place-items: center;
  color: var(--smuted);
  transition: color 0.16s ease;
}
.kindswitch .kopt .ic {
  width: 14px;
  height: 14px;
  stroke-width: 2;
}
/* The icon sitting on the thumb: accent on white = high contrast. */
.kindswitch[data-on='chat'] .kopt:first-of-type,
.kindswitch[data-on='gallery'] .kopt:last-of-type {
  color: var(--saccent);
}
.gcount {
  font-size: 12px;
  color: var(--smuted);
}
.sprite {
  position: absolute;
}
</style>
