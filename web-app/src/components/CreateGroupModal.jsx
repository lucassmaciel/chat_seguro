import React, { useState } from 'react'

function CreateGroupModal({ availableClients, onCreate, onClose }) {
  const [groupName, setGroupName] = useState('')
  const [selectedMembers, setSelectedMembers] = useState([])
  const [loading, setLoading] = useState(false)

  const toggleMember = (clientId) => {
    if (selectedMembers.includes(clientId)) {
      setSelectedMembers(selectedMembers.filter((id) => id !== clientId))
    } else {
      setSelectedMembers([...selectedMembers, clientId])
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!groupName.trim()) {
      alert('Por favor, insira um nome para o grupo')
      return
    }
    if (selectedMembers.length === 0) {
      alert('Por favor, selecione pelo menos um membro')
      return
    }

    setLoading(true)
    try {
      await onCreate(groupName.trim(), selectedMembers)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in"
      onClick={onClose}
    >
      <div
        className="bg-gray-800 rounded-3xl shadow-2xl w-full max-w-md max-h-[90vh] overflow-hidden animate-scale-in border border-gray-700"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-5 border-b border-gray-700 flex items-center justify-between bg-gray-800">
          <h2 className="text-xl font-semibold text-white">Criar Novo Grupo</h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-6 max-h-[calc(90vh-140px)] overflow-y-auto">
          <div>
            <label htmlFor="groupName" className="block text-sm font-medium text-gray-300 mb-2">
              Nome do Grupo
            </label>
            <input
              id="groupName"
              type="text"
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              placeholder="Digite o nome do grupo"
              disabled={loading}
              autoFocus
              className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400 disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-3">
              Selecione os Membros
            </label>
            {availableClients.length === 0 ? (
              <div className="p-8 text-center bg-gray-700/30 rounded-xl">
                <div className="w-12 h-12 rounded-full bg-gray-700 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                  </svg>
                </div>
                <p className="text-sm text-gray-400 mb-1">Nenhum usuário disponível</p>
                <p className="text-xs text-gray-500">Outros usuários precisam estar online</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {availableClients.map((clientId) => (
                  <label
                    key={clientId}
                    className="flex items-center space-x-3 p-3 rounded-xl hover:bg-gray-700/50 cursor-pointer transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={selectedMembers.includes(clientId)}
                      onChange={() => toggleMember(clientId)}
                      disabled={loading}
                      className="w-5 h-5 text-blue-600 border-gray-600 bg-gray-700 rounded focus:ring-blue-500 focus:ring-2"
                    />
                    <div className="flex items-center space-x-3 flex-1">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white text-xs font-semibold shadow-lg">
                        {clientId[0]?.toUpperCase()}
                      </div>
                      <span className="text-sm text-gray-200 font-medium">{clientId}</span>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>

          <div className="flex space-x-3 pt-4 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="flex-1 py-3 px-4 bg-gray-700 text-gray-200 font-medium rounded-xl hover:bg-gray-600 transition-colors disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading || !groupName.trim() || selectedMembers.length === 0}
              className="flex-1 py-3 px-4 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-xl shadow-lg hover:shadow-xl hover:shadow-blue-500/50 transform hover:scale-[1.02] active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            >
              {loading ? 'Criando...' : 'Criar Grupo'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default CreateGroupModal
