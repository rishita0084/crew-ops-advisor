import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Vite's default binds IPv6 only ([::1]). On Windows `localhost` may resolve to
    // either stack, so a browser reaching for 127.0.0.1 gets connection refused.
    // Binding all interfaces makes the console reachable both ways (and from a phone
    // on the same network, which is handy for a demo).
    host: true,
    port: 5173,
    strictPort: true,
  },
})
