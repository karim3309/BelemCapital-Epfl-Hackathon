import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'framer-motion'
import React from 'react'
import { createRoot } from 'react-dom/client'
import { SourceProvider } from './api/source'
import App from './App'
import './index.css'
import { SelectionProvider } from './state/selection'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
})

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <SourceProvider>
        <SelectionProvider>
          <MotionConfig reducedMotion="user">
            <App />
          </MotionConfig>
        </SelectionProvider>
      </SourceProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
