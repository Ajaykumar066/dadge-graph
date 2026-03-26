/**
 * GraphCanvas.jsx
 *
 * The main interactive graph visualization.
 *
 * INTERACTIONS:
 * - Click a node    → show its properties in NodeSidebar
 * - Double-click    → expand its neighbours into the canvas
 * - Search bar      → find and focus a specific node
 * - Layout button   → re-run dagre auto-layout
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
} from 'reactflow'
import 'reactflow/dist/style.css'

import { Search, LayoutDashboard, RefreshCw, Loader } from 'lucide-react'

import GraphNode   from './GraphNode'
import NodeSidebar from './NodeSidebar'
import { graphApi } from '../api/graph'
import { toReactFlowElements, getNodeConfig } from '../utils/graphConfig'
import { applyDagreLayout } from '../utils/layout'

// Register our custom node type with React Flow
const NODE_TYPES = { graphNode: GraphNode }

export default function GraphCanvas({ highlightedNodeIds = [] }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  const [loading,        setLoading]        = useState(true)
  const [expanding,      setExpanding]      = useState(false)
  const [selectedNode,   setSelectedNode]   = useState(null)
  const [sidebarData,    setSidebarData]    = useState(null)
  const [searchQuery,    setSearchQuery]    = useState('')
  const [searchResults,  setSearchResults]  = useState([])
  const [searching,      setSearching]      = useState(false)

  // Track which node IDs are already on the canvas to avoid duplicates
  const canvasNodeIds = useRef(new Set())

  // ── Load initial graph overview ───────────────────────────
  useEffect(() => {
    loadOverview()
  }, [])

  // ── Highlight nodes when chat references them ─────────────
  useEffect(() => {
    if (!highlightedNodeIds.length) return
    setNodes(prev => prev.map(n => ({
      ...n,
      data: {
        ...n.data,
        highlighted: highlightedNodeIds.includes(n.id),
      },
    })))
  }, [highlightedNodeIds])

  async function loadOverview() {
    setLoading(true)
    try {
      const data = await graphApi.getOverview(80)
      renderGraph(data.nodes, data.edges)
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

    let finalNodes = rfNodes
    let finalEdges = rfEdges

    if (merge) {
      // Add only nodes not already on canvas
      const existingIds = new Set(nodes.map(n => n.id))
      const freshNodes  = rfNodes.filter(n => !existingIds.has(n.id))
      const freshEdges  = rfEdges.filter(e =>
        !edges.find(ex => ex.id === e.id)
      )
      finalNodes = [...nodes, ...freshNodes]
      finalEdges = [...edges, ...freshEdges]
    }

    // Apply dagre layout
    const { nodes: laid, edges: laidEdges } = applyDagreLayout(
      finalNodes, finalEdges
    )

    // Track all node IDs on canvas
    laid.forEach(n => canvasNodeIds.current.add(n.id))

    setNodes(laid)
    setEdges(laidEdges)
  }

  // ── Click: show node detail in sidebar ───────────────────
  const onNodeClick = useCallback(async (_, node) => {
    setSelectedNode(node)
    try {
      const data = await graphApi.getNode(node.id)
      setSidebarData(data)
    } catch (err) {
      console.error('Failed to load node detail:', err)
    }
  }, [])

  // ── Double-click: expand neighbours onto canvas ───────────
  const onNodeDoubleClick = useCallback(async (_, node) => {
    setExpanding(true)
    try {
      const data = await graphApi.getNode(node.id)
      if (data.neighbours?.length) {
        renderGraph(
          [node.data, ...data.neighbours],
          data.edges,
          true   // merge into existing canvas
        )
      }
    } catch (err) {
      console.error('Failed to expand node:', err)
    } finally {
      setExpanding(false)
    }
  }, [nodes, edges])

  // ── Sidebar neighbour click: expand that node ─────────────
  async function onSidebarNodeClick(neighbourNode) {
    setSelectedNode({ id: neighbourNode.id, data: { properties: neighbourNode.properties, labels: neighbourNode.labels } })
    try {
      const data = await graphApi.getNode(neighbourNode.id)
      setSidebarData(data)
      // Also expand it onto canvas if not already there
      if (!canvasNodeIds.current.has(neighbourNode.id)) {
        renderGraph([neighbourNode, ...data.neighbours], data.edges, true)
      }
    } catch (err) {
      console.error('Failed to load neighbour:', err)
    }
  }

  // ── Search ────────────────────────────────────────────────
  async function handleSearch(e) {
    const q = e.target.value
    setSearchQuery(q)
    if (q.length < 2) { setSearchResults([]); return }

    setSearching(true)
    try {
      const data = await graphApi.search(q)
      setSearchResults(data.results || [])
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setSearching(false)
    }
  }

  function onSearchResultClick(node) {
    setSearchQuery('')
    setSearchResults([])
    // Add to canvas if not already there
    if (!canvasNodeIds.current.has(node.id)) {
      renderGraph([node], [], true)
    }
    // Select it
    setSelectedNode({ id: node.id })
    graphApi.getNode(node.id).then(data => setSidebarData(data))
  }

  return (
    <div className="flex flex-1 overflow-hidden">

      {/* ── Graph Canvas ─────────────────────────────────── */}
      <div className="flex-1 flex flex-col relative">

        {/* Toolbar */}
        <div className="
          flex items-center gap-2 px-3 py-2
          bg-graph-panel border-b border-graph-border
        ">
          {/* Search */}
          <div className="relative flex-1 max-w-xs">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500"
            />
            <input
              value={searchQuery}
              onChange={handleSearch}
              placeholder="Search nodes..."
              className="
                w-full pl-8 pr-3 py-1.5 text-xs
                bg-graph-bg border border-graph-border rounded
                text-slate-200 placeholder-slate-600
                focus:outline-none focus:border-graph-accent
              "
            />
            {/* Search dropdown */}
            {searchResults.length > 0 && (
              <div className="
                absolute top-full left-0 right-0 mt-1 z-50
                bg-graph-panel border border-graph-border rounded
                shadow-xl max-h-48 overflow-y-auto
              ">
                {searchResults.map(node => {
                  const cfg = getNodeConfig(node.labels?.[0])
                  const props = node.properties || {}
                  const name = props[cfg.nameField] || props[cfg.idField] || node.id
                  return (
                    <button
                      key={node.id}
                      onClick={() => onSearchResultClick(node)}
                      className="
                        w-full text-left px-3 py-2 text-xs
                        hover:bg-graph-border transition-colors
                        flex items-center gap-2
                      "
                    >
                      <span
                        style={{ backgroundColor: cfg.color }}
                        className="text-white text-xs px-1.5 py-0.5 rounded font-bold flex-shrink-0"
                      >
                        {cfg.label}
                      </span>
                      <span className="text-slate-300 truncate font-mono">{name}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* Actions */}
          <button
            onClick={loadOverview}
            className="
              flex items-center gap-1.5 px-2.5 py-1.5 text-xs
              bg-graph-bg border border-graph-border rounded
              text-slate-400 hover:text-slate-200
              hover:border-graph-accent transition-colors
            "
          >
            <RefreshCw size={12} />
            Reset
          </button>

          <button
            onClick={() => {
              const { nodes: laid, edges: laidEdges } = applyDagreLayout(nodes, edges)
              setNodes(laid)
              setEdges(laidEdges)
            }}
            className="
              flex items-center gap-1.5 px-2.5 py-1.5 text-xs
              bg-graph-bg border border-graph-border rounded
              text-slate-400 hover:text-slate-200
              hover:border-graph-accent transition-colors
            "
          >
            <LayoutDashboard size={12} />
            Layout
          </button>

          {/* Status indicators */}
          {loading && (
            <span className="flex items-center gap-1 text-xs text-slate-500">
              <Loader size={12} className="animate-spin" /> Loading...
            </span>
          )}
          {expanding && (
            <span className="flex items-center gap-1 text-xs text-graph-accent">
              <Loader size={12} className="animate-spin" /> Expanding...
            </span>
          )}

          <span className="text-xs text-slate-600 ml-auto">
            {nodes.length} nodes · {edges.length} edges
          </span>
        </div>

        {/* React Flow Canvas */}
        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.1}
            maxZoom={2}
            deleteKeyCode={null}
          >
            <Background color="#2a2d3a" gap={20} size={1} />
            <Controls />
            <MiniMap
              nodeColor={n => getNodeConfig(n.data?.nodeType)?.color || '#94a3b8'}
              maskColor="rgba(15,17,23,0.8)"
            />
          </ReactFlow>
        </div>

        {/* Hint */}
        {!loading && nodes.length > 0 && (
          <div className="
            absolute bottom-12 left-3
            text-xs text-slate-600 pointer-events-none
          ">
            Click to inspect · Double-click to expand
          </div>
        )}
      </div>

      {/* ── Node Sidebar ──────────────────────────────────── */}
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
