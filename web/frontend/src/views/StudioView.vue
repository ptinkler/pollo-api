<!--
  Unified Studio shell (overhaul). Thin orchestrator: it owns the shared
  catalogue + composer settings, wires useStudio()'s state/behaviour to the
  presentational panes (sidebar / feed+composer / inspector), and holds the
  icon sprite. All logic lives in useStudio; all markup in the child
  components. Route: /studio — runs alongside the existing app during the build.
-->
<script setup>
import { ref, reactive, computed, provide, inject, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { useComposerSettings, MODES } from '../composables/useComposerSettings'
import { useStudio } from '../composables/useStudio'
import StudioSidebar from '../components/studio/StudioSidebar.vue'
import StudioInspector from '../components/studio/StudioInspector.vue'
import StudioComposer from '../components/studio/StudioComposer.vue'
import StudioFeed from '../components/studio/StudioFeed.vue'
import StudioGenerations from '../components/studio/StudioGenerations.vue'
import GenerationGrid from '../components/studio/GenerationGrid.vue'
import GenerationModal from '../components/studio/GenerationModal.vue'
import GenerationQueueDock from '../components/studio/GenerationQueueDock.vue'
import { useGenQueue } from '../composables/useGenQueue'
import { chatMediaUrl, chatMediaPreviewUrl } from '../composables/useChat'
import StudioSpace from '../components/studio/StudioSpace.vue'
import StudioMedia from '../components/studio/StudioMedia.vue'
import StudioUsage from '../components/studio/StudioUsage.vue'
import StudioCharactersPage from '../components/studio/StudioCharactersPage.vue'
import StudioInstructionsPage from '../components/studio/StudioInstructionsPage.vue'
import StudioRequestLog from '../components/studio/StudioRequestLog.vue'
import StudioSettings from '../components/studio/StudioSettings.vue'
import StudioTools from '../components/studio/StudioTools.vue'
import StudioIconSprite from '../components/studio/StudioIconSprite.vue'
import StudioBalances from '../components/studio/StudioBalances.vue'
import MediaPicker from '../components/media/MediaPicker.vue'
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

const models = reactive({ text: [], image: [], video: [], audio: [] })
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
  lane,
  estimate,
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
  applyGenerationSettings,
  pinMedia,
  stop,
  deleteExchange,
  addFromLibrary,
  enhancing,
  enhanceDraft,
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

// A gallery is for straight generations: only Image and Video modes (no
// Auto/Text — the chat model is never involved), sent exactly as written.
const inGallery = computed(() => threadView.value === 'gallery')
// Each view keeps its own prompt draft, and gallery sends run beside the chat
const draftStash = { chat: '', gallery: '' }
watch(
  threadView,
  (v, old) => {
    if (old) draftStash[old] = draft.value
    if (old && old !== v) draft.value = draftStash[v]
    lane.value = v === 'gallery' ? 'gallery' : null
  },
  { immediate: true },
)
const chatMessages = computed(() => messages.value.filter(m => !m.lane))
const composerModes = computed(() =>
  inGallery.value ? MODES.filter(m => m.id === 'image' || m.id === 'video') : MODES,
)
watch(
  [inGallery, mode],
  () => {
    if (inGallery.value && mode.value !== 'image' && mode.value !== 'video') mode.value = 'image'
  },
  { immediate: true },
)

// The generation shown in the big-view card modal, and whether its message is
// in the open thread (so manage actions — regenerate/delete — are available).
const pickerOpen = ref(false)
const galleryItem = ref(null)
const galleryManage = ref(false)
function openGeneration(item) {
  galleryItem.value = item
  galleryManage.value = true
}
async function onGalleryFavourite(item) {
  await favouriteMedia({ id: item.message_id }, { mediaId: item.id, favourite: !item.favourite })
}
// Always-visible generation queue (polls across all threads; survives navigation).
const genQueue = useGenQueue()
const { entries: queueItems, pending: queuePending, done: queueDone } = genQueue
onMounted(() => genQueue.start())
onUnmounted(() => genQueue.stop())
// Generate from the composer, then refresh the queue so the new tile shows at once.
function onGenerate() {
  send()
  genQueue.refresh()
}
// Clicking a queued item jumps to that thread's gallery (where its tile lives).
function openQueueItem(e) {
  router.push(`/${e.conversation_id}/gallery`)
}

// Modal "Retry" / "Regenerate". A failed item retries in place (backend only
// allows regenerating errored media); a successful one re-rolls as a fresh
// generation with the same settings (apply + send), leaving the original.
function regenerateFromModal(item) {
  if (item.status === 'error') {
    const msg = messages.value.find(m => m.id === item.message_id)
    if (msg) regenerateMedia(msg, { mediaId: item.id })
  } else {
    applyGenerationSettings(item)
    send()
  }
  genQueue.refresh()
  galleryItem.value = null
}
// "Use settings": fill the composer from this generation (model, mode, options,
// prompt), close the modal, and leave it for the user to tweak and Generate.
function useSettingsFromModal(item) {
  applyGenerationSettings(item)
  galleryItem.value = null
}
// "Picture/Video from this": attach the image, switch mode, and close the modal.
function useImageFromModal(e) {
  galleryItem.value = null
  useImage(e)
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

// Navigation: center panes are real routes so the back button works
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
          :fav-filter="false"
          empty="No favourites yet — star a generation to add it here."
          @open="openFavourite"
          @favourite="onFavUnstar"
        />
      </template>

      <template v-else>
        <div class="top">
          <div class="ttitle">{{ activeTitle }}</div>
          <div class="vtoggle">
            <button :class="{ on: threadView === 'chat' }" title="Chat view" @click="setThreadView('chat')">
              <svg class="ic"><use href="#s-chat" /></svg>
            </button>
            <button :class="{ on: threadView === 'gallery' }" title="Gallery view" @click="setThreadView('gallery')">
              <svg class="ic"><use href="#s-image" /></svg>
            </button>
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
          <StudioBalances :balances="balances" :spend="spend" :messages="messages" @usage="router.push('/usage')" />
          <button class="iconbtn" title="Inspector" @click="rightCollapsed = !rightCollapsed">
            <svg class="ic"><use href="#s-cog" /></svg>
          </button>
        </div>

        <StudioFeed
          v-if="threadView === 'chat'"
          :messages="chatMessages"
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
          :modes="composerModes"
          :hint="currentMode.hint"
          :sending="sending"
          :can-send="canSend"
          :attachments="attachments"
          :uploading="uploading"
          :enhancing="enhancing"
          :estimate="estimate"
          :video-input="!!settings.activeInfo.value?.video_input"
          :audio-input="!!settings.activeInfo.value?.audio_input"
          @send="onGenerate"
          @files="addFiles"
          @remove="removeAttachment"
          @clear="[...attachments].forEach(removeAttachment)"
          @library="pickerOpen = true"
          @enhance="enhanceDraft"
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

    <MediaPicker :open="pickerOpen" title="Attach images" @pick="addFromLibrary" @close="pickerOpen = false" />

    <MediaLightbox :item="lightbox" @close="lightbox = null" @use-image="useImage" />

    <GenerationModal
      :item="galleryItem"
      :can-manage="galleryManage"
      :theme="dataTheme"
      @close="galleryItem = null"
      @favourite="galleryManage ? onGalleryFavourite($event) : onFavUnstar($event)"
      @use-image="useImageFromModal"
      @use-settings="useSettingsFromModal"
      @regenerate="regenerateFromModal"
      @delete="deleteFromModal"
      @open-thread="openThreadFromModal"
    />

    <GenerationQueueDock
      :entries="queueItems"
      :pending="queuePending"
      :done="queueDone"
      @open="openQueueItem"
      @clear="genQueue.clearDone"
      @clear-one="genQueue.clearOne"
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

  <StudioIconSprite />
</template>

<style scoped src="./StudioView.css"></style>
