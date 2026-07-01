# 🔍 Job Sentinel / Vigía de Empleo

[English](#english) · [Español](#español)

---

<a id="english"></a>

Automated job alert system with AI filtering. Runs every Monday, analyses listings with Claude, extracts the most in-demand skills, and sends a weekly email with relevant opportunities ranked by score.

---

## How it works

```
LinkedIn / Indeed / Climatebase
         │
         ▼
   Quick filter          ← discards internships, traineeships and irrelevant titles
         │
         ▼
  Flag target companies  ← 🎯 flag, no discard
         │
         ▼
   Deduplication
         │
         ▼
  Claude analysis        ← score 1-10 + red flag detection + skills extraction
         │
         ▼
  Weekly email           ← listings ranked by score + market skills table
         │
         ▼
  skills_tracker.json    ← updated in the repo automatically
```

---

## Customisation — the three files you need to edit

You don't need to touch the code. All configuration lives in three files:

### `perfil.txt` — Your professional profile

Write here who you are, your experience, and what you're looking for. Claude reads it to assess whether each listing fits you.

**How to edit it:** open it with any text editor (Notepad, VS Code, etc.) and write in natural language, as if it were a short CV. The more specific you are about your skills and constraints (e.g. "I can't relocate to London"), the better the filtering.

---

### `habilidades.yaml` — Your skills and current level

Define which technologies you know and where you stand. The system uses them to show, in each email, whether the skills the market requires are ones you already have or still need to learn.

```yaml
- nombre: Python
  nivel: consolidado    # consolidado | aprendiendo | pendiente
  aliases: [python]     # other names the skill might appear under in listings
```

**How to edit it:**
- Change `nivel` to `consolidado`, `aprendiendo`, or `pendiente` to reflect your real situation.
- If you learn a new skill, move it from `pendiente` to `aprendiendo` or `consolidado`.
- To add a skill not in the list:
  ```yaml
  - nombre: My New Skill
    nivel: aprendiendo
    aliases: [my new skill, another way to write it]
  ```


---

### `config.yaml` — Everything else

Controls platforms, searches, target companies, filters, and AI criteria.

#### Enable or disable platforms

```yaml
plataformas:
  linkedin: true
  indeed: true
  climatebase: false   # ← disable Climatebase
```

#### Change searches

```yaml
busquedas_linkedin_indeed:
  - ["Data Scientist energy", "Spain"]
  - ["Your target role", "Spain"]    # ← add or change lines
```

#### Add target companies

```yaml
empresas_objetivo:
  tier_1_maxima_prioridad:
    - google
    - your favourite company    # ← add here
```

#### Adjust the score threshold

```yaml
configuracion_general:
  puntuacion_minima: 4   # raise to receive fewer but better-matched results
```

#### Change AI penalties

Can you relocate? Don't mind a DevOps-heavy stack? Edit the `penalizaciones` section in `config.yaml` to suit your situation:

```yaml
penalizaciones:
  # Remove the city line if you can go on-site:
  # - "Location [city] without mention of remote/hybrid: -2"
  - "Requires >5 years of specific DS/ML experience: -2"
  ...
```

#### Customise the sector axes

`criterios_ia` → `ejes` groups listings by sector. The axes shipped here (`principal`, `secundario_a`, `secundario_b`) are **examples** — rename them and rewrite their descriptions to match the sectors you target. Keep `otros`: it's the catch-all, intentionally penalised so off-target roles score lower.

---

## Initial setup

### 1. Clone and prepare

```bash
git clone https://github.com/YOUR_USERNAME/vigia-de-empleo.git
cd vigia-de-empleo
pip install -r requirements.txt
```

### 2. Edit the configuration files

1. Open `perfil.txt` and write your profile.
2. Open `habilidades.yaml` and adjust your levels.
3. Open `config.yaml` and customise the searches, companies, and filters.

### 3. Claude API key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an API key
3. The system uses `claude-haiku` by default — approximate cost of **€0.02–0.05 per weekly run**

> You can change the model in `config.yaml` → `configuracion_general` → `modelo_ia`.

### 4. Set up Gmail for automated sending

Gmail requires an **App Password** for SMTP sending:

1. Enable [two-step verification](https://myaccount.google.com/security)
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a password for "Mail" (16 characters)
4. Save it — it's only shown once

### 5. GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | The 16-character App Password |
| `DESTINATARIO_EMAIL` | Email where you'll receive alerts |

> ⚠️ Never put keys directly in the code or configuration files.

### 6. Workflow permissions

To allow the pipeline to update `skills_tracker.json` in the repo:

**Settings → Actions → General → Workflow permissions → Read and write permissions** ✅

### 7. Test manually

**GitHub → Actions → Vigía de Empleo Semanal → Run workflow**

Or locally:

```bash
export ANTHROPIC_API_KEY="your_key"
export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="your_app_password"
export DESTINATARIO_EMAIL="you@gmail.com"

python job_alert.py
```

Without environment variables configured, the script saves the result as `email_preview.html`.

> **Real-time logs:** in GitHub Actions, Python buffers stdout, so the progress counter may appear in bursts or look frozen even when the run is fine. To see each line live, run `python -u job_alert.py` (or set `PYTHONUNBUFFERED: "1"` under the workflow's `env`).

---

## Skills tracker and dashboard

The system automatically extracts technical skills from each analysed listing and accumulates them in `skills_tracker.json`. This lets you:

- See which technologies appear most in the market week by week.
- Identify the gap between what the market demands and your current level.

To visualise it, open `skills_dashboard.html` in the browser and load `skills_tracker.json` with the upload button.

---

## Changing the schedule

In `.github/workflows/weekly_job_alert.yml`:

```yaml
- cron: '0 3 * * 1'   # Monday 08:00 CET (03:00 UTC)
# '0 3 * * 2'         → Tuesday
# '0 3 * * 1,4'       → Monday and Thursday
```

---

## Project structure

```
vigia-de-empleo/
├── config.yaml                    # ← EDIT: platforms, searches, companies, filters, AI
├── perfil.txt                     # ← EDIT: your professional profile
├── habilidades.yaml               # ← EDIT: your skills and levels
├── .github/
│   └── workflows/
│       └── weekly_job_alert.yml   # Weekly automation
├── scrapers/
│   └── climatebase.py             # Climatebase scraper (do not edit)
├── job_alert.py                   # Main script (do not edit)
├── skills_tracker.json            # Skills history (updated every Monday)
├── skills_dashboard.html          # Interactive skills tracker visualisation
├── migrate_skills_tracker.py      # Migration tool (advanced use)
├── requirements.txt
└── README.md
```

---

## Notes on scraping

The system uses [JobSpy](https://github.com/Bunsly/JobSpy) to access LinkedIn and Indeed. LinkedIn detects aggressive scraping — the script includes pauses between searches to minimise blocks. If LinkedIn starts failing consistently, Indeed continues to work independently. You can disable LinkedIn in `config.yaml` if it causes problems.

---

## Red flag detection

Claude doesn't just score technical fit — it also detects warning signs in the description:

- Non-existent data teams (*"you'll be the first data person"*, *"you'll report to the CTO"*)
- *"do-everything"* roles without clear specialisation
- Unstructured environments (*"we value autonomy and initiative"*)

Alerts appear marked with ⚠️ in the email. You can customise what alerts Claude looks for in `config.yaml` → `criterios_ia` → `senales_alerta`.

---

*Last updated: June 2026*

---

<a id="español"></a>

# 🔍 Vigía de Empleo

Sistema automatizado de alertas de empleo con filtrado por IA. Se ejecuta cada lunes, analiza las ofertas con Claude, extrae los skills más demandados y envía un email con las oportunidades relevantes ordenadas por puntuación.

---

## ¿Cómo funciona?

```
LinkedIn / Indeed / Climatebase
         │
         ▼
   Filtro rápido          ← descarta becas, prácticas y títulos irrelevantes
         │
         ▼
  Marca empresas objetivo ← flag 🎯, no descarta
         │
         ▼
   Deduplicación
         │
         ▼
  Análisis con Claude     ← puntuación 1-10 + detección de red flags + extracción de skills
         │
         ▼
  Email semanal           ← ofertas ordenadas por puntuación + tabla de skills del mercado
         │
         ▼
  skills_tracker.json     ← se actualiza en el repo automáticamente
```

---

## Personalización — los tres archivos que debes editar

No necesitas tocar el código. Toda la configuración está en tres archivos:

### `perfil.txt` — Tu perfil profesional

Escribe aquí quién eres, tu experiencia y qué buscas. Claude lo lee para evaluar si cada oferta encaja contigo.

**Cómo editarlo:** ábrelo con cualquier editor de texto (Bloc de notas, VS Code, etc.) y escribe en lenguaje natural, como si fuera un breve currículum. Cuanto más específico seas sobre tus habilidades y restricciones (p. ej. "no me puedo mudar a Madrid"), mejor será el filtrado.

---

### `habilidades.yaml` — Tus skills y nivel actual

Define qué tecnologías conoces y en qué punto estás. El sistema las usa para mostrarte, en cada email, si las skills que pide el mercado ya las tienes o aún te quedan por aprender.

```yaml
- nombre: Python
  nivel: consolidado    # consolidado | aprendiendo | pendiente
  aliases: [python]     # otros nombres con que puede aparecer en ofertas
```

**Cómo editarlo:**
- Cambia `nivel` a `consolidado`, `aprendiendo` o `pendiente` según tu situación real.
- Si aprendes una skill nueva, cámbiala de `pendiente` a `aprendiendo` o `consolidado`.
- Para añadir una skill que no está en la lista:
  ```yaml
  - nombre: Mi Nueva Skill
    nivel: aprendiendo
    aliases: [mi nueva skill, otra forma de escribirlo]
  ```

---

### `config.yaml` — Todo lo demás

Controla las plataformas, las búsquedas, las empresas de interés, los filtros y los criterios de la IA.

#### Activar o desactivar plataformas

```yaml
plataformas:
  linkedin: true
  indeed: true
  climatebase: false   # ← desactivar Climatebase
```

#### Cambiar las búsquedas

```yaml
busquedas_linkedin_indeed:
  - ["Data Scientist energy", "Spain"]
  - ["Tu rol objetivo", "Spain"]    # ← añade o cambia líneas
```

#### Añadir empresas de interés

```yaml
empresas_objetivo:
  tier_1_maxima_prioridad:
    - google
    - tu empresa favorita    # ← añade aquí
```

#### Ajustar el umbral de puntuación

```yaml
configuracion_general:
  puntuacion_minima: 4   # sube para recibir menos pero más ajustadas
```

#### Cambiar las penalizaciones de la IA

¿Puedes moverte a Madrid? ¿No te importa el stack DevOps? Edita la sección `penalizaciones` en `config.yaml` para adaptarla a tu situación:

```yaml
penalizaciones:
  # Elimina la línea de Madrid si puedes ir presencial:
  # - "Ubicación Madrid sin mención de remoto/híbrido: -2"
  - "Requiere >5 años de experiencia específica en DS/ML puro: -2"
  ...
```

#### Personalizar los ejes sectoriales

`criterios_ia` → `ejes` agrupa las ofertas por sector. Los ejes que vienen de serie (`principal`, `secundario_a`, `secundario_b`) son **ejemplos**: renómbralos y reescribe sus descripciones según los sectores que te interesen. Conserva `otros`: es el cajón de sastre y se penaliza a propósito para que las ofertas fuera de foco puntúen más bajo.

---

## Configuración inicial

### 1. Clonar y preparar

```bash
git clone https://github.com/TU_USUARIO/vigia-de-empleo.git
cd vigia-de-empleo
pip install -r requirements.txt
```

### 2. Editar los archivos de configuración

1. Abre `perfil.txt` y escribe tu perfil.
2. Abre `habilidades.yaml` y ajusta tus niveles.
3. Abre `config.yaml` y personaliza las búsquedas, empresas y filtros.

### 3. API key de Claude

1. Ve a [console.anthropic.com](https://console.anthropic.com)
2. Crea una API key
3. El sistema usa `claude-haiku` por defecto — coste aproximado de **0.02–0.05 € por ejecución semanal**

> Puedes cambiar el modelo en `config.yaml` → `configuracion_general` → `modelo_ia`.

### 4. Configurar Gmail para envío automático

Gmail requiere una **App Password** para envío por SMTP:

1. Activa la [verificación en dos pasos](https://myaccount.google.com/security)
2. Ve a [App Passwords](https://myaccount.google.com/apppasswords)
3. Genera una contraseña para "Mail" (16 caracteres)
4. Guárdala — solo se muestra una vez

### 5. Secrets en GitHub

**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|--------|-------|
| `ANTHROPIC_API_KEY` | Tu API key de Anthropic |
| `GMAIL_ADDRESS` | Tu dirección de Gmail |
| `GMAIL_APP_PASSWORD` | Los 16 caracteres del App Password |
| `DESTINATARIO_EMAIL` | Email donde recibirás las alertas |

> ⚠️ Nunca pongas claves directamente en el código ni en los archivos de configuración.

### 6. Permisos del workflow

Para que el pipeline pueda actualizar `skills_tracker.json` en el repo:

**Settings → Actions → General → Workflow permissions → Read and write permissions** ✅

### 7. Probar manualmente

**GitHub → Actions → Vigía de Empleo Semanal → Run workflow**

O en local:

```bash
export ANTHROPIC_API_KEY="tu_key"
export GMAIL_ADDRESS="tu@gmail.com"
export GMAIL_APP_PASSWORD="tu_app_password"
export DESTINATARIO_EMAIL="tu@gmail.com"

python job_alert.py
```

Sin variables de entorno configuradas, el script guarda el resultado como `email_preview.html`.

> **Logs en tiempo real:** en GitHub Actions, Python almacena la salida en un búfer, así que el contador de progreso puede aparecer a ráfagas o parecer congelado aunque la ejecución vaya bien. Para ver cada línea al instante, ejecuta `python -u job_alert.py` (o pon `PYTHONUNBUFFERED: "1"` en el `env` del workflow).

---

## Skills tracker y dashboard

El sistema extrae automáticamente los skills técnicos de cada oferta analizada y los acumula en `skills_tracker.json`. Esto permite:

- Ver qué tecnologías aparecen más en el mercado semana a semana.
- Identificar el gap entre lo que pide el mercado y tu nivel actual.

Para visualizarlo, abre `skills_dashboard.html` en el navegador y carga el archivo `skills_tracker.json` con el botón de carga.

---

## Cambiar el horario de ejecución

En `.github/workflows/weekly_job_alert.yml`:

```yaml
- cron: '0 3 * * 1'   # Lunes 08:00 CET (03:00 UTC)
# '0 3 * * 2'         → Martes
# '0 3 * * 1,4'       → Lunes y jueves
```

---

## Estructura del proyecto

```
vigia-de-empleo/
├── config.yaml                    # ← EDITA: plataformas, búsquedas, empresas, filtros, IA
├── perfil.txt                     # ← EDITA: tu perfil profesional
├── habilidades.yaml               # ← EDITA: tus skills y niveles
├── .github/
│   └── workflows/
│       └── weekly_job_alert.yml   # Automatización semanal
├── scrapers/
│   └── climatebase.py             # Scraper de Climatebase (no tocar)
├── job_alert.py                   # Script principal (no tocar)
├── skills_tracker.json            # Histórico de skills (actualizado cada lunes)
├── skills_dashboard.html          # Visualización interactiva del skills tracker
├── migrate_skills_tracker.py      # Herramienta de migración (uso avanzado)
├── requirements.txt
└── README.md
```

---

## Notas sobre scraping

El sistema usa [JobSpy](https://github.com/Bunsly/JobSpy) para acceder a LinkedIn e Indeed. LinkedIn detecta scraping agresivo — el script incluye pausas entre búsquedas para minimizar bloqueos. Si LinkedIn empieza a fallar consistentemente, Indeed sigue funcionando de forma independiente. Puedes desactivar LinkedIn en `config.yaml` si da problemas.

---

## Detección de red flags

Claude no solo puntúa el encaje técnico — también detecta señales de alerta en la descripción:

- Equipos de datos inexistentes (*"serás el primero en datos"*, *"reportarás al CTO"*)
- Roles de *"para todo"* sin especialización clara
- Entornos sin estructura (*"buscamos autonomía e iniciativa"*)

Las alertas aparecen marcadas con ⚠️ en el email. Puedes personalizar qué alertas busca Claude en `config.yaml` → `criterios_ia` → `senales_alerta`.

---

*Última actualización: junio 2026*
