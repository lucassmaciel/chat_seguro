import React, { useState, useEffect, useRef } from 'react'

function ChatWindow({ conversation, clientId, onSendMessage, onOpenSidebar }) {
  const [message, setMessage] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [conversation.history])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (message.trim()) {
      onSendMessage(message)
      setMessage('')
      inputRef.current?.focus()
    }
  }

  const formatTime = (timestamp) => {
    if (!timestamp) return new Date().toLocaleTimeString('pt-BR', {
      hour: '2-digit',
      minute: '2-digit',
    })
    return timestamp
  }

  return (
    <div className="flex flex-1 flex-col h-full bg-gray-900 overflow-hidden">
      {/* Header */}
      <div className="px-4 sm:px-6 py-4 border-b border-gray-800 bg-gray-900/80 backdrop-blur-xl flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg ${
            conversation.type === 'group'
              ? 'bg-gradient-to-br from-purple-500 to-purple-600'
              : 'bg-gradient-to-br from-blue-500 to-blue-600'
          }`}>
            {conversation.type === 'group' ? '👥' : '💬'}
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">{conversation.id}</h2>
            <p className="text-xs text-gray-400">
              {conversation.type === 'group' ? 'Grupo' : 'Conversa privada'}
            </p>
          </div>
        </div>
        <button
          onClick={onOpenSidebar}
          className="lg:hidden px-3 py-2 text-xs font-semibold text-gray-200 bg-gray-800 border border-gray-700 rounded-lg"
        >
          Conversas
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 bg-gray-900">
        {conversation.history.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-gray-400 text-sm mb-1">Nenhuma mensagem ainda</p>
              <p className="text-gray-500 text-xs">Envie a primeira mensagem para começar</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3 max-w-3xl mx-auto">
            {conversation.history.map((msg, index) => {
              const isOwn = msg.sender === clientId
              return (
                <div
                  key={index}
                  className={`flex ${isOwn ? 'justify-end' : 'justify-start'} animate-fade-in`}
                >
                  <div className={`max-w-[70%] ${isOwn ? 'order-2' : 'order-1'}`}>
                    {!isOwn && (
                      <div className="text-xs text-gray-400 mb-1 px-1">{msg.sender}</div>
                    )}
                    <div
                      className={`px-4 py-2.5 rounded-2xl shadow-lg ${
                        isOwn
                          ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-br-md'
                          : 'bg-gray-800 text-gray-100 border border-gray-700 rounded-bl-md'
                      }`}
                    >
                      <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
                        {msg.message}
                      </p>
                      <div className={`text-xs mt-1.5 ${
                        isOwn ? 'text-blue-100' : 'text-gray-400'
                      }`}>
                        {formatTime(msg.timestamp)}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="px-4 py-4 border-t border-gray-800 bg-gray-900">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="flex items-end space-x-3">
            <div className="flex-1 relative">
              <input
                ref={inputRef}
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={`Digite uma mensagem${conversation.type === 'group' ? ' no grupo' : ''}...`}
                className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-500"
              />
            </div>
            <button
              type="submit"
              disabled={!message.trim()}
              className="p-3 bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-2xl shadow-lg hover:shadow-xl hover:shadow-blue-500/50 transform hover:scale-105 active:scale-95 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ChatWindow
