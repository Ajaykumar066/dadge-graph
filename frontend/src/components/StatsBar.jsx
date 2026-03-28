import { useEffect, useState } from 'react'
import { graphApi } from '../api/graph'

export default function StatsBar() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    graphApi.getStats().then(setStats).catch(console.error)
  }, [])

  if (!stats) return null

  const items = [
    { label: 'Business Partners', value: stats.nodes.BusinessPartner    || 0, color: '#6366f1' },
    { label: 'Sales Orders',      value: stats.nodes.SalesOrder         || 0, color: '#22c55e' },
    { label: 'Deliveries',        value: stats.nodes.OutboundDelivery   || 0, color: '#f59e0b' },
    { label: 'Billing Docs',      value: stats.nodes.BillingDocument    || 0, color: '#f87171' },
    { label: 'Payments',          value: stats.nodes.Payment            || 0, color: '#34d399' },
    { label: 'Products',          value: stats.nodes.Product            || 0, color: '#38bdf8' },
    { label: 'Total Nodes',       value: stats.totals.nodes             || 0, color: '#94a3b8' },
    { label: 'Relationships',     value: stats.totals.relationships     || 0, color: '#94a3b8' },
  ]

  return (
    <div className="flex items-center gap-4 px-4 py-1.5
                    bg-gray-900 border-b border-gray-800
                    overflow-x-auto flex-shrink-0">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-1.5 flex-shrink-0">
          <div
            style={{ backgroundColor: item.color }}
            className="w-2 h-2 rounded-full"
          />
          <span className="text-xs text-gray-500">{item.label}:</span>
          <span className="text-xs font-mono font-semibold text-gray-300">
            {item.value.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  )
}