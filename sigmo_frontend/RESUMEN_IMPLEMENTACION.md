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

### Mejoras técnicas sugeridas antes de continuar
- Agregar endpoint `GET /api/masters/pins/{id}/` y `PATCH` en el backend para habilitar edición individual de pines
- Agregar endpoint `PATCH /api/masters/vehicles/{id}/` para edición y toggle de vehículos
- Implementar refresh token automático (actualmente el token de 8h expira sin renovación silenciosa)
- Considerar paginación server-side para clientes y tarifas cuando el volumen crezca
- Agregar tests con Vitest + Vue Test Utils para los composables críticos (useAuth, usePermissions)
