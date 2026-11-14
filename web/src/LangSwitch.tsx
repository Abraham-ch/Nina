import { setLang, useLang, type Lang } from './i18n'

/** EN / ES switch. Used in the landing header and in the app header. */
export default function LangSwitch({ className = '' }: { className?: string }) {
  const lang = useLang()
  return (
    <div
      className={`lang-switch ${className}`}
      role="group"
      aria-label={lang === 'es' ? 'Idioma' : 'Language'}
    >
      {(['en', 'es'] as Lang[]).map((code) => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={lang === code}
          onClick={() => setLang(code)}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
