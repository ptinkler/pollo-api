import { computed, ref } from 'vue'
import { fetchInstructions, patchConversation } from './useChat'

// Saved instruction snippets and groups, and the ones attached to the open
// chat (or to the next new one: the defaults, until the user changes them).
// A chat holds any number of snippets and groups; both are flattened and
// de-duped server-side into what the model is sent (see _conversation_instructions).
// `inherited`: { snippets, groups } — ids its defaults attach, on top of its own.
export function useChatInstructions({ convId, conversation, showToast, inherited }) {
  const instructions = ref([]) // all saved snippets
  const groups = ref([]) // all saved groups
  const instructionIds = ref([]) // snippets attached to this chat
  const groupIds = ref([]) // groups attached to this chat

  const withInherited = (kind, own) => [...new Set([...(inherited?.value[kind] || []), ...own])]
  const attachedInstructions = computed(() =>
    withInherited('snippets', instructionIds.value)
      .map(id => instructions.value.find(i => i.id === id))
      .filter(Boolean),
  )
  const attachedGroups = computed(() =>
    withInherited('groups', groupIds.value)
      .map(id => groups.value.find(g => g.id === id))
      .filter(Boolean),
  )
  // Groups first, then individual snippets — what the sidebar summary shows
  const attachmentSummary = computed(() =>
    [...attachedGroups.value.map(g => g.name), ...attachedInstructions.value.map(i => i.name)].join(', '),
  )

  async function loadInstructions() {
    try {
      const data = await fetchInstructions()
      instructions.value = data.instructions
      groups.value = data.groups || []
      // ChatView owns new-chat seeding (it also knows the pending space), so
      // loading the catalogue never changes what's attached here.
    } catch {
      /* 401 handled by auth prompt */
    }
  }

  async function patch(fields) {
    if (!convId.value) return // new chats get them on creation
    try {
      await patchConversation(convId.value, fields)
      if (conversation.value) Object.assign(conversation.value, fields)
    } catch (e) {
      showToast(`Couldn't update instructions: ${e.message}`, 'error')
    }
  }

  function setInstructions(ids) {
    instructionIds.value = ids
    patch({ instruction_ids: ids })
  }

  function setGroups(ids) {
    groupIds.value = ids
    patch({ instruction_group_ids: ids })
  }

  // The chat model saved and attached a snippet (create_instruction tool)
  function onInstructionUsed(item, ids) {
    if (item) {
      const i = instructions.value.findIndex(x => x.id === item.id)
      if (i === -1) instructions.value.push(item)
      else instructions.value.splice(i, 1, item)
    }
    instructionIds.value = ids
  }

  // The management dialog created/edited/deleted snippets or groups
  async function onInstructionsChanged() {
    await loadInstructions()
    // Drop anything that no longer exists from this chat's attachments
    instructionIds.value = instructionIds.value.filter(id => instructions.value.some(i => i.id === id))
    groupIds.value = groupIds.value.filter(id => groups.value.some(g => g.id === id))
  }

  return {
    instructions,
    groups,
    instructionIds,
    groupIds,
    attachedInstructions,
    attachedGroups,
    attachmentSummary,
    loadInstructions,
    setInstructions,
    setGroups,
    onInstructionUsed,
    onInstructionsChanged,
  }
}
