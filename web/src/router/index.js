import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../pages/LoginPage.vue') },
  {
    path: '/',
    component: () => import('../pages/AppLayout.vue'),
    children: [
      { path: '', name: 'Overview', component: () => import('../pages/OverviewPage.vue') },
      { path: 'stations', name: 'Stations', component: () => import('../pages/StationsPage.vue') },
      { path: 'warnings', name: 'Warnings', component: () => import('../pages/WarningsPage.vue') },
      { path: 'forecast', name: 'Forecast', component: () => import('../pages/ForecastPage.vue') },
      { path: 'devices', name: 'Devices', component: () => import('../pages/DevicesPage.vue') },
      { path: 'reports', name: 'Reports', component: () => import('../pages/ReportsPage.vue') },
      { path: 'agent', name: 'Agent', component: () => import('../pages/AgentPage.vue') },
      { path: 'admin/users', name: 'AdminUsers', component: () => import('../pages/AdminUsersPage.vue'), meta: { role: 'super_admin' } },
      { path: 'admin/settings', name: 'AdminSettings', component: () => import('../pages/AdminSettingsPage.vue'), meta: { role: 'admin' } },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() { return { top: 0 } }
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.name !== 'Login' && !token) return next('/login')
  if (to.name === 'Login' && token) return next('/')
  next()
})

export default router
