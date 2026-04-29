import { defineStore } from 'pinia'
import api from '../api'

const SSE_MAX_RETRIES = 10
const SSE_BASE_DELAY = 1000

export const useMessengerStore = defineStore('messenger', {
  state: () => ({
    channels: [],
    activeChannelId: null,
    messages: [],
    unreadCount: 0,
    hasMoreChannels: false,
    hasMoreMessages: false,
    loading: false,
    // SSE state
    connectionMode: 'disconnected', // 'live' | 'polling' | 'disconnected'
    typingIndicators: {}, // channelId → { userId, timeout }
    // Internal
    _channelTimer: null,
    _messageTimer: null,
    _eventSource: null,
    _sseRetries: 0,
    _sseReconnectTimer: null,
  }),

  getters: {
    activeChannel: (state) =>
      state.channels.find((c) => c.id === state.activeChannelId),
    isTyping: (state) => (channelId) =>
      !!state.typingIndicators[channelId],
  },

  actions: {
    // ── REST API actions (unchanged) ─────────────────

    async fetchChannels(append = false) {
      this.loading = true
      try {
        const params = { limit: 30 }
        if (append && this.channels.length > 0) {
          // For pagination, would need offset_timestamp
        }
        const { data } = await api.get('/messenger/channels', { params })
        if (append) {
          this.channels.push(...data.channels)
        } else {
          this.channels = data.channels
        }
        this.hasMoreChannels = data.has_more
      } catch (e) {
        console.error('fetchChannels error:', e)
      }
      this.loading = false
    },

    async fetchMessages(channelId) {
      if (!channelId) return
      try {
        const { data } = await api.get(`/messenger/channels/${channelId}/messages`, {
          params: { limit: 50 },
        })
        this.messages = data.messages
        this.hasMoreMessages = data.has_more
      } catch (e) {
        console.error('fetchMessages error:', e)
      }
    },

    async sendMessage(text) {
      if (!this.activeChannelId || !text.trim()) return
      try {
        await api.post(`/messenger/channels/${this.activeChannelId}/messages`, { text })
        await this.fetchMessages(this.activeChannelId)
      } catch (e) {
        console.error('sendMessage error:', e)
        throw e
      }
    },

    async markRead(channelId) {
      try {
        await api.post(`/messenger/channels/${channelId}/read`)
      } catch (e) {
        // silent
      }
    },

    async sendTyping(channelId) {
      try {
        await api.post(`/messenger/channels/${channelId}/typing`)
      } catch (e) {
        // silent
      }
    },

    async fetchUnreadCount() {
      try {
        const { data } = await api.get('/messenger/unread-count')
        this.unreadCount = data.count
      } catch (e) {
        // silent
      }
    },

    selectChannel(channelId) {
      this.activeChannelId = channelId
      this.messages = []
      this.fetchMessages(channelId)
      this.markRead(channelId)
      // Only start message polling if in polling mode
      if (this.connectionMode === 'polling') {
        this.startMessagePolling()
      }
    },

    // ── Polling (fallback) ───────────────────────────

    startChannelPolling() {
      this.stopChannelPolling()
      this._channelTimer = setInterval(() => {
        this.fetchChannels()
        this.fetchUnreadCount()
      }, 15000)
    },

    stopChannelPolling() {
      if (this._channelTimer) {
        clearInterval(this._channelTimer)
        this._channelTimer = null
      }
    },

    startMessagePolling() {
      this.stopMessagePolling()
      if (!this.activeChannelId) return
      this._messageTimer = setInterval(() => {
        this.fetchMessages(this.activeChannelId)
      }, 5000)
    },

    stopMessagePolling() {
      if (this._messageTimer) {
        clearInterval(this._messageTimer)
        this._messageTimer = null
      }
    },

    _startPollingFallback() {
      this.connectionMode = 'polling'
      this.startChannelPolling()
      if (this.activeChannelId) {
        this.startMessagePolling()
      }
    },

    _stopPollingFallback() {
      this.stopChannelPolling()
      this.stopMessagePolling()
    },

    // ── SSE connection ───────────────────────────────

    connectSSE() {
      this.disconnectSSE()

      const apiKey = localStorage.getItem('x-api-key')
      if (!apiKey) {
        console.warn('No API key, falling back to polling')
        this._startPollingFallback()
        return
      }

      const baseUrl = import.meta.env.VITE_API_URL || '/api/v1'
      const url = `${baseUrl}/messenger/realtime/events?api_key=${encodeURIComponent(apiKey)}`

      try {
        this._eventSource = new EventSource(url)
        this._sseRetries = 0

        this._eventSource.addEventListener('connected', () => {
          console.log('SSE connected')
          this.connectionMode = 'live'
          this._sseRetries = 0
          this._stopPollingFallback()
        })

        this._eventSource.addEventListener('new_message', (e) => {
          this._handleNewMessage(JSON.parse(e.data))
        })

        this._eventSource.addEventListener('typing', (e) => {
          this._handleTyping(JSON.parse(e.data))
        })

        this._eventSource.addEventListener('read', (e) => {
          this._handleRead(JSON.parse(e.data))
        })

        this._eventSource.addEventListener('disconnected', () => {
          console.warn('SSE: backend WS disconnected')
          this._scheduleReconnect()
        })

        this._eventSource.addEventListener('keepalive', () => {
          // Just a heartbeat, no action needed
        })

        this._eventSource.onerror = () => {
          console.warn('SSE connection error')
          this._eventSource.close()
          this._eventSource = null
          this._scheduleReconnect()
        }
      } catch (e) {
        console.error('SSE init failed:', e)
        this._startPollingFallback()
      }
    },

    disconnectSSE() {
      if (this._sseReconnectTimer) {
        clearTimeout(this._sseReconnectTimer)
        this._sseReconnectTimer = null
      }
      if (this._eventSource) {
        this._eventSource.close()
        this._eventSource = null
      }
      this.connectionMode = 'disconnected'
    },

    _scheduleReconnect() {
      this._sseRetries++
      if (this._sseRetries > SSE_MAX_RETRIES) {
        console.warn('SSE: max retries reached, falling back to polling')
        this._startPollingFallback()
        return
      }

      const delay = Math.min(SSE_BASE_DELAY * Math.pow(2, this._sseRetries - 1), 30000)
      console.log(`SSE: reconnecting in ${delay}ms (attempt ${this._sseRetries}/${SSE_MAX_RETRIES})`)

      this._sseReconnectTimer = setTimeout(() => {
        this.connectSSE()
      }, delay)
    },

    // ── SSE event handlers ───────────────────────────

    _handleNewMessage(event) {
      const msg = event.payload
      if (!msg) return

      // Update channel list: move channel to top, update last message
      const channelId = msg.channel_id
      const idx = this.channels.findIndex((c) => c.id === channelId)
      if (idx >= 0) {
        const ch = { ...this.channels[idx] }
        ch.last_message_text = msg.text
        ch.last_message_at = msg.created_at
        if (channelId !== this.activeChannelId) {
          ch.unread_count = (ch.unread_count || 0) + 1
          ch.is_read = false
          this.unreadCount++
        }
        this.channels.splice(idx, 1)
        this.channels.unshift(ch)
      } else {
        // New channel — refetch
        this.fetchChannels()
      }

      // If this channel is active, append message to view
      if (channelId === this.activeChannelId) {
        const normalized = {
          id: msg.message_id || msg.id,
          channel_id: msg.channel_id,
          author_id: msg.author_id,
          text: msg.text,
          message_type: msg.type || 'text',
          media_url: null,
          media_info: msg.media || null,
          is_read: false,
          created_at: msg.created_at,
        }
        // Avoid duplicates
        if (!this.messages.find((m) => m.id === normalized.id)) {
          this.messages.push(normalized)
        }
        this.markRead(channelId)
      }
    },

    _handleTyping(event) {
      const payload = event.payload
      if (!payload) return
      const channelId = payload.channel_id || payload.channelId
      if (!channelId) return

      // Set typing indicator with auto-clear
      const existing = this.typingIndicators[channelId]
      if (existing?.timeout) {
        clearTimeout(existing.timeout)
      }

      const timeout = setTimeout(() => {
        delete this.typingIndicators[channelId]
      }, 3000)

      this.typingIndicators[channelId] = {
        userId: payload.user_id || payload.userId,
        timeout,
      }
    },

    _handleRead(event) {
      const payload = event.payload
      if (!payload) return
      const channelId = payload.channel_id || payload.channelId

      const idx = this.channels.findIndex((c) => c.id === channelId)
      if (idx >= 0) {
        this.channels[idx] = { ...this.channels[idx], is_read: true, unread_count: 0 }
      }

      // Update messages is_read if in active channel
      if (channelId === this.activeChannelId) {
        this.messages = this.messages.map((m) => ({ ...m, is_read: true }))
      }
    },
  },
})
