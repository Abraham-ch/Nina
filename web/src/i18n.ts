import { useSyncExternalStore } from 'react'

// Interface language: English by default, Spanish optional. The choice is remembered per browser.
export type Lang = 'en' | 'es'
const listeners = new Set<() => void>()
function initial(): Lang {
  const query = new URLSearchParams(location.search).get('lang')
  if (query === 'en' || query === 'es') return query
  try {
    return localStorage.getItem('nina-lang') === 'es' ? 'es' : 'en'
  } catch {
    return 'en'
  }
}
let current: Lang = initial()
document.documentElement.lang = current

export const getLang = () => current
export function setLang(lang: Lang) {
  current = lang
  try {
    localStorage.setItem('nina-lang', lang)
  } catch {
    /* private mode: keep it for this session only */
  }
  document.documentElement.lang = lang
  listeners.forEach((listener) => listener())
}
export const useLang = () =>
  useSyncExternalStore((fn) => {
    listeners.add(fn)
    return () => listeners.delete(fn)
  }, getLang)

/** Pick the string for the active language: tr(english, spanish). */
export const tr = (en: string, es: string) => (current === 'es' ? es : en)
export const locale = () => (current === 'es' ? 'es-PE' : 'en-US')
