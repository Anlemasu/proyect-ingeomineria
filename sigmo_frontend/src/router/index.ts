import { defineComponent, h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationNormalized, NavigationGuardNext } from 'vue-router'
import { useAuthStore } from '@/stores/auth.store'
import { getAllowedRoles } from '@/constants/navigation'

const UnderConstruction = defineComponent({
  props: { module: { type: String, default: 'Módulo' } },
  setup(props) {
    return () => h('div', { class: 'flex items-center justify-center h-64 text-gray-400 text-sm' },
      `${props.module} — en construcción`)
  },
})

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/auth/LoginPage.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/unauthorized',
      name: 'unauthorized',
      component: () => import('@/pages/UnauthorizedPage.vue'),
    },
    {
      path: '/',
      component: () => import('@/components/layout/AppShell.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('@/pages/DashboardPage.vue'),
        },

        // ── Operación ──────────────────────────────────────────────────────────
        {
          path: 'trips',
          name: 'trips',
          component: () => import('@/pages/trips/TripsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'trips/adjustments',
          name: 'trips-adjustments',
          component: () => import('@/pages/trips/AdjustmentsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'cash-closing',
          name: 'cash-closing',
          component: () => import('@/pages/cash-closing/CashClosingPage.vue'),
          meta: { requiresAuth: true },
        },

        // ── Clientes ───────────────────────────────────────────────────────────
        {
          path: 'masters/clients',
          name: 'clients',
          component: () => import('@/pages/masters/ClientsPage.vue'),
          meta: { requiresAuth: true },
        },

        // ── Maestros ───────────────────────────────────────────────────────────
        {
          path: 'masters/materials',
          name: 'materials',
          component: () => import('@/pages/masters/MaterialsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'masters/vehicles',
          name: 'vehicles',
          component: () => import('@/pages/masters/VehiclesPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'masters/payment-methods',
          name: 'payment-methods',
          component: () => import('@/pages/masters/PaymentMethodsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'masters/tariffs',
          name: 'tariffs',
          component: () => import('@/pages/masters/TariffsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'masters/pins',
          name: 'pins',
          component: () => import('@/pages/masters/PinsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'masters/origins',
          name: 'origins',
          component: () => import('@/pages/masters/OriginsPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'masters/cities',
          name: 'cities',
          component: () => import('@/pages/masters/CitiesPage.vue'),
          meta: { requiresAuth: true },
        },

        // ── Finanzas ───────────────────────────────────────────────────────────
        {
          path: 'advances',
          name: 'advances',
          component: () => import('@/pages/advances/AdvancesPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'invoicing',
          name: 'invoicing',
          component: () => import('@/pages/invoicing/InvoicingPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'expenses',
          name: 'expenses',
          component: () => import('@/pages/expenses/ExpensesPage.vue'),
          meta: { requiresAuth: true },
        },

        // ── Reportes ───────────────────────────────────────────────────────────
        {
          path: 'reports/general',
          name: 'reports-general',
          component: () => import('@/pages/reports/GeneralReportPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'reports/daily',
          name: 'reports-daily',
          component: () => import('@/pages/reports/DailyReportPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'reports/range',
          name: 'reports-range',
          component: { ...UnderConstruction, props: { module: 'Reporte por Rango' } },
          meta: { requiresAuth: true },
        },

        // ── Administración ─────────────────────────────────────────────────────
        {
          path: 'admin/users',
          name: 'admin-users',
          component: () => import('@/pages/admin/UsersPage.vue'),
          meta: { requiresAuth: true },
        },
        {
          path: 'admin/audit-log',
          name: 'admin-audit-log',
          component: () => import('@/pages/admin/AuditLogPage.vue'),
          meta: { requiresAuth: true },
        },
      ],
    },
  ],
})

router.beforeEach((to: RouteLocationNormalized, _from: RouteLocationNormalized, next: NavigationGuardNext) => {
  const store = useAuthStore()

  if (to.meta.requiresAuth === false) {
    if (store.isAuthenticated && to.name === 'login') {
      return next('/')
    }
    return next()
  }

  if (!store.isAuthenticated) {
    return next('/login')
  }

  // FASE 5.4: los roles permitidos por ruta ya no se duplican aquí — se
  // leen de la misma configuración centralizada que usa el menú de
  // navegación (constants/navigation.ts), para que menú y guardas de ruta
  // nunca queden desincronizados entre sí.
  const allowedRoles = getAllowedRoles(to.path)
  if (allowedRoles && store.user && !allowedRoles.includes(store.user.role)) {
    return next('/unauthorized')
  }

  next()
})

export default router
