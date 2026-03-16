<script setup>
import { onMounted, onUnmounted, computed } from 'vue'
import { useMessengerStore } from '../stores/messenger'
import ChannelList from '../components/messenger/ChannelList.vue'
import ChatWindow from '../components/messenger/ChatWindow.vue'
import CallHistory from '../components/messenger/CallHistory.vue'

const messengerStore = useMessengerStore()

const isLive = computed(() => messengerStore.connectionMode === 'live')
const isPolling = computed(() => messengerStore.connectionMode === 'polling')

onMounted(() => {
  messengerStore.fetchChannels()
  messengerStore.fetchUnreadCount()
  messengerStore.connectSSE()
})

onUnmounted(() => {
  messengerStore.disconnectSSE()
  messengerStore.stopChannelPolling()
  messengerStore.stopMessagePolling()
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center gap-3">
      <h2 class="text-2xl font-bold">Messenger</h2>
      <span v-if="isLive" class="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-green-500/20 text-green-400">
        <span class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse"></span>
        Live
      </span>
      <span v-else-if="isPolling" class="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-yellow-500/20 text-yellow-400">
        <span class="w-1.5 h-1.5 rounded-full bg-yellow-400"></span>
        Polling
      </span>
    </div>

    <div class="flex gap-4 h-[calc(100vh-16rem)]">
      <ChannelList class="w-80 flex-shrink-0" />
      <ChatWindow class="flex-1" />
    </div>

    <CallHistory />
  </div>
</template>
