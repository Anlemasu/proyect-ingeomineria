import { defineComponent, h } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteLocationNormalized, NavigationGuardNext } from 'vue-router'
import { useAuthStore } from '@/stores/auth.store'

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
          redirect: '/masters/clients',
        },

        // ── Operación ──────────────────────────────────────────────────────────
        {
          path: 'trips',
          name: 'trips',
          component: { ...UnderConstruction, props: { module: 'Registro de Viajes' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'cashier'] },
        },
        {
          path: 'trips/adjustments',
          name: 'trips-adjustments',
          component: { ...UnderConstruction, props: { module: 'Ajustes del Día' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'cashier', 'commercial_admin'] },
        },
        {
          path: 'cash-closing',
          name: 'cash-closing',
          component: { ...UnderConstruction, props: { module: 'Cierre de Caja' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'cashier'] },
        },

        // ── Clientes ───────────────────────────────────────────────────────────
        {
          path: 'masters/clients',
          name: 'clients',
          component: () => import('@/pages/masters/ClientsPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'accountant', 'auditor'] },
        },

        // ── Maestros ───────────────────────────────────────────────────────────
        {
          path: 'masters/materials',
          name: 'materials',
          component: () => import('@/pages/masters/MaterialsPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'auditor'] },
        },
        {
          path: 'masters/vehicles',
          name: 'vehicles',
          component: () => import('@/pages/masters/VehiclesPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'auditor'] },
        },
        {
          path: 'masters/payment-methods',
          name: 'payment-methods',
          component: () => import('@/pages/masters/PaymentMethodsPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'auditor'] },
        },
        {
          path: 'masters/tariffs',
          name: 'tariffs',
          component: () => import('@/pages/masters/TariffsPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'auditor'] },
        },
        {
          path: 'masters/pins',
          name: 'pins',
          component: () => import('@/pages/masters/PinsPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'auditor'] },
        },
        {
          path: 'masters/origins',
          name: 'origins',
          component: () => import('@/pages/masters/OriginsPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'cashier', 'auditor'] },
        },

        // ── Finanzas ───────────────────────────────────────────────────────────
        {
          path: 'advances',
          name: 'advances',
          component: () => import('@/pages/advances/AdvancesPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'accountant', 'commercial_admin'] },
        },
        {
          path: 'invoicing',
          name: 'invoicing',
          component: () => import('@/pages/invoicing/InvoicingPage.vue'),
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'accountant'] },
        },
        {
          path: 'expenses',
          name: 'expenses',
          component: { ...UnderConstruction, props: { module: 'Gastos' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'cashier', 'commercial_admin'] },
        },

        // ── Reportes ───────────────────────────────────────────────────────────
        {
          path: 'reports/general',
          name: 'reports-general',
          component: { ...UnderConstruction, props: { module: 'Reporte General' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'accountant', 'auditor'] },
        },
        {
          path: 'reports/daily',
          name: 'reports-daily',
          component: { ...UnderConstruction, props: { module: 'Reporte Diario' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'accountant', 'auditor', 'cashier'] },
        },
        {
          path: 'reports/range',
          name: 'reports-range',
          component: { ...UnderConstruction, props: { module: 'Reporte por Rango' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'commercial_admin', 'accountant', 'auditor'] },
        },

        // ── Administración ─────────────────────────────────────────────────────
        {
          path: 'admin/users',
          name: 'admin-users',
          component: { ...UnderConstruction, props: { module: 'Gestión de Usuarios' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser'] },
        },
        {
          path: 'admin/audit-log',
          name: 'admin-audit-log',
          component: { ...UnderConstruction, props: { module: 'Log de Auditoría' } },
          meta: { requiresAuth: true, allowedRoles: ['superuser', 'auditor'] },
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

  const allowedRoles = to.meta.allowedRoles as string[] | undefined
  if (allowedRoles && store.user && !allowedRoles.includes(store.user.role)) {
    return next('/unauthorized')
  }

  next()
})

export default router
