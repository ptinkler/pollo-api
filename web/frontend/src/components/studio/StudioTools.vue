<!-- Tools & library, shown in the center pane (its own top-level button, no
     longer buried under Settings). Links to the library/tool panes plus the
     global defaults and chat import. -->
<script setup>
defineEmits(['close', 'navigate', 'defaults', 'import'])

const TOOLS = [
  { route: 'characters', label: 'Characters', note: 'Reusable characters for chats and generations' },
  { route: 'instructions', label: 'Instructions', note: 'Snippets and groups sent to the chat model' },
  { route: 'presets', label: 'Presets', note: 'Saved model and option sets' },
  { route: 'usage', label: 'Credit usage', note: 'Balances for every provider' },
  { route: 'request-log', label: 'Request log', note: 'What was sent to each provider' },
]
</script>

<template>
  <div class="page">
    <div class="pwrap narrow">
      <div class="phead">
        <h1>Tools &amp; library</h1>
        <div class="hactions">
          <button class="btn" @click="$emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <div class="links">
        <button class="link" @click="$emit('defaults')">
          <span class="lmain"
            ><span class="llabel">Default instructions &amp; characters</span
            ><span class="lnote">Attached to every chat, or to every chat in a space</span></span
          >
          <svg class="ic"><use href="#s-chev" /></svg>
        </button>
        <button v-for="t in TOOLS" :key="t.route" class="link" @click="$emit('navigate', t.route)">
          <span class="lmain"
            ><span class="llabel">{{ t.label }}</span
            ><span class="lnote">{{ t.note }}</span></span
          >
          <svg class="ic"><use href="#s-chev" /></svg>
        </button>
        <button class="link" @click="$emit('import')">
          <span class="lmain"
            ><span class="llabel">Import chats…</span
            ><span class="lnote">Bring in an export from another instance</span></span
          >
          <svg class="ic"><use href="#s-chev" /></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.links {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: var(--r-lg);
  padding: 6px;
}
.link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: none;
  border-radius: var(--r);
  background: none;
  color: var(--sfg);
  cursor: pointer;
  text-align: left;
}
.link:hover {
  background: var(--shover);
}
.lmain {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.llabel {
  font-size: 13.5px;
  font-weight: 500;
}
.lnote {
  font-size: 12px;
  color: var(--smuted);
}
.link .ic {
  color: var(--sfaint);
  flex-shrink: 0;
}
</style>
