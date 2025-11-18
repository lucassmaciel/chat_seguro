import React, { useState } from 'react'
import { API_BASE_URL } from '../config'

function Login({ onLogin }) {
  const [mode, setMode] = useState('login')
  const [step, setStep] = useState('auth')
  const [form, setForm] = useState({
    email: '',
    password: '',
    confirmPassword: '',
    clientId: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [mfaToken, setMfaToken] = useState('')
  const [mfaCode, setMfaCode] = useState('')

  const resetFeedback = () => {
    setError('')
    setStatusMessage('')
  }

  const handleChange = (field) => (event) => {
    setForm((prev) => ({ ...prev, [field]: event.target.value }))
  }

  const handleRegister = async (event) => {
    event.preventDefault()
    resetFeedback()
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: form.email.trim(),
          password: form.password,
          confirm_password: form.confirmPassword,
          client_id: form.clientId.trim(),
        }),
      })
      const data = await response.json()
      if (data.status === 'ok') {
        setStatusMessage('Registro concluído! Faça login para continuar.')
        setMode('login')
        setForm((prev) => ({ ...prev, password: '', confirmPassword: '' }))
      } else {
        setError(data.detail || 'Erro ao registrar usuário')
      }
    } catch (err) {
      console.error(err)
      setError('Erro de conexão. Verifique o servidor.')
    } finally {
      setLoading(false)
    }
  }

  const handleLoginSubmit = async (event) => {
    event.preventDefault()
    resetFeedback()
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: form.email.trim(),
          password: form.password,
        }),
      })
      const data = await response.json()
      if (data.status === 'mfa_required') {
        setStep('mfa')
        setMfaToken(data.token)
        setStatusMessage('Enviamos um código para o seu e-mail. Confira e insira abaixo.')
      } else if (data.status === 'ok') {
        onLogin({ clientId: data.client_id, sessionToken: data.session_token })
      } else {
        setError(data.detail || 'Erro ao realizar login')
      }
    } catch (err) {
      console.error(err)
      setError('Erro de conexão. Verifique o servidor.')
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyMfa = async (event) => {
    event.preventDefault()
    if (!mfaToken) {
      setError('Token MFA ausente. Refaça o login.')
      return
    }
    resetFeedback()
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/verify-mfa`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token: mfaToken,
          code: mfaCode.trim(),
        }),
      })
      const data = await response.json()
      if (data.status === 'ok') {
        onLogin({ clientId: data.client_id, sessionToken: data.session_token })
      } else {
        setError(data.detail || 'Código inválido')
      }
    } catch (err) {
      console.error(err)
      setError('Erro de conexão ao validar MFA')
    } finally {
      setLoading(false)
    }
  }

  const renderForm = () => {
    if (step === 'mfa') {
      return (
        <form onSubmit={handleVerifyMfa} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Código MFA
            </label>
            <input
              type="text"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              placeholder="Digite o código enviado"
              className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400"
            />
          </div>
          <div className="flex space-x-3">
            <button
              type="button"
              onClick={() => {
                setStep('auth')
                setMfaCode('')
                setMfaToken('')
              }}
              className="flex-1 py-3 bg-gray-700 text-gray-200 rounded-xl hover:bg-gray-600 transition-all"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading || !mfaCode.trim()}
              className="flex-1 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-xl shadow-lg hover:shadow-xl hover:shadow-blue-500/50 transform hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 disabled:opacity-50"
            >
              Validar código
            </button>
          </div>
        </form>
      )
    }

    if (mode === 'register') {
      return (
        <form onSubmit={handleRegister} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">E-mail</label>
            <input
              type="email"
              value={form.email}
              onChange={handleChange('email')}
              placeholder="seu.email@empresa.com"
              className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Nome de Usuário</label>
            <input
              type="text"
              value={form.clientId}
              onChange={handleChange('clientId')}
              placeholder="ex: alice, squad-crypto"
              className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Senha</label>
            <input
              type="password"
              value={form.password}
              onChange={handleChange('password')}
              placeholder="Mínimo 8 caracteres"
              className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Confirmar senha</label>
            <input
              type="password"
              value={form.confirmPassword}
              onChange={handleChange('confirmPassword')}
              placeholder="Repita a senha"
              className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-xl shadow-lg hover:shadow-xl hover:shadow-blue-500/50 transform hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 disabled:opacity-50"
          >
            Criar conta segura
          </button>
        </form>
      )
    }

    return (
      <form onSubmit={handleLoginSubmit} className="space-y-5">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">E-mail</label>
          <input
            type="email"
            value={form.email}
            onChange={handleChange('email')}
            placeholder="seu.email@empresa.com"
            className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Senha</label>
          <input
            type="password"
            value={form.password}
            onChange={handleChange('password')}
            placeholder="••••••••"
            className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-white placeholder-gray-400"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-xl shadow-lg hover:shadow-xl hover:shadow-blue-500/50 transform hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 disabled:opacity-50"
        >
          Entrar com MFA
        </button>
      </form>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md animate-fade-in">
        <div className="bg-gray-800/90 backdrop-blur-xl rounded-3xl shadow-2xl p-8 border border-gray-700/50">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 mb-4 shadow-lg shadow-blue-500/50">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <h1 className="text-3xl font-semibold text-white mb-2">Chat Seguro</h1>
            <p className="text-sm text-gray-400">Autenticação forte com senha + MFA</p>
          </div>

          {step === 'auth' && (
            <div className="flex mb-6 rounded-2xl overflow-hidden border border-gray-700">
              {['login', 'register'].map((tab) => (
                <button
                  key={tab}
                  onClick={() => {
                    resetFeedback()
                    setMode(tab)
                  }}
                  className={`flex-1 py-2 text-sm font-medium transition-all ${
                    mode === tab
                      ? 'bg-blue-600 text-white'
                      : 'bg-transparent text-gray-400 hover:text-white'
                  }`}
                  type="button"
                >
                  {tab === 'login' ? 'Entrar' : 'Registrar'}
                </button>
              ))}
            </div>
          )}

          {statusMessage && (
            <div className="bg-green-900/40 border border-green-700 text-green-200 px-4 py-3 rounded-xl text-sm mb-4">
              {statusMessage}
            </div>
          )}

          {error && (
            <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-3 rounded-xl text-sm mb-4">
              {error}
            </div>
          )}

          {renderForm()}

          <div className="mt-6 text-center text-xs text-gray-500">
            {step === 'mfa'
              ? 'Dica: confira a caixa de entrada e o lixo eletrônico do e-mail informado; se o código não chegar em até 1 minuto, refaça o login para solicitar um novo.'
              : 'As credenciais protegem seu ID público e suas chaves criptográficas.'}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Login
