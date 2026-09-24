# Arquitectura y decisiones

## Despliegue: por qué la app corre sin servidor por defecto

El plan inicial preveía un backend ligero (Node o Python) para todo,
principalmente para no exponer las credenciales de MyAudi en el cliente.
Al pedir "cómo lo abro / hazlo tú" para publicarla, la limitación real es
que solo hay forma de desplegar **contenido estático** sin depender de
cuentas externas que no puedo crear en tu nombre (Render, Railway, un VPS,
etc.): GitHub Pages. Un backend Python no se puede ejecutar ahí.

Por eso `frontend/js/api.js` implementa dos versiones detrás de la misma
interfaz `Api`, elegidas en `detectApi()` al arrancar:

- `createNetworkApi()` — llama a `/api/...` (el backend FastAPI de
  `backend/`). Se usa automáticamente si ese backend responde.
- `createLocalApi()` — mismo cálculo (`frontend/js/calculator.js`, un
  port directo de `backend/app/calculator.py`), pero guardando config,
  estado de batería y sesiones en `localStorage` en vez de SQLite. Se usa
  cuando no hay backend (caso de GitHub Pages).

`detectApi()` simplemente prueba `fetch("api/config")`: si responde,
backend; si no, local. El resto de la app (`app.js`, `index.html`) no sabe
ni le importa cuál de las dos está activa.

Consecuencia: el backend de `backend/` sigue existiendo tal cual se montó
(SQLite, sesiones, el módulo aislado de MyAudi) para cuando quieras
autoalojarlo — pero la versión publicada en GitHub Pages nunca lo toca, y
por tanto tampoco puede usar la integración automática de MyAudi (que
necesita un servidor para guardar credenciales con seguridad). Si algún
día se activa esa integración, tendría sentido en el modo autoalojado, no
en el estático.

## Investigación previa (resumen)

### MyAudi — viable, pero hay que tratarla como frágil

- La API no oficial (`audiconnectpy`, paquete PyPI mantenido activamente y
  usado por la integración `audi_connect_ha` de Home Assistant) es la vía
  más razonable: implementa el flujo OAuth2/OIDC de 13 pasos por nosotros,
  en lugar de tener que reimplementarlo desde cero a partir de
  [Grudesky/myaudi-api](https://github.com/Grudesky/myaudi-api) o
  [audiconnect/audi_connect_ha](https://github.com/audiconnect/audi_connect_ha).
- Riesgos confirmados por los issue trackers públicos (a fecha de esta
  investigación, sept. 2026):
  - **Rate limiting agresivo**: del orden de ~6 peticiones/hora antes de un
    bloqueo temporal de cuenta que afecta también a la app oficial.
  - **Fallos de "Invalid credentials"** recurrentes en 2026, en varios casos
    atribuidos a comprobaciones de *Play Integrity* en el endpoint de login
    de Audi, que un cliente no oficial no siempre puede satisfacer. Esto es
    un riesgo del backend de Audi, no un bug que se pueda arreglar aquí.
- Decisión: se aísla toda la integración en
  `backend/app/integrations/myaudi_source.py`, detrás de la interfaz
  `BatterySource`, deshabilitada por defecto (`MYAUDI_AUTO_ENABLED=false`).
  Si falla en cualquier momento, cae automáticamente a la entrada manual
  del %, sin tocar el resto de la app. **No se ha podido probar contra una
  cuenta real** (no hay credenciales disponibles en este entorno) — antes
  de usarla en producción, instalar `audiconnectpy`, revisar su API real en
  `site-packages` y ajustar `_fetch_soc_raw` si hace falta.

### Policharger — sin API pública, entrada manual para v1

- No se ha encontrado ninguna librería ni documentación pública de una API
  REST. La app usa MQTT contra su propia nube (con BLE/ESP-NOW/Modbus RTU
  para la comunicación con el propio cargador), sin biblioteca de terceros
  conocida.
- Reverse-engineering viable en teoría (capturar tráfico con mitmproxy y
  ver si hay algo por debajo del MQTT, o extraer las credenciales del
  broker), pero de complejidad y riesgo no triviales: certificate pinning
  probable, protocolo propietario sobre MQTT, y sin garantía de éxito.
- Decisión, tal y como se anticipaba en el planteamiento inicial: **v1 usa
  entrada manual** para los kWh de Policharger. La interfaz
  `ChargeReadingSource` (`backend/app/integrations/charge_source.py`) deja
  el hueco para una fuente automática futura sin tocar el cálculo de coste
  ni los endpoints de sesión.

## Estructura del proyecto

```
app-carga-coche/
├── backend/                        # FastAPI (Python) — API + estático
│   ├── app/
│   │   ├── calculator.py           # lógica pura de coste/energía (sin I/O)
│   │   ├── models.py               # esquemas Pydantic de la API
│   │   ├── store.py                # persistencia SQLite (config, sesiones, lecturas)
│   │   ├── config.py               # settings desde variables de entorno
│   │   ├── main.py                 # composición de la app y wiring de fuentes
│   │   ├── routers/                # /api/config, /api/battery, /api/sessions
│   │   └── integrations/
│   │       ├── battery_source.py   # interfaz + ManualBatterySource + MyAudiBatterySource
│   │       ├── myaudi_source.py    # cliente MyAudi aislado (frágil, sin probar en real)
│   │       └── charge_source.py    # interfaz + ManualChargeSource (Policharger v1)
│   └── tests/                      # pytest: calculator + API end-to-end
├── frontend/                       # PWA (HTML/CSS/JS vanilla, instalable)
│   ├── index.html
│   ├── manifest.webmanifest
│   ├── service-worker.js
│   ├── css/, js/, icons/
├── docs/ARCHITECTURE.md            # este documento
├── .env.example
└── README.md
```

## Por qué las fuentes de datos son intercambiables

Tanto el % de batería como los kWh de sesión se piden a través de una
interfaz (`BatterySource.get_soc()` / `ChargeReadingSource.record_reading()`)
en lugar de llamarse directamente desde los routers o desde el cálculo.
Así, cambiar MyAudi automático ↔ manual, o añadir en el futuro un
Policharger automático, es cuestión de instanciar una clase distinta en
`main.py` — el cálculo de coste (`calculator.py`) y el modelo de sesión
(`store.py`) no cambian.

## Flujo de una carga

1. `POST /api/battery/manual` (o la fuente automática) fija el % inicial.
2. `GET /api/battery/plan?price_per_kwh=...&target_percent=...` da el coste
   estimado hasta el objetivo sin necesidad de abrir una sesión (requisitos
   1 y 2 del planteamiento inicial).
3. `POST /api/sessions` abre una sesión con ese % inicial, objetivo y precio.
4. Cada vez que Policharger reporta un nuevo total de kWh de la sesión,
   `POST /api/sessions/{id}/readings` lo registra y la respuesta ya trae el
   coste acumulado en tiempo real.
5. Al desconectar el cargador, `POST /api/sessions/{id}/finish` cierra la
   sesión (con el % final si se conoce, o el estimado a partir de los kWh).
6. `GET /api/sessions` da el historial simple pedido como "nice to have".
