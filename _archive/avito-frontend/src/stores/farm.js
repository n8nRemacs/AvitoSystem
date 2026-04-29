import { defineStore } from 'pinia'
import api from '../api'

export const useFarmStore = defineStore('farm', {
  state: () => ({
    devices: [],
    bindings: [],
    schedule: [],
    loading: false,
  }),

  actions: {
    async fetchDevices() {
      try {
        const { data } = await api.get('/farm/devices')
        this.devices = data.devices || []
      } catch (e) {
        console.error('fetchDevices error:', e)
      }
    },

    async fetchBindings() {
      try {
        const { data } = await api.get('/farm/bindings')
        this.bindings = data.bindings || []
      } catch (e) {
        console.error('fetchBindings error:', e)
      }
    },

    async fetchSchedule() {
      try {
        const { data } = await api.get('/farm/schedule')
        this.schedule = data.schedule || []
      } catch (e) {
        console.error('fetchSchedule error:', e)
      }
    },

    async createDevice(payload) {
      const { data } = await api.post('/farm/devices', payload)
      await this.fetchDevices()
      return data
    },

    async createBinding(payload) {
      const { data } = await api.post('/farm/bindings', payload)
      await this.fetchBindings()
      return data
    },

    async deleteBinding(bindingId) {
      await api.delete(`/farm/bindings/${bindingId}`)
      await this.fetchBindings()
    },

    async fetchAll() {
      this.loading = true
      await Promise.all([this.fetchDevices(), this.fetchBindings(), this.fetchSchedule()])
      this.loading = false
    },
  },
})
