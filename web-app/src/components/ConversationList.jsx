import React from 'react'

function ConversationList({ conversations, selectedId, onSelect, onCreateGroup }) {
  const sortedConversations = [...conversations].sort((a, b) => {
    if (a.type !== b.type) {
      return a.type === 'group' ? -1 : 1
    }
    return a.id.localeCompare(b.id)
  })

  const getLastMessage = (conv) => {
    if (conv.history && conv.history.length > 0) {
      return conv.history[conv.history.length - 1].message
    }
    return null
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-h-0">
      <div className="px-4 py-3 border-b border-gray-700 flex items-center justify-between bg-gray-800/50">
        <h3 className="text-sm font-semibold text-gray-300">Conversas</h3>
        <button
          onClick={onCreateGroup}
          className="p-1.5 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 hover:text-blue-400"
          title="Criar grupo"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {sortedConversations.length === 0 ? (
          <div className="p-8 text-center">
            <div className="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center mx-auto mb-3">
              <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <p className="text-sm text-gray-400 mb-1">Nenhuma conversa ainda</p>
            <p className="text-xs text-gray-500">Crie um grupo ou aguarde mensagens</p>
          </div>
        ) : (
          <div className="py-2">
            {sortedConversations.map((conv) => {
              const isSelected = selectedId === conv.id
              const lastMessage = getLastMessage(conv)
              
              return (
                <div
                  key={conv.id}
                  onClick={() => onSelect(conv.id)}
                  className={`px-4 py-3 mx-2 rounded-xl cursor-pointer transition-all duration-200 ${
                    isSelected
                      ? 'bg-blue-600/30 border border-blue-500/50 shadow-lg shadow-blue-500/20'
                      : 'hover:bg-gray-700/50'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <div className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center text-lg shadow-lg ${
                      conv.type === 'group' 
                        ? 'bg-gradient-to-br from-purple-500 to-purple-600' 
                        : 'bg-gradient-to-br from-blue-500 to-blue-600'
                    }`}>
                      {conv.type === 'group' ? '👥' : '💬'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <h4 className={`text-sm font-semibold truncate ${
                          isSelected ? 'text-blue-300' : 'text-gray-200'
                        }`}>
                          {conv.id}
                        </h4>
                      </div>
                      {lastMessage && (
                        <p className="text-xs text-gray-400 truncate">
                          {lastMessage.length > 40 ? lastMessage.substring(0, 40) + '...' : lastMessage}
                        </p>
                      )}
                      {!lastMessage && (
                        <p className="text-xs text-gray-500 italic">Nova conversa</p>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

export default ConversationList
