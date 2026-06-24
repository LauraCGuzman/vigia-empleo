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

> **Nota:** El dashboard de skills (`skills_dashboard.html`) tiene su propia copia de los niveles en el código JavaScript. Si cambias niveles en `habilidades.yaml`, recuerda también actualizarlos en el dashboard para que coincidan.

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
    - iberdrola
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
