<!-- One joined strip: this thread's spend + the provider balances. Every segment
     is clickable — balances open the usage page, Spent opens a per-model breakdown. -->
<script setup>
import { computed, ref } from 'vue'
import { shortModel, fmtCost } from '../../utils/format'

const props = defineProps({
  balances: { type: Object, default: () => ({}) },
  spend: { type: Object, default: null },
  messages: { type: Array, default: () => [] },
})
const emit = defineEmits(['usage'])

const open = ref(false)
const fmtCredits = v => (v == null ? '—' : Math.round(v).toLocaleString())
const fmtBal = v => (v == null ? '—' : `$${v.toFixed(2)}`)

const pills = computed(() => [
  { id: 'pollo', label: 'Pollo', value: fmtCredits(props.balances.pollo), tip: 'Pollo credits remaining' },
  { id: 'openrouter', label: 'OpenRouter', value: fmtBal(props.balances.openrouter), tip: 'OpenRouter balance' },
  { id: 'venice', label: 'Venice', value: fmtBal(props.balances.venice), tip: 'Venice balance' },
])

const label = computed(() => {
  const s = props.spend
  if (!s) return ''
  const usd = (s.usd || 0) + (s.inherited_usd || 0)
  const cr = (s.credits || 0) + (s.inherited_credits || 0)
  return [usd && fmtCost(usd), cr && `${cr} cr`].filter(Boolean).join(' · ')
})

// USD per model for this thread's own messages (inherited spend is one line)
const byModel = computed(() => {
  const totals = new Map()
  for (const m of props.messages) {
    if (!m.cost) continue
    const key = m.model || 'unknown'
    totals.set(key, (totals.get(key) || 0) + Number(m.cost))
  }
  return [...totals].map(([model, usd]) => ({ model, usd })).sort((a, b) => b.usd - a.usd)
})
</script>

<template>
  <div class="bals">
    <button v-if="label" class="seg spent" title="Spent in this thread — click for breakdown" @click="open = !open">
      Spent <b>{{ label }}</b>
    </button>
    <button
      v-for="p in pills"
      :key="p.id"
      class="seg"
      :class="p.id"
      :title="`${p.tip} — click for usage`"
      @click="emit('usage')"
    >
      {{ p.label }} <b>{{ p.value }}</b>
    </button>

    <div v-if="open" class="pop-back" @click="open = false"></div>
    <div v-if="open" class="pop">
      <div class="pop-title">Spent in this thread</div>
      <div v-for="r in byModel" :key="r.model" class="row">
        <span class="m">{{ shortModel(r.model) }}</span
        ><b>{{ fmtCost(r.usd) }}</b>
      </div>
      <div v-if="spend?.inherited_usd || spend?.inherited_credits" class="row">
        <span class="m">Inherited from the branched chat</span>
        <b>{{
          [
            spend.inherited_usd && fmtCost(spend.inherited_usd),
            spend.inherited_credits && `${spend.inherited_credits} cr`,
          ]
            .filter(Boolean)
            .join(' · ')
        }}</b>
      </div>
      <div v-if="spend?.credits" class="row">
        <span class="m">Pollo credits</span><b>{{ spend.credits }} cr</b>
      </div>
      <div v-if="!byModel.length && !spend?.credits" class="row"><span class="m">Nothing yet</span></div>
      <button class="pop-link" @click="((open = false), emit('usage'))">Full usage →</button>
    </div>
  </div>
</template>

<style scoped>
.bals {
  position: relative;
  display: inline-flex;
  border: 1px solid var(--sborder);
  border-radius: 7px;
  overflow: visible;
}
.seg {
  font: inherit;
  font-size: 12px;
  color: var(--smuted);
  background: none;
  border: 0;
  border-left: 1px solid var(--sborder);
  padding: 3px 9px;
  white-space: nowrap;
  cursor: pointer;
}
.seg:first-child {
  border-left: 0;
  border-radius: 6px 0 0 6px;
}
.seg:last-of-type {
  border-radius: 0 6px 6px 0;
}
.seg:hover {
  background: var(--saccent-soft);
  color: var(--sfg);
}
.seg b {
  color: var(--sfg);
  font-weight: 600;
}
.pop-back {
  position: fixed;
  inset: 0;
  z-index: 40;
}
.pop {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 41;
  min-width: 260px;
  background: var(--sbg2);
  border: 1px solid var(--sborder);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  font-size: 12.5px;
  color: var(--sfg);
}
.pop-title {
  font-weight: 600;
  margin-bottom: 6px;
}
.row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 2px 0;
}
.m {
  color: var(--smuted);
}
.pop-link {
  margin-top: 8px;
  background: none;
  border: 0;
  color: var(--saccent);
  cursor: pointer;
  padding: 0;
  font: inherit;
}
</style>
