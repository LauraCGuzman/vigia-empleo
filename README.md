# 🔍 Vigía de Empleo

Sistema automatizado de alertas de empleo con filtrado por IA. Se ejecuta cada lunes, analiza las ofertas con Claude, extrae los skills más demandados del mercado y envía un email con las oportunidades relevantes ordenadas por puntuación.

---

## ¿Cómo funciona?

```
JobSpy (LinkedIn + Indeed)
         │
         ▼
   Filtro rápido          ← descarta becas, títulos irrelevantes
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
  skills_tracker.json     ← se actualiza en el repo automáticamente (mantiene el cron activo)
```

---

## Configuración inicial

### 1. Clonar y preparar

```bash
git clone https://github.com/TU_USUARIO/vigia-de-empleo.git
cd vigia-de-empleo
pip install -r requirements.txt
```

### 2. Editar `config.yaml`

**Este es el único archivo que necesitas tocar.** Abre `config.yaml` y personaliza:

- `perfil` — tu experiencia, stack técnico y restricciones de ubicación
- `busquedas` — los roles y ubicaciones que quieres monitorizar
- `empresas_objetivo` — empresas que aparecerán destacadas con 🎯
- `exclusiones` — palabras que descartan ofertas automáticamente
- `mis_skills` — tu nivel actual en cada tecnología (`yes` / `learning` / `no`)

### 3. API key de Claude

1. Ve a [console.anthropic.com](https://console.anthropic.com)
2. Crea una API key
3. El sistema usa `claude-haiku` — coste aproximado de **0.02–0.05 € por ejecución semanal**

> ℹ️ Se probó con la API gratuita de Gemini pero presentó problemas de compatibilidad y cuotas. Claude Haiku es la opción recomendada por estabilidad y coste.

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

> ⚠️ Nunca pongas claves directamente en el código ni en `config.yaml`.

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

## Skills tracker

El sistema extrae automáticamente los skills técnicos de cada oferta analizada y los acumula en `skills_tracker.json`. Esto permite:

- Ver qué tecnologías pide el mercado semana a semana
- Identificar el gap entre lo que pide el mercado y tu nivel actual
- Seguir la evolución a lo largo del tiempo

Para visualizarlo, abre `skills_dashboard.html` en el navegador y carga `skills_tracker.json`.

**Para actualizar tu nivel** a medida que aprendes, edita `mis_skills` en `config.yaml`:

```yaml
mis_skills:
  Python: "yes"       # consolidado — lo pones en el CV sin problema
  SQL: "learning"     # en curso
  TensorFlow: "no"    # pendiente
```

El dashboard actualiza los colores y el porcentaje de gap automáticamente.

---

## Personalización avanzada

Todo lo habitual se hace en `config.yaml`. Para ajustes de lógica de puntuación (criterios de scoring, penalizaciones, umbral de corte), edita directamente `job_alert.py` — los comentarios indican dónde:

```python
# En main(): umbral de puntuación mínima para incluir una oferta
if analysis.get("puntuacion", 5) >= 4:   # sube si recibes demasiadas ofertas
```

```python
# En analizar_con_claude(): criterios del prompt de evaluación
# Personaliza las penalizaciones según tu situación
```

### Cambiar el horario

En `.github/workflows/weekly_job_alert.yml`:

```yaml
- cron: '0 7 * * 1'  # Lunes 08:00 CET (07:00 UTC)
# '0 7 * * 2'   → Martes
# '0 7 * * 1,4' → Lunes y jueves
```

---

## Detección de red flags

Claude no solo puntúa el encaje técnico — también detecta señales de alerta en la descripción:

- Equipos de datos inexistentes (*"serás el primero en datos"*, *"reportarás al CTO"*)
- Roles de *"para todo"* sin especialización clara
- Entornos sin estructura (*"buscamos autonomía e iniciativa"*)
- Stack caótico o proyectos heredados sin documentar

Las alertas aparecen marcadas con ⚠️ en el email.

---

## Notas sobre scraping

El sistema usa [JobSpy](https://github.com/Bunsly/JobSpy) para acceder a LinkedIn e Indeed. LinkedIn detecta scraping agresivo — el script incluye pausas entre búsquedas para minimizar bloqueos. Si LinkedIn empieza a fallar consistentemente, Indeed sigue funcionando de forma independiente.

---

## Estructura del proyecto

```
vigia-de-empleo/
├── .github/
│   └── workflows/
│       └── weekly_job_alert.yml   # Automatización semanal + commit automático
├── config.yaml                    # ← Edita esto. Tu perfil, búsquedas, skills.
├── job_alert.py                   # Script principal (no necesitas tocarlo)
├── skills_tracker.json            # Histórico de skills (actualizado cada lunes)
├── skills_dashboard.html          # Visualización interactiva del skills tracker
├── requirements.txt
└── README.md
```

---

*Última actualización: abril 2026*
