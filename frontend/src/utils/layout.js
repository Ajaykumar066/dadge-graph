/**
 * layout.js
 *
 * Auto-layout for graph nodes using dagre.
 *
 * WHY DAGRE:
 * Without layout, all nodes stack at position (0,0).
 * Dagre is a directed graph layout engine — it arranges nodes
 * in a clean top-to-bottom hierarchy that matches the O2C flow:
 * BusinessPartner → SalesOrder → Delivery → Billing → Payment
 */

import dagre from '@dagrejs/dagre'

const NODE_WIDTH  = 160
const NODE_HEIGHT = 60

export function applyDagreLayout(nodes, edges, direction = 'LR') {
  const dagreGraph = new dagre.graphlib.Graph()

  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({
    rankdir:  direction,   // LR = left-to-right, TB = top-to-bottom
    nodesep:  60,
    ranksep:  100,
    marginx:  40,
    marginy:  40,
  })

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, {
      width:  NODE_WIDTH,
      height: NODE_HEIGHT,
    })
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  const layoutedNodes = nodes.map((node) => {
    const pos = dagreGraph.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH  / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })

  return { nodes: layoutedNodes, edges }
}
