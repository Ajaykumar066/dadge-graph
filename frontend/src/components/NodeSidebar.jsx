/**
 * NodeSidebar.jsx
 *
 * Slide-in panel showing full properties of a selected node.
 * Also shows its neighbours with expand buttons.
 */

import { X, ExternalLink } from 'lucide-react'
import { getNodeConfig } from '../utils/graphConfig'

function PropertyRow({ label, value }) {
  if (value === null || value === undefined || value === '') return null

  const display = typeof value === 'boolean'
    ? (value ? 'Yes' : 'No')
    : String(value)

  return (
    <div className="flex flex-col py-1.5 border-b border-graph-border">
      <span className="text-xs text-slate-500 uppercase tracking-wider">
        {label}
      </span>
      <span className="text-xs text-slate-200 font-mono mt-0.5 break-all">
        {display}
      </span>
    </div>
  )
}

export default function NodeSidebar({ node, neighbours, onClose, onNodeClick }) {
  if (!node) return null

  const label  = node.labels?.[0] || 'Unknown'
  const config = getNodeConfig(label)
  const props  = node.properties || {}

  // Group neighbours by type for cleaner display
  const neighboursByType = (neighbours || []).reduce((acc, n) => {
    const t = n.labels?.[0] || 'Unknown'
    if (!acc[t]) acc[t] = []
    acc[t].push(n)
    return acc
  }, {})

  return (
    <div className="
      flex flex-col h-full bg-graph-panel
      border-l border-graph-border w-72 flex-shrink-0
    ">
      {/* Header */}
      <div
        style={{ borderBottomColor: config.color }}
        className="flex items-center justify-between p-3 border-b-2"
      >
        <div className="flex items-center gap-2">
          <span
            style={{ backgroundColor: config.color }}
            className="text-xs font-bold text-white px-2 py-0.5 rounded"
          >
            {config.label}
          </span>
          <span className="text-sm text-slate-300 font-medium">
            {config.displayName}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-500 hover:text-slate-200 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {/* Properties */}
      <div className="flex-1 overflow-y-auto p-3">
        <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">
          Properties
        </p>
        <div className="space-y-0">
          {Object.entries(props).map(([key, val]) => (
            key !== 'nodeLabel' && (
              <PropertyRow key={key} label={key} value={val} />
            )
          ))}
        </div>

        {/* Neighbours */}
        {Object.keys(neighboursByType).length > 0 && (
          <div className="mt-4">
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">
              Connected Nodes ({neighbours.length})
            </p>
            {Object.entries(neighboursByType).map(([type, nodes]) => {
              const nConfig = getNodeConfig(type)
              return (
                <div key={type} className="mb-3">
                  <p
                    style={{ color: nConfig.color }}
                    className="text-xs font-semibold mb-1"
                  >
                    {nConfig.displayName} ({nodes.length})
                  </p>
                  {nodes.slice(0, 5).map((n) => {
                    const nProps = n.properties || {}
                    const display = nProps[nConfig.nameField]
                      || nProps[nConfig.idField]
                      || n.id
                    return (
                      <button
                        key={n.id}
                        onClick={() => onNodeClick(n)}
                        className="
                          flex items-center justify-between w-full
                          text-left text-xs text-slate-300 px-2 py-1
                          hover:bg-graph-border rounded transition-colors
                          font-mono truncate
                        "
                      >
                        <span className="truncate">{display}</span>
                        <ExternalLink size={10} className="ml-1 flex-shrink-0 text-slate-500" />
                      </button>
                    )
                  })}
                  {nodes.length > 5 && (
                    <p className="text-xs text-slate-600 px-2">
                      +{nodes.length - 5} more
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}