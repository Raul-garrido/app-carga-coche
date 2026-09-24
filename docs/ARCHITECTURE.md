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

- **Corrección sobre una investigación anterior**: la primera versión de
  esta sección decía que había que usar un paquete llamado `audiconnectpy`,
  descrito por un resumen de búsqueda como "mantenido activamente". Al
  intentar instalarlo (`pip install audiconnectpy`) resultó que **no
  existe en PyPI** (404 en `pypi.org/pypi/audiconnectpy/json`) — el
  resumen se apoyaba en contenido que no correspondía a un paquete real.
  Lección: para una dependencia de la que va a depender toda una
  integración, instalarla y comprobarlo es obligatorio, no basta con un
  resumen de búsqueda.
- Base real, verificada instalando ambos paquetes en un entorno aislado y
  leyendo su código fuente en `site-packages` (no solo su documentación):
  [`carconnectivity`](https://github.com/tillsteinbach/CarConnectivity)
  (framework multi-marca, activamente mantenido) +
  [`carconnectivity-connector-audi`](https://github.com/acfischer42/CarConnectivity-connector-audi)
  (conector específico de Audi, última versión en PyPI de junio de 2026).
  El conector ya trae su propio hilo en segundo plano que sondea la API de
  Audi por su cuenta y hace backoff de 15 minutos si recibe un 429 — no
  hace falta que nuestro código gestione el rate limiting a mano.
- Riesgos que siguen siendo reales, confirmados por issue trackers
  públicos (sept. 2026): rate limiting agresivo (del orden de ~6
  peticiones/hora antes de bloqueo temporal de cuenta, que afecta también
  a la app oficial), y fallos de "Invalid credentials" recurrentes en
  2026, en varios casos atribuidos a comprobaciones de *Play Integrity* en
  el login de Audi que un cliente no oficial no siempre puede satisfacer.
  Esto es un riesgo del backend de Audi, no algo que se arregle aquí.
- Decisión: se aísla toda la integración en
  `backend/app/integrations/myaudi_source.py`, detrás de la interfaz
  `BatterySource`, deshabilitada por defecto (`MYAUDI_AUTO_ENABLED=false`).
  Si falla en cualquier momento, cae automáticamente a la entrada manual
  del %, sin tocar el resto de la app.
- Además del %, se expone si está cargando y el tiempo restante estimado
  que reporta la propia Audi (`Charging.estimated_date_reached`), y
  `backend/app/auto_session.py` usa esa señal de "cargando sí/no" para
  abrir y cerrar la sesión de carga sola — solo los kWh de Policharger
  siguen siendo manuales, porque no hay forma automática de conseguirlos.
- **Probada contra una cuenta real de Audi (septiembre 2026): el login
  falla.** `MyAudiClient.start()` arranca el hilo en segundo plano sin
  problema, pero el intercambio de token contra
  `emea.bff.cariad.digital/auth/v1/idk/oidc/token` devuelve
  `400 {"error":"invalid assertion headers"}`. No es un fallo de
  credenciales: es el mismo error que reportan otros usuarios de
  `carconnectivity-connector-audi` en
  [issue #29](https://github.com/acfischer42/CarConnectivity-connector-audi/issues/29) —
  Audi/CARIAD exige desde mayo de 2026 una atestación "Play Integrity" en
  el intercambio de token que solo la app oficial firmada puede
  satisfacer. La librería lo arregló parcialmente en la v0.3.2 (la que usa
  este proyecto), pero hay reportes de julio de 2026 de que ha vuelto a
  romperse por otra vía (la página de login ahora se renderiza con
  JavaScript y el parser HTML de la librería ya no encuentra el campo de
  contraseña). Fuera del alcance de este proyecto arreglarlo: dependería
  de un cambio en la librería (p. ej. automatizar el login con un
  navegador real) o de que Audi abra una vía oficial. El fallback a
  entrada manual (confirmado también en esta prueba) sí funciona
  correctamente.

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
│   │   ├── routers/                # /api/config, /api/battery, /api/sessions, /api/myaudi
│   │   └── integrations/
│   │       ├── battery_source.py   # interfaz + ManualBatterySource + MyAudiBatterySource
│   │       ├── myaudi_source.py    # cliente MyAudi aislado (frágil, ya probado en real: falla)
│   │       ├── myaudi_manager.py   # activar/probar MyAudi en caliente desde la API (sin reiniciar)
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
Policharger automático, es cuestión de instanciar una clase distinta —
el cálculo de coste (`calculator.py`) y el modelo de sesión (`store.py`)
no cambian.

Esa fuente activa, además, puede cambiar **en caliente**, sin reiniciar el
servidor: `app.state.battery_source` es en realidad un
`DynamicBatterySource` (`myaudi_manager.py`) que delega en lo que esté
activo en cada momento. `MyAudiManager` es quien decide qué hay detrás —
manual o MyAudi — a partir de las credenciales guardadas en SQLite
(`Store.get_myaudi_credentials()`), y lo cambia cuando llegan peticiones a
`/api/myaudi/credentials` desde la tarjeta "MyAudi automático" de la PWA.
`AutoSessionManager` y los routers guardan una única referencia estable a
ese `DynamicBatterySource`, así que no necesitan enterarse del cambio.

`POST /api/myaudi/test` reinicia el cliente de MyAudi desde cero contra
las credenciales guardadas y sondea `get_status()` durante unos segundos,
capturando el último mensaje de error concreto que registren los loggers
de `carconnectivity` (filtrando el volcado de traceback que la librería
mete en el nivel CRITICAL, y quedándose solo con los mensajes ERROR
legibles) — así la PWA puede mostrar el motivo real del fallo (p. ej.
`invalid assertion headers`) en vez de un mensaje genérico.

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
