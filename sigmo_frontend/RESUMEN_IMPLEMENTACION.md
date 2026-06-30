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
