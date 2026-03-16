import axios from 'axios'

const authApi = axios.create({
  baseURL: import.meta.env.VITE_AUTH_URL || '/auth/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add JWT token to protected requests
authApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// Handle 401 — try refresh, otherwise redirect to login
authApi.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const { data } = await axios.post(
            (import.meta.env.VITE_AUTH_URL || '/auth/v1') + '/refresh',
            { refresh_token: refreshToken }
          )
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          original.headers['Authorization'] = `Bearer ${data.access_token}`
          return authApi(original)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

export default authApi
