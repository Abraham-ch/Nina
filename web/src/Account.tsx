import { Download, FileClock, LogOut, ShieldCheck, UserRound, X } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'

import { api, post } from './api'
import { locale, tr } from './i18n'
import type { AuditEntry as Registro, Download as Descarga, Login, Register, User } from './types'

type Vista = 'formulario' | 'perfil' | 'descargas' | 'auditoria'
type Props = {
  open: boolean
  onOpen: (v: boolean) => void
  user: User | null
  onUser: (u: User | null) => void
  onNotice: (s: string) => void
  onError: (s: string) => void
}

/** Role labels as [english, spanish]; the tokens themselves stay untranslated. */
const ROLES: Record<User['role'], [string, string]> = {
  visitante: ['Viewer · read only', 'Visitante · solo consulta'],
  analista: ['Analyst · exports and saves analyses', 'Analista · exporta y guarda análisis'],
  admin: [
    'Administrator · imports, syncs and trains models',
    'Administrador · importa, sincroniza y entrena modelos',
  ],
}

export default function Account({ open, onOpen, user, onUser, onNotice, onError }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const [vista, setVista] = useState<Vista>('formulario')
  const [modo, setModo] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState(''),
    [password, setPassword] = useState(''),
    [nombre, setNombre] = useState(''),
    [rol, setRol] = useState<Register['role']>('analista')
  const [busy, setBusy] = useState(false),
    [historial, setHistorial] = useState<Descarga[] | null>(null),
    [denegado, setDenegado] = useState(''),
    [auditoria, setAuditoria] = useState<Registro[] | null>(null)
  useEffect(() => {
    if (open) {
      if (!ref.current?.open) ref.current?.showModal()
    } else ref.current?.close()
  }, [open])
  useEffect(() => {
    setVista(user ? 'perfil' : 'formulario')
    setHistorial(null)
    setDenegado('')
    setAuditoria(null)
  }, [user?.id, open])
  useEffect(() => {
    if (vista !== 'descargas' || !user) return
    setHistorial(null)
    setDenegado('')
    api<Descarga[]>('/downloads')
      .then(setHistorial)
      .catch((e) => setDenegado(String(e)))
  }, [vista, user?.id])
  useEffect(() => {
    if (vista !== 'auditoria' || !user) return
    setAuditoria(null)
    setDenegado('')
    api<Registro[]>('/audit')
      .then(setAuditoria)
      .catch((e) => setDenegado(String(e)))
  }, [vista, user?.id])
  async function enviar(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    const cuerpo: Login | Register =
      modo === 'login'
        ? { email, password }
        : { email, password, role: rol, ...(nombre ? { display_name: nombre } : {}) }
    try {
      const cuenta = await post<User>(`/auth/${modo}`, cuerpo)
      onUser(cuenta)
      setEmail('')
      setPassword('')
      setNombre('')
      onNotice(
        modo === 'login'
          ? tr(`Signed in as ${cuenta.email}.`, `Sesión iniciada como ${cuenta.email}.`)
          : tr(
              'Account created. You can now export and save analyses.',
              'Cuenta creada. Ya puedes exportar y guardar análisis.',
            ),
      )
    } catch (error) {
      onError(String(error))
    } finally {
      setBusy(false)
    }
  }
  async function salir() {
    setBusy(true)
    try {
      await post('/auth/logout', {})
      onUser(null)
      onNotice(tr('Signed out.', 'Sesión cerrada.'))
    } catch (error) {
      onError(String(error))
    } finally {
      setBusy(false)
    }
  }
  const fecha = (iso: string) => new Date(iso).toLocaleString(locale())
  return (
    <dialog
      ref={ref}
      className="nina-dialog account-dialog"
      onCancel={() => onOpen(false)}
      onClick={(e) => {
        if (e.target === ref.current) onOpen(false)
      }}
      aria-labelledby="account-title"
    >
      <div className="dialog-head">
        <div>
          <span className="kicker">
            {vista === 'descargas'
              ? tr('Your history', 'Historial propio')
              : vista === 'auditoria'
                ? tr('Recorded activity', 'Actividad registrada')
                : user
                  ? tr('Your account', 'Tu cuenta')
                  : tr('Access', 'Acceso')}
          </span>
          <h2 id="account-title">
            {vista === 'descargas'
              ? tr('My downloads', 'Mis descargas')
              : vista === 'auditoria'
                ? tr('Audit log', 'Auditoría')
                : user
                  ? tr('Profile', 'Perfil')
                  : modo === 'login'
                    ? tr('Sign in to NINA', 'Entrar en NINA')
                    : tr('Create an account', 'Crear una cuenta')}
          </h2>
        </div>
        <button onClick={() => onOpen(false)} aria-label={tr('Close dialog', 'Cerrar diálogo')}>
          <X size={20} />
        </button>
      </div>
      {vista === 'formulario' ? (
        <form className="dialog-body account-form" onSubmit={enviar}>
          <p>
            {modo === 'login'
              ? tr(
                  'Sign in to export, save analyses under your authorship and consult your history.',
                  'Inicia sesión para exportar, guardar análisis con tu autoría y consultar tu historial.',
                )
              : tr(
                  'The first registration on this base becomes administrator; later ones choose their role.',
                  'El primer registro de la base se vuelve administrador; los siguientes eligen su rol.',
                )}
          </p>
          <label>
            {tr('Email', 'Correo')}
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@example.com"
            />
          </label>
          <label>
            {tr('Password', 'Contraseña')}
            <input
              type="password"
              autoComplete={modo === 'login' ? 'current-password' : 'new-password'}
              required
              minLength={modo === 'register' ? 8 : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {modo === 'register' && (
            <>
              <label>
                {tr('Display name (optional)', 'Nombre visible (opcional)')}
                <input
                  maxLength={80}
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  placeholder={tr(
                    'How you want to appear in your history',
                    'Cómo quieres aparecer en tu historial',
                  )}
                />
              </label>
              <label>
                {tr('Role', 'Rol')}
                <select value={rol} onChange={(e) => setRol(e.target.value as Register['role'])}>
                  <option value="visitante">
                    {tr('Viewer · read only', 'Visitante · solo consulta')}
                  </option>
                  <option value="analista">
                    {tr(
                      'Analyst · exports and saves analyses',
                      'Analista · exporta y guarda análisis',
                    )}
                  </option>
                </select>
              </label>
              <p className="small-note">
                {tr(
                  'Becoming an administrator requires being the first registration on this base. Choose ',
                  'Para convertirte en administrador hay que ser el primer registro de esta base. Elige ',
                )}
                <strong>{tr('analyst', 'analista')}</strong>
                {tr(' if you plan to export.', ' si vas a exportar.')}
              </p>
            </>
          )}
          <button className="button dark" type="submit" disabled={busy}>
            {modo === 'login' ? tr('Sign in', 'Entrar') : tr('Create account', 'Crear cuenta')}
          </button>
          <button
            type="button"
            className="text-link"
            onClick={() => setModo(modo === 'login' ? 'register' : 'login')}
          >
            {modo === 'login'
              ? tr('Create an account instead', 'Crear una cuenta en su lugar')
              : tr('I already have an account', 'Ya tengo una cuenta')}
          </button>
        </form>
      ) : vista === 'perfil' ? (
        <div className="dialog-body account-form">
          <div className="account-card">
            <UserRound size={18} />
            <div>
              <strong>{user?.display_name || user?.email}</strong>
              <small>{user?.email}</small>
            </div>
          </div>
          <p className="role-line">
            <ShieldCheck size={15} />
            {user ? tr(ROLES[user.role][0], ROLES[user.role][1]) : ''}
          </p>
          <dl className="account-meta">
            <div>
              <dt>{tr('Account created', 'Cuenta creada')}</dt>
              <dd>
                {user?.created_at ? new Date(user.created_at).toLocaleDateString(locale()) : '—'}
              </dd>
            </div>
            <div>
              <dt>{tr('Downloads in the last hour', 'Descargas en la última hora')}</dt>
              <dd>{historial?.length ?? '—'}</dd>
            </div>
          </dl>
          <button className="button outline" onClick={() => setVista('descargas')}>
            <Download size={16} />
            {tr('My downloads', 'Mis descargas')}
          </button>
          {user?.role === 'admin' && (
            <button className="button outline" onClick={() => setVista('auditoria')}>
              <FileClock size={16} />
              {tr('Audit log', 'Auditoría')}
            </button>
          )}
          <button className="button dark" onClick={salir} disabled={busy}>
            <LogOut size={16} />
            {tr('Sign out', 'Cerrar sesión')}
          </button>
        </div>
      ) : vista === 'auditoria' ? (
        <div className="dialog-body">
          <p>
            {tr(
              'Only the administrator role can read this record: who imported, synced or trained, and when.',
              'Solo el rol administrador lee este registro: quién importó, sincronizó o entrenó, y cuándo.',
            )}
          </p>
          {denegado ? (
            <p className="permission-state" role="alert">
              {denegado}
            </p>
          ) : !auditoria ? (
            <p role="status">{tr('Loading activity…', 'Consultando la actividad…')}</p>
          ) : auditoria.length === 0 ? (
            <p>
              {tr(
                'No operation has been recorded yet.',
                'Todavía no se ha registrado ninguna operación.',
              )}
            </p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr('Date', 'Fecha')}</th>
                    <th>{tr('Action', 'Acción')}</th>
                    <th>{tr('Target', 'Objeto')}</th>
                    <th>{tr('Detail', 'Detalle')}</th>
                  </tr>
                </thead>
                <tbody>
                  {auditoria.map((r) => (
                    <tr key={r.id}>
                      <td>{fecha(r.created_at)}</td>
                      <td>{r.action}</td>
                      <td>{r.target || '—'}</td>
                      <td>{r.detail || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <button className="text-link" onClick={() => setVista('perfil')}>
            {tr('Back to my profile', 'Volver a mi perfil')}
          </button>
        </div>
      ) : (
        <div className="dialog-body">
          {denegado ? (
            <p className="permission-state" role="alert">
              {denegado}
            </p>
          ) : !historial ? (
            <p role="status">{tr('Loading your history…', 'Consultando tu historial…')}</p>
          ) : historial.length === 0 ? (
            <p>
              {tr(
                'You have not downloaded anything yet. Export an analysis and it will be recorded here with its filters.',
                'Aún no has descargado nada. Exporta un análisis y quedará registrado aquí con sus filtros.',
              )}
            </p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>{tr('Date', 'Fecha')}</th>
                    <th>{tr('Kind', 'Tipo')}</th>
                    <th>{tr('Rows', 'Filas')}</th>
                    <th>{tr('Analysis', 'Análisis')}</th>
                  </tr>
                </thead>
                <tbody>
                  {historial.map((d) => (
                    <tr key={d.id}>
                      <td>{fecha(d.created_at)}</td>
                      <td>{d.kind}</td>
                      <td>{d.rows}</td>
                      <td>
                        <code>{d.analysis_id.slice(0, 10)}…</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <button className="text-link" onClick={() => setVista('perfil')}>
            {tr('Back to my profile', 'Volver a mi perfil')}
          </button>
        </div>
      )}
    </dialog>
  )
}
