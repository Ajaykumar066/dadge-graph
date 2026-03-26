/**
 * GraphNode.jsx
 *
 * Custom React Flow node component.
 * Renders a colored badge with the node type label and display name.
 *
 * WHY CUSTOM NODE:
 * React Flow's default node is a plain white box.
 * We need color-coded nodes with the entity type visible at a glance.
 */

import { memo } from 'react'
import { Handle, Position } from 'reactflow'

function GraphNode({ data, selected }) {
  const { config, displayName, nodeType, highlighted } = data

  const isActive = selected || highlighted

  return (
    <div
      style={{
        borderColor: isActive ? config.color : '#2a2d3a',
        borderWidth:  isActive ? 2 : 1,
        boxShadow:    isActive ? `0 0 12px ${config.color}66` : 'none',
      }}
      className="
        rounded-lg border bg-[#1a1d27] cursor-pointer
        transition-all duration-150 min-w-[140px] max-w-[160px]
      "
    >
      {/* Top badge — node type */}
      <div
        style={{ backgroundColor: config.color }}
        className="
          rounded-t-lg px-2 py-0.5
          flex items-center justify-between
        "
      >
        <span className="text-xs font-bold text-white tracking-wide">
          {config.label}
        </span>
        <span className="text-xs text-white/70 truncate ml-1 max-w-[80px]">
          {nodeType}
        </span>
      </div>

      {/* Body — display name */}
      <div className="px-2 py-1.5">
        <p
          className="text-xs text-slate-200 truncate font-mono"
          title={displayName}
        >
          {displayName || '—'}
        </p>
      </div>

      {/* React Flow connection handles */}
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: config.color, width: 8, height: 8, border: 'none' }}
      />
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: config.color, width: 8, height: 8, border: 'none' }}
      />
    </div>
  )
}

export default memo(GraphNode)