import { tr } from '../i18n'

// ponytail: mock team; replace names and roles, and put photos in web/public/assets/members/ (e.g. photo: '/assets/members/ana.jpg').
// Without a photo the card shows the initials.
const TEAM: { name: string; role: [en: string, es: string]; photo?: string }[] = [
  {
    name: 'Marlon Bustos',
    role: ['Data and harmonization', 'Datos y armonización'],
    photo: '/assets/members/mdbp.jpg',
  },
  {
    name: 'Abraham Chafloque',
    role: ['UX/UI and frontend', 'UX/UI y frontend'],
    photo: '/assets/members/ac.jpg',
  },
  {
    name: 'Steve Luzquiños',
    role: ['Backend: API, accounts, exports', 'Backend: API, cuentas, exportaciones'],
    photo: '/assets/members/al.jpg',
  },
]

const initials = (name: string) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()

export default function Team() {
  return (
    <section className="landing-team" aria-labelledby="landing-team-title">
      <p className="landing-kicker">{tr('The team', 'El equipo')}</p>
      <h2 id="landing-team-title">{tr('Who builds NINA', 'Quiénes construyen NINA')}</h2>
      <ul className="landing-team-list">
        {TEAM.map((m, i) => (
          <li key={i}>
            {m.photo ? (
              <img src={m.photo} alt="" className="landing-team-photo" loading="lazy" />
            ) : (
              <span className="landing-team-photo" aria-hidden="true">
                {initials(m.name)}
              </span>
            )}
            <strong>{m.name}</strong>
            <span>{tr(...m.role)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
