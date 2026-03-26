import client from './client'

export const graphApi = {
  getStats: () =>
    client.get('/api/graph/stats').then(r => r.data),

  getOverview: (limit = 100) =>
    client.get(`/api/graph/overview?limit=${limit}`).then(r => r.data),

  getNode: (nodeId) =>
    client.get(`/api/graph/node/${encodeURIComponent(nodeId)}`).then(r => r.data),

  search: (q) =>
    client.get(`/api/graph/search?q=${encodeURIComponent(q)}`).then(r => r.data),
}

export const chatApi = {
  sendMessage: (question, sessionId) =>
    client.post('/api/chat/', { question, session_id: sessionId }).then(r => r.data),

  getHistory: (sessionId) =>
    client.get(`/api/chat/history/${sessionId}`).then(r => r.data),

  clearHistory: (sessionId) =>
    client.delete(`/api/chat/history/${sessionId}`).then(r => r.data),
}

export const analyticsApi = {
  getFlowTrace: (billingDocumentId) =>
    client.get(`/api/analytics/flow-trace/${billingDocumentId}`).then(r => r.data),

  getBrokenFlows: (flowType = 'all') =>
    client.get(`/api/analytics/broken-flows?flow_type=${flowType}`).then(r => r.data),

  getTopProducts: (limit = 10) =>
    client.get(`/api/analytics/top-products?limit=${limit}`).then(r => r.data),
}