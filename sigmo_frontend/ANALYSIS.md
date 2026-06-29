# Backend Analysis — SIGMO

## Framework & Structure

- **Framework:** Django 6.0.5 + Django REST Framework 3.x + SimpleJWT
- **Database:** PostgreSQL
- **Auth:** JWT via `rest_framework_simplejwt`
- **Structure:** Monorepo with Django apps under `apps/`: users, clients, masters, trips, advances, expenses, invoices, cash_closing, audit

## JWT Configuration

- Algorithm: HS256
- Access token lifetime: **8 hours** (RF-06B)
- Refresh token lifetime: 1 day, with rotation
- Header: `Authorization: Bearer <token>`
- Auth header type: `Bearer`

## JWT Payload Fields (SimpleJWT defaults)

SimpleJWT encodes the Django user `id` (int) in the `user_id` claim. The frontend reads the `user` object returned by the login endpoint response body (not from the JWT payload directly).

Login response shape:
```json
{
  "access": "<JWT>",
  "refresh": "<JWT>",
  "user": {
    "id": 1,
    "name": "...",
    "email": "...",
    "username": "...",
    "role": "superuser",
    "role_display": "Superusuario",
    "state": true
  }
}
```

## Roles (exact strings in DB/JWT)

| Key              | Value              | Display                  |
|------------------|--------------------|--------------------------|
| SUPERUSER        | `superuser`        | Superusuario             |
| COMMERCIAL_ADMIN | `commercial_admin` | Administrador Comercial  |
| CASHIER          | `cashier`          | Operador de Caja         |
| ACCOUNTANT       | `accountant`       | Contador                 |
| AUDITOR          | `auditor`          | Auditor                  |

## Login Logic (RF-03)

- Lockout key stored in Django cache (in-memory `LocMemCache`)
- After **10 failed attempts** → account locked for **15 minutes**
- Locked response: HTTP 429 with `{ "error": "Cuenta bloqueada..." }`
- Failed auth response: HTTP 401 with `{ "error": "Credenciales incorrectas. Intentos fallidos: N/10." }`
- Inactive user response: HTTP 403

## All Endpoints Consumed by the Frontend

| Method | Path                              | Purpose                              |
|--------|-----------------------------------|--------------------------------------|
| POST   | /api/users/login/                 | Login — returns access+refresh+user  |
| POST   | /api/users/logout/                | Logout (logs audit event)            |
| POST   | /api/users/change-password/       | Change own password                  |
| GET    | /api/clients/                     | List clients (filter: name, nit, state) |
| POST   | /api/clients/                     | Create client                        |
| GET    | /api/clients/{id}/                | Get client detail                    |
| PATCH  | /api/clients/{id}/                | Update client (NIT stripped server-side) |
| GET    | /api/masters/material-types/      | List material types                  |
| POST   | /api/masters/material-types/      | Create material type                 |
| PATCH  | /api/masters/material-types/{id}/ | Update material type                 |
| GET    | /api/masters/vehicle-types/       | List vehicle types                   |
| POST   | /api/masters/vehicle-types/       | Create vehicle type                  |
| PATCH  | /api/masters/vehicle-types/{id}/  | Update vehicle type                  |
| GET    | /api/masters/vehicles/            | List vehicles (filter: plaque)       |
| POST   | /api/masters/vehicles/            | Create vehicle                       |
| GET    | /api/masters/payment-methods/     | List payment methods                 |
| POST   | /api/masters/payment-methods/     | Create payment method                |
| PATCH  | /api/masters/payment-methods/{id}/| Update payment method                |
| GET    | /api/masters/origin-sites/        | List origin sites                    |
| POST   | /api/masters/origin-sites/        | Create origin site                   |
| PATCH  | /api/masters/origin-sites/{id}/   | Update origin site                   |
| GET    | /api/masters/tariffs/             | List tariffs (filter: client)        |
| POST   | /api/masters/tariffs/             | Create tariff                        |
| PATCH  | /api/masters/tariffs/{id}/        | Update tariff (closes old, creates new) |
| GET    | /api/masters/pins/                | List pins (filter: plaque)           |
| POST   | /api/masters/pins/                | Create pin manually                  |
| POST   | /api/masters/pins/import/         | Import pins from .xlsx/.csv          |

## Missing / Partial Endpoints

- `GET /api/clients/?nit=X&state=all` — The backend filters `state` only if provided. Passing `state=all` falls through to the `else` clause which only shows active. To get all records (for NIT uniqueness check), the frontend passes `state=all` which the backend ignores (no `all` case) and returns only active. **Workaround:** frontend checks the returned list for duplicates; the backend also validates NIT uniqueness server-side and returns a 400 error on create.
- `GET /api/clients/check-nit/` — **Does not exist in the backend.** NIT uniqueness is enforced server-side on POST validation. The frontend implements client-side duplicate detection by querying the list endpoint with the NIT filter. Noted in: composable placeholder not needed since we use list endpoint directly.
- `PATCH /api/masters/pins/{id}/` — **No detail view for pins in the backend URLs.** The `PinsDumperImportView` handles bulk updates via import. Manual per-record edit/activate/deactivate is not available via API. Frontend hides edit and toggle actions for pins.
- `PATCH /api/masters/vehicles/{id}/` — No vehicle detail view. Vehicles cannot be edited or toggled once created. Frontend hides edit/toggle actions.

## Validation Rules Discovered

### Clients
- NIT: unique, normalized (spaces and hyphens stripped server-side), max 15 chars
- Phone: must be positive decimal (stored as DECIMAL(10,0))
- NIT cannot be changed on PATCH (server strips it from data)

### Vehicle Types
- Name: unique case-insensitive
- Capacity: positive decimal > 0
- Cannot deactivate if vehicles are associated

### Materials
- Name: unique case-insensitive

### Payment Methods
- Cannot deactivate the last active payment method (HTTP 400)
- `is_advance` flag: cannot be changed after creation (business rule)

### Tariffs
- Value must be > 0
- PATCH closes old tariff (sets end_date = today, state = false) and creates a new one atomically
- `client` is nullable (null = general tariff)

### Pins
- Plaque: forced uppercase (max 6 chars)
- Import: matches on (plaque + ambiental_pin), upserts if found

### Vehicles
- Plaque: unique, uppercase
- Cannot assign inactive vehicle type

## Security Decisions

### Token Storage
JWT stored in `localStorage` (key: `sigmo_token`). HttpOnly cookies were not chosen because:
1. The auth store is frontend-controlled and needs to read the token synchronously on app load.
2. The backend does not set cookies — it returns tokens in the response body.
3. No XSS vectors exist in this SPA (no v-html with user data, no dynamic script injection).

### CSRF
Not applicable. The backend uses stateless JWT authentication. Django's CSRF middleware applies only to session-based views, not to DRF JWT endpoints.

### Token Expiry on App Load
The app decodes the JWT payload (base64) and checks the `exp` claim on every page load via `authStore.initialize()`. If expired, the session is cleared.
