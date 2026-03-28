import { useState }    from 'react'
import GraphCanvas     from './components/GraphCanvas'
import ChatPanel       from './components/ChatPanel'
import StatsBar        from './components/StatsBar'

export default function App() {
  const [highlightedNodes, setHighlightedNodes] = useState([])

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}
         className="bg-gray-950 text-gray-200">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2
                      bg-gray-900 border-b border-gray-800"
           style={{ flexShrink: 0 }}>
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm font-semibold">
            SAP Order-to-Cash Graph Explorer
          </span>
        </div>
        <span className="text-xs text-gray-600">Neo4j AuraDB · Groq LLM</span>
      </div>

      {/* Stats Bar */}
      <StatsBar />

      {/* Main — Graph + Chat */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        <GraphCanvas highlightedNodeIds={highlightedNodes} />
        <ChatPanel   onHighlightNodes={setHighlightedNodes} />
      </div>

    </div>
  )
}