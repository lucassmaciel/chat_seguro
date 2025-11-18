import React, { useState } from 'react'
import Login from './components/Login'
import ChatInterface from './components/ChatInterface'

function App() {
  const [clientId, setClientId] = useState(null)

  const handleLogin = (id) => {
    setClientId(id)
  }

  const handleLogout = () => {
    setClientId(null)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950">
      {!clientId ? (
        <Login onLogin={handleLogin} />
      ) : (
        <ChatInterface clientId={clientId} onLogout={handleLogout} />
      )}
    </div>
  )
}

export default App
