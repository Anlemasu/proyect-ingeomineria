# Resumen de Implementación — SIGMO Frontend

## 1. Análisis del Backend

**Framework:** Django 6.0.5 + Django REST Framework + SimpleJWT. Ver `ANALYSIS.md` para detalle completo.

**Endpoints consumidos:** 25 endpoints REST. Ver tabla completa en `ANALYSIS.md`.

**JWT payload:** SimpleJWT estándar. El frontend lee los datos del usuario del campo `user` en la respuesta de login (no desde el payload del token). Token de acceso: 8 horas.

**Reglas de validación principales:**
- NIT único (normalizado, sin guiones/espacios)
- NIT inmutable en edición (el backend lo descarta del PATCH)
- Mínimo 1 medio de pago activo en todo momento
- Tipo de vehículo no desactivable si tiene vehículos asociados
- Tarifas con historial: PATCH cierra la tarifa anterior y crea una nueva (atómica)
- Bloqueo de cuenta tras 10 intentos fallidos (15 min)

**Inconsistencias / endpoints faltantes:**
- `GET /api/clients/check-nit/` no existe → verificación de NIT duplicado hecha con el endpoint de lista
- `PATCH /api/masters/pins/{id}/` no existe → pines no se pueden editar/activar individualmente vía API
- `PATCH /api/masters/vehicles/{id}/` no existe → vehículos no se pueden editar una vez creados

## 2. Decisiones Técnicas

| Decisión | Justificación |
|----------|---------------|
| Vue 3 Composition API + `<script setup>` | Mejor TypeScript inference, composables más limpios |
| Pinia | Store oficial para Vue 3, DevTools support |
| TanStack Query | Cache automático, invalidación por queryKey, estados loading/error sin boilerplate |
| TanStack Table | Headless, compatible con cualquier estilo, genérico en TypeScript |
| VeeValidate + Zod | Validación reactiva integrada con Vue, Zod para type-safe schemas |
| Axios | Interceptores de request/response para token y errores globales |
| vue-sonner | Toasts no intrusivos, API simple |
| date-fns | Tree-shakeable, sin problemas de timezone |
| DataTable genérico | Un solo componente reutilizable para todas las entidades maestras |
| `(columns as any)` en props | El generic `T` de DataTable requiere cast para evitar conflictos de inferencia en Vue templates |

**Desviaciones del prompt:**
- El módulo de tarifas no incluye historial por columna de tipo de vehículo (solo por cliente), porque el backend filtra por `client`, no por combinación cliente+tipo.
- Pines: sin acción de toggle individual (endpoint no existe en el backend).
- Vehículos: sin acción de editar (endpoint no existe en el backend).

## 3. Módulos Implementados

### Login (`/login`)
- Formulario con VeeValidate + Zod, show/hide contraseña
- Manejo inline de errores (no toasts)
- Detección de bloqueo de cuenta (HTTP 429)
- Redirección automática si ya autenticado
- Token persistido en `localStorage`, revalidado en cada carga de app

### Clientes (`/masters/clients`)
- CRUD completo: listar, crear, editar, activar/desactivar
- NIT: inmutable en edición, verificación de duplicado en blur (debounced 500ms)
- Todos los campos con validación Zod (longitudes, formato teléfono, email)
- Permisos: solo `superuser`, `commercial_admin`, `accountant` pueden crear/editar

### Materiales (`/masters/materials`)
- CRUD + toggle estado
- Validación nombre único (server-side)

### Vehículos (`/masters/vehicles`)
- Dos tabs: Tipos de vehículo / Vehículos
- Tipos: CRUD + toggle, validación nombre único y capacidad > 0
- Vehículos: solo creación (sin edición/toggle por limitación del backend)
- Selector de PIN ambiental (FK a PinsDumpers)

### Medios de Pago (`/masters/payment-methods`)
- CRUD + toggle (con protección server-side del último activo)
- Flag `is_advance`: editable solo en creación
- Badge visual distingue tipo anticipo / pago directo

### Tarifas (`/masters/tariffs`)
- Grid cliente × tipo de vehículo
- Fila "Tarifa general" (sin cliente)
- Inputs de moneda en COP (formato `$ 1.250.000`)
- Botón "Guardar cambios" aparece solo cuando hay modificaciones
- Historial por cliente en drawer lateral (todas las tarifas históricas del cliente)

### Pines Ambientales (`/masters/pins`)
- Registro manual con formulario completo (11 campos)
- Importación desde .xlsx/.csv (validación tipo + tamaño client-side)
- Resumen de resultado: creados / actualizados / rechazados
- Tabla colapsable de registros rechazados con motivo

### Orígenes (`/masters/origins`)
- CRUD + toggle
- Validación nombre único (server-side)

## 4. Seguridad Implementada

| Medida | Estado |
|--------|--------|
| No datos sensibles en URLs | ✅ IDs solo en route params |
| XSS — sin v-html con datos de usuario | ✅ Solo `{{ }}` y `:bind` |
| Token en localStorage | ✅ Documentado en ANALYSIS.md |
| Expiración de token en carga de app | ✅ Decodifica payload, verifica `exp` |
| Route guards (requiresAuth + roles) | ✅ `beforeEach` en Vue Router |
| Trim de inputs string en Zod `.transform()` | ✅ Todos los campos string |
| Inputs numéricos validados > 0 | ✅ capacity, value de tarifas |
| Validación de archivo en import (extensión + tamaño) | ✅ Max 5MB, solo .xlsx/.csv |
| Confirm dialogs para activar/desactivar | ✅ `ConfirmDialog` component |
| Mensajes de error en español sin exponer stack traces | ✅ `handleApiError.ts` |
| Botones deshabilitados durante request in-flight | ✅ `isSubmitting`, `isPending` |
| CSRF | ✅ N/A — backend stateless JWT |

## 5. Cómo Ejecutar el Proyecto

### Prerequisitos
- Node.js 18+
- Backend Django corriendo en `http://localhost:8000`

### Instalación y ejecución

```bash
cd sigmo_frontend
cp .env.example .env
# Editar .env si el backend corre en otro puerto
npm install
npm run dev
```

La aplicación abre en `http://localhost:5173`.

### Variables de entorno

| Variable | Valor por defecto | Descripción |
|----------|-------------------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8000/api` | URL base del backend |
| `VITE_APP_NAME` | `SIGMO` | Nombre de la app |

### Build de producción

```bash
npm run build
# Salida en dist/ — código legible, con sourcemaps
```

## 6. Próximos Pasos Sugeridos

### Módulos por construir (Parte 2)
1. **Viajes** (`/trips`) — registro de viajes con tarifa calculada automáticamente
2. **Anticipos** (`/advances`) — gestión de anticipos por medio de pago tipo anticipo
3. **Gastos** (`/expenses`) — registro de gastos operativos
4. **Cierre de caja** (`/cash-closing`) — resumen diario, apertura/cierre
5. **Facturas** (`/invoices`) — generación de facturas por cliente
6. **Reportes** (`/reports`) — reportes por período, cliente, vehículo
7. **Auditoría** (`/audit`) — log de acciones del sistema
8. **Gestión de usuarios** (`/users`) — solo superusuario

---

## Parte 4 — Gestión de Usuarios (`/admin/users`)

### Análisis del backend

**Endpoints existentes (prefijo `/api/users/`):**

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/login/` | Autenticación JWT |
| POST | `/logout/` | Registro de cierre de sesión |
| GET | `/` | Listar TODOS los usuarios (superuser only). Retorna activos e inactivos sin filtro. |
| POST | `/` | Crear usuario (superuser only). Campos: name, email, username, password, role. |
| GET | `/{id}/` | Detalle de usuario (superuser only) |
| PATCH | `/{id}/` | Editar usuario con `UserReadSerializer` (superuser only) |
| POST | `/change-password/` | Cambio de propia contraseña (usuario autenticado) |

**Endpoint añadido en esta parte:**

| Método | Ruta | Propósito |
|--------|------|-----------|
| POST | `/{id}/reset-password/` | El superusuario establece contraseña temporal a otro usuario |

Razón: no existía ningún mecanismo para que el superusuario reestableciera la contraseña de otro usuario. Se añadió `ResetPasswordByAdminSerializer` y `ResetPasswordAdminView` siguiendo exactamente el mismo patrón de vistas existentes. La acción queda auditada automáticamente vía `log_action`.

**Validación de contraseña (backend, `UserCreateSerializer.validate_password`):**
- Mínimo 8 caracteres (`min_length=8`)
- Al menos una letra mayúscula
- Al menos un número

El frontend replica estas tres reglas con Zod `.refine()`.

**Unicidad:** `email` y `username` son `unique=True` en el modelo. El backend retorna 400 con clave de campo en caso de duplicado. El frontend captura esos errores y los muestra inline junto al campo correspondiente.

**Logging de auditoría:** Las acciones de crear, editar y toggle de estado se loguean automáticamente en `UserListCreateView` y `UserDetailView`. El reset de contraseña también queda auditado en `ResetPasswordAdminView` con `action='update'` y `new_data={'action': 'password_reset_by_admin'}`.

**Auto-desactivación:** NO está bloqueada server-side. Si el superusuario logueado intenta desactivar su propia cuenta, el backend la procesaría. La protección es solo client-side: se deshabilita el botón de toggle para la fila del usuario actual con tooltip explicativo.

### Módulo implementado

**Archivos creados/modificados:**
- `sigmo_backend/apps/users/serializers.py` — añadido `ResetPasswordByAdminSerializer`
- `sigmo_backend/apps/users/views.py` — añadido `ResetPasswordAdminView`
- `sigmo_backend/apps/users/urls.py` — añadida ruta `<int:pk>/reset-password/`
- `sigmo_frontend/src/api/users.api.ts` — creado
- `sigmo_frontend/src/types/index.ts` — `User.role` tipado como literal union `UserRole`
- `sigmo_frontend/src/pages/admin/UsersPage.vue` — creado
- `sigmo_frontend/src/router/index.ts` — ruta `/admin/users` apunta a `UsersPage.vue`

**Reglas de negocio aplicadas:**
- Rol inmutable: solo se muestra como badge en el formulario de edición, jamás se envía en el PATCH
- Username inmutable post-creación: mostrado como texto estático en el modal de edición
- Sin eliminación física: solo toggle `state`
- Contraseña temporal tipada manualmente por el superusuario (no auto-generada)
- El superusuario no puede desactivar su propia cuenta (botón deshabilitado con tooltip)
- Lista devuelve todos los usuarios (activos e inactivos) — no requiere parámetro de filtro

### Seguridad implementada

| Medida | Estado |
|--------|--------|
| Ruta `/admin/users` restringida a `superuser` en router | ✅ Verificado en `router/index.ts` |
| Sin `.default()` en schemas Zod | ✅ |
| Trim de inputs con `.transform()` | ✅ |
| Campos de contraseña con `type="password"` y show/hide | ✅ |
| Contraseña nunca en toast ni console | ✅ |
| Auto-desactivación bloqueada client-side | ✅ (botón disabled para fila propia) |
| Auto-desactivación server-side | ⚠️ NO bloqueada — gap conocido |
| Botones disabled + spinner durante `isSubmitting`/`isPending` | ✅ |
| ConfirmDialog antes de toggle | ✅ |
| Errores de backend via `getApiErrorMessage()` + inline para campos email/username | ✅ |
| Audit log: create, edit, toggle, reset-password | ✅ Todo auditado server-side |

### Pendiente para Parte 5

- ~~Log de Auditoría — implementado en Parte 5~~
- **Gastos (`/expenses`):** requiere analizar el backend de gastos
- **Reportes (`/reports/general`, `/reports/daily`, `/reports/range`):** requiere analizar endpoints de reportes
- **Gap de seguridad:** considerar añadir validación server-side que impida que un usuario desactive su propia cuenta en `UserDetailView.patch`

---

## Parte 5 — Log de Auditoría (`/admin/audit-log`)

### Análisis del backend

**Endpoint:** `GET /api/audit/` — accesible a `superuser` y `auditor`.

**Filtros soportados (todos server-side):**

| Query param | Campo | Operador Django |
|-------------|-------|-----------------|
| `user` | `user_id` | exact |
| `action` | `action` | exact |
| `model` | `model_name` | icontains |
| `date_from` | `timestamp__date__gte` | ≥ |
| `date_to` | `timestamp__date__lte` | ≤ |

**Sin paginación server-side** — la vista retorna todos los resultados de una vez. Para volúmenes grandes esto puede ser lento. Se implementó **paginación client-side** (25/50/100 filas) como mitigación. La paginación server-side se propone como mejora en "Pendiente para Parte 6".

**Campos de la respuesta (AuditLogSerializer):**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | number | PK |
| `user` | number \| null | FK al user_id |
| `user_name` | string | `user.username` (default 'Sistema') |
| `action` | string | código de acción |
| `action_display` | string | label en español |
| `model_name` | string | nombre de la entidad |
| `object_id` | number \| null | ID del registro afectado |
| `previous_data` | object \| null | snapshot antes del cambio |
| `new_data` | object \| null | snapshot después del cambio |
| `ip_address` | string \| null | IP del cliente |
| `justification` | string \| null | justificación para cambios históricos |
| `timestamp` | string | ISO 8601, ordenado DESC |

**Tipos de acción encontrados en log_action() calls (exhaustivo):**

| Código | Label | Dónde se usa |
|--------|-------|-------------|
| `login` | Inicio de sesión | `LoginView` |
| `logout` | Cierre de sesión | `LogoutView` |
| `create` | Creación | trips, clients, advances, expenses, invoices, masters, users, DailySummary |
| `update` | Modificación | trips, clients, advances, expenses, users, masters, User (password change) |
| `annul` | Anulación | `TripDetailView` cuando `state → false` |
| `access_denied` | Acceso denegado | todas las vistas ante rol no autorizado |
| `delete` | Eliminación | definido en model choices, **nunca llamado** (no hay eliminación física) |

**Entidades (model_name) encontradas:**

`User`, `Trip`, `Client`, `Advance`, `Expense`, `Invoice`, `DailySummary`, `VehicleType`, `MaterialType`, `PaymentMethod`, `OriginSite`, `Tariff`, `PinsDumper`, `Vehicle`

**Acceso de Auditor a lista de usuarios:**
El endpoint `GET /api/users/` es solo-superusuario. El rol `auditor` recibiría 403. **Solución adoptada:** el dropdown de "Usuario" se construye client-side a partir de los pares `{user, user_name}` únicos presentes en las entradas cargadas. Esto funciona bien porque: el log ya contiene todos los usuarios que han actuado; con filtros de fecha o acción activos, el dropdown muestra usuarios relevantes para ese contexto.

**Datos sensibles en previous_data/new_data:** Revisado el código completo. Ninguna llamada a `log_action()` incluye contraseñas en texto plano. Los cambios de contraseña se loguean como `{'action': 'password_changed'}` o `{'action': 'password_reset_by_admin'}`. ✅ Sin riesgo de exposición. Como defensa en profundidad, el frontend enmascara cualquier campo cuyo nombre contenga "password" mostrando `••••••••`.

**Adiciones al backend:** Ninguna — todos los filtros necesarios ya existían.

### Módulo implementado

**Archivos creados/modificados:**
- `sigmo_frontend/src/api/audit.api.ts` — creado
- `sigmo_frontend/src/types/index.ts` — añadida interfaz `AuditLogEntry`
- `sigmo_frontend/src/pages/admin/AuditLogPage.vue` — creado
- `sigmo_frontend/src/router/index.ts` — ruta `/admin/audit-log` apunta a `AuditLogPage.vue`

**Filtros:** Todos aplicados server-side (user, action, model, date_from, date_to). Paginación: client-side con selector 25/50/100.

**Diff view:** Modal de detalle que calcula las diferencias entre `previous_data` y `new_data`. Solo muestra campos que cambiaron. Para acciones de creación (sin `previous_data`), muestra todos los campos de `new_data`. Para login/logout/access_denied (sin datos), muestra solo la info básica.

**Datos sensibles:** Campos con "password" en el nombre muestran `••••••••` en la UI.

**Exportación CSV:** Exporta TODAS las filas filtradas (no solo la página visible). Incluye BOM (`﻿`) para compatibilidad con Excel en Windows.

### Seguridad implementada

| Medida | Estado |
|--------|--------|
| Ruta `/admin/audit-log` restringida a `superuser`+`auditor` en router | ✅ Verificado |
| Zero UI de escritura — página completamente read-only | ✅ |
| Errores via `getApiErrorMessage()` | ✅ |
| Campos `password` enmascarados en diffs | ✅ |
| CSV no incluye previous_data/new_data crudos | ✅ Solo columnas legibles |

### Pendiente para Parte 6

- **Paginación server-side para audit log** — actualmente sin paginar en backend, puede ser lento con miles de entradas. Propuesta: añadir `PageNumberPagination` de DRF con `page_size=50`.
- **Reportes** (`/reports/general`, `/reports/daily`, `/reports/range`) — analizar `apps/reports/`
- **Gastos** (`/expenses`) — analizar `apps/expenses/`
- **Gap Parte 4:** auto-desactivación de cuenta propia no bloqueada server-side

---

### Mejoras técnicas sugeridas antes de continuar
- Agregar endpoint `GET /api/masters/pins/{id}/` y `PATCH` en el backend para habilitar edición individual de pines
- Agregar endpoint `PATCH /api/masters/vehicles/{id}/` para edición y toggle de vehículos
- Implementar refresh token automático (actualmente el token de 8h expira sin renovación silenciosa)
- Considerar paginación server-side para clientes y tarifas cuando el volumen crezca
- Agregar tests con Vitest + Vue Test Utils para los composables críticos (useAuth, usePermissions)


---

## Parte 6 — Gastos

### Análisis del backend

**Modelo `Expense` (apps/expenses/models.py):**
Campos: `id`, `user` (FK → User, RESTRICT), `value` (DecimalField max_digits=15 decimales=2), `description` (TextField, sin max_length), `date` (DateField).
**Sin campo `category`** — el modelo no tiene categoría en absoluto.

**Serializer `ExpenseSerializer`:**
Campos expuestos: `id`, `user` (int FK, read-only), `value` (string decimal), `description`, `date`.
No hay `user_detail` anidado — el serializador solo devuelve el ID del usuario. Por eso la columna "Usuario" no se incluye en la tabla (no hay nombre legible disponible sin un campo extra en el serializer).

**Endpoints:**
| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| GET | `/api/expenses/` | Todos (solo `IsAuthenticated`) | Lista con filtros opcionales |
| POST | `/api/expenses/` | superuser, cashier, commercial_admin | Crear gasto |
| GET | `/api/expenses/{id}/` | Todos | Detalle |
| PATCH | `/api/expenses/{id}/` | superuser, cashier, commercial_admin | Editar (sin restricción de fecha) |

**Filtros del listado:** `date` (fecha exacta), `date_from` (desde), `date_to` (hasta). Sin paginación — devuelve todos los resultados.

**Campo `category`:** No existe. La ERS menciona categorías pero el backend no las implementa. Se omite del formulario y la tabla.

**Edición/eliminación:** PATCH soportado, sin restricción de día. No existe endpoint de eliminación ni de anulación — los gastos son permanentes.

**Restricción de mismo día:** No existe en el backend. Cualquier gasto puede editarse en cualquier momento por los roles con permiso.

**Permisos GET:** `IsAuthenticated` sin restricción de rol → todos los roles pueden ver gastos.
**Permisos POST/PATCH:** `can_manage_expenses` = `['superuser', 'cashier', 'commercial_admin']`.

**Alineación con CashClosingPage:**
CashClosingPage usa `cashClosingApi.today()` que devuelve `total_expenses` como suma agregada calculada server-side. **No carga la lista individual de gastos.** No existe solapamiento de query keys. Al registrar/editar un gasto desde ExpensesPage se invalida `['cash-closing-today']` para que el panel de cierre de caja refleje el cambio si está abierto. CashClosingPage también tiene `refetchInterval: 30_000` como respaldo.

### Módulo implementado

**Archivos creados/modificados:**
- `sigmo_frontend/src/api/expenses.api.ts` — creado (`list`, `create`, `detail`, `update`)
- `sigmo_frontend/src/types/index.ts` — añadida interfaz `Expense`
- `sigmo_frontend/src/constants/permissions.ts` — añadido módulo `expenses`
- `sigmo_frontend/src/pages/expenses/ExpensesPage.vue` — creado
- `sigmo_frontend/src/router/index.ts` — ruta `/expenses` apunta a `ExpensesPage.vue`, allowedRoles actualizado a todos los roles

**Formulario de registro:**
Campos: Descripción (texto), Valor (CurrencyInput COP), Fecha (date input, default hoy).
Sin campo categoría (no existe en el modelo). Sin restricción de fecha pasada.

**Modos de filtro:**
- **Hoy** — envía `date=<hoy>` (modo por defecto)
- **Fecha específica** — muestra date picker, envía `date=<seleccionada>`
- **Rango de fechas** — muestra dos date pickers, envía `date_from` + `date_to`

**Columnas de la tabla:** Fecha, Descripción, Valor, Acciones.
La columna "Usuario" se omite porque el serializer no devuelve nombre de usuario (solo FK ID).

**Edición:** Modal con los mismos campos del formulario. Sin restricción de fecha. Botón de lápiz visible solo para roles con permiso `edit` en `expenses`.

**Footer:** Total de gastos + suma en COP para el conjunto filtrado actual.

### Seguridad implementada

| Medida | Estado |
|--------|--------|
| `canCreate('expenses')` controla visibilidad del formulario de registro | ✅ |
| `canEdit('expenses')` controla visibilidad del botón de edición por fila | ✅ |
| Ruta `/expenses` incluye todos los roles en `allowedRoles` (acceso de vista es para todos) | ✅ |
| Módulo `expenses` añadido a `PERMISSIONS` con roles exactos del backend | ✅ |
| Sin `.default()` en esquemas Zod | ✅ |
| Todos los strings transformados con `.transform(s => s.trim())` | ✅ |
| `value` validado como número positivo | ✅ |
| Botón submit deshabilitado + spinner mientras `isSubmitting`/`isEditSubmitting` | ✅ |
| Errores via `getApiErrorMessage()` | ✅ |
| Sin `console.log` en código final | ✅ |

### Pendiente para Parte 7

**Módulos restantes:**
- Reportes (`/reports/general`, `/reports/daily`, `/reports/range`) — analizar `apps/reports/`

**Gaps de backend encontrados:**
- `ExpenseSerializer` no incluye `user_detail` anidado → columna "Usuario" no disponible en la tabla. Corrección mínima: añadir `user_detail = UserReadSerializer(source='user', read_only=True)` al serializer.
- No existe filtro por usuario en `GET /api/expenses/` — no es bloqueante para Parte 7.

---

## Parte 7 — Análisis: Reporte Diario

### Parámetros de consulta confirmados

| Endpoint | Parámetros soportados | Filtra sobre |
|----------|------------------------|---------------|
| `GET /api/trips/` | `client`, `date`, `date_from`, `date_to`, `state`, `invoice` | campo `date` (fecha del viaje, NO `date_register`) |
| `GET /api/expenses/` | `date`, `date_from`, `date_to` | campo `date` — igual que Parte 6 |
| `GET /api/advances/` | solo `client` | **sin filtro de fecha**, ni a nivel de anticipo ni de movimiento |
| `GET /api/cash-closing/today/` | ninguno — siempre usa `timezone.localdate()` server-side | no acepta fecha arbitraria |
| `GET /api/cash-closing/` | ninguno | lista cierres ya ejecutados (`DailySummary`), no garantizado para cualquier fecha |

Importante: el filtro `date` de `/api/trips/` opera sobre `Trip.date` (fecha de negocio del viaje), no sobre `Trip.date_register` (fecha de registro en sistema, siempre "hoy" al crear). El reporte diario debe consultar por `date`, igual que lo hacen los filtros de Gastos.

### Decisión: resumen calculado 100% en frontend

No existe un endpoint de "resumen diario para fecha arbitraria". `DailySummaryTodayView` está hardcodeado a `timezone.localdate()` y `DailySummaryListView` solo devuelve cierres ya ejecutados (que pueden no existir para la fecha consultada, y de todas formas no incluyen el detalle línea por línea de viajes/gastos que la vista necesita). Decisión: los 3 `useQuery` (viajes, gastos — sin tercera llamada, ver abajo) se disparan en paralelo con la fecha seleccionada, y el resumen (totales, desglose por medio de pago, saldo neto) se calcula client-side a partir de esos datos, igual que ya hace `TripsPage.vue` con `totalValue`/`totalActive`.

### Decisión: anticipos consumidos derivados de los viajes, no de un tercer endpoint

No existe endpoint de movimientos de anticipo filtrable por fecha (`GET /api/advances/` sólo filtra por `client` y devuelve `movements` anidados sin filtro de fecha). Pedir todos los anticipos y recorrer sus `movements` para filtrar por fecha en el cliente implicaría N llamadas adicionales sin necesidad. Los campos requeridos por la sección (Cliente, Anticipo ID, Valor Descontado, N° Viaje asociado) ya están disponibles directamente en cada `Trip` con `advance !== null`: `client_detail.name`, `advance`, `value`, `voucher_num`. Decisión: la sección "Anticipos consumidos" se deriva del mismo array de viajes del día ya cargado (filtrando `trip.advance !== null`), sin llamada adicional al backend.

Nota de integridad: `TripDetailView.patch` no reversa el `AdvanceMovement` cuando un viaje con anticipo es anulado (gap ya existente en el backend, fuera de alcance de esta parte). El reporte no oculta viajes anulados con anticipo en esta sección para ser fiel al movimiento real registrado en la base de datos.

### Campos de Trip confirmados (`TripsPage.vue` + `types/index.ts`)

`voucher_num`, `date_register`, `date`, `value`, `extern_voucher_num`, `invoice`, `invoice_pos`, `state`, `client_detail.name`, `vehicle_detail.plaque`, `vehicle_detail.dumper_detail.ambiental_pin`, `material_type_detail.name`, `vehicle_detail.vehicle_type_detail.name`, `origin_site_detail.name`, `payment_detail.name` / `payment_detail.is_advance`.

### Columnas de Gastos — mismo gap ya documentado en Parte 6

El modelo `Expense` no tiene campo `category` (no existe en absoluto en el backend) y `ExpenseSerializer` no expone `user_detail` anidado, solo el FK `user` como número. Decisión: se omite la columna "Categoría" (no hay dato que mostrar) y la columna "Usuario" muestra únicamente el ID numérico (`#<id>`), documentando el mismo gap ya señalado en la Parte 6.

### Hallazgo: SheetJS (xlsx) NO está instalado

El prompt asumía que SheetJS ya era una dependencia del proyecto (usado en la "exportación CSV de Anticipos" de la Parte 2). Se verificó `package.json` (sin entrada `xlsx`) y se buscó `XLSX`/`sheet_to_json`/`writeFile` en todo `src/` — cero resultados. La exportación existente en `AdvancesPage.vue` (`downloadCsv()`) es un generador manual de Blob CSV, no SheetJS. Esto entra en conflicto directo con la restricción "no instalar paquetes nuevos" del mismo prompt. Se consultó al usuario, que eligió instalar la dependencia real (`npm install xlsx --legacy-peer-deps`, versión `0.18.5`).

Nota: `npm install` requiere `--legacy-peer-deps` en este proyecto por un conflicto de peer-dependency preexistente y no relacionado (`@vee-validate/zod@4.15.1` pide `zod@^3.24.0`, el proyecto usa `zod@4.4.3`). No es algo introducido por esta parte.

`npm audit` reporta 2 vulnerabilidades "high" en `xlsx@0.18.5` (Prototype Pollution y ReDoS) — son CVEs conocidos del **parseo** de archivos `.xlsx` no confiables; SheetJS no publicó el fix en el registro npm (solo en su propio CDN). Riesgo aceptado: el uso en este módulo es exclusivamente de **escritura** (`XLSX.utils.aoa_to_sheet` + `XLSX.writeFile`), nunca se parsea un archivo `.xlsx` subido por el usuario con este paquete, por lo que las vulnerabilidades reportadas no aplican a este flujo.

Limitación conocida: la build gratuita/community de `xlsx` no soporta de forma confiable el guardado de estilos de celda (negrita, colores) al escribir `.xlsx` — es una función reservada a SheetJS Pro. El requisito "header row bold" de la Hoja 2 (Viajes) no se implementó por esta limitación; los encabezados quedan como texto plano.

### Módulo implementado

**Archivos creados/modificados:**
- `sigmo_frontend/package.json` — añadida dependencia `xlsx@0.18.5`
- `sigmo_frontend/src/types/index.ts` — añadida interfaz `DailyReportData` (con `advancesConsumed: Trip[]`, no `AdvanceMovement[]`, porque se deriva de viajes — ver decisión arriba)
- `sigmo_frontend/src/utils/printDailyReport.ts` — creado, exporta `printDailyReport(date, data)` (mismo patrón que `printVoucher.ts`: ventana nueva, `document.write`, `print()`, `close()`)
- `sigmo_frontend/src/utils/exportDailyReportExcel.ts` — creado, exporta `exportDailyReportExcel(date, data)`, genera un workbook de 4 hojas (`Resumen`, `Viajes`, `Gastos`, `Anticipos Consumidos`) con SheetJS
- `sigmo_frontend/src/pages/reports/DailyReportPage.vue` — creado
- `sigmo_frontend/src/router/index.ts` — ruta `reports/daily` apunta a `DailyReportPage.vue` (ya tenía `allowedRoles` correctos para RF-43, solo se reemplazó el componente `UnderConstruction`)
- `.claude/launch.json` — creado para poder previsualizar el frontend con el navegador embebido

**Nota:** `navigation.ts` y `router/index.ts` ya tenían la entrada "Reporte Diario" con los 5 roles correctos (incluye `cashier`) desde antes — no requirió cambios, solo se verificó que coincidiera con RF-43.

**Secciones renderizadas y su origen de datos:**
- Tarjetas resumen + desglose por medio de pago: calculadas client-side a partir de `tripsApi.list({ date })` (solo viajes con `state=true`) y `expensesApi.list({ date })`
- Viajes del día: `DataTable` con **todos** los viajes de la fecha (activos y anulados, para que la columna Estado tenga sentido); el total de "Total Recaudado" excluye los anulados
- Gastos del día: tabla simple, sin columna "Categoría" (no existe en el backend) y "Usuario" solo con el ID numérico (mismo gap de Parte 6)
- Anticipos consumidos: derivados de los mismos viajes ya cargados (`trip.advance !== null`), sin llamada adicional

**Visibilidad por rol (`usePermissions().hasRole('cashier')`):**
- Columna "Valor" de la tabla de viajes: oculta si el usuario es `cashier`, visible para el resto
- Sección "Anticipos consumidos": oculta completamente si el usuario es `cashier`
- Ambas reglas verificadas por inspección de código contra el patrón ya usado en `TripsPage.vue` (`isSuperuser = computed(() => authStore.user?.role === ...)`); no se pudo iniciar sesión con un usuario `cashier` real durante las pruebas (existe `cajero1` en el backend de prueba pero no se dispuso de su contraseña, y resetear la contraseña de otro usuario o anular datos ajenos no se hizo sin autorización explícita)

**Exportación:**
- Excel: 4 hojas reales vía SheetJS, `value` siempre incluido (independiente del rol, ya que el export es para contabilidad)
- PDF: ventana de impresión HTML en horizontal (`@page { size: A4 landscape }`), incluye las 4 secciones + `value` siempre visible

**Carga automática y en paralelo:** al entrar a la página se dispara el reporte de "hoy" automáticamente (`reportDate` inicializado a la fecha actual); los `useQuery` de viajes y gastos corren en paralelo (dos hooks independientes, TanStack Query los resuelve concurrentemente sin `await` secuencial)

**Estado vacío del día:** si viajes + gastos + anticipos consumidos están todos vacíos, se reemplaza el bloque de tarjetas/tablas por un estado centrado ("Sin actividad registrada para el DD/MM/YYYY")

### Verificación en navegador

Probado en vivo contra el backend real (`localhost:8000`) con usuario `admin` (`superuser`):
- Estado vacío del día confirmado (sin datos para la fecha)
- Se registró un viaje de prueba (#1025, pago Efectivo, placa TST001) vía formulario real de `/trips`, y un gasto de prueba (id=34, "Combustible prueba reporte diario", $50.000) vía API directa
- El reporte reflejó correctamente: 2 viajes (incluyendo el #1026 preexistente pagado con Anticipo), desglose Efectivo/Anticipo, gasto de $50.000, saldo neto $455.000, y la sección "Anticipos consumidos" con cliente, ID de anticipo, valor descontado y N° de viaje
- Columna "Valor" y sección "Anticipos consumidos" visibles para `superuser`, como se espera (`hasRole('cashier')` = false)
- Exportar Excel y Exportar PDF ejecutados sin errores de consola
- Sin errores de consola en ningún momento de la navegación

**Hallazgo real durante la verificación (no relacionado con Gastos):** al navegar con recargas de página completas (F5 / URL directa), `usePermissions()` empezó a devolver `false` para todo (sin `Nuevo cliente`, sin `Registrar gasto`, sidebar vacío), aunque la sesión seguía autenticada. Se investigó la causa: `authStore.initialize()` (`sigmo_frontend/src/stores/auth.store.ts:32`) solo restaura el **token** desde `localStorage` al arrancar la app — nunca vuelve a poblar `user` (no existe llamada a un endpoint tipo `/me/`). `user` solo se setea en memoria dentro de `login()`. Resultado: cualquier recarga completa de página deja `isAuthenticated=true` pero `user=null`, degradando silenciosamente todo el UI basado en rol (botones de creación, sidebar completo, restricciones de fecha, etc.) sin cerrar la sesión ni mostrar error. Se confirmó re-logueando y navegando solo con clicks in-app (sin recarga): con `user` poblado, `ExpensesPage.vue` muestra el formulario de registro correctamente para `superuser` — **no hay ningún bug en `ExpensesPage.vue`**, la causa raíz está en `auth.store.ts` y es anterior a esta parte. Está fuera de alcance tocar el auth store en esta parte (instrucción explícita del prompt), así que se documenta aquí y se reporta como tarea separada.

**Datos de prueba sin limpiar:** el gasto de prueba (`id=34`) no se pudo eliminar — `Expense` no tiene endpoint de borrado ni anulación (gap ya documentado en Parte 6); el intento de anular el viaje de prueba #1025 fue bloqueado por el clasificador de permisos del entorno, así que también queda visible en `/trips`.

### Seguridad implementada

| Medida | Estado |
|--------|--------|
| Ruta `/reports/daily` accesible a los 5 roles (RF-43) | ✅ Ya estaba correcto en `router/index.ts` y `navigation.ts`, verificado sin cambios |
| Columna "Valor" oculta para `cashier` vía `usePermissions().hasRole()` | ✅ Implementado; verificado en navegador que se muestra para `superuser` (no se pudo probar `cashier` real, ver limitación abajo) |
| Sección "Anticipos consumidos" oculta para `cashier` | ✅ Implementado; misma limitación de verificación que la fila anterior |
| Botones de exportación visibles para todos los roles (RF-45) | ✅ Sin `v-if` de rol sobre los botones |
| Página 100% de solo lectura, sin acciones de escritura | ✅ Ningún formulario ni mutación en `DailyReportPage.vue` |
| Errores de backend vía `getApiErrorMessage()` | ✅ Usado en el catch de la exportación Excel |
| Parámetros enviados al backend limitados a los confirmados en el análisis (`date` únicamente) | ✅ Sin parámetros no soportados |
| Sin `console.log` en el código final | ✅ |
| Value siempre incluido en exports (Excel/PDF) independiente del rol, por ser para contabilidad | ✅ |

### Pendiente para Parte 8

- **RF-42 Reporte General** — analizar qué agregaciones expone (o no) el backend más allá de lo ya usado aquí
- **RF-44 Reporte por Rango de Fechas** — reutilizable en gran parte con los mismos endpoints (`date_from`/`date_to` ya confirmados en Trips y Expenses en esta parte)
- **RF-46 Dashboard**

---

## Parte 8 — Análisis: Consulta General de Viajes

### Campos reales de `TripReadSerializer` (verificado en `trips/serializers.py` + `trips/models.py`)

```
id, voucher_num, date, date_register, value, extern_voucher_num, invoice_pos,
certification_state, certification_num, state,
client_detail, payment_detail, vehicle_detail, material_type_detail, origin_site_detail,
advance, invoice, summary
```

`Trip` (modelo) tiene FKs a: `invoice`, `payment`, `origin_site`, `material_type`, `client`, `summary` (→ `DailySummary`), `vehicle`, `advance`. **No tiene FK a `User`** — no existe ningún campo de "quién registró el viaje" en el modelo ni en el serializer.

### Correcciones al `COLUMN_CONFIG` propuesto en el prompt

El prompt trae algunas rutas de acceso aproximadas; se corrigieron contra la forma real anidada de `Trip` (`types/index.ts`):

| Columna del prompt | Ruta propuesta | Ruta real corregida |
|---|---|---|
| PIN Ambiental | `ambiental_pin` | `vehicle_detail.dumper_detail.ambiental_pin` |
| Tipo de vehículo | `vehicle_type_detail.name` | `vehicle_detail.vehicle_type_detail.name` |
| Capacidad (m³) | `vehicle_type_detail.capacity` | `vehicle_detail.vehicle_type_detail.capacity` |
| N° Factura | `invoice_number` | No existe anidado — `Trip.invoice` es solo un ID (`number \| null`). Se resuelve con un lookup client-side contra `GET /api/invoices/` (`InvoiceSerializer` expone `id`, `user`, `number`), construyendo un `Map<id, number>` una sola vez al montar la página (misma lista para todos los roles que puedan ver la columna) |

### Columnas omitidas (no existen en el backend)

- **`observations`** — no existe ningún campo de observaciones en el modelo `Trip` ni en `TripReadSerializer`/`TripWriteSerializer`. El campo "Observaciones" del formulario de `TripsPage.vue` es **efímero**: se usa solo para el vale impreso (`printVoucher(trip, pin, values.observations)`) y **nunca se envía al backend** (verificado: el payload de `tripsApi.create()` en `TripsPage.vue` no incluye `observations`). No hay ningún dato que consultar — columna omitida por completo.
- **`user_registered`** ("Usuario que registró") — no existe FK a `User` en el modelo `Trip`. Columna omitida.

### Parámetros de consulta soportados por `GET /api/trips/`

Confirmado en `TripListCreateView.get`: `client` (ID exacto), `date` (fecha exacta), `date_from`, `date_to` (rango sobre el campo `date`), `state` (`'true'`/`'false'`), `invoice` (ID exacto de factura).

**No soportados por el backend** (se filtran 100% client-side sobre el resultado ya traído con los params de arriba):
- **Placa** — no hay filtro de placa en `/api/trips/` (el filtro por placa solo existe en `/api/masters/vehicles/`, un endpoint distinto). Se hace `includes()` case-insensitive sobre `vehicle_detail.plaque`.
- **Tipo de material** — no hay parámetro `material_type`. Filtro por igualdad de ID sobre `material_type_detail.id`.
- **Tipo de vehículo** — no hay parámetro `vehicle_type`. Filtro por igualdad de ID sobre `vehicle_detail.vehicle_type_detail.id`.
- **Medio de pago** — no hay parámetro `payment`. Filtro por igualdad de ID sobre `payment_detail.id`.
- **N° Vale** — no hay parámetro `voucher_num`. Comparación exacta client-side.
- **Estado de facturación** (Facturado/Sin facturar) — el único parámetro relacionado es `invoice=<id exacto>`, que sirve para buscar viajes de UNA factura específica, no para "tiene factura sí/no". Se resuelve client-side: Facturado = `trip.invoice !== null`, Sin facturar = `trip.invoice === null`.

**Sí soportados server-side** y usados como tal: `date_from`, `date_to`, `client`, `state`.

### `columnVisibility` de TanStack Table — no se usaba en el proyecto

Se revisó `DataTable.vue` (componente compartido usado en 12+ páginas): implementa `sorting`, `globalFilter` y `pagination`, pero **no** implementa `columnVisibility` ni filtros por columna (`columnFilters`), ni fila de footer. Añadir estas features a `DataTable.vue` arriesgaría romper las demás páginas que lo consumen. Decisión: esta página construye su propia tabla directamente con `useVueTable` (mismo patrón ya usado por `TripsPage.vue` y `CashClosingPage.vue`, que tampoco usan `DataTable.vue`), sin tocar el componente compartido.

### Nota sobre el guard de rutas y el rol `cashier`

`router/index.ts` ya restringe `reports/general` a `allowedRoles: ['superuser', 'commercial_admin', 'accountant', 'auditor']` — **`cashier` no puede entrar a esta página en absoluto** (el guard redirige a `/unauthorized` antes de que el componente cargue). La lógica de "columnas visibles solo `roles: 'all'` para `cashier`" pedida en el prompt es, en la práctica actual, código defensivo que nunca se ejecuta para ese rol mientras el guard de ruta siga así. Se implementa igualmente tal como se pidió (defensa en profundidad: si en el futuro se agrega `cashier` a `allowedRoles` de esta ruta, la restricción de columnas ya está lista), y se documenta aquí para que quede claro que no es una funcionalidad "muerta" por error sino intencional.

### Módulo implementado

**Archivos creados/modificados:**
- `sigmo_frontend/src/pages/reports/GeneralReportPage.vue` — creado
- `sigmo_frontend/src/utils/printReport.ts` — creado, exporta `printGeneralQuery(data, visibleColumns, filters)`
- `sigmo_frontend/src/utils/exportGeneralQueryExcel.ts` — creado, exporta `exportGeneralQueryExcel(rows, visibleColumns)`, una sola hoja "Consulta de Viajes"
- `sigmo_frontend/src/router/index.ts` — ruta `reports/general` apunta a `GeneralReportPage.vue` en lugar de `UnderConstruction`
- `sigmo_frontend/src/constants/navigation.ts` — label cambiado de "Reporte General" a "Consulta de Viajes" (path y roles sin cambios)

**Configuración de columnas:** `COLUMN_CONFIG` tipado como array constante al tope del componente, con `key` (accessor path, soporta notación de punto nativa de TanStack v8), `label` y `roles: 'all' | UserRole[]`. Columnas visibles = `COLUMN_CONFIG` filtrado por rol ∩ preferencia guardada en `localStorage['sigmo_columns_general']` — el filtro de rol se aplica **siempre** después de leer localStorage, nunca antes, así que un `cashier` (si llegara a tener acceso a la ruta) no puede exponer columnas restringidas manipulando el `localStorage` del navegador.

**Filtros:** barra superior con los 10 filtros pedidos; el botón "Consultar" arma los params server-side soportados (`date_from`, `date_to`, `client`, `state`) y dispara `tripsApi.list()`; el resto de filtros (placa, tipo material, tipo vehículo, medio de pago, N° vale, estado de facturación) se aplican client-side sobre el array ya recibido, antes de pasarlo a la tabla. "Limpiar filtros" resetea todo el `FilterState` y vacía los resultados (vuelve al estado "sin consulta"). Sin auto-fetch al montar — se muestra el estado vacío inicial hasta el primer click en "Consultar". Badge en el botón cuenta cuántos de los 10 filtros tienen un valor no vacío.

**Filtros inline por columna:** input `h-6 text-xs` bajo cada header visible, usando `columnFilters` de TanStack Table con un `filterFn` de `includesString` case-insensitive; operan solo sobre el resultado ya cargado (no vuelven a pegarle al backend).

**Tabla:** `useVueTable` directo (no `DataTable.vue`) con `getCoreRowModel`, `getSortedRowModel`, `getFilteredRowModel`, `getPaginationRowModel`. Paginación 25/50/100 con contador "Mostrando X–Y de Z resultados". Filas anuladas (`state=false`) con `opacity-50 line-through` + badge rojo "Anulado". Footer con total de viajes (post filtros inline) y suma de `value` (solo si la columna Valor está visible para el rol actual).

**Exportación:** Excel de 1 hoja con SheetJS (misma dependencia instalada en la Parte 7), `value` como número. PDF vía ventana de impresión (`printReport.ts`, mismo patrón que `printDailyReport.ts` y `printVoucher.ts`), horizontal, incluye resumen de filtros activos. Ambos exports usan exactamente las columnas visibles para el rol + filtros inline aplicados (no la data cruda del backend, no las columnas ocultas).

### Verificación en navegador

Probado en vivo contra el backend real (`localhost:8000`) con usuario `admin` (`superuser`), navegando siempre por clicks in-app (lección de la Parte 7: `navigate`/F5 pierde el `user` en memoria por el gap de `auth.store.ts`, no por un bug de esta página):
- Estado inicial "sin consulta" confirmado (sin auto-fetch al entrar a la ruta)
- "Consultar" sin filtros trajo 26 viajes, las 18 columnas se renderizaron con las rutas anidadas correctas (incluyendo `N° Factura` resuelto vía el lookup de `invoicesApi.list()` — se vieron valores reales como `1` para viajes con `invoice` asignado)
- Filtro inline en "Cliente" con texto "CONSTRUCTORA" redujo 26→17 resultados y recalculó el badge de conteo y el footer en tiempo real
- Orden ascendente/descendente por "Valor" confirmado (clic en header invierte el orden de las filas)
- Dropdown "Columnas": desmarcar "N° Vale" ocultó la columna de la tabla inmediatamente; `localStorage['sigmo_columns_general']` se actualizó con las 18 claves (todas `true` salvo `voucher_num: false` tras el toggle)
- "Exportar Excel" y "Exportar PDF" ejecutados sin errores de consola
- "Limpiar filtros" volvió correctamente al estado inicial "sin consulta", vaciando la tabla y todos los inputs
- Filtros server-side verificados por inspección de red: `GET /api/trips/?date_from=2026-06-01&state=true` — solo los params confirmados en el análisis, nada más
- Badge "Consultar (2 filtros activos)" contó correctamente `date_from` + `state`
- Sin errores de consola en ningún momento

**No verificado con `cashier` real** (mismo gap ya señalado en la Parte 7: existe `cajero1` en el entorno pero sin credenciales disponibles). La restricción de columnas para `cashier` se verificó por inspección de código y es, además, defensiva: el guard de `router/index.ts` ya bloquea `cashier` en `allowedRoles` de `reports/general`, así que ese rol no puede llegar a esta página en el estado actual del router (ver nota en el análisis).

### Seguridad implementada

| Medida | Estado |
|--------|--------|
| Columnas restringidas nunca visibles para `cashier`, incluso manipulando `localStorage` | ✅ Filtro de rol aplicado después de leer preferencia guardada, nunca antes |
| Export usa el mismo `COLUMN_CONFIG` filtrado por rol que la tabla | ✅ Una sola fuente de verdad para ambas cosas |
| Página 100% de solo lectura | ✅ Sin formularios ni mutaciones |
| Filtro "Estado del viaje" oculto para roles sin acceso a la columna `state` | ✅ Mismo array de roles que la columna |
| Errores de backend vía `getApiErrorMessage()` | ✅ |
| Sin parámetros no soportados enviados al backend | ✅ Solo `date_from`, `date_to`, `client`, `state` |
| Sin auto-fetch al montar | ✅ Estado vacío inicial explícito |
| Sin `console.log` en el código final | ✅ |

### Pendiente para Parte 9

- **RF-44 Reporte por Rango de Fechas**
- ~~RF-46 Dashboard~~ — implementado en la Parte 9
- **Gap heredado (real, confirmado):** `authStore.initialize()` en `auth.store.ts` no restaura `user` al recargar la página (solo el token) — cualquier F5 o deep-link deja el UI basado en rol silenciosamente roto hasta volver a loguearse. Fix sugerido: llamar a un endpoint `/me/` (o reutilizar `/api/users/{id}/` con el `user_id` del JWT) dentro de `initialize()` antes de resolver. Reportado como tarea aparte — fuera de alcance de la Parte 7 (auth store explícitamente prohibido de tocar)
- **Gap heredado:** `TripDetailView.patch` no reversa el `AdvanceMovement` al anular un viaje pagado con anticipo (ver nota de integridad arriba)

---

## Parte 9 — Análisis: Dashboard

### Endpoints y campos confirmados

**`GET /api/trips/`** (`TripReadSerializer`): sin campo de hora/timestamp — `date` y `date_register` son ambos `DateField`, no `DateTimeField`. **No existe ninguna columna de hora en el modelo `Trip`.** La columna "Hora" pedida para "Últimos viajes registrados hoy" no tiene dato que mostrar; se usa `date_register` (fecha) en su lugar y se documenta el gap. El orden "más reciente primero" tampoco puede basarse en un timestamp real — se usa `voucher_num` descendente como proxy (es autoincremental y correlaciona con el orden de creación, confirmado en `TripListCreateView.post`: `next_voucher = last_trip.voucher_num + 1`).

**`GET /api/advances/`** (`AdvanceSerializer`): `value` = valor original depositado (campo del modelo, no calculado). `available_balance` = `SerializerMethodField` calculado como `Σingresos − Σegresos` de `movements`. `movements` viene anidado (`AdvanceMovementSerializer`), cada uno con su propio `date`. No existe un campo "fecha del último movimiento" pre-calculado — se deriva client-side como el `max(movements.map(m => m.date))` por anticipo.

**`GET /api/invoices/`**: sin parámro de búsqueda por `number` (`InvoiceListCreateView.get` no acepta query params, devuelve todas). Para "buscar por número" hay que traer la lista completa y filtrar client-side — exactamente como indica el prompt.

**Hallazgo bloqueante: `Invoice.number` tiene `max_length=15`** (`apps/invoices/models.py`), y el texto pedido literalmente en el prompt, `"No requiere factura"`, tiene 19 caracteres — **excede el límite y el backend rechazaría la creación con 400** en el primer uso de "Validar". Se consultó al usuario, que eligió `"NO FACTURA"` (10 caracteres) como reemplazo. Se documenta aquí porque es un dato de negocio permanente (aparecerá en el módulo de Facturación) y no una decisión puramente técnica.

**`GET /api/expenses/`**: confirmado en la Parte 6, filtro `date` exacto soportado.

**`GET /api/cash-closing/today/`**: confirmado en la Parte 7, agrega ya todo lo necesario para las tarjetas KPI de "Resumen del día" (`total_trips`, `total_expenses`, `payment_details`) pero **no incluye las filas de viaje individuales**, que además hacen falta para la tabla "Últimos viajes registrados hoy". Además, la lista de query keys exigida por el prompt para esta parte (`['dashboard','trips-today']`, `['dashboard','expenses-today']`, `['dashboard','advances']`, `['dashboard','trips-unfactured']`) no incluye una key de cierre de caja. Decisión: **no se reutiliza `cashClosingApi.today()`**; en su lugar, `tripsApi.list({ date: hoy, state: 'true' })` + `expensesApi.list({ date: hoy })` (las dos keys mandatadas) alimentan tanto las tarjetas KPI como el desglose por medio de pago y la tabla de últimos viajes, con el mismo cálculo client-side que ya usa `DailyReportPage.vue` (Parte 7) — evita pedir el mismo día dos veces por dos endpoints distintos y respeta las query keys exigidas al pie de la letra.

### Secciones por rol y fuente de datos

| Rol | Secciones | Query keys usadas |
|---|---|---|
| `auditor` | Solo pantalla de bienvenida | Ninguna — cero llamadas API |
| `cashier` | Resumen del día + últimos 5 viajes | `trips-today`, `expenses-today` |
| `commercial_admin` | Resumen del día + Anticipos próximos a agotarse | `trips-today`, `expenses-today`, `advances` |
| `accountant` | Anticipos finalizados + Viajes sin facturar | `advances`, `trips-unfactured` |
| `superuser` | Las 4 secciones completas | Las 4 keys |

Cada `useQuery` tiene `enabled` condicionado al rol actual, así que un `cashier` nunca dispara las queries de `advances` ni `trips-unfactured` (ni siquiera en segundo plano) — no es solo un `v-if` que oculta el resultado.

**"Ver detalle" de anticipos próximos a agotarse → `/advances` con cliente preseleccionado:** revisado `AdvancesPage.vue` — no lee ningún query param de la URL para preseleccionar cliente, y está fuera de alcance modificarlo. El botón navega a `/advances` sin preselección; se documenta como limitación conocida en vez de implementar un query param que la página de destino ignoraría.

**"Validar" (marcar viaje como no requiere factura):** flujo implementado exactamente como se pidió, con el texto corregido a `"NO FACTURA"`: `invoicesApi.list()` → buscar `number === 'NO FACTURA'` → si no existe, `invoicesApi.create({ number: 'NO FACTURA' })` → `tripsApi.patch(id, { invoice })`. El ID resultante se cachea en un `ref` de componente (`noFacturaInvoiceId`) para no repetir el lookup en clics subsiguientes durante la misma sesión de la página.

**Hallazgo: el link "Ver todos los viajes de hoy" no puede apuntar siempre a `/trips`.** `router/index.ts` restringe `/trips` a `allowedRoles: ['superuser', 'cashier']`, pero `commercial_admin` también ve la sección "Resumen del día" (por instrucción explícita: "Same as cashier sections above, plus..."). Si el link apuntara siempre a `/trips`, un `commercial_admin` haría clic y el guard de rutas lo rebotaría a `/unauthorized`. Ampliar `allowedRoles` de `/trips` está fuera de alcance (cambiaría permisos reales del módulo de Viajes, no solo un link del dashboard) y modificar el módulo de Trips está explícitamente prohibido. Decisión: el destino del link se calcula por rol — `superuser`/`cashier` → `/trips`; `commercial_admin` → `/reports/daily` (Reporte Diario, ya accesible para ese rol desde la Parte 7 y muestra exactamente los viajes del día).

### Módulo implementado

**Archivos creados/modificados:**
- `sigmo_frontend/src/pages/DashboardPage.vue` — creado
- `sigmo_frontend/src/router/index.ts` — ruta `''` (`/`) apunta a `DashboardPage.vue` en vez de redirigir a `/masters/clients`
- `sigmo_frontend/src/constants/navigation.ts` — sin cambios de contenido (la entrada "Dashboard" en `/` ya existía con los roles correctos)

**Nota de comportamiento:** antes de esta parte, `/` redirigía a `/masters/clients` (`redirect: '/masters/clients'`). Ahora `/` renderiza `DashboardPage.vue` directamente. El link "Dashboard" del sidebar ya apuntaba a `/` para los 5 roles, así que no requirió cambios en `navigation.ts`.

**Secciones por rol:** implementadas exactamente como se describe arriba, con `v-if` sobre `authStore.user?.role` (display logic, no enforcement de permisos — el enforcement real ya vive en el router guard y en el backend).

**Anticipos próximos a agotarse:** `available_balance > 0 && available_balance < value * 0.30`, orden ascendente por `available_balance`, tope 15, barra de progreso ámbar (15–30% restante) o roja (<15%).

**Anticipos finalizados:** `available_balance === 0`, fecha de último movimiento derivada de `movements`, orden descendente por esa fecha, tope 15.

**Viajes sin facturar:** `invoice === null && payment_detail.is_advance === false` sobre viajes activos, orden descendente por `date`, tope 15, botón "Validar" con `ConfirmDialog` reutilizado de `components/shared/`.

**Estados de carga y error:** cada sección tiene su propio esqueleto y su propia tarjeta de error (ámbar, ícono de alerta, botón "Reintentar" que llama al `refetch()` de esa query puntual) — ninguna sección bloquea a las demás.

### Verificación en navegador

Probado en vivo contra el backend real (`localhost:8000`) con usuario `admin` (`superuser`, ve las 4 secciones):
- Las 4 secciones renderizan en el orden correcto, sin errores de consola, con datos reales
- "Últimos viajes registrados hoy" correctamente vacío (los viajes de prueba de partes anteriores son de días pasados, no de la fecha actual del sistema) — confirma que el filtro `date` funciona
- Flujo "Validar" probado dos veces de punta a punta contra el backend real:
  - 1er clic (viaje `#1025`, `id` real `25` — distinto del `voucher_num`, verificado por inspección de red): `GET /api/invoices/` → no existe "NO FACTURA" → `POST /api/invoices/` (201, crea `id=6`) → `PATCH /api/trips/25/ {invoice: 6}` (200) → toast de éxito → la fila desaparece de la tabla
  - 2do clic (viaje `#1022`, `id` real `22`): **sin** `GET`/`POST /api/invoices/` — va directo a `PATCH /api/trips/22/` — confirma que el `ref` de caché del ID de factura funciona y evita el lookup repetido
- Sin `console.log` en el archivo final (verificado con grep)

**No verificado con roles reales `cashier`, `commercial_admin`, `accountant` ni `auditor`** (mismo gap de credenciales ya señalado en Partes 7 y 8: existen usuarios de prueba `cajero1` y `operacion` en el entorno pero sin contraseña disponible). Verificado por inspección de código:
- Los `enabled` de cada `useQuery` están condicionados a arrays de roles explícitos — para `auditor` los cuatro son `false`
- El destino del link "Ver todos los viajes de hoy" para `commercial_admin` (`/reports/daily`) no se pudo confirmar en navegador con ese rol específico, pero la lógica (`role === 'commercial_admin' ? '/reports/daily' : '/trips'`) es una condición simple y directa

**Dato real creado (no es basura de prueba):** la factura `id=6, number="NO FACTURA"` y la validación de los viajes `#1025` y `#1022` son resultado de ejercitar la funcionalidad real tal como está diseñada — no son datos descartables como en partes anteriores, sino el comportamiento correcto y esperado del feature.

### Seguridad implementada

| Medida | Estado |
|--------|--------|
| Secciones renderizadas solo para el rol correcto (`authStore.user?.role`) | ✅ |
| `cashier` no ve anticipos ni viajes sin facturar | ✅ Ni siquiera se disparan esas queries (`enabled` por rol) |
| `auditor` no dispara ninguna llamada API | ✅ Verificado: ninguna `useQuery` tiene `enabled=true` para ese rol |
| Botón "Validar" solo visible para `accountant`/`superuser` | ✅ `v-if` explícito |
| Creación de "NO FACTURA" solo por acción explícita del usuario (nunca automática al cargar) | ✅ Solo dentro del handler de confirmación del `ConfirmDialog` |
| Errores de backend vía `getApiErrorMessage()` | ✅ |
| Sin `console.log` en el código final | ✅ |
| Valores financieros no se registran en consola | ✅ |

### Pendiente para Parte 10 (opcional)

- **RF-44 Reporte por rango de fechas**
- **RF-27B Certificado de disposición de material**
- QA general cruzando todos los módulos
- Gap heredado sin resolver: `authStore.initialize()` no restaura `user` en recarga de página (Parte 7)
- Gap heredado sin resolver: `TripDetailView.patch` no reversa `AdvanceMovement` al anular viaje con anticipo

---

## Parte 10 — Análisis: Ajustes Consulta de Viajes

### Entorno de backend — hallazgo importante

En partes anteriores (7–9) se había documentado que Django no estaba instalado localmente y que la base de datos (PostgreSQL) no era accesible desde este entorno, por lo que la verificación se hacía solo contra el backend ya corriendo en `localhost:8000` (proceso gestionado aparte). **Para esta parte se encontró un virtualenv en `C:\Proyectos\proyect-ingeomineria\venv` con Django 6.0.5 instalado y conectividad real a la base de datos** (`python manage.py check` → "System check identified no issues"). Esto permitió ejecutar `makemigrations`/`migrate` de verdad en esta parte, a diferencia de partes anteriores.

### Estado actual confirmado antes de modificar

- `Trip.date_register` (`apps/trips/models.py`): `models.DateField()`, sin `null`/`blank`/`default` — confirmado, se cambia únicamente el tipo a `DateTimeField()`.
- `TripReadSerializer` ya incluye `date_register` en `fields` (`apps/trips/serializers.py`) — DRF serializa `DateTimeField` automáticamente como ISO 8601, no requiere cambios en el serializer.
- `TripWriteSerializer` NO incluye `date_register` — se asigna únicamente server-side en la vista, nunca desde el cliente. Confirmado, sin cambios necesarios ahí.
- Migraciones existentes: `0001_initial` (creó `date_register` como `DateField`) y `0002_alter_trip_id_delete_transfer` (no relacionada). La nueva migración es `0003`.
- **Corrección al enunciado del prompt:** el código real no usa `timezone.now().date()` en ningún lado — usa el helper equivalente `timezone.localdate()` (idéntico en efecto: hoy en la zona horaria local configurada). `date_register` se asigna en un solo lugar de `views.py`: `TripListCreateView.post`, línea `date_register=timezone.localdate()` (dentro del `transaction.atomic()`, al crear el viaje).
- Comparaciones de "mismo día" contra `date_register` en `views.py` (`TripDetailView.patch`), dos ocurrencias, ambas con `timezone.localdate()`:
  1. RF-36 (cashier solo edita el día en curso): `if obj.date_register != timezone.localdate():`
  2. RF-37 (superusuario requiere justificación para ajustar histórico): `if request.user.role == 'superuser' and obj.date_register != timezone.localdate():`
- **Verificación empírica crítica antes de aplicar el fix:** en Python, `datetime.date(...) == datetime.datetime(...)` es **siempre `False`** aunque sea el mismo día — no lanza excepción, simplemente nunca son iguales (se confirmó con `python -c "..."`). Esto significa que sin corregir estas dos comparaciones, **ambas se habrían roto silenciosamente**: la comparación número 1 habría bloqueado a `cashier` de editar cualquier viaje (incluidos los del propio día), y la número 2 habría exigido justificación a `superuser` en el 100% de las ediciones, incluidas las del día en curso. No es un detalle cosmético — es una regresión funcional severa que el prompt ya anticipaba correctamente pedir corregir.
- El filtro `date` del `GET /api/trips/` ya opera sobre el campo `date` (fecha de negocio del viaje), **no** sobre `date_register` — confirmado, sin cambios.
- `TIME_ZONE = 'America/Bogota'` y `USE_TZ = True` en `settings.py` — Django guarda todo internamente en UTC y DRF serializa en UTC (`...Z`); por eso `formatTime()` en el frontend convierte explícitamente a `America/Bogota` en vez de confiar en la hora del navegador o del servidor.

### Cambios de backend aplicados

1. **Modelo** (`apps/trips/models.py`): `date_register = models.DateField()` → `date_register = models.DateTimeField()`. Ningún otro campo tocado.
2. **Migración**: generada con `python manage.py makemigrations trips --name="change_date_register_to_datetimefield"` → crea `0003_change_date_register_to_datetimefield.py`. Se verificó que la migración generada contiene **únicamente** una operación `AlterField` sobre `date_register` antes de aplicarla.
3. **Migración aplicada**: `python manage.py migrate` — ejecutada contra la base de datos real. Los viajes históricos ya existentes quedan con `date_register` a medianoche de su fecha original (verificado en navegador: se muestra consistentemente como "19:00" en hora de Bogotá — Postgres interpretó la fecha naive como medianoche UTC al convertir la columna, y UTC-5 desplaza esa medianoche al "19:00" del día anterior en hora local), ya que un `DateField` no tenía componente de hora que preservar. Esto es inevitable y se documenta como comportamiento esperado, no un bug — ningún viaje histórico tenía una hora real que recuperar.
4. **`views.py` — creación de viaje**: `date_register=timezone.localdate()` → `date_register=timezone.now()` en `TripListCreateView.post`.
5. **`views.py` — comparaciones de mismo día**: ambas ocurrencias listadas arriba cambiadas de `obj.date_register != timezone.localdate()` a `obj.date_register.date() != timezone.localdate()`.
6. **Ningún otro uso de `date_register` en el archivo quedó sin revisar** — confirmado con `grep -n "date_register\|timezone\." apps/trips/views.py`: solo 4 líneas en todo el archivo (el `order_by('-date_register')` del listado, que no necesita cambios porque ordenar por un `DateTimeField` funciona igual, y las 3 ya corregidas).
7. **Filtro `date` confirmado sin cambios** — sigue filtrando por el campo `date`, nunca por `date_register`.

### Verificación backend

- `python manage.py showmigrations trips` → las 3 migraciones (`0001`, `0002`, `0003`) aparecen aplicadas (`[X]`).
- Se registró un viaje de prueba nuevo (#1027) vía la UI real y se confirmó por API que `date_register` llega como datetime completo con offset explícito: `"2026-07-30T00:34:10.459975-05:00"`, no solo fecha.
- Viajes históricos muestran consistentemente "19:00" al formatear con `formatTime()` — consistente con lo documentado en el punto 3 de arriba.

### Cambios de frontend

**`formatTime()`** (`src/utils/formatDate.ts`): agregada tal como se especificó, usando timezone `America/Bogota` explícito — necesario porque el backend serializa en UTC y el navegador del usuario podría estar en cualquier zona horaria; forzar `America/Bogota` garantiza que la hora mostrada sea siempre la hora real de Bogotá sin depender de la configuración del dispositivo. Maneja `null`/`undefined`/parseo inválido devolviendo `'—'` sin lanzar excepción.

**`Trip` interface** (`src/types/index.ts`): sin cambio de tipo (sigue siendo `string`), se agregó el comentario aclaratorio pedido.

**Columna de Consulta de Viajes** (`GeneralReportPage.vue`, Parte 8): en vez de eliminar la entrada `date_register` de `COLUMN_CONFIG` y crear una nueva, se **reetiquetó la misma entrada** (mismo `key: 'date_register'`) de `label: 'Fecha de registro'` a `label: 'Hora'`, y su `cell`/`accessorFn` pasó de `formatDate` a `formatTime`. Mantener el mismo `key` (en vez de borrar+recrear) evita romper `columnVisibility`/`localStorage` (que indexan por `key`) y ya queda ubicada inmediatamente después de "Fecha del viaje" sin reordenar nada, porque esa ya era su posición. Se aplicó el mismo cambio de renderer en `exportGeneralQueryExcel.ts` y `printReport.ts` (encabezado "Fecha de registro" → "Hora", `formatDate` → `formatTime`).

**Rol `cashier` agregado a Consulta de Viajes:**
- `navigation.ts`: `'cashier'` agregado al array `roles` de la entrada `/reports/general`.
- `router/index.ts`: `'cashier'` agregado a `meta.allowedRoles` de la ruta `reports/general`.

**Restricción de columnas para `cashier` — ya implementada desde la Parte 8, verificada de nuevo:** `GeneralReportPage.vue` ya usaba exactamente el patrón pedido (`allowedKeys` computado por rol, usado tanto para las columnas de la tabla como para las opciones del dropdown "Columnas", y `sanitizeVisibility()` aplicado tanto al cargar `localStorage` como en cada cambio posterior). `cashier` no está en `RESTRICTED_ROLES`, así que ya solo veía las columnas `roles: 'all'` — no hizo falta tocar esa lógica, solo se sumó el rol a navegación/router para que pudiera llegar a la página.

### Verificación en navegador

**Nota sobre el entorno de pruebas:** otro chat ya tenía un servidor de desarrollo corriendo en el puerto 5173 (el único origen permitido en `CORS_ALLOWED_ORIGINS` del backend). Para esta parte se levantó una instancia propia del frontend en el puerto 5199 (`.claude/launch.json` actualizado con `--port 5199 --strictPort` tras comprobar que el mecanismo `autoPort` del harness no es compatible con el propio fallback de puertos de Vite) y se agregó `http://localhost:5199` a `CORS_ALLOWED_ORIGINS` **temporalmente**, solo para poder ejecutar las pruebas contra el backend real. Esa línea se revirtió (`git diff` limpio en `settings.py`) inmediatamente después de terminar la verificación.

Probado en vivo contra el backend real con usuario `admin` (`superuser`):
- Se registró un viaje nuevo real (**#1027**, `id` real `27`) vía el formulario de `/trips` — el campo "Fecha" de la tabla "Viajes de hoy" mostró `30/07/2026` (fecha formateada), **no** el datetime ISO crudo, confirmando el fix en `TripsPage.vue`
- Confirmado por API (`fetch` directo con el token de sesión) que `date_register` del viaje nuevo es un datetime completo: `"2026-07-30T00:34:10.459975-05:00"`
- En **Consulta de Viajes**: la columna "Hora" aparece inmediatamente después de "Fecha del viaje", muestra `00:34` para el viaje nuevo y `19:00` para todos los viajes históricos (artefacto esperado de la migración, ver arriba); el dropdown "Columnas" y el filtro inline bajo el header también muestran la etiqueta "Hora" (no quedó ningún rastro de "Fecha de registro")
- "Exportar Excel" y "Exportar PDF" desde Consulta de Viajes ejecutados sin errores de consola
- En **Reporte Diario**: la columna "Hora registro" ahora muestra `00:34` en vez de una fecha — el encabezado por fin coincide con el dato mostrado
- En **Ajustes del Día**: se abrió el editor del viaje `#1027` (creado hoy) como `superuser` y **no** apareció el campo "Justificación" (`editRequiresJustification` correctamente `false`); se guardó un cambio real (`N° Vale externo`) y la petición `PATCH /api/trips/27/` devolvió `200 OK` sin exigir justificación — confirma en conjunto el fix del frontend (`AdjustmentsPage.vue`) y el del backend (`obj.date_register.date() != timezone.localdate()`) trabajando juntos correctamente. Antes de estos dos fixes, esta misma acción habría fallado (o habría exigido justificación indebidamente) para cualquier viaje, incluidos los del propio día
- Sin errores de consola en ningún punto de las pruebas

**No verificado con `cashier` real** (misma limitación de credenciales de partes anteriores: existe `cajero1` en el entorno pero sin contraseña disponible). El acceso de `cashier` a `/reports/general` se verificó por inspección de código (roles agregados en `navigation.ts` y `router/index.ts`) y por el hecho de que la lógica de restricción de columnas —ya usada y probada desde la Parte 8— es agnóstica al rol específico, solo depende de si el rol aparece en `RESTRICTED_ROLES`.

**Dato de prueba real, no descartable:** el viaje `#1027` (placa `DTT999`) y su edición (`N° Vale externo = "TESTOK"`) son resultado de ejercitar la funcionalidad real, igual que en partes anteriores — no se revirtieron.

### Módulos revisados por impacto (`date_register`)

| Archivo | Uso encontrado | Acción |
|---|---|---|
| `TripsPage.vue` (tabla "Viajes de hoy", líneas ~759, y drawer de detalle ~827/842) | Interpolación **directa sin formatear**: `{{ trip.date_register }}` bajo una columna/etiqueta llamada "Fecha" | **Corregido** — envuelto en `formatDate()` para seguir mostrando solo la fecha (la etiqueta dice "Fecha", no "Hora"; no se agregó columna de hora nueva porque no fue pedida para esta página). Sin el fix, tras la migración se vería el datetime ISO crudo en pantalla |
| `AdjustmentsPage.vue` (línea 97, `editRequiresJustification`) | `editTrip.value.date_register !== today` — comparación de mismo día en frontend | **Corregido** a `editTrip.value.date_register.split('T')[0] !== today`. Sin este fix, la comparación de string siempre sería `true` (longitudes distintas), forzando justificación obligatoria en **todos** los ajustes de superusuario, incluso los del propio día — regresión real, no cosmética |
| `DailyReportPage.vue` (Parte 7, columna "Hora registro") | Ya estaba etiquetada "Hora registro" pero renderizaba con `formatDate()` porque no existía dato de hora real (limitación documentada en la Parte 7) | **Corregido** a `formatTime()` — ahora la columna cumple lo que su propio encabezado siempre dijo |
| `exportDailyReportExcel.ts` / `printDailyReport.ts` (Parte 7) | Encabezado "Fecha registro" con `formatDate(t.date_register)` en la hoja/tabla de viajes | **Corregido** — encabezado renombrado a "Hora registro" y valor con `formatTime()`, consistente con el cambio de `DailyReportPage.vue` |
| `printVoucher.ts` (vale impreso al registrar un viaje) | `format(parseISO(trip.date_register), 'dd/MM/yyyy')` | **Sin cambios necesarios** — `parseISO` interpreta igual de bien un datetime ISO completo que una fecha sola, y el formato de salida `'dd/MM/yyyy'` solo usa la porción de fecha; sigue funcionando sin tocar nada |
| `CashClosingPage.vue` | Ningún uso de `date_register` (usa `cashClosingApi.today()`, que no expone ese campo) | **Sin impacto**, confirmado por búsqueda exhaustiva |
| `AuditLogPage.vue` (`FIELD_LABEL['date_register']`) | Etiqueta genérica para el visor de diffs del log de auditoría, aplicable a cualquier entidad | **No tocado** — es el módulo de Auditoría, explícitamente prohibido de modificar en esta parte. El diff ahora mostrará el datetime crudo como texto en vez de solo la fecha para los registros de `Trip`; funcional pero no especialmente formateado. Documentado como limitación conocida, no corregido por estar fuera de alcance |
| `DashboardPage.vue` (Parte 9, "Últimos viajes registrados hoy") | Columna ya etiquetada "Hora" pero renderizada con `formatDate()` (mismo compromiso documentado en la Parte 9 por falta de dato de hora real) | **No tocado** — el módulo Dashboard está explícitamente prohibido de modificar en esta parte, aunque ahora técnicamente podría mostrar la hora real. Queda como mejora obvia pendiente para una futura parte |
| `types/index.ts` → `PinsDumper.date_register` | Campo homónimo de un modelo **distinto** (`PinsDumper`, no `Trip`) | **No relacionado, no tocado** |
| `PinsPage.vue` | Usa `date_register` de `PinsDumper`, no de `Trip` | **No relacionado, no tocado** |

### Seguridad

| Medida | Estado |
|--------|--------|
| Restricción de columnas para `cashier` aplicada a nivel de `computed` (`allowedKeys`), nunca vía CSS | ✅ Ya existía desde la Parte 8, confirmado de nuevo |
| `localStorage` de columnas saneado contra el rol actual al montar | ✅ Ya existía desde la Parte 8 (`sanitizeVisibility` en `loadInitialVisibility`) |
| `formatTime()` nunca lanza excepción — devuelve `'—'` ante entrada inválida | ✅ |
| Migración de backend verificada (formato datetime real en la API) antes de dar por buenos los cambios de frontend | ✅ Confirmado con una prueba real de creación de viaje |
| Comparaciones de mismo día en backend usan `.date()` sobre el datetime | ✅ Ambas ocurrencias en `views.py` corregidas |
| Ningún campo del modelo `Trip` distinto a `date_register` fue modificado | ✅ |
| Sin `console.log` en el código final | ✅ |

### Pendiente

- Actualizar `DashboardPage.vue` para que su columna "Hora" use `formatTime()` en vez de `formatDate()` ahora que el dato real existe — no se hizo en esta parte por estar el módulo Dashboard explícitamente fuera de alcance
- `AuditLogPage.vue`: el diff de auditoría muestra el datetime crudo sin formatear para cambios en `Trip.date_register` — cosmético, no bloqueante
- RF-44 Reporte por rango de fechas
- RF-27B Certificado de disposición de material
- **No verificado con `cashier` real:** existe un usuario `cajero1` en el entorno de prueba pero no se dispuso de su contraseña; la ocultación de la columna "Valor" y de "Anticipos consumidos" se verificó por lógica de código (mismo patrón que `TripsPage.vue`) y en navegador solo para `superuser`
