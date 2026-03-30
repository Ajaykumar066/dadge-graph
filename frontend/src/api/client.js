// /**
//  * client.js
//  *
//  * Central Axios instance for all API calls.
//  *
//  * WHY A CENTRAL INSTANCE:
//  * - One place to set the base URL
//  * - One place to add auth headers later
//  * - Consistent error handling across all requests
//  */

// import axios from 'axios'

// const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

// const client = axios.create({
//   baseURL: API_BASE,
//   timeout: 60000,  // 60 seconds
// })

// // Log errors in development
// client.interceptors.response.use(
//   (response) => response,
//   (error) => {
//     console.error('API Error:', error.response?.data || error.message)
//     return Promise.reject(error)
//   }
// )

// export default client

import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.response.use(
  response => response,
  error => {
    console.error('API Error:', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

/**
 * Wakes up the Render backend before the app loads.
 * Polls /wake every 3 seconds until Neo4j is connected.
 * Shows a loading state in the UI during this time.
 */
export async function wakeUpBackend(onStatus) {
  const MAX_ATTEMPTS = 20  // 60 seconds max
  let attempts = 0

  while (attempts < MAX_ATTEMPTS) {
    try {
      onStatus(`Connecting to server... (${attempts + 1}/${MAX_ATTEMPTS})`)
      const res = await axios.get(`${API_BASE}/wake`, { timeout: 10000 })
      if (res.data.status === 'ready') {
        onStatus(null)  // clear status
        return true
      }
    } catch (err) {
      // Server still waking up — keep trying
    }
    attempts++
    await new Promise(r => setTimeout(r, 3000))
  }

  onStatus('Backend is slow to respond. Please wait...')
  return false
}

/**
 * Sends a keep-alive ping every 14 minutes.
 * Prevents Render free tier from sleeping.
 */
export function startKeepAlive() {
  const INTERVAL = 14 * 60 * 1000  // 14 minutes

  const ping = async () => {
    try {
      await axios.get(`${API_BASE}/ping`, { timeout: 5000 })
      console.log('Keep-alive ping sent')
    } catch (err) {
      console.warn('Keep-alive ping failed:', err.message)
    }
  }

  // Ping immediately then every 14 minutes
  ping()
  return setInterval(ping, INTERVAL)
}

export default client