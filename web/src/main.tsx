import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'
import { useLang } from './i18n'
import Landing from './landing/Landing'

import './style.css'

// Landing page unless a shared link (?s=) or #atlas; the browser Back button returns to the landing.
const inAtlas = () => location.hash === '#atlas' || new URLSearchParams(location.search).has('s')

function Root() {
  const lang = useLang()
  const [atlas, setAtlas] = useState(inAtlas)
  useEffect(() => {
    const sync = () => setAtlas(inAtlas())
    addEventListener('hashchange', sync)
    addEventListener('popstate', sync)
    return () => {
      removeEventListener('hashchange', sync)
      removeEventListener('popstate', sync)
    }
  }, [])
  useEffect(() => {
    scrollTo(0, 0)
  }, [atlas])
  // Reading the language here re-renders the whole tree (no memoized children) without losing state.
  void lang
  return atlas ? (
    <App />
  ) : (
    <Landing
      onEnter={() => {
        location.hash = 'atlas'
      }}
    />
  )
}

createRoot(document.getElementById('root')!).render(<Root />)
