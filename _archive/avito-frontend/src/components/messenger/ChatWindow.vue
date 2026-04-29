<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useMessengerStore } from '../../stores/messenger'
import { useAuthStore } from '../../stores/auth'
import MessageBubble from './MessageBubble.vue'
import ComposeBox from './ComposeBox.vue'

const messengerStore = useMessengerStore()
const authStore = useAuthStore()
const messagesContainer = ref(null)

const isTyping = computed(() => {
  if (!messengerStore.activeChannelId) return false
  return messengerStore.isTyping(messengerStore.activeChannelId)
})

watch(
  () => messengerStore.messages.length,
  async () => {
    await nextTick()
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  }
)
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl border border-gray-700/50 flex flex-col overflow-hidden">
    <template v-if="messengerStore.activeChannel">
      <!-- Header -->
      <div class="px-4 py-3 border-b border-gray-700/50 flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold text-white">{{ messengerStore.activeChannel.contact_name }}</h3>
          <p class="text-xs text-gray-400">{{ messengerStore.activeChannel.info?.item_title }}</p>
        </div>
      </div>

      <!-- Messages -->
      <div ref="messagesContainer" class="flex-1 overflow-y-auto p-4 space-y-2">
        <MessageBubble
          v-for="msg in messengerStore.messages"
          :key="msg.id"
          :message="msg"
          :isOwn="String(msg.author_id) === String(authStore.session?.user_id)"
        />
        <div v-if="messengerStore.messages.length === 0" class="text-center text-gray-500 text-sm py-8">
          No messages
        </div>
        <!-- Typing indicator -->
        <div v-if="isTyping" class="flex items-center gap-1 text-xs text-gray-400 py-1">
          <span class="flex gap-0.5">
            <span class="w-1 h-1 rounded-full bg-gray-400 animate-bounce" style="animation-delay: 0ms"></span>
            <span class="w-1 h-1 rounded-full bg-gray-400 animate-bounce" style="animation-delay: 150ms"></span>
            <span class="w-1 h-1 rounded-full bg-gray-400 animate-bounce" style="animation-delay: 300ms"></span>
          </span>
          <span>typing...</span>
        </div>
      </div>

      <!-- Compose -->
      <ComposeBox />
    </template>

    <div v-else class="flex-1 flex items-center justify-center text-gray-500 text-sm">
      Select a chat to start messaging
    </div>
  </div>
</template>
