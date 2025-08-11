import { defineConfig } from 'vite'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js']
  },
  server: {
    port: 3000,
    host: true,
    open: true,
    cors: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  },

  build: {
    outDir: 'dist',
    sourcemap: true,
    minify: 'terser',
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor code for better caching
          vendor: ['axios']
        }
      }
    }
  },

  css: {
    devSourcemap: true,
    preprocessorOptions: {
      scss: {
        additionalData: `@import "./src/styles/base/variables.css";`
      }
    }
  },

  define: {
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version),
  }
})
