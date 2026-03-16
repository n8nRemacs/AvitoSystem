<script setup>
import { ref } from 'vue'
import { useMessengerStore } from '../../stores/messenger'

const messengerStore = useMessengerStore()
const text = ref('')
const sending = ref(false)

async function send() {
  if (!text.value.trim() || sending.value) return
  sending.value = true
  try {
    await messengerStore.sendMessage(text.value)
    text.value = ''
  } catch (e) {
    console.error('send failed:', e)
  }
  sending.value = false
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

let typingTimeout = null
function onInput() {
  if (typingTimeout) clearTimeout(typingTimeout)
  typingTimeout = setTimeout(() => {
    if (messengerStore.activeChannelId) {
      messengerStore.sendTyping(messengerStore.activeChannelId)
    }
  }, 500)
}
</script>

<template>
  <div class="px-4 py-3 border-t border-gray-700/50">
    <div class="flex gap-2">
      <textarea
        v-model="text"
        @keydown="onKeydown"
        @input="onInput"
        rows="1"
        placeholder="Type a message..."
        class="flex-1 px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white resize-none focus:outline-none focus:border-blue-500"
      />
      <button
        @click="send"
        :disabled="!text.trim() || sending"
        class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
      >
        Send
      </button>
    </div>
  </div>
</template>
