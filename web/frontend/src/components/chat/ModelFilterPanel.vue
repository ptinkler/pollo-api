<!-- The model picker's filter menu: tick as many providers / capabilities as
     you like (they narrow the list live). Sits inside the picker's own pop-up. -->
<script setup>
defineProps({
  providers: { type: Array, default: () => [] }, // [{ id, label, n, title, color }]
  tags: { type: Array, default: () => [] }, // [{ slug, label, n, color }]
  selProviders: { type: Array, default: () => [] },
  selTags: { type: Array, default: () => [] },
  uncensoredCount: { type: Number, default: 0 },
  hiddenCount: { type: Number, default: 0 },
  anyFilter: { type: Boolean, default: false },
})
const uncensoredOnly = defineModel('uncensoredOnly', { type: Boolean, default: false })
const showHidden = defineModel('showHidden', { type: Boolean, default: false })
defineEmits(['toggle-provider', 'toggle-tag', 'clear'])
</script>

<template>
  <div class="fpanel" role="group" aria-label="Filters" @mousedown.stop>
    <template v-if="providers.length">
      <div class="fhead">Provider</div>
      <label v-for="p in providers" :key="p.id" class="frow provider" :title="p.title">
        <input type="checkbox" :checked="selProviders.includes(p.id)" @change="$emit('toggle-provider', p.id)" />
        <span class="flabel"
          ><span class="fpill" :style="{ '--b': p.color }">{{ p.label }}</span></span
        >
        <span class="fn">{{ p.n }}</span>
      </label>
    </template>

    <template v-if="tags.length">
      <div v-if="providers.length" class="fsep"></div>
      <div class="fhead">Capability</div>
      <label v-for="t in tags" :key="t.slug" class="frow tag">
        <input type="checkbox" :checked="selTags.includes(t.slug)" @change="$emit('toggle-tag', t.slug)" />
        <span class="flabel"
          ><span class="fpill" :style="{ '--b': t.color }">{{ t.label }}</span></span
        >
        <span class="fn">{{ t.n }}</span>
      </label>
    </template>

    <template v-if="uncensoredCount || hiddenCount">
      <div class="fsep"></div>
      <label v-if="uncensoredCount" class="frow uncensored-only" title="Only list models marked uncensored">
        <input v-model="uncensoredOnly" type="checkbox" />
        <span class="flabel">Uncensored only</span>
        <span class="fn">{{ uncensoredCount }}</span>
      </label>
      <label
        v-if="hiddenCount"
        class="frow show-hidden"
        title="Models left out of the list: not enabled for this API key, or retired"
      >
        <input v-model="showHidden" type="checkbox" />
        <span class="flabel">Show hidden models</span>
        <span class="fn">{{ hiddenCount }}</span>
      </label>
    </template>

    <button v-if="anyFilter" type="button" class="fclear" @click="$emit('clear')">Clear all filters</button>
  </div>
</template>

<style scoped>
.fpanel {
  position: absolute;
  top: 46px;
  right: 8px;
  z-index: 2;
  width: min(260px, calc(100% - 16px));
  max-height: calc(100% - 54px);
  overflow-y: auto;
  padding: 8px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
}
.fhead {
  padding: 4px 8px;
  font-size: 0.75rem;
  color: var(--text2);
}
.fsep {
  height: 1px;
  margin: 6px 4px;
  background: var(--border);
}
.frow {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 8px;
  border-radius: 8px;
  font-size: 0.85rem;
  color: var(--text);
  cursor: pointer;
  user-select: none;
}
.frow:hover {
  background: var(--surface);
}
.frow input {
  margin: 0;
  accent-color: var(--accent);
}
.flabel {
  flex: 1;
}
/* The same pill the row badges use, in the tag's own colour */
.fpill {
  --b: var(--text2);
  display: inline-block;
  padding: 1px 7px;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 600;
  line-height: 1.5;
  color: var(--b);
  background: color-mix(in srgb, var(--b) 16%, transparent);
}
.fn {
  font-size: 0.75rem;
  color: var(--text2);
}
.fclear {
  display: block;
  width: 100%;
  margin-top: 6px;
  padding: 7px 8px;
  background: none;
  border: none;
  border-top: 1px solid var(--border);
  color: var(--text2);
  font-size: 0.8rem;
  text-align: left;
  cursor: pointer;
}
.fclear:hover {
  color: var(--text);
}
</style>
