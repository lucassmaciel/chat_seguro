// Configuração da API - pode ser sobrescrita por variáveis de ambiente
// Em cenários multiporta (ex.: front em 3000/3001 e API em 8000),
// usamos valores explícitos para evitar depender do proxy do Vite.
const API_HOST = import.meta.env.VITE_API_HOST || window.location.hostname || 'localhost'
const API_PORT = import.meta.env.VITE_API_PORT || '8000'

const HTTP_PROTOCOL = window.location.protocol === 'https:' ? 'https' : 'http'
const WS_PROTOCOL = HTTP_PROTOCOL === 'https' ? 'wss' : 'ws'

export const API_BASE_URL = `${HTTP_PROTOCOL}://${API_HOST}:${API_PORT}`
export const WS_BASE_URL = `${WS_PROTOCOL}://${API_HOST}:${API_PORT}`

