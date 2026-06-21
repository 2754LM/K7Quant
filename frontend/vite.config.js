import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8765', changeOrigin: true }
    }
  },
  base: './',
  build: {
    // 第三方库 (naive-ui) 体积较大, 已通过 manualChunks 隔离, 不会阻塞首屏
    chunkSizeWarningLimit: 2000,  // 2MB
    rollupOptions: {
      output: {
        // 拆 vendor 拆成独立 chunk, 利用浏览器并行下载 + 缓存复用
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('echarts')) return 'vendor-echarts'
            if (id.includes('naive-ui')) return 'vendor-naive'
            if (id.includes('@vue') || id.includes('/vue/') || id.includes('vue-router') || id.includes('pinia')) return 'vendor-vue'
            if (id.includes('axios')) return 'vendor-axios'
            return 'vendor'
          }
          return undefined
        },
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
      }
    }
  }
})
