<script setup>
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

const levelColors = {
  warning: 'bg-yellow-900/30 border-yellow-600/50 text-yellow-300',
  critical: 'bg-red-900/30 border-red-600/50 text-red-300',
  expired: 'bg-red-900/50 border-red-500 text-red-200',
}
</script>

<template>
  <div
    v-for="alert in authStore.alerts"
    :key="alert.level"
    class="p-4 rounded-lg border"
    :class="levelColors[alert.level] || levelColors.warning"
  >
    <p class="text-sm font-medium">{{ alert.message }}</p>
  </div>
</template>
