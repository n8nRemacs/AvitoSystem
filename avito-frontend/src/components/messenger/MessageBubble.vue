<script setup>
const props = defineProps({
  message: { type: Object, required: true },
  isOwn: { type: Boolean, default: false },
})

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="flex" :class="isOwn ? 'justify-end' : 'justify-start'">
    <div
      class="max-w-[70%] px-3 py-2 rounded-2xl text-sm"
      :class="isOwn
        ? 'bg-blue-600 text-white rounded-br-sm'
        : 'bg-gray-700 text-gray-100 rounded-bl-sm'"
    >
      <!-- Text -->
      <p v-if="message.text">{{ message.text }}</p>

      <!-- Media -->
      <p v-if="message.message_type === 'image'" class="text-xs opacity-70">[Image]</p>
      <p v-if="message.message_type === 'voice'" class="text-xs opacity-70">[Voice]</p>
      <p v-if="message.message_type === 'video'" class="text-xs opacity-70">[Video]</p>
      <p v-if="message.message_type === 'file'" class="text-xs opacity-70">[File]</p>
      <p v-if="message.message_type === 'location'" class="text-xs opacity-70">[Location]</p>

      <!-- Time + read status -->
      <div class="flex items-center justify-end gap-1 mt-1">
        <span class="text-xs opacity-50">{{ formatTime(message.created_at) }}</span>
        <span v-if="isOwn" class="text-xs" :class="message.is_read ? 'text-blue-300' : 'opacity-50'">
          {{ message.is_read ? '✓✓' : '✓' }}
        </span>
      </div>
    </div>
  </div>
</template>
