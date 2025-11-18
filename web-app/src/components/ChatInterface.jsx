import React, { useState, useEffect, useRef } from 'react'
import ConversationList from './ConversationList'
import ChatWindow from './ChatWindow'
import CreateGroupModal from './CreateGroupModal'
import { API_BASE_URL, WS_BASE_URL } from '../config'

function ChatInterface({ clientId, sessionToken, onLogout }) {
  const [conversations, setConversations] = useState([])
  const [availableClients, setAvailableClients] = useState([])
  const [availableGroups, setAvailableGroups] = useState([])
  const [selectedConversation, setSelectedConversation] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [syncError, setSyncError] = useState('')
  const isInitialLoadRef = useRef(true)
  const wsRef = useRef(null)

  useEffect(() => {
    // Resetar estado quando clientId mudar
    isInitialLoadRef.current = true
    setSelectedConversation(null)
    setLoading(true)
    setSyncError('')

    let reconnect = true
    let reconnectTimeout

    const connectWebSocket = () => {
      const ws = new WebSocket(`${WS_BASE_URL}/ws/${clientId}`)
      wsRef.current = ws

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (['new_message', 'update_ui', 'message_sent'].includes(data.type)) {
          loadConversations()
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
      }

      ws.onclose = () => {
        if (reconnect) {
          reconnectTimeout = setTimeout(connectWebSocket, 3000)
        }
      }
    }

    const interval = setInterval(loadConversations, 3000)
    loadConversations()
    connectWebSocket()

    return () => {
      reconnect = false
      clearInterval(interval)
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId])

  const loadConversations = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/conversations?client_id=${clientId}`
      )
      const data = await response.json()

      if (response.status === 401) {
        setSyncError('Sessão expirada. Faça login novamente para continuar.')
        onLogout()
        return
      }

      if (data.status === 'ok') {
        setSyncError('')
        const newConversations = data.conversations || []
        setConversations(newConversations)
        setAvailableClients(data.available_clients || [])
        setAvailableGroups(data.available_groups || [])

        // Só selecionar automaticamente a primeira conversa no primeiro carregamento
        setSelectedConversation(prevSelected => {
          if (isInitialLoadRef.current && !prevSelected && newConversations.length > 0) {
            isInitialLoadRef.current = false
            return newConversations[0].id
          }
          if (isInitialLoadRef.current) {
            isInitialLoadRef.current = false
          }
          // Preservar a seleção atual se a conversa ainda existir
          if (prevSelected && newConversations.find(c => c.id === prevSelected)) {
            return prevSelected
          }
          // Se a conversa selecionada não existe mais, manter null (usuário escolhe manualmente)
          return prevSelected
        })
      } else if (data.detail) {
        setSyncError(data.detail)
      }
    } catch (error) {
      console.error('Erro ao carregar conversas:', error)
      setSyncError('Erro ao sincronizar dados. Verifique sua conexão.')
    } finally {
      setLoading(false)
    }
  }

  const handleSendMessage = async (message) => {
    if (!selectedConversation || !message.trim()) return

    try {
      const response = await fetch(`${API_BASE_URL}/api/send-message`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          to: selectedConversation,
          message: message.trim(),
          client_id: clientId,
        }),
      })

      const data = await response.json()
      if (data.status === 'ok') {
        // Recarregar imediatamente para mostrar a mensagem
        setTimeout(loadConversations, 100)
      } else {
        alert('Erro ao enviar mensagem: ' + (data.detail || 'Erro desconhecido'))
      }
    } catch (error) {
      console.error('Erro ao enviar mensagem:', error)
      alert('Erro de conexão ao enviar mensagem')
    }
  }

  const handleCreateGroup = async (groupName, members) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/create-group`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          group_id: groupName,
          members: members,
          client_id: clientId,
        }),
      })

      const data = await response.json()
      if (data.status === 'ok') {
        setShowCreateGroup(false)
        setTimeout(loadConversations, 500)
      } else {
        alert('Erro ao criar grupo: ' + (data.detail || 'Erro desconhecido'))
      }
    } catch (error) {
      console.error('Erro ao criar grupo:', error)
      alert('Erro de conexão ao criar grupo')
    }
  }

  const handleLogout = async () => {
    try {
      const headers = sessionToken
        ? {
            'X-Session-Token': sessionToken,
          }
        : undefined
      await fetch(`${API_BASE_URL}/api/logout`, {
        method: 'POST',
        headers,
      })
    } catch (error) {
      console.error('Erro no logout:', error)
    }
    onLogout()
  }

  const currentConversation = conversations.find(
    (c) => c.id === selectedConversation
  )

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent"></div>
          <p className="mt-4 text-gray-400">Carregando...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen flex overflow-hidden bg-gray-900">
      {/* Sidebar */}
      <div className="w-80 bg-gray-800 border-r border-gray-700 flex flex-col shadow-lg">
        <div className="p-4 border-b border-gray-700 bg-gray-800/80 backdrop-blur-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white font-semibold shadow-lg shadow-blue-500/50">
                {clientId[0]?.toUpperCase()}
              </div>
              <div>
                <div className="font-semibold text-white text-sm">{clientId}</div>
                <div className="text-xs text-gray-400 flex items-center">
                  <span className="w-2 h-2 bg-green-500 rounded-full mr-1.5 animate-pulse"></span>
                  Online
                </div>
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="p-2 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
              title="Sair"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </div>
        </div>

        <ConversationList
          conversations={conversations}
          selectedId={selectedConversation}
          onSelect={setSelectedConversation}
          onCreateGroup={() => setShowCreateGroup(true)}
        />
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-gray-900">
        {syncError && (
          <div className="px-6 py-3 bg-red-900/40 text-red-200 text-sm text-center border-b border-red-700/40">
            {syncError}
          </div>
        )}
        {currentConversation ? (
          <ChatWindow
            conversation={currentConversation}
            clientId={clientId}
            onSendMessage={handleSendMessage}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center bg-gray-900">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-300 mb-2">Selecione uma conversa</h2>
              <p className="text-gray-500 text-sm">Escolha uma conversa da lista para começar</p>
            </div>
          </div>
        )}
      </div>

      {showCreateGroup && (
        <CreateGroupModal
          availableClients={availableClients.filter((c) => c !== clientId)}
          onCreate={handleCreateGroup}
          onClose={() => setShowCreateGroup(false)}
        />
      )}
    </div>
  )
}

export default ChatInterface
