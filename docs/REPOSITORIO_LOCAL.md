# Repositorio local en nasa_app

La raíz de trabajo es `C:\Users\david\vscode_projects\nasa_app`. Contiene `.git`, está conectada a `https://github.com/Abraham-ch/Nina.git` y utiliza la rama local `mvp`, con seguimiento de `origin/mvp`.

## Organización

| Ruta desde la raíz | Uso |
|---|---|
| `mvp/` | Aplicación funcional, scripts, pruebas y documentación del MVP |
| `apps/`, `packages/`, `infra/`, `docs/` | Estructura del monorepo conservada desde GitHub |
| `start-nina.ps1`, `setup-nina.ps1` | Arranque e instalación desde la raíz |
| `mvp/.venv/` | Entorno Python 3.14 del MVP, creado con sus dependencias fijadas |
| `.venv/` | Entorno independiente del monorepo, administrado por `uv` |
| `.env` | Credenciales y configuración local, excluidas de Git |
| `data/` | Base, archivos procesados y cachés existentes, excluidos de Git |
| `data_abraham/` | Archivos FIRMS aportados por el equipo, excluidos de Git |
| `.nina-qa/` | Verificaciones y respaldo del traslado, excluidos de Git |

Las rutas relativas de `NINA_DATA_DIR` se resuelven desde la raíz del repositorio. La aplicación carga `.env` de la raíz; un `.env` dentro de `mvp/`, si existe, puede sobrescribir esa configuración. En el contenedor independiente se mantiene la raíz `/app`.

Los entornos se separaron porque el monorepo selecciona Python 3.12, mientras que el MVP se preparó con Python 3.14. Los lanzadores llaman directamente a `mvp/.venv/Scripts/python.exe`, independientemente del entorno activado en la terminal. Para activar manualmente el entorno del MVP: `.\mvp\.venv\Scripts\Activate.ps1`.

## Trabajo desde PowerShell

```powershell
cd C:\Users\david\vscode_projects\nasa_app
git status
git branch
.\start-nina.ps1
```

Una instalación nueva se prepara con `setup-nina.ps1`. El servicio se detiene con Ctrl+C. Desde la raíz, `docker compose up --build` utiliza el contexto `mvp/` y monta `data/`; esta alternativa requiere el motor Docker y no se declara probada por el traslado.

## Integración de ramas

La rama local antigua `mvp` (`b998040`) contenía el mismo árbol `mvp/` que el commit posterior `1f2aa14`. La rama publicada agregó después las correcciones del atlas (`9dcdb56`). Se integraron ambas historias mediante un merge, conservando las correcciones posteriores en los conflictos de archivos añadidos en ambas ramas. No se reescribió el historial remoto.

Los cambios locales de consultas con memoria acotada, exportación por bloques e importación mundial se conservaron en `mvp/`. La base parcial `data/world-build/` y los originales de `data_abraham/` se mantuvieron en su ubicación. Este traslado no termina la ingesta mundial ni valida la armonización científica.

El antiguo directorio `.nina-qa/mvp-repo` se conserva como respaldo de archivos; su metadato Git se archiva para que la única raíz Git activa del workspace sea `nasa_app`. Los respaldos no se publican.

## Comprobaciones del traslado

- Las consultas y exportaciones del MVP pasaron sus 28 pruebas locales.
- La interfaz compiló desde `mvp/web/`.
- El monorepo completó sus nueve tareas de lint y tipos. La fase actual no define una tarea `test` en Turborepo.
- Los cuatro lanzadores PowerShell tienen sintaxis válida y el lanzador de la raíz inicia el servicio.
- La API local y la página principal respondieron correctamente; la base conservó sus 2.108.030 observaciones.
- Los archivos preparados para Git se revisaron para excluir credenciales; los originales, las bases y los respaldos permanecen ignorados.

El traslado y la integración de ramas se guardan en commits locales. No implican publicación de datos ni un push automático a GitHub.
