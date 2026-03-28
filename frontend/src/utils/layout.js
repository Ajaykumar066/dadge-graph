export function applyForceLayout(nodes, edges) {
  if (!nodes.length) return { nodes, edges }

  const WIDTH   = 1200
  const HEIGHT  = 800
  const cx      = WIDTH  / 2
  const cy      = HEIGHT / 2

  // Group nodes by type for cleaner clustering
  const groups = {}
  nodes.forEach(n => {
    const type = n.data?.nodeType || 'Unknown'
    if (!groups[type]) groups[type] = []
    groups[type].push(n)
  })

  const groupNames  = Object.keys(groups)
  const numGroups   = groupNames.length
  const positioned  = {}

  groupNames.forEach((type, gi) => {
    const groupNodes  = groups[type]
    const groupAngle  = (gi / numGroups) * 2 * Math.PI
    const groupRadius = 280

    // Center of this group cluster
    const gcx = cx + Math.cos(groupAngle) * groupRadius
    const gcy = cy + Math.sin(groupAngle) * groupRadius

    groupNodes.forEach((node, ni) => {
      const spread     = Math.min(60, 400 / groupNodes.length)
      const nodeAngle  = (ni / groupNodes.length) * 2 * Math.PI
      const nodeRadius = Math.min(spread * Math.sqrt(groupNodes.length), 120)

      positioned[node.id] = {
        x: gcx + Math.cos(nodeAngle) * nodeRadius,
        y: gcy + Math.sin(nodeAngle) * nodeRadius,
      }
    })
  })

  return {
    nodes: nodes.map(n => ({
      ...n,
      position: positioned[n.id] || { x: cx, y: cy },
    })),
    edges,
  }
}