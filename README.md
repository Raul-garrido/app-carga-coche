# Calculadora de coste de carga (MyAudi + Policharger)

PWA personal para calcular el coste real de cada carga de un híbrido
enchufable, combinando el % de batería (MyAudi) con los kWh reportados por
el cargador (Policharger), que no se comunican entre sí ni calculan coste
en euros.

## Cómo abrirla

**En el móvil, sin instalar nada:** abre este enlace en el navegador —

**https://raul-garrido.github.io/app-carga-coche/**

(la publica automáticamente GitHub Pages en cuanto se sube código a este
repositorio; ver `.github/workflows/deploy-pages.yml`). Luego, en el menú
del navegador, "Añadir a pantalla de inicio" (Safari/iOS) o "Instalar
aplicación" (Chrome/Android) para tenerla como un icono más, a pantalla
completa y sin barra de navegador.

Esta versión funciona **sin ningún servidor**: todo (el % de batería, el
precio, las sesiones y el historial) se guarda en el propio navegador del
móvil. Si limpias los datos del navegador o cambias de móvil, se pierde el
historial — es una app de un solo dispositivo, no una cuenta en la nube.

## Estado

- ✅ Lógica de cálculo (kWh cargados/restantes, coste estimado, coste de
  sesión en tiempo real) — probada con `pytest` (Python) y verificada
  también en su versión JS (`frontend/js/calculator.js`).
- ✅ PWA instalable, con entrada manual tanto para el % (MyAudi) como para
  los kWh de sesión (Policharger) — probada de punta a punta con
  Playwright, incluida la persistencia tras recargar la página.
- ⚠️ Integración automática con MyAudi: módulo aislado ya montado
  (`backend/app/integrations/myaudi_source.py`), pero **sin probar contra
  una cuenta real** — requiere tus credenciales y validar la API exacta de
  `audiconnectpy` antes de activarla. Solo disponible en el modo
  autoalojado (ver abajo), no en la versión de GitHub Pages.
- ❌ Integración automática con Policharger: no viable en un tiempo
  razonable (sin API pública). Queda como entrada manual, por diseño.

## Dos formas de ejecutarla

### 1. GitHub Pages (recomendada, la de arriba)

No hace falta hacer nada: cualquier cambio subido a este repo se publica
solo en unos minutos en la URL de arriba. Es 100% estática (HTML/CSS/JS),
sin backend, con los datos en el propio navegador.

### 2. Autoalojada (avanzado — solo si más adelante quieres MyAudi automático)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m pytest                       # corre la lógica de cálculo + API
uvicorn app.main:app --reload --port 8000
```

Abre `http://localhost:8000` — sirve la PWA y la API (FastAPI + SQLite)
desde el mismo servidor. La propia app detecta sola si hay backend
disponible (`frontend/js/api.js:detectApi()`): si lo hay, usa esa API en
vez del almacenamiento del navegador, para tener los datos centralizados y
dejar sitio a la integración automática de MyAudi.

## Uso

1. Introduce el % que marca MyAudi.
2. Introduce el precio €/kWh y el objetivo de carga (%) → verás el coste
   estimado para completar la carga, sin necesidad de iniciar nada.
3. Pulsa "Iniciar sesión" al enchufar el coche. Cada vez que mires
   Policharger, escribe el total de kWh que marca y pulsa "Añadir
   lectura" — el coste acumulado se actualiza al momento.
4. Al desenchufar, pulsa "Finalizar sesión" (con el % final si lo sabes).
   Queda guardada en el historial.

## Activar MyAudi automático (experimental, no probado, solo modo autoalojado)

```bash
pip install -r requirements-myaudi.txt
cp .env.example .env   # rellena MYAUDI_USERNAME / MYAUDI_PASSWORD / MYAUDI_SPIN
# y pon MYAUDI_AUTO_ENABLED=true
```

Antes de confiar en esto: lee los avisos en
`backend/app/integrations/myaudi_source.py` sobre rate limiting y los
fallos de login reportados en 2026. Si falla, la app cae automáticamente a
pedirte el % a mano — no debería romper nada más.

## Estructura

Ver el árbol completo en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), que
también recoge la investigación previa sobre las integraciones con MyAudi
y Policharger.

```
backend/               API FastAPI + lógica de cálculo + SQLite (modo autoalojado)
frontend/               PWA (HTML/CSS/JS vanilla) — esto es lo que sirve GitHub Pages
.github/workflows/      despliegue automático a GitHub Pages
docs/                   decisiones de arquitectura e investigación
```
