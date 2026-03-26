import GraphCanvas from './components/GraphCanvas'

export default function App() {
  return (
    <div className="flex flex-col h-screen bg-graph-bg text-slate-200">
      {/* Header */}
      <div className="
        flex items-center justify-between px-4 py-2
        bg-graph-panel border-b border-graph-border flex-shrink-0
      ">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-graph-accent animate-pulse" />
          <h1 className="text-sm font-semibold text-slate-200">
            SAP Order-to-Cash Graph Explorer
          </h1>
        </div>
        <span className="text-xs text-slate-600">
          Neo4j AuraDB · Groq LLM
        </span>
      </div>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        <GraphCanvas />
      </div>
    </div>
  )
} 


