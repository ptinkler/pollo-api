<!-- One joined strip: this thread's spend + the provider balances. Every segment
     is clickable — balances open the usage page, Spent opens a per-model breakdown. -->
<script setup>
import { computed, ref } from 'vue'
import { shortModel, fmtCost, creditsToUsd } from '../../utils/format'

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
  {
    id: 'pollo',
    label: 'Pollo',
    value: props.balances.pollo == null ? '—' : fmtBal(creditsToUsd(props.balances.pollo)),
    tip: `Pollo balance (${fmtCredits(props.balances.pollo)} credits)`,
  },
  { id: 'openrouter', label: 'OpenRouter', value: fmtBal(props.balances.openrouter), tip: 'OpenRouter balance' },
  { id: 'venice', label: 'Venice', value: fmtBal(props.balances.venice), tip: 'Venice balance' },
])

const label = computed(() => {
  const s = props.spend
  if (!s) return ''
  // Pollo's credits count in dollars too, so one figure covers every provider
  const cr = (s.credits || 0) + (s.inherited_credits || 0)
  return fmtCost((s.usd || 0) + (s.inherited_usd || 0) + creditsToUsd(cr))
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
    <button v-if="label" class="bseg spent" title="Spent in this thread — click for breakdown" @click="open = !open">
      Spent <b>{{ label }}</b>
    </button>
    <a
      v-for="p in pills"
      :key="p.id"
      class="bseg"
      :class="p.id"
      :title="`${p.tip} — click for usage`"
      href="/usage"
      @click.prevent="emit('usage')"
    >
      {{ p.label }} <b>{{ p.value }}</b>
    </a>

    <div v-if="open" class="pop-back" @click="open = false"></div>
    <div v-if="open" class="pop">
      <div class="pop-title">Spent in this thread</div>
      <div v-for="r in byModel" :key="r.model" class="row">
        <span class="m">{{ shortModel(r.model) }}</span
        ><b>{{ fmtCost(r.usd) }}</b>
      </div>
      <div v-if="spend?.inherited_usd || spend?.inherited_credits" class="row">
        <span class="m">Inherited from the branched chat</span>
        <b>{{ fmtCost((spend.inherited_usd || 0) + creditsToUsd(spend.inherited_credits)) }}</b>
      </div>
      <div v-if="spend?.credits" class="row">
        <span class="m">Pollo ({{ spend.credits }} cr)</span><b>{{ fmtCost(creditsToUsd(spend.credits)) }}</b>
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
  border-radius: var(--r);
  overflow: visible;
}
.bseg {
  text-decoration: none;
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
.bseg:first-child {
  border-left: 0;
  border-radius: 7px 0 0 7px;
}
.bseg:last-of-type {
  border-radius: 0 7px 7px 0;
}
.bseg:hover {
  background: var(--saccent-soft);
  color: var(--sfg);
}
.bseg b {
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
  background: var(--spanel2);
  border: 1px solid var(--sborder);
  border-radius: var(--r-lg);
  padding: 10px 12px;
  box-shadow: var(--shadow-pop);
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
