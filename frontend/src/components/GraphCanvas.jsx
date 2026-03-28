
import { useState, useCallback, useEffect, useRef } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { Search, RefreshCw, Loader } from 'lucide-react'

import GraphNode   from './GraphNode'
import NodeSidebar from './NodeSidebar'
import { graphApi } from '../api/graph'
import { toReactFlowElements, getNodeConfig } from '../utils/graphConfig'
import { applyForceLayout } from '../utils/layout'

// ✅ MUST be outside the component — never inside
const NODE_TYPES = { graphNode: GraphNode }

export default function GraphCanvas({ highlightedNodeIds = [] }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [loading,       setLoading]       = useState(true)
  const [expanding,     setExpanding]     = useState(false)
  const [selectedNode,  setSelectedNode]  = useState(null)
  const [sidebarData,   setSidebarData]   = useState(null)
  const [searchQuery,   setSearchQuery]   = useState('')
  const [searchResults, setSearchResults] = useState([])

  
  const canvasNodeIds = useRef(new Set())
  // const reactFlowRef   = useRef(null)
  useEffect(() => { loadOverview() }, [])

  useEffect(() => {
    if (!highlightedNodeIds.length) return
    setNodes(prev => prev.map(n => ({
      ...n,
      data: { ...n.data, highlighted: highlightedNodeIds.includes(n.id) },
    })))
  }, [highlightedNodeIds])

  async function loadOverview() {
    setLoading(true)
    canvasNodeIds.current.clear()
    try {
    const data = await graphApi.getOverview(150)
      renderGraph(data.nodes, data.edges, false)
    } catch (err) {
      console.error('Failed to load graph:', err)
    } finally {
      setLoading(false)
    }
  }

  function renderGraph(newNodes, newEdges, merge = false) {
    const { rfNodes, rfEdges } = toReactFlowElements(
      newNodes, newEdges, highlightedNodeIds
    )
  
    const styledEdges = rfEdges.map(e => ({
      ...e,
      label:  undefined,
      type:   'straight',
      style:  { stroke: '#3b82f655', strokeWidth: 0.8 },
    }))
  
    let finalNodes = rfNodes
    let finalEdges = styledEdges
  
    if (merge) {
      const existingIds = new Set(nodes.map(n => n.id))
      const freshNodes  = rfNodes.filter(n => !existingIds.has(n.id))
      const freshEdges  = styledEdges.filter(
        e => !edges.find(ex => ex.id === e.id)
      )
      finalNodes = [...nodes, ...freshNodes]
      finalEdges = [...edges, ...freshEdges]
    }
  
    const { nodes: laid, edges: laidEdges } = applyForceLayout(finalNodes, finalEdges)
    laid.forEach(n => canvasNodeIds.current.add(n.id))
    setNodes(laid)
    setEdges(laidEdges)
  
    // Fit view after nodes are positioned
    // setTimeout(() => {
    //   const rfInstance = reactFlowRef.current
    //   if (rfInstance) rfInstance.fitView({ padding: 0.15 })
    // }, 100)
  }

  const onNodeClick = useCallback(async (_, node) => {
    setSelectedNode(node)
    try {
      const data = await graphApi.getNode(node.id)
      setSidebarData(data)
    } catch (err) { console.error(err) }
  }, [])

  const onNodeDoubleClick = useCallback(async (_, node) => {
    setExpanding(true)
    try {
      const data = await graphApi.getNode(node.id)
      if (data.neighbours?.length) {
        renderGraph([node.data, ...data.neighbours], data.edges, true)
      }
    } catch (err) { console.error(err) }
    finally { setExpanding(false) }
  }, [nodes, edges])

  async function onSidebarNodeClick(neighbourNode) {
    setSelectedNode({ id: neighbourNode.id })
    try {
      const data = await graphApi.getNode(neighbourNode.id)
      setSidebarData(data)
      if (!canvasNodeIds.current.has(neighbourNode.id)) {
        renderGraph([neighbourNode, ...data.neighbours], data.edges, true)
      }
    } catch (err) { console.error(err) }
  }

  async function handleSearch(e) {
    const q = e.target.value
    setSearchQuery(q)
    if (q.length < 2) { setSearchResults([]); return }
    try {
      const data = await graphApi.search(q)
      setSearchResults(data.results || [])
    } catch (err) { console.error(err) }
  }

  function onSearchResultClick(node) {
    setSearchQuery('')
    setSearchResults([])
    if (!canvasNodeIds.current.has(node.id)) {
      renderGraph([node], [], true)
    }
    setSelectedNode({ id: node.id })
    graphApi.getNode(node.id).then(data => setSidebarData(data))
  }

  return (
    <div style={{ display: 'flex', flex: 1, overflow: 'hidden', height: '100%' }}>

      {/* ── Main canvas column ── */}
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, height: '100%' }}>

        {/* Toolbar */}
        <div style={{ flexShrink: 0 }}
             className="flex items-center gap-2 px-3 py-2
                        bg-gray-900 border-b border-gray-800">

          {/* Search */}
          <div className="relative flex-1 max-w-xs">
            <Search size={13}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              value={searchQuery}
              onChange={handleSearch}
              placeholder="Search nodes..."
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-gray-800
                         border border-gray-700 rounded text-gray-200
                         placeholder-gray-600 focus:outline-none focus:border-blue-500"
            />
            {searchResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 z-50
                              bg-gray-900 border border-gray-700 rounded
                              shadow-xl max-h-48 overflow-y-auto">
                {searchResults.map(node => {
                  const cfg   = getNodeConfig(node.labels?.[0])
                  const props = node.properties || {}
                  const name  = props[cfg.nameField] || props[cfg.idField] || node.id
                  return (
                    <button key={node.id} onClick={() => onSearchResultClick(node)}
                      className="w-full text-left px-3 py-2 text-xs
                                 hover:bg-gray-800 transition-colors
                                 flex items-center gap-2">
                      <span style={{ backgroundColor: cfg.color }}
                            className="text-white text-xs px-1.5 py-0.5 rounded font-bold">
                        {cfg.label}
                      </span>
                      <span className="text-gray-300 truncate font-mono">{name}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          <button onClick={loadOverview}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs
                       bg-gray-800 border border-gray-700 rounded
                       text-gray-400 hover:text-gray-200 transition-colors">
            <RefreshCw size={12} /> Reset
          </button>

          {(loading || expanding) && (
            <span className="flex items-center gap-1 text-xs text-gray-500">
              <Loader size={12} className="animate-spin" />
              {loading ? 'Loading...' : 'Expanding...'}
            </span>
          )}

          <span className="text-xs text-gray-600 ml-auto">
            {nodes.length} nodes · {edges.length} edges
          </span>
        </div>

        {/* React Flow — takes all remaining height */}
        <div style={{ flex: 1, minHeight: 0 }}>
          <ReactFlow
            // ref={reactFlowRef}
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.15 }}
            minZoom={0.05}
            maxZoom={3}
            deleteKeyCode={null}
          >
            <Background color="#1f2937" gap={24} size={1} />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={n => getNodeConfig(n.data?.nodeType)?.color || '#6b7280'}
              maskColor="rgba(0,0,0,0.7)"
              style={{ background: '#111827' }}
            />
          </ReactFlow>
        </div>

        <div className="absolute bottom-12 left-3 text-xs text-gray-700 pointer-events-none">
          Click to inspect · Double-click to expand
        </div>
      </div>

      {/* ── Sidebar ── */}
      {selectedNode && sidebarData && (
        <NodeSidebar
          node={sidebarData.node}
          neighbours={sidebarData.neighbours}
          onClose={() => { setSelectedNode(null); setSidebarData(null) }}
          onNodeClick={onSidebarNodeClick}
        />
      )}
    </div>
  )
}
