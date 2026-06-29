# Resumen de Implementación — SIGMO Frontend — Parte 2

Cubre las 3 tareas completadas en la segunda sesión de desarrollo:
navegación centralizada, módulo de Anticipos y módulo de Facturación.

---

## Contexto de partida

Al inicio de esta sesión existían los módulos de **Autenticación** y **Maestros** (Clientes, Materiales, Vehículos, Medios de Pago, Tarifas, Pines, Orígenes). El frontend compilaba sin errores y se comunicaba correctamente con el backend Django.

---

## Task 1 — Navegación centralizada + Sidebar colapsable

### Problema resuelto

El sidebar anterior no tenía estructura de grupos, no colapsaba y los permisos de visibilidad estaban dispersos. No existía un solo lugar donde definir qué rutas existen en el sistema.

### Archivos creados / modificados

#### `src/constants/navigation.ts` _(nuevo)_
Fuente única de verdad para todas las rutas de la aplicación. Define la estructura de árbol con dos tipos:
- `NavLeaf` — ruta hoja con `path`, `icon`, `label` y `roles` permitidos
- `NavGroup` — grupo con `children: NavLeaf[]`

Estructura completa:
```
Dashboard        → /                              (todos los roles)
Operación        → grupo
  Registro Viajes  → /trips                       (superuser, cashier)
  Ajustes del Día  → /trips/adjustments           (superuser, cashier, commercial_admin)
  Cierre de Caja   → /cash-closing                (superuser, cashier)
Clientes         → /masters/clients               (superuser, commercial_admin, accountant, auditor)
Maestros         → grupo
  Materiales       → /masters/materials           (superuser, commercial_admin, auditor)
  Vehículos        → /masters/vehicles            (superuser, commercial_admin, auditor)
  Medios de Pago   → /masters/payment-methods     (superuser, commercial_admin, auditor)
  Tarifas          → /masters/tariffs             (superuser, commercial_admin, auditor)
  Pines            → /masters/pins                (superuser, commercial_admin, auditor)
  Orígenes         → /masters/origins             (superuser, commercial_admin, cashier, auditor)
Finanzas         → grupo
  Anticipos        → /advances                    (superuser, accountant, commercial_admin)
  Facturación      → /invoicing                   (superuser, accountant)
  Gastos           → /expenses                    (superuser, cashier, commercial_admin)
Reportes         → grupo
  General          → /reports/general             (superuser, commercial_admin, accountant, auditor)
  Diario           → /reports/daily               (todos)
  Por Rango        → /reports/range               (superuser, commercial_admin, accountant, auditor)
Administración   → grupo
  Usuarios         → /admin/users                 (superuser)
  Log de Auditoría → /admin/audit-log             (superuser, auditor)
```

#### `src/composables/useNavigation.ts` _(nuevo)_
- `visibleNav: ComputedRef<NavItem[]>` — filtra el árbol de navegación según el rol del usuario autenticado. Los grupos aparecen solo si al menos un hijo es visible.
- `isLeafVisible(path: string): boolean` — recorre el árbol y retorna si la ruta existe y el rol del usuario tiene acceso.

#### `src/composables/usePermissions.ts` _(actualizado)_
- Añadida función `canAccess(path: string): boolean` que delega a `useNavigation().isLeafVisible()`.

#### `src/components/layout/Sidebar.vue` _(reescrito)_
Sidebar con las siguientes características:
- **Expandido (240px) / Colapsado (64px)** — transición CSS `transition-all duration-300`
- **Grupos colapsables** con animación `max-height` y chevron rotado 180° al abrir
- **Auto-expansión** del grupo que contiene la ruta activa, tanto al cargar como en cada cambio de ruta (watcher en `route.path`)
- **Estado activo** en la hoja seleccionada y en el header del grupo cuando un hijo está activo
- **Modo colapsado**: solo íconos con tooltip nativo `title` al hover. Los grupos se pueden expandir incluso colapsados mostrando solo íconos de los hijos debajo del grupo.
- Ninguna lógica de roles en el componente — todo viene de `visibleNav` de `useNavigation()`
- Botón de logout y botón colapsar/expandir al pie del sidebar

#### `src/router/index.ts` _(reescrito)_
- Importaciones separadas: `vue-router` para `createRouter`/`createWebHistory`, sin mezclar con `vue`
- Componente `UnderConstruction` inline como placeholder para módulos no implementados aún
- Rutas añadidas con `allowedRoles` correctos según `navigation.ts`:
  - `/trips`, `/trips/adjustments`, `/cash-closing` (Operación)
  - `/advances`, `/invoicing`, `/expenses` (Finanzas)
  - `/reports/general`, `/reports/daily`, `/reports/range` (Reportes)
  - `/admin/users`, `/admin/audit-log` (Administración)
- Las rutas de `/advances` e `/invoicing` apuntan a los componentes reales (construidos en Task 2 y 3)
- Guard `beforeEach` con tipos explícitos `RouteLocationNormalized` y `NavigationGuardNext`

---

## Task 2 — Módulo de Anticipos (`/advances`)

### Análisis del backend realizado

Endpoints disponibles en `apps/advances/`:

| Método | URL | Descripción | Roles |
|--------|-----|-------------|-------|
| GET | `/api/advances/` | Lista todos, filtrable `?client=` | todos autenticados |
| POST | `/api/advances/` | Crea anticipo + movimiento inicial | superuser, accountant, commercial_admin |
| GET | `/api/advances/{id}/` | Detalle | todos autenticados |
| PATCH | `/api/advances/{id}/` | Editar | solo superuser |
| GET | `/api/advances/balance/{client_id}/` | Suma saldos disponibles del cliente | todos autenticados |

**Estructura del response de `AdvanceSerializer`:**
```json
{
  "id": 1,
  "client": 1,
  "client_detail": { /* objeto Client completo */ },
  "user": 1,
  "value": "1000000.00",
  "transfer_num": 12345,
  "date": "2024-01-15",
  "proforma_number": null,
  "observations": null,
  "available_balance": 800000.0,
  "movements": [
    {
      "id": 1,
      "advance": 1,
      "trip": null,
      "type_movement": "ingreso",
      "amount": "1000000.00",
      "trips_quantity": 0,
      "date": "2024-01-15",
      "description": "Anticipo registrado. Ref: 12345"
    }
  ]
}
```

**Cálculo de `available_balance`:** calculado en el backend (sum ingresos − sum egresos de movimientos).

**Decisión de diseño:** los movimientos vienen embebidos en cada `Advance`, por lo que un solo `GET /api/advances/` entrega todo lo necesario para las tres pestañas — sin requests adicionales por cliente ni por movimiento.

**Modificación al backend realizada:**
- `apps/advances/views.py`: el campo `trips_quantity` del movimiento inicial estaba hardcodeado a `0`. Se modificó para leerlo del request (`int(request.data.get('trips_quantity', 0))`), con validación de tipo y límite mínimo en 0. El cambio es backward-compatible.

### Archivos creados / modificados

#### `src/types/index.ts`
Tipos añadidos:
```typescript
interface AdvanceMovement {
  id: number; advance: number; trip: number | null
  type_movement: 'ingreso' | 'egreso'
  amount: string; trips_quantity: number; date: string; description: string | null
}
interface Advance {
  id: number; client: number; client_detail: Client; user: number
  value: string; transfer_num: number; date: string
  proforma_number: number | null; observations: string | null
  available_balance: number; movements: AdvanceMovement[]
}
interface AdvanceBalance { client_id: number; balance: number }
```

#### `src/api/advances.api.ts` _(nuevo)_
```typescript
advancesApi.list(params?)       // GET /advances/ con ?client opcional
advancesApi.create(data)        // POST /advances/
advancesApi.update(id, data)    // PATCH /advances/{id}/
advancesApi.balance(clientId)   // GET /advances/balance/{id}/
```
El `create` acepta `trips_quantity?: number` (campo nuevo en el backend).

#### `src/pages/advances/AdvancesPage.vue` _(nuevo)_

**Panel de alertas**
- Calcula el saldo total por cliente sumando `available_balance` de todos sus anticipos
- Muestra banner rojo `AlertTriangle` por cada cliente con saldo negativo
- Cada alerta es descartable individualmente (botón ×)
- Se actualiza en cada refetch automático (cada 60 segundos)

**Tab 1 — Registro de Anticipos**
- Tabla con columnas: Fecha, Cliente, Valor, N° Consignación, N° Proforma, Saldo Disponible
- Saldo Disponible con color dinámico: verde > 0, rojo < 0, gris = 0
- Columna de acciones: ícono ojo (todos los roles) abre el panel de detalle; ícono lápiz (solo superuser) abre el modal de edición
- Formulario (modal) con VeeValidate + Zod:
  - Cliente (select, solo en creación)
  - Fecha (date input, default hoy)
  - Valor (CurrencyInput en COP)
  - N° Consignación (integer > 0)
  - N° de Viajes (integer ≥ 0, solo en creación, opcional, default 0)
  - N° Proforma (integer, opcional)
  - Observaciones (textarea, opcional)
- En edición: cliente se muestra como texto no editable; N° Viajes no aparece (pertenece al movimiento inicial ya creado)

**Tab 2 — Estado de Cuenta por Cliente**
- Selector de cliente
- Tres cards: Total Ingresado (verde), Total Consumido (rojo), Saldo Disponible (azul/rojo)
- Tabla "Anticipos registrados" con saldo de cada anticipo y botón ojo para detalle
- Tabla "Historial de movimientos" con badge de tipo ingreso/egreso
- Botón "Exportar CSV" genera archivo con BOM UTF-8 (apertura directa en Excel)

**Tab 3 — Historial de Movimientos**
- Filtros: cliente + fecha desde/hasta + botón limpiar
- Tabla completa: Fecha, Cliente, Anticipo ID, Tipo (badge), Valor, Viajes, Descripción, Viaje N°
- Botón "Exportar CSV" exporta los datos filtrados

**Panel de detalle (drawer lateral)**
- Se abre al hacer clic en el ícono ojo de cualquier fila (Tab 1 y Tab 2)
- Overlay semitransparente con clic para cerrar
- Muestra: nombre del cliente, fecha, valor, N° consignación, N° proforma, saldo disponible (con color), observaciones (siempre visibles en un cuadro gris), lista de movimientos ordenados por fecha
- Cada movimiento muestra: tipo (badge verde/rojo), valor, fecha, descripción, viajes y N° de viaje si aplica
- Botón "Editar" (solo superuser) que cierra el drawer y abre el modal de edición

**Consulta con refetchInterval:** el query de anticipos se refresca automáticamente cada 60 segundos, lo que mantiene el panel de alertas actualizado sin intervención del usuario.

---

## Task 3 — Módulo de Facturación (`/invoicing`)

### Análisis del backend realizado

Endpoints disponibles en `apps/invoices/`:

| Método | URL | Descripción | Roles |
|--------|-----|-------------|-------|
| GET | `/api/invoices/` | Lista todas las facturas | todos autenticados |
| POST | `/api/invoices/` | Crea una factura | superuser, accountant |
| GET | `/api/invoices/{id}/` | Detalle | todos autenticados |

**Modelo Invoice** (minimalista):
```python
class Invoice(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, ...)
    number = models.CharField(max_length=15)
```
Solo tiene número de referencia — sin fecha, sin cliente, sin monto. El vínculo con los viajes se establece por el FK `invoice` en el modelo `Trip`.

Filtros disponibles en `GET /api/trips/`:
- `?client=`, `?date=`, `?date_from=`, `?date_to=`, `?state=`, `?invoice=`

**Hallazgo crítico — campo `invoice` ausente en TripWriteSerializer:**
El serializer de escritura `TripWriteSerializer` no incluía `invoice` ni `invoice_pos`. Sin este cambio era imposible asignar una factura a un viaje vía PATCH.

**Modificación al backend realizada:**
- `apps/trips/serializers.py`: añadidos `'invoice'` e `'invoice_pos'` a `TripWriteSerializer.Meta.fields`. El cambio es backward-compatible (campos opcionales en PATCH parcial).

**Flujo de asignación:**
1. Frontend obtiene todos los viajes (`GET /api/trips/`)
2. Filtra client-side: pendientes = `state=true AND invoice=null`, facturados = `invoice !== null`
3. Usuario selecciona viajes con checkboxes
4. Modal: elige crear factura nueva (`POST /api/invoices/`) o seleccionar una existente
5. En paralelo (`Promise.all`): `PATCH /api/trips/{id}/` para cada viaje, asignando `invoice_id` e `invoice_pos` secuencial (1, 2, 3…)

### Archivos creados / modificados

#### `src/types/index.ts`
Tipos añadidos:
```typescript
interface Invoice { id: number; user: number; number: string }

interface Trip {
  id: number; voucher_num: number; date: string; date_register: string
  value: string; extern_voucher_num: string | null; invoice_pos: number | null
  certification_state: boolean | null; certification_num: string | null
  state: boolean; client_detail: Client; payment_detail: PaymentMethod
  vehicle_detail: Vehicle; material_type_detail: MaterialType
  origin_site_detail: OriginSite; advance: number | null
  invoice: number | null; summary: number | null
}
```

#### `src/api/invoices.api.ts` _(nuevo)_
```typescript
invoicesApi.list()              // GET /invoices/
invoicesApi.create({ number })  // POST /invoices/
invoicesApi.detail(id)          // GET /invoices/{id}/
```

#### `src/api/trips.api.ts` _(nuevo)_
```typescript
tripsApi.list(params?)          // GET /trips/ con filtros opcionales
tripsApi.patch(id, data)        // PATCH /trips/{id}/ — acepta invoice, invoice_pos, state, justification
```

#### `src/pages/invoicing/InvoicingPage.vue` _(nuevo)_

**Tab "Pendientes de Facturar"**
- Tabla HTML nativa (no DataTable) para tener control total sobre checkboxes y estilos de selección
- Clic en cualquier parte de la fila alterna la selección; clic en el header del checkbox selecciona/deselecciona todo
- Filas seleccionadas con fondo azul claro
- Ordenamiento manual por columna (Voucher, Fecha, Cliente, Valor) con indicador de dirección (ChevronUp/Down)
- Filtros: cliente + fecha desde/hasta
- Badge en la pestaña con el total de viajes pendientes
- Skeleton de carga animado (5 filas × 7 columnas) mientras llegan los datos
- Estado vacío con mensaje descriptivo

**Footer flotante de selección**
- Aparece/desaparece con animación `slide-up` (CSS transition)
- Muestra: conteo de viajes seleccionados, total en COP
- Botón "Limpiar selección" y botón "Asignar Factura" (solo superuser/accountant)
- La selección se limpia automáticamente al cambiar los filtros

**Modal "Asignar Factura"**
- Header: título + resumen (N viajes — total en COP)
- Selector de modo con "radio cards" visuales:
  - **Nueva factura**: input texto con validación (requerido, máx 15 chars)
  - **Factura existente**: select de facturas previamente creadas
- Lista scrollable de viajes seleccionados con número de posición, N° voucher, cliente y valor
- Al confirmar: crea la factura si es nueva → PATCH todos los viajes en paralelo
- Invalida los queries `['trips']` e `['invoices']` al completarse exitosamente
- Toast de éxito con conteo de viajes asignados
- Manejo diferenciado de errores de validación (no muestra toast, solo el error inline)

**Tab "Registros Facturados"**
- Filtro adicional: selector de factura específica
- DataTable con columnas: N° Voucher, Fecha, Cliente, N° Factura (texto azul), Posición, Valor, Vehículo, Medio de Pago
- N° Factura resuelto a texto: busca en la lista de facturas cargadas por `invoice_id`

---

## Cambios al Backend (resumen)

| Archivo | Cambio | Motivo |
|---------|--------|--------|
| `apps/advances/views.py` | Lee `trips_quantity` del request al crear el movimiento inicial del anticipo | El campo estaba hardcodeado a `0`; ahora es configurable desde el formulario |
| `apps/trips/serializers.py` | Añade `invoice` e `invoice_pos` a `TripWriteSerializer.fields` | Sin este campo era imposible asignar una factura a un viaje vía PATCH |

Ambos cambios son **backward-compatible**: los campos son opcionales en PATCH y tienen valores por defecto si no se envían.

---

## Decisiones técnicas tomadas en esta sesión

| Decisión | Justificación |
|----------|---------------|
| Movimientos embebidos en cada Advance | El serializer del backend ya los incluye → un solo query cubre las tres pestañas sin N+1 |
| Balance de clientes calculado client-side | Evita N peticiones a `/advances/balance/{id}/` por cada cliente; se computa de los datos ya en caché |
| Tabla HTML nativa en Tab 1 de Facturación | DataTable genérico no soporta checkboxes por diseño; la tabla nativa da control total sobre selección y estilos por fila |
| `Promise.all` para asignación masiva de facturas | Paralelismo en el PATCH de cada viaje; el backend acepta PATCH parcial, cada operación es independiente |
| `invoice_pos` asignado secuencialmente | Posición 1…N según el orden de selección del usuario; el backend lo acepta como campo nullable opcional |
| CSV con BOM UTF-8 (`'﻿'`) | Excel en Windows interpreta el BOM y abre el CSV sin diálogo de importación ni caracteres corruptos |
| Drawer lateral (no modal) para detalle de anticipo | El detalle incluye una lista de movimientos que puede ser larga; el drawer permite scroll sin bloquear la tabla |
| Refetch automático cada 60s en Anticipos | Los saldos cambian cuando se registran viajes desde otro usuario; el panel de alertas se mantiene actualizado |
| Selección limpiada al cambiar filtros (Facturación) | Evita asignar factura a viajes que ya no son visibles en la lista filtrada |

---

## Estructura de archivos generados (Parte 2)

```
sigmo_frontend/src/
├── constants/
│   └── navigation.ts          ← árbol de navegación con roles
├── composables/
│   ├── useNavigation.ts       ← visibleNav + isLeafVisible
│   └── usePermissions.ts      ← añadido canAccess()
├── components/layout/
│   └── Sidebar.vue            ← reescrito: colapsable, grupos animados
├── router/
│   └── index.ts               ← reescrito: todas las rutas con allowedRoles
├── types/
│   └── index.ts               ← añadidos Invoice, Trip, Advance, AdvanceMovement, AdvanceBalance
├── api/
│   ├── advances.api.ts        ← nuevo
│   ├── invoices.api.ts        ← nuevo
│   └── trips.api.ts           ← nuevo
└── pages/
    ├── advances/
    │   └── AdvancesPage.vue   ← nuevo (3 tabs + drawer + alertas)
    └── invoicing/
        └── InvoicingPage.vue  ← nuevo (2 tabs + multi-select + modal)
```

---

## Estado del sistema al final de la Parte 2

### Módulos completamente funcionales

| Módulo | Ruta | Estado |
|--------|------|--------|
| Login | `/login` | Completo |
| Clientes | `/masters/clients` | Completo |
| Materiales | `/masters/materials` | Completo |
| Vehículos | `/masters/vehicles` | Completo |
| Medios de Pago | `/masters/payment-methods` | Completo |
| Tarifas | `/masters/tariffs` | Completo |
| Pines Ambientales | `/masters/pins` | Completo |
| Orígenes | `/masters/origins` | Completo |
| Anticipos | `/advances` | Completo |
| Facturación | `/invoicing` | Completo |

### Módulos con placeholder (en construcción)

| Módulo | Ruta | Pendiente |
|--------|------|-----------|
| Registro de Viajes | `/trips` | Formulario de registro, cálculo de tarifa automático |
| Ajustes del Día | `/trips/adjustments` | Edición y anulación de viajes del día |
| Cierre de Caja | `/cash-closing` | Apertura/cierre, resumen del día |
| Gastos | `/expenses` | Registro y consulta de gastos operativos |
| Reporte General | `/reports/general` | Reporte consolidado por período |
| Reporte Diario | `/reports/daily` | Resumen del día en curso |
| Reporte por Rango | `/reports/range` | Filtro por fechas y exportación |
| Gestión de Usuarios | `/admin/users` | CRUD de usuarios, asignación de roles |
| Log de Auditoría | `/admin/audit-log` | Visualización de acciones del sistema |

### Próximas sugerencias

1. **Viajes** es el módulo central del sistema (es el origen de los movimientos de anticipo y de los registros a facturar). Es el siguiente módulo recomendado.
2. Implementar **refresh token silencioso** antes de que el sistema entre en producción (el token de acceso expira a las 8h sin renovación automática).
3. Considerar un endpoint `GET /api/trips/?invoice__isnull=true` en el backend para evitar cargar todos los viajes cuando el volumen sea alto.
4. Agregar `GET/PATCH /api/masters/pins/{id}/` y `PATCH /api/masters/vehicles/{id}/` para habilitar edición individual en esos módulos.
