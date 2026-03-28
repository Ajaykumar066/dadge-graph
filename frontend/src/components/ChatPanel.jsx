import { useState, useRef, useEffect } from 'react'
import { Send, Trash2, Loader, Bot, User } from 'lucide-react'
import { chatApi } from '../api/graph'
import { v4 as uuidv4 } from 'uuid'

// Generate a stable session ID for this browser tab
const SESSION_ID = uuidv4()

const EXAMPLE_QUESTIONS = [
  "Which products have the most billing documents?",
  "Find orders delivered but not billed",
   "Show me cancelled billing documents",
 "Trace the flow of billing document 90504248",
  "Show me the full flow of sales order 10000000",
]

function Message({ msg }) {
  const isUser = msg.role === 'user'

  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      <div className={`
        flex-shrink-0 w-7 h-7 rounded-full
        flex items-center justify-center text-white
        ${isUser ? 'bg-blue-600' : 'bg-indigo-700'}
      `}>
        {isUser ? <User size={13} /> : <Bot size={13} />}
      </div>

      {/* Bubble */}
      <div className={`
        max-w-[80%] rounded-lg px-3 py-2 text-xs leading-relaxed
        ${isUser
          ? 'bg-blue-600 text-white rounded-tr-none'
          : 'bg-gray-800 text-gray-200 rounded-tl-none border border-gray-700'
        }
      `}>
        {msg.content}

        {/* Show cypher if present */}
        {msg.cypher && (
          <details className="mt-2">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-200">
              View Cypher query
            </summary>
            <pre className="mt-1 text-xs text-green-400 bg-gray-900
                            rounded p-2 overflow-x-auto whitespace-pre-wrap">
              {msg.cypher}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel({ onHighlightNodes }) {
  const [messages,    setMessages]    = useState([
    {
      role:    'assistant',
      content: 'Hi! I can help you analyze the SAP Order-to-Cash data. Ask me anything about orders, deliveries, billing documents, or payments.',
    }
  ])
  const [input,     setInput]     = useState('')
  const [loading,   setLoading]   = useState(false)
  const bottomRef   = useRef(null)
  const inputRef    = useRef(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(question) {
    const q = (question || input).trim()
    if (!q || loading) return

    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: q }])
    setLoading(true)

    try {
      const result = await chatApi.sendMessage(q, SESSION_ID)

      setMessages(prev => [...prev, {
        role:    'assistant',
        content: result.answer,
        cypher:  result.is_domain ? result.cypher : null,
      }])

      // Highlight referenced nodes in the graph
      if (result.highlighted_nodes?.length && onHighlightNodes) {
        onHighlightNodes(result.highlighted_nodes)
      }

    } catch (err) {
      setMessages(prev => [...prev, {
        role:    'assistant',
        content: 'Sorry, something went wrong. Please try again.',
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  async function clearChat() {
    await chatApi.clearHistory(SESSION_ID)
    setMessages([{
      role:    'assistant',
      content: 'Conversation cleared. How can I help you?',
    }])
  }

  return (
    <div className="flex flex-col bg-gray-900 border-l border-gray-800"
         style={{ width: 360, flexShrink: 0 }}>

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3
                      border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          <span className="text-sm font-semibold text-gray-200">
            Chat with Graph
          </span>
        </div>
        <button
          onClick={clearChat}
          className="text-gray-600 hover:text-gray-300 transition-colors"
          title="Clear conversation"
        >
          <Trash2 size={14} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((msg, i) => (
          <Message key={i} msg={msg} />
        ))}

        {/* Loading indicator */}
        {loading && (
          <div className="flex gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-700
                            flex items-center justify-center flex-shrink-0">
              <Bot size={13} className="text-white" />
            </div>
            <div className="bg-gray-800 border border-gray-700 rounded-lg
                            rounded-tl-none px-3 py-2">
              <Loader size={14} className="animate-spin text-gray-400" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Example questions */}
      <div className="px-3 pb-2 flex-shrink-0">
        <p className="text-xs text-gray-600 mb-1.5">Quick questions:</p>
        <div className="flex flex-col gap-1">
          {EXAMPLE_QUESTIONS.slice(0, 3).map((q, i) => (
            <button
              key={i}
              onClick={() => sendMessage(q)}
              disabled={loading}
              className="text-left text-xs text-gray-400 hover:text-blue-400
                         hover:bg-gray-800 rounded px-2 py-1
                         transition-colors truncate disabled:opacity-50"
            >
              → {q}
            </button>
          ))}
        </div>
      </div>

      {/* Input */}
      <div className="p-3 border-t border-gray-800 flex-shrink-0">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your data..."
            disabled={loading}
            className="flex-1 text-xs bg-gray-800 border border-gray-700
                       rounded px-3 py-2 text-gray-200
                       placeholder-gray-600 focus:outline-none
                       focus:border-blue-500 disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-500
                       disabled:opacity-40 disabled:cursor-not-allowed
                       rounded text-white transition-colors flex-shrink-0"
          >
            <Send size={13} />
          </button>
        </div>
      </div>
    </div>
  )
}