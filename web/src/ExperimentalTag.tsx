import { tr } from './i18n'

// Shown wherever the harmonized draft appears: it has not passed its scientific gates.
export default function ExperimentalTag() {
  return (
    <span
      className="experimental-tag"
      title={tr(
        'Draft harmonization: it has not passed its scientific validation gates.',
        'Armonización en borrador: no ha superado sus pruebas de validación científica.',
      )}
    >
      {tr('Experimental', 'Experimental')}
    </span>
  )
}
