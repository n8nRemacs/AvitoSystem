<script setup>
import { ref, onUnmounted, computed } from 'vue'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

const isOpen = ref(false)
const status = ref('idle') // idle | connecting | started | auth_complete | error
const errorMsg = ref('')
const screenshotSrc = ref('')
const ws = ref(null)

const apiKey = computed(() => localStorage.getItem('avito_api_key') || '')

function connect() {
  if (!apiKey.value) {
    errorMsg.value = 'Set API key first (click API Key button in header)'
    status.value = 'error'
    return
  }

  isOpen.value = true
  status.value = 'connecting'
  errorMsg.value = ''

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const url = `${protocol}//${host}/api/v1/auth/browser?api_key=${encodeURIComponent(apiKey.value)}`

  const socket = new WebSocket(url)
  ws.value = socket

  socket.onopen = () => {
    socket.send(JSON.stringify({ type: 'start' }))
  }

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)

      if (msg.type === 'status' && msg.status === 'started') {
        status.value = 'started'
      } else if (msg.type === 'screenshot' && msg.data) {
        screenshotSrc.value = 'data:image/jpeg;base64,' + msg.data
      } else if (msg.type === 'auth_complete') {
        status.value = 'auth_complete'
        // Refresh session data
        authStore.fetchStatus()
        authStore.fetchHistory()
        authStore.fetchTokenDetails()
        setTimeout(() => close(), 3000)
      } else if (msg.type === 'error') {
        errorMsg.value = msg.message
        status.value = 'error'
      }
    } catch (e) {
      // Ignore parse errors
    }
  }

  socket.onerror = () => {
    status.value = 'error'
    errorMsg.value = 'WebSocket connection failed'
  }

  socket.onclose = () => {
    if (status.value === 'connecting' || status.value === 'started') {
      status.value = 'idle'
    }
  }
}

function sendClick(event) {
  if (!ws.value || ws.value.readyState !== WebSocket.OPEN) return

  const rect = event.target.getBoundingClientRect()
  // Scale click coordinates to match the 420x900 viewport
  const imgWidth = event.target.naturalWidth || event.target.width
  const imgHeight = event.target.naturalHeight || event.target.height
  const scaleX = 420 / rect.width
  const scaleY = 900 / rect.height

  const x = Math.round((event.clientX - rect.left) * scaleX)
  const y = Math.round((event.clientY - rect.top) * scaleY)

  ws.value.send(JSON.stringify({ type: 'click', x, y }))
}

function sendKey(event) {
  if (!ws.value || ws.value.readyState !== WebSocket.OPEN) return

  // Relay key presses to the remote browser
  const specialKeys = ['Enter', 'Backspace', 'Tab', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']
  if (specialKeys.includes(event.key)) {
    event.preventDefault()
    ws.value.send(JSON.stringify({ type: 'key', key: event.key }))
  } else if (event.key.length === 1) {
    event.preventDefault()
    ws.value.send(JSON.stringify({ type: 'text', text: event.key }))
  }
}

function close() {
  if (ws.value && ws.value.readyState === WebSocket.OPEN) {
    ws.value.send(JSON.stringify({ type: 'close' }))
    ws.value.close()
  }
  ws.value = null
  isOpen.value = false
  status.value = 'idle'
  screenshotSrc.value = ''
}

onUnmounted(() => close())
</script>

<template>
  <div class="bg-avito-card rounded-lg p-4">
    <h3 class="text-lg font-semibold mb-3">Authorize via Browser</h3>

    <div v-if="!isOpen" class="space-y-3">
      <p class="text-sm text-gray-400">
        Opens a real Avito login page in a remote browser.
        You enter your credentials directly into Avito — we never see your password.
        After login, tokens are extracted automatically.
      </p>
      <button @click="connect"
              class="px-4 py-2 bg-avito-accent text-white rounded hover:bg-blue-600 transition">
        Open Remote Browser
      </button>
    </div>

    <div v-else class="space-y-3">
      <!-- Status bar -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span v-if="status === 'connecting'" class="text-yellow-400 text-sm">Connecting...</span>
          <span v-else-if="status === 'started'" class="text-green-400 text-sm">Browser active — enter your credentials</span>
          <span v-else-if="status === 'auth_complete'" class="text-green-400 text-sm font-bold">Authorization successful!</span>
          <span v-else-if="status === 'error'" class="text-red-400 text-sm">{{ errorMsg }}</span>
        </div>
        <button @click="close" class="text-sm text-gray-400 hover:text-white">Close</button>
      </div>

      <!-- Browser viewport -->
      <div v-if="screenshotSrc" class="relative border border-gray-700 rounded overflow-hidden"
           style="max-width: 420px; max-height: 600px;">
        <img :src="screenshotSrc"
             @click="sendClick"
             @keydown="sendKey"
             tabindex="0"
             class="w-full cursor-pointer focus:outline-none focus:ring-2 focus:ring-avito-accent"
             alt="Remote browser" />
        <div class="absolute bottom-0 left-0 right-0 bg-black/50 text-xs text-gray-300 px-2 py-1">
          Click on the image to interact. Press keys to type.
        </div>
      </div>

      <!-- Loading state -->
      <div v-else-if="status === 'connecting' || status === 'started'"
           class="flex items-center justify-center h-48 bg-gray-800 rounded">
        <span class="text-gray-400">Loading browser...</span>
      </div>

      <!-- Auth complete state -->
      <div v-if="status === 'auth_complete'"
           class="bg-green-900/50 border border-green-700 rounded p-3 text-green-300 text-sm">
        Tokens extracted and saved. This window will close automatically.
      </div>
    </div>
  </div>
</template>
