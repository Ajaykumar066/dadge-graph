/**
 * graphConfig.js
 *
 * Central configuration for graph visualization.
 * Every node type gets a color, an icon label, and a display name.
 *
 * WHY CENTRALIZE THIS:
 * The node colors are used in 3 places — the canvas, the legend,
 * and the node detail sidebar. One source of truth prevents mismatch.
 */

export const NODE_CONFIG = {
    BusinessPartner: {
      color:       '#6366f1',   // indigo
      bgColor:     '#1e1b4b',
      label:       'BP',
      displayName: 'Business Partner',
      idField:     'businessPartner',
      nameField:   'fullName',
    },
    SalesOrder: {
      color:       '#22c55e',   // green
      bgColor:     '#14532d',
      label:       'SO',
      displayName: 'Sales Order',
      idField:     'salesOrder',
      nameField:   'salesOrder',
    },
    SalesOrderItem: {
      color:       '#86efac',   // light green
      bgColor:     '#14532d',
      label:       'SOI',
      displayName: 'Order Item',
      idField:     'itemId',
      nameField:   'itemId',
    },
    SalesOrderScheduleLine: {
      color:       '#bbf7d0',
      bgColor:     '#14532d',
      label:       'SL',
      displayName: 'Schedule Line',
      idField:     'scheduleId',
      nameField:   'scheduleId',
    },
    OutboundDelivery: {
      color:       '#f59e0b',   // amber
      bgColor:     '#451a03',
      label:       'OD',
      displayName: 'Delivery',
      idField:     'deliveryDocument',
      nameField:   'deliveryDocument',
    },
    OutboundDeliveryItem: {
      color:       '#fcd34d',
      bgColor:     '#451a03',
      label:       'ODI',
      displayName: 'Delivery Item',
      idField:     'deliveryItemId',
      nameField:   'deliveryItemId',
    },
    BillingDocument: {
      color:       '#f87171',   // red
      bgColor:     '#450a0a',
      label:       'BD',
      displayName: 'Billing Doc',
      idField:     'billingDocument',
      nameField:   'billingDocument',
    },
    BillingDocumentItem: {
      color:       '#fca5a5',
      bgColor:     '#450a0a',
      label:       'BDI',
      displayName: 'Billing Item',
      idField:     'billingItemId',
      nameField:   'billingItemId',
    },
    JournalEntry: {
      color:       '#c084fc',   // purple
      bgColor:     '#3b0764',
      label:       'JE',
      displayName: 'Journal Entry',
      idField:     'journalEntryId',
      nameField:   'journalEntryId',
    },
    Payment: {
      color:       '#34d399',   // emerald
      bgColor:     '#022c22',
      label:       'PAY',
      displayName: 'Payment',
      idField:     'paymentId',
      nameField:   'paymentId',
    },
    Product: {
      color:       '#38bdf8',   // sky blue
      bgColor:     '#082f49',
      label:       'PRD',
      displayName: 'Product',
      idField:     'product',
      nameField:   'description',
    },
    Plant: {
      color:       '#fb923c',   // orange
      bgColor:     '#431407',
      label:       'PLT',
      displayName: 'Plant',
      idField:     'plant',
      nameField:   'plantName',
    },
  }
  
  export const DEFAULT_CONFIG = {
    color:       '#94a3b8',
    bgColor:     '#1e293b',
    label:       '?',
    displayName: 'Unknown',
    idField:     'id',
    nameField:   'id',
  }
  
  /**
   * Returns the config for a given node label.
   */
  export function getNodeConfig(label) {
    return NODE_CONFIG[label] || DEFAULT_CONFIG
  }
  
  /**
   * Returns the human-readable display name for a node.
   */
  export function getNodeDisplayName(node) {
    const label  = node.labels?.[0]
    const config = getNodeConfig(label)
    const props  = node.properties || {}
    return props[config.nameField] || props[config.idField] || node.id
  }
  
  /**
   * Converts backend node/edge format to React Flow format.
   *
   * WHY THIS TRANSFORM:
   * React Flow expects nodes with { id, position, data, type }
   * and edges with { id, source, target, label }.
   * The backend returns a different shape — we normalize here,
   * once, so components never deal with raw backend format.
   */
  export function toReactFlowElements(nodes, edges, highlightedIds = []) {
    const highlightSet = new Set(highlightedIds)
  
    const rfNodes = nodes.map((node, index) => {
      const label  = node.labels?.[0] || 'Unknown'
      const config = getNodeConfig(label)
      const isHighlighted = highlightSet.has(node.id)
  
      // Simple grid layout — frontend will auto-layout with dagre
      const col = index % 8
      const row = Math.floor(index / 8)
  
      return {
        id:       node.id,
        type:     'graphNode',           // our custom node type
        position: { x: col * 180, y: row * 120 },
        data: {
          label:       config.label,
          displayName: getNodeDisplayName(node),
          nodeType:    label,
          properties:  node.properties,
          config:      config,
          highlighted: isHighlighted,
        },
      }
    })
  
    const rfEdges = edges.map((edge) => ({
      id:      edge.id,
      source:  edge.startNode,
      target:  edge.endNode,
      type:    'straight',
      style:   { stroke: '#3b82f655', strokeWidth: 0.8 },
      // Remove label entirely — no label prop at all
    }))
    
    return { rfNodes, rfEdges }
  }