/**
 * client.js
 *
 * Central Axios instance for all API calls.
 *
 * WHY A CENTRAL INSTANCE:
 * - One place to set the base URL
 * - One place to add auth headers later
 * - Consistent error handling across all requests
 */

import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,   // 30s — LLM calls can be slow
  headers: {
    'Content-Type': 'application/json',
  },
})

// Log errors in development
client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

export default client