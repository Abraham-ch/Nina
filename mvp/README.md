# NINA · MVP local

Aplicación para explorar detecciones de fuego de NASA FIRMS: API FastAPI, interfaz React/TypeScript con Cesium y base analítica DuckDB. Versión 0.2.0.

Esta carpeta contiene una aplicación independiente del monorepo de la raíz. Ejecuta los comandos desde `Nina/mvp`.

La versión final incorpora lecturas consistentes durante la ingesta, actualización espacial de productos estándar y provisionales, orientación del asistente por rol y cartografía mundial validada. El visor, el calendario, la comparación y el experimento comparten territorio y período.

El [estado de la versión 0.2](ESTADO_V2.md) documenta las funciones y comprobaciones de la entrega. Sus cifras de observaciones corresponden al entorno donde se descargaron los datos; cada clon empieza con una base vacía y genera sus propios resultados.

## Obtener el proyecto

```bash
git clone --branch mvp --single-branch https://github.com/Abraham-ch/Nina.git
cd Nina/mvp
```

## Windows

Requisitos: Python 3.14 y Node.js 22 con npm disponibles en PATH. La instalación necesita Internet.

```powershell
.\setup-nina.ps1
.\start-nina.ps1
```

Abrir http://127.0.0.1:8000. La primera ejecución crea una base vacía: el visor abre, pero las consultas muestran datos no disponibles hasta importar o descargar observaciones. No se incorporan datos simulados.

Para preparar también el histórico público de Perú, detener el servidor y ejecutar:

```powershell
.\setup-nina.ps1 -DownloadData
.\start-nina.ps1
```

La descarga no requiere credenciales. Obtiene los archivos anuales que publica FIRMS, verifica tamaño y SHA-256, importa las detecciones y entrena modelos exploratorios. Puede tardar y necesita espacio para CSV, Parquet y DuckDB; se puede repetir para reanudar los archivos pendientes.

Si PowerShell bloquea los scripts, los pasos manuales son:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
npm.cmd --prefix web ci
npm.cmd --prefix web run build
.\.venv\Scripts\python.exe -m uvicorn nina.main:app --host 127.0.0.1 --port 8000
```

## Linux o macOS

Con Python 3.14 y Node.js 22 instalados:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
npm --prefix web ci
npm --prefix web run build
python -m uvicorn nina.main:app --host 127.0.0.1 --port 8000
```

Para incorporar el histórico y el modelo, detener el servidor y ejecutar con el entorno activado:

```bash
python scripts/bootstrap_data.py
python -m nina.ingest
python -m nina.science
```

## Docker

Con Docker y su motor en ejecución, desde esta carpeta:

```bash
docker compose up --build
```

Abrir http://127.0.0.1:8000. Los datos se conservan en `./data`, montado como volumen. El contenedor también arranca con una base vacía.

Para preparar el histórico, detener el servidor antes de importar:

```bash
docker compose down
docker compose run --rm nina python scripts/bootstrap_data.py
docker compose run --rm nina python -m nina.ingest
docker compose run --rm nina python -m nina.science
docker compose up
```

Usar una sola instancia de la API. DuckDB y la cola de trabajos son locales; no ejecutar importaciones o entrenamiento desde otro proceso mientras el servidor esté abierto.

## Configuración opcional

Copiar `.env.example` a `.env` dentro de esta carpeta. Las variables pueden quedar vacías para abrir la app e importar el histórico público.

| Variable | Uso |
| --- | --- |
| `FIRMS_MAP_KEY` | Descargas recientes y mensuales desde la API FIRMS. |
| `NINA_LLM_BASE_URL`, `NINA_LLM_API_KEY`, `NINA_LLM_MODEL` | Proveedor opcional compatible con Chat Completions. Sin ellos, el asistente responde con evidencia local. |
| `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` | Reservadas para futuras descargas científicas L2; el MVP no las procesa. |
| `NINA_DATA_DIR` | Carpeta de almacenamiento local; por defecto `data`. El descargador del histórico y Compose utilizan `./data`. |

Reiniciar el servidor después de cambiar `.env`. Las credenciales permanecen en el servidor y no se incluyen en Git.

## API y desarrollo

- API interactiva: http://127.0.0.1:8000/docs.
- Estado: http://127.0.0.1:8000/api/health.
- Contrato de los 22 endpoints: [openapi.json](openapi.json), importable en Postman.
- Regenerar el contrato: `python scripts/export_openapi.py` con el entorno virtual activado.

La API de esta aplicación usa el prefijo `/api`. El contrato `apps/api/API_CONTRACT.md` de la raíz pertenece al servicio del monorepo.

Para desarrollar la interfaz, mantener la API abierta y ejecutar en otra terminal:

```bash
npm --prefix web run dev
```

Vite sirve la web en http://127.0.0.1:5173 y reenvía `/api` al backend en el puerto 8000. `127.0.0.1` corresponde a la computadora de cada desarrollador.

Verificar la copia en Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.nina-qa/pytest-local
npm.cmd --prefix web run build
```

En Linux/macOS, con el entorno activado, usar `python -m pytest -q --basetemp=.nina-qa/pytest-local` y `npm --prefix web run build`. Las pruebas usan datos pequeños en directorios temporales separados.

Con el servidor detenido y el entorno activado, `python scripts/verify_v2.py --refresh-parquet` comprueba los hashes de los archivos importados y actualiza el snapshot Parquet. Su resultado se guarda localmente en `data/release-v0.2.json`. `python scripts/validate_geography.py` valida y normaliza la cartografía de países incluida; si se modifica, volver a compilar la interfaz.

## Contenido y alcance

Se incluyen código, dependencias fijadas, scripts de instalación, pruebas y cartografía de referencia con su procedencia. Los CSV descargados, base DuckDB, resultados de modelos, exportaciones, dependencias instaladas, compilados y credenciales se generan localmente y están excluidos de Git.

El histórico público se descarga para Perú. Las adquisiciones globales o por área dependen de `FIRMS_MAP_KEY` y de la disponibilidad verificada del producto y las fechas. La aplicación distingue las observaciones de cada instrumento y muestra períodos sin datos como no disponibles. Los meses se agrupan en UTC.

Los modelos son calibraciones exploratorias de conteos mensuales; no constituyen una armonización científica validada ni una estimación de fuego no observado. Las detecciones son píxeles térmicos, no incendios individuales ni superficie quemada.

Datos: NASA FIRMS, LANCE y ESDIS. Propuesta independiente sin respaldo de NASA. FIRMS no recomienda estos datos para decisiones tácticas o a escala local. Consultar las [fuentes y cita de FIRMS](https://www.earthdata.nasa.gov/data/tools/firms) y sus [limitaciones](https://www.earthdata.nasa.gov/data/tools/firms/faq).

La cartografía mundial procede de Natural Earth 110m y la imagen de referencia de NASA GIBS; sus atribuciones están en `web/public/assets/attribution.json`. Los límites regionales de Perú proceden de geoBoundaries gbOpen, representación de 2008 y dominio público, con procedencia en `data/boundaries/provenance.json`; son una referencia generalizada.
