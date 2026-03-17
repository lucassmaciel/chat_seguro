import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // Porta do servidor React (pode ser sobrescrita por variável de ambiente)
  const port = parseInt(process.env.PORT || process.env.VITE_PORT || '3000', 10)
  
  // Porta da API backend (padrão 8000)
  const apiPort = process.env.VITE_API_PORT || '8000'
  const apiHost = process.env.VITE_API_HOST || 'localhost'
  
  return {
    plugins: [react()],
    server: {
      port: port,
      strictPort: false, // Permite usar outra porta se a especificada estiver ocupada
      proxy: {
        '/api': {
          target: `http://${apiHost}:${apiPort}`,
          changeOrigin: true,
        },
        '/ws': {
          target: `ws://${apiHost}:${apiPort}`,
          ws: true,
        }
      }
    }
  }
})

