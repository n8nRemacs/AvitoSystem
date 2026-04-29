import { defineStore } from 'pinia'
import authApi from '../api/tenant-auth'

export const useTenantStore = defineStore('tenant', {
  state: () => ({
    user: null,
    isAuthenticated: false,
    loading: false,
    error: null,

    // OTP flow state
    otpPhone: null,
    otpPurpose: null,
    otpChannel: null,
    otpExpiresIn: 0,
  }),

  getters: {
    isEmailVerified: (state) => state.user?.email_verified ?? false,
    userRole: (state) => state.user?.role ?? null,
    userName: (state) => state.user?.name ?? state.user?.phone ?? '',
  },

  actions: {
    // Initialize from localStorage
    init() {
      const token = localStorage.getItem('access_token')
      if (token) {
        this.isAuthenticated = true
        this.fetchProfile()
      }
    },

    // Register new tenant
    async register(phone, email, name, otpChannel = 'console') {
      this.loading = true
      this.error = null
      try {
        const { data } = await authApi.post('/register', {
          phone, email, name, otp_channel: otpChannel,
        })
        this.otpPhone = phone
        this.otpPurpose = 'register'
        this.otpChannel = data.channel
        this.otpExpiresIn = data.expires_in
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || 'Registration failed'
        throw e
      } finally {
        this.loading = false
      }
    },

    // Request login OTP
    async login(phone, otpChannel = 'console') {
      this.loading = true
      this.error = null
      try {
        const { data } = await authApi.post('/login', {
          phone, otp_channel: otpChannel,
        })
        this.otpPhone = phone
        this.otpPurpose = 'login'
        this.otpChannel = data.channel
        this.otpExpiresIn = data.expires_in
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || 'Login failed'
        throw e
      } finally {
        this.loading = false
      }
    },

    // Verify OTP and get tokens
    async verifyOtp(code) {
      this.loading = true
      this.error = null
      try {
        const { data } = await authApi.post('/verify-otp', {
          phone: this.otpPhone,
          code,
          purpose: this.otpPurpose,
        })
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        this.isAuthenticated = true
        this.otpPhone = null
        this.otpPurpose = null
        await this.fetchProfile()
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || 'Verification failed'
        throw e
      } finally {
        this.loading = false
      }
    },

    // Fetch user profile
    async fetchProfile() {
      try {
        const { data } = await authApi.get('/profile')
        this.user = data
        this.isAuthenticated = true
      } catch (e) {
        if (e.response?.status === 401) {
          this.logout()
        }
      }
    },

    // Update profile
    async updateProfile(updates) {
      this.loading = true
      this.error = null
      try {
        const { data } = await authApi.patch('/profile', updates)
        this.user = data
        return data
      } catch (e) {
        this.error = e.response?.data?.detail || 'Update failed'
        throw e
      } finally {
        this.loading = false
      }
    },

    // Logout
    async logout() {
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          await authApi.post('/logout', { refresh_token: refreshToken })
        } catch {
          // ignore errors on logout
        }
      }
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      this.user = null
      this.isAuthenticated = false
      this.error = null
    },

    clearError() {
      this.error = null
    },
  },
})
