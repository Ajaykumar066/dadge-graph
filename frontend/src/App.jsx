// import { useState }    from 'react'
// import GraphCanvas     from './components/GraphCanvas'
// import ChatPanel       from './components/ChatPanel'
// import StatsBar        from './components/StatsBar'

// export default function App() {
//   const [highlightedNodes, setHighlightedNodes] = useState([])

//   return (
//     <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}
//          className="bg-gray-950 text-gray-200">

//       {/* Header */}
//       <div className="flex items-center justify-between px-4 py-2
//                       bg-gray-900 border-b border-gray-800"
//            style={{ flexShrink: 0 }}>
//         <div className="flex items-center gap-3">
//           <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
//           <span className="text-sm font-semibold">
//             SAP Order-to-Cash Graph Explorer
//           </span>
//         </div>
//         <span className="text-xs text-gray-600">Neo4j AuraDB · Groq LLM</span>
//       </div>

//       {/* Stats Bar */}
//       <StatsBar />

//       {/* Main — Graph + Chat */}
//       <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
//         <GraphCanvas highlightedNodeIds={highlightedNodes} />
//         <ChatPanel   onHighlightNodes={setHighlightedNodes} />
//       </div>

//     </div>
//   )
// }

import { useState, useEffect } from 'react'
import GraphCanvas from './components/GraphCanvas'
import ChatPanel   from './components/ChatPanel'
import StatsBar    from './components/StatsBar'
import { wakeUpBackend, startKeepAlive } from './api/client'

export default function App() {
  const [highlightedNodes, setHighlightedNodes] = useState([])
  const [wakeStatus,       setWakeStatus]       = useState('Connecting to server...')
  const [isReady,          setIsReady]          = useState(false)

  useEffect(() => {
    let keepAliveTimer = null

    async function init() {
      // Wake up backend first
      const ready = await wakeUpBackend(setWakeStatus)
      setIsReady(true)
      setWakeStatus(null)

      // Start keep-alive to prevent future sleep
      keepAliveTimer = startKeepAlive()
    }

    init()

    // Cleanup on unmount
    return () => {
      if (keepAliveTimer) clearInterval(keepAliveTimer)
    }
  }, [])

  // Loading screen while backend wakes up
  if (!isReady) {
    return (
      <div style={{
        height:         '100vh',
        display:        'flex',
        flexDirection:  'column',
        alignItems:     'center',
        justifyContent: 'center',
        backgroundColor: '#030712',
        color:           '#e2e8f0',
        gap:             '16px',
      }}>
        {/* Animated dots */}
        <div style={{ display: 'flex', gap: '8px' }}>
          {['#6366f1', '#22c55e', '#f59e0b', '#f87171', '#34d399'].map((color, i) => (
            <div key={i} style={{
              width:           '10px',
              height:          '10px',
              borderRadius:    '50%',
              backgroundColor: color,
              animation:       `bounce 1s ease-in-out ${i * 0.15}s infinite`,
            }} />
          ))}
        </div>

        <p style={{ fontSize: '14px', fontWeight: 600 }}>
          SAP Order-to-Cash Graph Explorer
        </p>

        <p style={{ fontSize: '12px', color: '#64748b', maxWidth: '300px', textAlign: 'center' }}>
          {wakeStatus}
        </p>

        <p style={{ fontSize: '11px', color: '#374151' }}>
          Free tier backend may take up to 30 seconds to start
        </p>

        <style>{`
          @keyframes bounce {
            0%, 100% { transform: translateY(0);   opacity: 1; }
            50%       { transform: translateY(-8px); opacity: 0.5; }
          }
        `}</style>
      </div>
    )
  }

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

      {/* Main */}
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
        <GraphCanvas highlightedNodeIds={highlightedNodes} />
        <ChatPanel   onHighlightNodes={setHighlightedNodes} />
      </div>

    </div>
  )
}