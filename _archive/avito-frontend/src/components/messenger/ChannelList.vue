<script setup>
import { ref } from 'vue'
import { useMessengerStore } from '../../stores/messenger'

const messengerStore = useMessengerStore()
const searchQuery = ref('')

function filteredChannels() {
  if (!searchQuery.value) return messengerStore.channels
  const q = searchQuery.value.toLowerCase()
  return messengerStore.channels.filter((c) =>
    (c.contact_name || '').toLowerCase().includes(q) ||
    (c.info?.item_title || '').toLowerCase().includes(q)
  )
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl border border-gray-700/50 flex flex-col overflow-hidden">
    <!-- Search -->
    <div class="p-3 border-b border-gray-700/50">
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Search chats..."
        class="w-full px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500"
      />
    </div>

    <!-- Channels -->
    <div class="flex-1 overflow-y-auto">
      <div
        v-for="ch in filteredChannels()"
        :key="ch.id"
        @click="messengerStore.selectChannel(ch.id)"
        class="px-3 py-3 cursor-pointer border-b border-gray-700/20 transition-colors"
        :class="messengerStore.activeChannelId === ch.id
          ? 'bg-avito-card'
          : 'hover:bg-gray-700/20'"
      >
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium text-white truncate">{{ ch.contact_name || 'Unknown' }}</span>
          <div class="flex items-center gap-2">
            <span v-if="ch.unread_count > 0" class="bg-blue-500 text-white text-xs rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
              {{ ch.unread_count }}
            </span>
            <span class="text-xs text-gray-500">{{ formatTime(ch.last_message_at) }}</span>
          </div>
        </div>
        <p class="text-xs text-gray-400 truncate mt-1">
          {{ ch.info?.item_title || '' }}
        </p>
        <p class="text-xs text-gray-500 truncate mt-0.5">
          {{ ch.last_message_text || '' }}
        </p>
      </div>

      <div v-if="messengerStore.channels.length === 0" class="p-4 text-center text-gray-500 text-sm">
        No channels loaded
      </div>
    </div>
  </div>
</template>
