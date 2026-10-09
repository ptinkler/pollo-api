<script setup>
// The empty chat: a greeting and a few prompts to start from
const emit = defineEmits(['suggest'])

const SUGGESTIONS = [
  { label: '💡 Explain diffusion models', text: 'Explain how diffusion models generate images, simply.' },
  { label: '🖼 Draw a snowy cabin', text: 'Draw a cozy isometric cabin in a snowy forest at dusk, warm window light' },
  {
    label: '🎬 Video of waves',
    text: 'Make a short video of ocean waves crashing on black sand at golden hour, slow dolly shot',
  },
  {
    label: '✨ Brainstorm & draw',
    text: 'Brainstorm 5 visual concepts for a coffee brand launch, then draw your favourite',
  },
]
</script>

<template>
  <div class="welcome">
    <h2><span>Hello.</span> What shall we make?</h2>
    <p>
      Chat with any OpenRouter model. Ask for a picture or a clip and it'll make one with your image and video models.
    </p>
    <div class="suggestions">
      <button v-for="s in SUGGESTIONS" :key="s.label" @click="emit('suggest', s.text)">{{ s.label }}</button>
    </div>
  </div>
</template>

<style scoped>
.welcome {
  max-width: 720px;
  margin: 14vh auto 0;
}

.welcome h2 {
  font-size: 2rem;
  font-weight: 600;
  line-height: 1.25;
  margin-bottom: 10px;
}

.welcome h2 span {
  background: linear-gradient(90deg, var(--accent2), #4b8bf5, #e17055);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.welcome p {
  color: var(--text2);
  margin-bottom: 24px;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.suggestions button {
  text-align: left;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  cursor: pointer;
  font-size: 0.87rem;
  line-height: 1.4;
  transition:
    border-color 0.2s,
    transform 0.2s;
}

.suggestions button:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
}

@media (max-width: 860px) {
  .welcome {
    margin-top: 4vh;
  }

  .welcome h2 {
    font-size: 1.5rem;
  }
}
</style>
