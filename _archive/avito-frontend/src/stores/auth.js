import { defineStore } from 'pinia'
import api from '../api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    session: null,
    tokenDetails: null,
    sessionHistory: [],
    alerts: [],
    loading: false,
    error: null,
    _pollTimer: null,
  }),

  actions: {
    async fetchStatus() {
      try {
        const { data } = await api.get('/sessions/current')
        this.session = data
        this.error = null
      } catch (e) {
        this.session = null
        this.error = e.response?.data?.detail || e.message
      }
    },

    async fetchAlerts() {
      try {
        const { data } = await api.get('/sessions/alerts')
        this.alerts = data.alerts || []
      } catch (e) {
        this.alerts = []
      }
    },

    async fetchTokenDetails() {
      try {
        const { data } = await api.get('/sessions/token-details')
        this.tokenDetails = data
      } catch (e) {
        this.tokenDetails = null
      }
    },

    async fetchHistory() {
      try {
        const { data } = await api.get('/sessions/history')
        this.sessionHistory = data.sessions || []
      } catch (e) {
        this.sessionHistory = []
      }
    },

    async uploadSession(payload) {
      this.loading = true
      try {
        const { data } = await api.post('/sessions', payload)
        await this.fetchStatus()
        await this.fetchHistory()
        this.loading = false
        return data
      } catch (e) {
        this.loading = false
        throw e
      }
    },

    async deleteSession() {
      try {
        await api.delete('/sessions')
        this.session = null
        this.tokenDetails = null
        this.alerts = []
        await this.fetchHistory()
      } catch (e) {
        throw e
      }
    },

    startPolling() {
      this.stopPolling()
      this.fetchStatus()
      this.fetchAlerts()
      this._pollTimer = setInterval(() => {
        this.fetchStatus()
        this.fetchAlerts()
      }, 30000)
    },

    stopPolling() {
      if (this._pollTimer) {
        clearInterval(this._pollTimer)
        this._pollTimer = null
      }
    },
  },
})
