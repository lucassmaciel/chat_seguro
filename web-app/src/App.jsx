import React, { useEffect, useState } from 'react'
import Login from './components/Login'
import ChatInterface from './components/ChatInterface'

const STORAGE_KEYS = {
  client: 'chatSeguroClientId',
  session: 'chatSeguroSessionToken',
}

const readStoredValue = (key) => {
  if (typeof window === 'undefined') {
    return null
  }
  return window.localStorage.getItem(key) || null
}

function App() {
  const [clientId, setClientId] = useState(() => readStoredValue(STORAGE_KEYS.client))
  const [sessionToken, setSessionToken] = useState(() => readStoredValue(STORAGE_KEYS.session))

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (clientId) {
      window.localStorage.setItem(STORAGE_KEYS.client, clientId)
    } else {
      window.localStorage.removeItem(STORAGE_KEYS.client)
    }
  }, [clientId])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (sessionToken) {
      window.localStorage.setItem(STORAGE_KEYS.session, sessionToken)
    } else {
      window.localStorage.removeItem(STORAGE_KEYS.session)
    }
  }, [sessionToken])

  const handleLogin = ({ clientId: id, sessionToken: token }) => {
    setClientId(id)
    setSessionToken(token || null)
  }

  const handleLogout = () => {
    setClientId(null)
    setSessionToken(null)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950">
      {!clientId ? (
        <Login onLogin={handleLogin} />
      ) : (
        <ChatInterface
          clientId={clientId}
          sessionToken={sessionToken}
          onLogout={handleLogout}
        />
      )}
    </div>
  )
}

export default App
