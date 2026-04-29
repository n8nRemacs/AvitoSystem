<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import AlertBanner from '../components/auth/AlertBanner.vue'
import TokenStatus from '../components/auth/TokenStatus.vue'
import SessionUpload from '../components/auth/SessionUpload.vue'
import TokenDetails from '../components/auth/TokenDetails.vue'
import SessionHistory from '../components/auth/SessionHistory.vue'
import RemoteBrowser from '../components/auth/RemoteBrowser.vue'

const authStore = useAuthStore()

onMounted(() => {
  authStore.startPolling()
  authStore.fetchHistory()
  authStore.fetchTokenDetails()
})

onUnmounted(() => {
  authStore.stopPolling()
})
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <h2 class="text-2xl font-bold">Authorization & Sessions</h2>

    <AlertBanner />
    <TokenStatus />
    <RemoteBrowser />
    <SessionUpload />
    <TokenDetails />
    <SessionHistory />
  </div>
</template>
