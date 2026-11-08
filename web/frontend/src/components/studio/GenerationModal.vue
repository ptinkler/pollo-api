<!-- The "big view" for a generation: large media on the left, its prompt and
     details plus actions on the right. Works for both the in-thread gallery
     and the cross-thread Favourites gallery — `canManage` gates the actions
     that need the generation's message to be in the open thread. -->
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { shortModel, fmtCost } from '../../utils/format'

const props = defineProps({
  // { url, kind, file, prompt?, model?, cost?, created_at?, favourite?, conversation_title? }
  item: { type: Object, default: null },
  canManage: { type: Boolean, default: false },
  // Studio theme ('dark' | 'light'), so the body-teleported modal keeps the --s* vars.
  theme: { type: String, default: '' },
})
const emit = defineEmits(['close', 'favourite', 'use-image', 'use-settings', 'regenerate', 'delete', 'open-thread'])

const isVideo = computed(() => props.item?.kind === 'video')
const isError = computed(() => props.item?.status === 'error')
const loop = ref(false) // videos don't autoplay; the user opts into looping
const when = computed(() => {
  const d = props.item?.created_at && new Date(props.item.created_at)
  return d && !isNaN(d) ? d.toLocaleString() : ''
})

function onKey(e) {
  if (e.key === 'Escape' && props.item) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <!-- Teleport to body (not .studio): .studio is an ancestor of this modal, so it
       isn't in the DOM yet when the Teleport first mounts — resolving .studio then
       fails and the modal never opens. The `studio` class + data-theme re-supply the
       --s* theme vars that would otherwise only cascade from the .studio ancestor. -->
  <Teleport to="body">
    <div v-if="item" class="gm-back studio" :data-theme="theme || undefined" @click="emit('close')">
      <div class="gm-card" @click.stop>
        <button class="gm-x" title="Close" @click="emit('close')">×</button>

        <div class="gm-media" :class="{ 'is-error': isError }">
          <div v-if="isError" class="gm-err">
            <div class="gm-err-title">{{ item.moderated ? 'Blocked by moderation' : 'Generation failed' }}</div>
            <div class="gm-err-msg">{{ item.error || 'Unknown error' }}</div>
          </div>
          <template v-else-if="isVideo">
            <video :src="item.url" controls :loop="loop" playsinline></video>
            <label class="gm-loop"><input v-model="loop" type="checkbox" /> Loop</label>
          </template>
          <img v-else :src="item.url" alt="" />
        </div>

        <div class="gm-side">
          <div class="gm-scroll">
            <div class="gm-prompt">{{ item.original_prompt || item.prompt || 'No prompt' }}</div>
            <details v-if="item.original_prompt && item.prompt && item.prompt !== item.original_prompt" class="gm-sent">
              <summary>Prompt sent to the model</summary>
              <div class="gm-prompt">{{ item.prompt }}</div>
            </details>
            <dl class="gm-meta">
              <template v-if="item.model">
                <dt>Model</dt>
                <dd>{{ shortModel(item.model) }}</dd>
              </template>
              <template v-if="item.cost">
                <dt>Cost</dt>
                <dd>{{ fmtCost(item.cost) || '—' }}</dd>
              </template>
              <template v-if="when">
                <dt>Created</dt>
                <dd>{{ when }}</dd>
              </template>
              <template v-if="item.conversation_title">
                <dt>Thread</dt>
                <dd>{{ item.conversation_title }}</dd>
              </template>
            </dl>
          </div>

          <div class="gm-actions">
            <button v-if="!isError" class="gm-btn" :class="{ on: item.favourite }" @click="emit('favourite', item)">
              <svg class="ic"><use href="#s-star" /></svg>{{ item.favourite ? 'Favourited' : 'Favourite' }}
            </button>
            <a v-if="!isError" class="gm-btn" :href="item.url" :download="item.file">
              <svg class="ic"><use href="#s-download" /></svg>Download
            </a>
            <button
              v-if="!isError && item.kind === 'image'"
              class="gm-btn"
              @click="emit('use-image', { file: item.file, mode: 'image', conversation_id: item.conversation_id })"
            >
              🖼 Picture from this
            </button>
            <button
              v-if="!isError"
              class="gm-btn"
              @click="emit('use-image', { file: item.file, mode: 'video', conversation_id: item.conversation_id })"
            >
              🎬 Video from this
            </button>
            <button v-if="canManage" class="gm-btn" @click="emit('use-settings', item)">
              <svg class="ic"><use href="#s-cog" /></svg>Use settings
            </button>
            <button v-if="canManage" class="gm-btn" :class="{ primary: isError }" @click="emit('regenerate', item)">
              <svg class="ic"><use href="#s-refresh" /></svg>{{ isError ? 'Retry' : 'Regenerate' }}
            </button>
            <button
              v-if="!canManage && item.conversation_id"
              class="gm-btn"
              @click="emit('open-thread', item.conversation_id)"
            >
              Open thread
            </button>
            <button v-if="canManage" class="gm-btn danger" @click="emit('delete', item)">
              <svg class="ic"><use href="#s-trash" /></svg>Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.gm-sent {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--smuted, inherit);
}
.gm-sent summary {
  cursor: pointer;
}
.gm-back {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.82);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.gm-card {
  position: relative;
  display: flex;
  gap: 0;
  width: min(1100px, 95vw);
  max-height: 90vh;
  background: var(--sbg);
  border: 1px solid var(--sborder);
  border-radius: 16px;
  overflow: hidden;
}
.gm-x {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 2;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}
.gm-media {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  display: grid;
  place-items: center;
  background: #000;
  padding: 10px;
}
.gm-media img,
.gm-media video {
  max-width: 100%;
  max-height: calc(90vh - 20px);
  object-fit: contain;
  border-radius: 8px;
}
.gm-media.is-error {
  background: var(--sbg2);
}
.gm-err {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  text-align: center;
  padding: 32px;
  max-width: 440px;
}
.gm-err-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--sdanger, #e5484d);
}
.gm-err-msg {
  font-size: 13px;
  line-height: 1.5;
  color: var(--smuted);
  white-space: pre-wrap;
  word-break: break-word;
}
.gm-btn.primary {
  background: var(--saccent);
  border-color: var(--saccent);
  color: #fff;
}
.gm-btn.primary:hover {
  filter: brightness(1.08);
  background: var(--saccent);
}
.gm-loop {
  position: absolute;
  left: 16px;
  bottom: 14px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #fff;
  background: rgba(0, 0, 0, 0.5);
  padding: 4px 9px;
  border-radius: 7px;
  cursor: pointer;
}
.gm-side {
  flex: 0 0 300px;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--sborder);
  background: var(--spanel2, var(--sbg2));
}
.gm-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 44px 16px 12px;
}
.gm-prompt {
  font-size: 13px;
  line-height: 1.5;
  color: var(--sfg);
  white-space: pre-wrap;
  margin-bottom: 14px;
}
.gm-meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
  margin: 0;
  font-size: 12px;
}
.gm-meta dt {
  color: var(--sfaint);
}
.gm-meta dd {
  margin: 0;
  color: var(--smuted);
  word-break: break-word;
}
.gm-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-top: 1px solid var(--sborder);
}
.gm-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  background: var(--sbg);
  color: var(--sfg);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  text-decoration: none;
}
.gm-btn:hover {
  background: var(--shover);
}
.gm-btn .ic {
  width: 16px;
  height: 16px;
}
.gm-btn.on {
  color: var(--saccent);
  border-color: var(--saccent);
}
.gm-btn.danger:hover {
  color: var(--sdanger, #e5484d);
  border-color: var(--sdanger, #e5484d);
}
@media (max-width: 760px) {
  .gm-card {
    flex-direction: column;
    max-height: 92vh;
  }
  .gm-side {
    flex: 1 1 auto;
    border-left: none;
    border-top: 1px solid var(--sborder);
  }
  .gm-scroll {
    padding-top: 12px;
  }
  .gm-media video,
  .gm-media img {
    max-height: 50vh;
  }
}
</style>
