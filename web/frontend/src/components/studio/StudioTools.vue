<!-- Tools & library, shown in the center pane (its own top-level button, no
     longer buried under Settings). Links to the library/tool panes plus the
     global defaults and chat import. -->
<script setup>
defineEmits(['close', 'navigate', 'defaults', 'import'])

const TOOLS = [
  { route: 'characters', label: 'Characters', note: 'Reusable characters for chats and generations' },
  { route: 'instructions', label: 'Instructions', note: 'Snippets and groups sent to the chat model' },
  { route: 'usage', label: 'Credit usage', note: 'Balances for every provider' },
  { route: 'request-log', label: 'Request log', note: 'What was sent to each provider' },
]
</script>

<template>
  <div class="tools">
    <div class="twrap">
      <div class="thead">
        <h1>Tools &amp; library</h1>
        <button class="closebtn" @click="$emit('close')">
          <svg class="ic"><use href="#s-chevL" /></svg> Back
        </button>
      </div>

      <div class="links">
        <button class="link" @click="$emit('defaults')">
          <span class="lmain"><span class="llabel">Default instructions &amp; characters</span></span>
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
          <span class="lmain"><span class="llabel">Import chats…</span></span>
          <svg class="ic"><use href="#s-chev" /></svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tools {
  flex: 1;
  overflow-y: auto;
  padding: 32px 22px;
}
.twrap {
  max-width: 720px;
  margin: 0 auto;
}
.thead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 22px;
}
h1 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
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
.links {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: 14px;
  padding: 8px;
}
.link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: none;
  border-radius: 9px;
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
  gap: 2px;
  min-width: 0;
}
.llabel {
  font-size: 14px;
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
