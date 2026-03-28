import { memo } from 'react'
import { Handle, Position } from 'reactflow'
import { getNodeConfig } from '../utils/graphConfig'

function GraphNode({ data, selected }) {
  const { nodeType, displayName, highlighted } = data
  const config   = getNodeConfig(nodeType)
  const isActive = selected || highlighted

  return (
    <div className="relative group" style={{ width: 14, height: 14 }}>
      {/* Outer glow ring for highlighted nodes */}
      {isActive && (
        <div style={{
          position:        'absolute',
          top:             -6,
          left:            -6,
          width:           26,
          height:          26,
          borderRadius:    '50%',
          border:          `2px solid ${config.color}`,
          boxShadow:       `0 0 12px ${config.color}`,
          animation:       'pulse 1.5s infinite',
          pointerEvents:   'none',
        }} />
      )}

      {/* The dot */}
      <div style={{
        width:           isActive ? 14 : 10,
        height:          isActive ? 14 : 10,
        borderRadius:    '50%',
        backgroundColor: config.color,
        boxShadow:       isActive
          ? `0 0 16px ${config.color}, 0 0 32px ${config.color}88`
          : `0 0 4px ${config.color}66`,
        border:          isActive ? '2px solid white' : 'none',
        transition:      'all 0.2s ease',
        cursor:          'pointer',
        position:        'relative',
        zIndex:          isActive ? 10 : 1,
      }} />

      {/* Tooltip */}
      <div className="
        absolute left-5 top-1/2 -translate-y-1/2
        bg-gray-900 border border-gray-700 rounded
        px-2 py-1 text-xs text-white whitespace-nowrap
        opacity-0 group-hover:opacity-100
        pointer-events-none z-50 shadow-xl
        transition-opacity duration-150
      ">
        <span style={{ color: config.color }} className="font-bold mr-1">
          {config.label}
        </span>
        {displayName}
      </div>

      <Handle type="target" position={Position.Left}
        style={{ opacity: 0, width: 1, height: 1 }} />
      <Handle type="source" position={Position.Right}
        style={{ opacity: 0, width: 1, height: 1 }} />
    </div>
  )
}

export default memo(GraphNode)