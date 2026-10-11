<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import MediaPicker from '../media/MediaPicker.vue'
import { importMedia } from '../../composables/useMedia'
import {
  createCharacter,
  updateCharacter,
  deleteCharacter,
  promoteCharacter,
  uploadCharacterImage,
  copyChatImageToCharacter,
  copyGenerationImageToCharacter,
  characterImageUrl,
} from '../../composables/useCharacters'
import { takeFiles } from '../../utils/files'

const MAX_IMAGES = 6 // mirrors MAX_IMAGES in web/characters.py

const props = defineProps({
  open: { type: Boolean, default: false },
  character: { type: Object, default: null }, // edit this one; null = create
  conversationId: { type: String, default: null }, // create as ad hoc in this chat
  // Images to start a new character with: { kind: 'chat', conversationId, file, preview },
  // { kind: 'generation', project, filename, preview } or { kind: 'media', mediaId, preview }
  seed: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'saved', 'deleted'])
const showToast = inject('showToast', () => {})

const name = ref('')
const description = ref('')
// The images in order, main first: saved ones { file } and ones to add on save
// ({ kind, preview, … } as in `seed`, or { kind: 'file', file: File })
const images = ref([])
const dragFrom = ref(null) // index of the image being dragged
const saving = ref(false)
const pickerOpen = ref(false)
const nameInput = ref(null)
let keySeq = 0

const isNew = computed(() => !props.character)
const total = computed(() => images.value.length)

watch(
  () => props.open,
  open => {
    if (!open) return
    name.value = props.character?.name ?? ''
    description.value = props.character?.description ?? ''
    images.value = [
      ...(props.character?.images ?? []).map(f => ({ kind: 'saved', saved: f, key: f })),
      ...props.seed.map(s => ({ ...s, key: ++keySeq })),
    ]
    nextTick(() => nameInput.value?.focus())
  },
)

function addFiles(files) {
  for (const file of [...files].filter(f => f.type.startsWith('image/'))) {
    if (total.value >= MAX_IMAGES) return showToast(`Up to ${MAX_IMAGES} images per character`, 'error')
    images.value.push({ kind: 'file', file, preview: URL.createObjectURL(file), key: ++keySeq })
  }
}

function addFromLibrary(items) {
  for (const i of items.slice(0, MAX_IMAGES - total.value)) {
    images.value.push({ kind: 'media', mediaId: i.id, preview: i.thumb_url || i.url, key: ++keySeq })
  }
}

const imageUrl = img => (img.kind === 'saved' ? characterImageUrl(props.character.id, img.saved) : img.preview)

function removeImage(img) {
  if (img.kind === 'file') URL.revokeObjectURL(img.preview)
  images.value = images.value.filter(x => x !== img)
}

function moveImage(from, to) {
  if (from === to || from == null) return
  const list = [...images.value]
  list.splice(to, 0, ...list.splice(from, 1))
  images.value = list
}

// Drag a thumbnail onto another to put it there (images dropped from outside are added)
function onDragStart(e, i) {
  dragFrom.value = i
  e.dataTransfer.effectAllowed = 'move'
}

function onDropOn(e, i) {
  if (dragFrom.value == null) return addFiles(e.dataTransfer?.files || [])
  moveImage(dragFrom.value, i)
  dragFrom.value = null
}

function addImage(id, p) {
  if (p.kind === 'chat') return copyChatImageToCharacter(id, p.conversationId, p.file)
  if (p.kind === 'generation') return copyGenerationImageToCharacter(id, p.project, p.filename)
  if (p.kind === 'media') return importMedia(p.mediaId, { target: 'character', character_id: id })
  return uploadCharacterImage(id, p.file)
}

async function save() {
  if (!name.value.trim()) return showToast('Give the character a name', 'error')
  saving.value = true
  try {
    const fields = { name: name.value.trim(), description: description.value.trim() }
    const saved = images.value.filter(img => img.kind === 'saved').map(img => img.saved)
    let c = isNew.value
      ? await createCharacter({ ...fields, conversation_id: props.conversationId })
      : await updateCharacter(props.character.id, { ...fields, images: saved })
    // New images are added at the end; then put everything in the order shown
    const order = []
    for (const img of images.value) {
      if (img.kind !== 'saved') c = await addImage(c.id, img)
      order.push(img.kind === 'saved' ? img.saved : c.images[c.images.length - 1])
    }
    if (order.join('/') !== c.images.join('/')) c = await updateCharacter(c.id, { images: order })
    emit('saved', c)
    emit('close')
  } catch (e) {
    showToast(`Save failed: ${e.message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function promote() {
  try {
    emit('saved', await promoteCharacter(props.character.id))
    showToast(`${props.character.name} saved — attach it to any chat or generation`, 'success')
  } catch (e) {
    showToast(`Couldn't save: ${e.message}`, 'error')
  }
}

async function remove() {
  if (!confirm(`Delete “${props.character.name}” and its images?`)) return
  try {
    await deleteCharacter(props.character.id)
    emit('deleted', props.character.id)
    emit('close')
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error')
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @click.self="emit('close')" @keydown.esc="emit('close')">
      <div class="dialog" role="dialog" aria-label="Character">
        <div class="head">
          <h3>{{ isNew ? 'New character' : character.name }}</h3>
          <span v-if="character?.adhoc || (isNew && conversationId)" class="tag" title="Only in this chat until saved"
            >this chat only</span
          >
          <button class="x" title="Close" @click="emit('close')">✕</button>
        </div>
        <p class="sub">
          The description is added to prompts and the images go to the model as references, so the character looks the
          same every time. Drag the images into order: the first is the main one, and when an image model takes fewer
          images than there are, each character's first ones go before the rest.
        </p>

        <label for="char-name">Name</label>
        <input id="char-name" ref="nameInput" v-model="name" maxlength="100" placeholder="e.g. Linh" />
        <label for="char-desc">Description</label>
        <textarea
          id="char-desc"
          v-model="description"
          maxlength="4000"
          placeholder="Appearance and anything that should stay the same: age, hair, build, clothing, style…"
        ></textarea>

        <label
          >Images <span class="count">{{ total }}/{{ MAX_IMAGES }}</span></label
        >
        <div class="images" @dragover.prevent @drop.prevent="addFiles($event.dataTransfer?.files || [])">
          <div
            v-for="(img, i) in images"
            :key="img.key"
            class="img"
            :class="{ main: i === 0, pending: img.kind !== 'saved', dragging: dragFrom === i }"
            draggable="true"
            title="Drag to reorder"
            @dragstart="onDragStart($event, i)"
            @dragend="dragFrom = null"
            @dragover.prevent
            @drop.prevent.stop="onDropOn($event, i)"
          >
            <img :src="imageUrl(img)" alt="" draggable="false" />
            <span v-if="i === 0" class="main-tag">main</span>
            <span v-else class="pos-tag">{{ i + 1 }}</span>
            <button v-if="i > 0" class="img-btn star" title="Make this the main image" @click="moveImage(i, 0)">
              ★
            </button>
            <button class="img-btn x-btn" title="Remove" @click="removeImage(img)">✕</button>
          </div>
          <template v-if="total < MAX_IMAGES">
            <label class="img add" title="Upload from this computer (or drop images here)">
              ＋
              <span class="add-label">Upload</span>
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                multiple
                hidden
                @change="addFiles(takeFiles($event))"
              />
            </label>
            <button
              type="button"
              class="img add"
              title="Choose from your uploads and creations"
              @click="pickerOpen = true"
            >
              🗂
              <span class="add-label">Library</span>
            </button>
          </template>
        </div>

        <MediaPicker
          :open="pickerOpen"
          title="Add images to the character"
          :max="MAX_IMAGES - total"
          @pick="addFromLibrary"
          @close="pickerOpen = false"
        />

        <div class="actions">
          <button v-if="character" class="btn btn-danger" @click="remove">Delete</button>
          <button
            v-if="character?.adhoc"
            class="btn btn-secondary"
            title="Keep it after this chat, and use it anywhere"
            @click="promote"
          >
            ⭐ Save to characters
          </button>
          <span class="spacer"></span>
          <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
          <button class="btn btn-primary" :disabled="saving || !name.trim()" @click="save">
            {{ saving ? 'Saving…' : isNew ? 'Create' : 'Save' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 1100;
  background: rgba(0, 0, 0, 0.7);
  display: grid;
  place-items: center;
  padding: 16px;
}

.dialog {
  width: min(560px, 100%);
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.head h3 {
  font-size: 1.1rem;
  font-weight: 600;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--surface2);
  color: var(--yellow);
}

.x {
  background: none;
  border: none;
  color: var(--text2);
  font-size: 1rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}

.x:hover {
  background: var(--surface2);
  color: var(--text);
}

.sub {
  font-size: 0.8rem;
  color: var(--text2);
  margin-bottom: 8px;
  line-height: 1.45;
}

label {
  font-size: 0.75rem;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-top: 4px;
}

.count {
  text-transform: none;
  letter-spacing: 0;
}

input,
textarea {
  width: 100%;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  font: inherit;
  font-size: 0.9rem;
}

textarea {
  min-height: 110px;
  resize: vertical;
}

.images {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  gap: 8px;
}

.img {
  position: relative;
  aspect-ratio: 1;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--surface2);
}

.img.main {
  border-color: var(--accent);
}

.img[draggable='true'] {
  cursor: grab;
}

.img.dragging {
  opacity: 0.4;
}

.img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.img.add {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  font-size: 1.6rem;
  color: var(--text2);
  cursor: pointer;
  border-style: dashed;
  margin: 0;
  text-transform: none;
}

.add-label {
  font-size: 0.68rem;
}

.img.add:hover {
  color: var(--text);
  border-color: var(--accent);
}

.main-tag {
  position: absolute;
  left: 4px;
  bottom: 4px;
  font-size: 0.62rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--accent);
  color: #fff;
}

.pos-tag {
  position: absolute;
  left: 4px;
  bottom: 4px;
  font-size: 0.62rem;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
}

.img-btn {
  position: absolute;
  top: 4px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 0.7rem;
  cursor: pointer;
}

.x-btn {
  right: 4px;
}

.star {
  left: 4px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.actions .btn {
  padding: 8px 14px;
}

.spacer {
  flex: 1;
}
</style>
