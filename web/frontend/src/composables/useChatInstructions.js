import { computed, ref } from 'vue'
import { fetchInstructions, patchConversation } from './useChat'

// Saved custom instructions, and the one attached to the open chat (or to
// the next new one: the default, until another is picked)
export function useChatInstructions({ convId, conversation, showToast }) {
  const instructions = ref([])
  const instructionId = ref(null)
  const attachedInstruction = computed(() => instructions.value.find(i => i.id === instructionId.value))
  const defaultInstructionId = () => instructions.value.find(i => i.is_default)?.id ?? null

  async function loadInstructions() {
    try {
      instructions.value = (await fetchInstructions()).instructions
      if (!convId.value) instructionId.value = defaultInstructionId()
    } catch {
      /* 401 handled by auth prompt */
    }
  }

  // Picking from the sidebar: saved on the chat right away (new chats get it on creation)
  async function setInstruction(id) {
    instructionId.value = id
    if (!convId.value) return
    try {
      const updated = await patchConversation(convId.value, { instruction_id: id })
      if (conversation.value) conversation.value.instruction_id = updated.instruction_id
    } catch (e) {
      showToast(`Couldn't attach instructions: ${e.message}`, 'error')
    }
  }

  async function onInstructionsChanged({ saved, deleted }) {
    await loadInstructions()
    if (deleted && instructionId.value === deleted) instructionId.value = null
    // Saving from the dialog attaches it here if nothing was attached yet
    if (saved && instructionId.value == null) setInstruction(saved.id)
  }

  return {
    instructions,
    instructionId,
    attachedInstruction,
    defaultInstructionId,
    loadInstructions,
    setInstruction,
    onInstructionsChanged,
  }
}
