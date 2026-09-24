# Calculadora de coste de carga (MyAudi + Policharger)

PWA personal para calcular el coste real de cada carga de un híbrido
enchufable, combinando el % de batería (MyAudi) con los kWh reportados por
el cargador (Policharger), que no se comunican entre sí ni calculan coste
en euros.

Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para la investigación
previa sobre las dos integraciones y las decisiones de diseño.

## Estado

- ✅ Lógica de cálculo (kWh cargados/restantes, coste estimado, coste de
  sesión en tiempo real) — probada con `pytest`.
- ✅ API (FastAPI) + PWA (HTML/CSS/JS vanilla, instalable) usando entrada
  manual tanto para el % (MyAudi) como para los kWh de sesión
  (Policharger).
- ⚠️ Integración automática con MyAudi: módulo aislado ya montado
  (`backend/app/integrations/myaudi_source.py`), pero **sin probar contra
  una cuenta real** — requiere tus credenciales y validar la API exacta de
  `audiconnectpy` antes de activarla.
- ❌ Integración automática con Policharger: no viable en un tiempo
  razonable (sin API pública). Queda como entrada manual, por diseño.

## Poner en marcha

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python3 -m pytest                       # corre la lógica de cálculo + API
uvicorn app.main:app --reload --port 8000
```

Abre `http://localhost:8000` — sirve la PWA y la API desde el mismo
servidor. Desde el móvil, en la misma red, usa la IP del ordenador y
"Añadir a pantalla de inicio" para instalarla.

## Uso

1. Introduce el % que marca MyAudi.
2. Introduce el precio €/kWh y el objetivo de carga (%) → verás el coste
   estimado para completar la carga, sin necesidad de iniciar nada.
3. Pulsa "Iniciar sesión" al enchufar el coche. Cada vez que mires
   Policharger, escribe el total de kWh que marca y pulsa "Añadir
   lectura" — el coste acumulado se actualiza al momento.
4. Al desenchufar, pulsa "Finalizar sesión" (con el % final si lo sabes).
   Queda guardada en el historial.

## Activar MyAudi automático (experimental, no probado)

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

Ver el árbol completo en [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```
backend/   API FastAPI + lógica de cálculo + persistencia SQLite
frontend/  PWA (HTML/CSS/JS vanilla), instalable en el móvil
docs/      decisiones de arquitectura e investigación
```
