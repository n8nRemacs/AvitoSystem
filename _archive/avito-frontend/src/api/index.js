import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add API key to every request
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('x-api-key')
  if (apiKey) {
    config.headers['X-Api-Key'] = apiKey
  }
  return config
})

// Handle errors globally
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn('API Key invalid or missing')
    }
    return Promise.reject(error)
  }
)

export default api
