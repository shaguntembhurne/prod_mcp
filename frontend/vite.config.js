import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_URL || 'http://127.0.0.1:8001'

  return {
    plugins: [
      react(),
      tailwindcss(),
    ],
    server: {
      port: 5173,
      // Proxy API requests to the Django backend during development.
      // Avoids browser CORS blocks without requiring backend modifications.
      proxy: {
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
