import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../store/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../pages/LoginPage.vue') },
  // 独立 3D 地形预览页 (public, 无需登录) —— 纯 3D 地形模型展示
  { path: '/terrain-preview', name: 'TerrainPreview', component: () => import('../pages/TerrainPreviewPage.vue') },
  {
    path: '/',
    component: () => import('../pages/AppLayout.vue'),
    children: [
      { path: '', name: 'Overview', component: () => import('../pages/OverviewPage.vue') },
      { path: 'warnings', name: 'Warnings', component: () => import('../pages/WarningsPage.vue') },
      { path: 'devices', name: 'Devices', component: () => import('../pages/DevicesPage.vue') },
      { path: 'reports', name: 'Reports', component: () => import('../pages/ReportsPage.vue') },
      { path: 'agent', name: 'Agent', component: () => import('../pages/AgentPage.vue') },
      { path: 'admin/users', name: 'AdminUsers', component: () => import('../pages/AdminUsersPage.vue'), meta: { role: 'super_admin' } },
      { path: 'admin/settings', name: 'AdminSettings', component: () => import('../pages/AdminSettingsPage.vue'), meta: { role: 'admin' } },
    ]
  },
  // Catch-all: redirect any unmatched path (e.g. stale /forecast bookmarks)
  // to the overview so a removed/renamed route never renders a blank page.
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() { return { top: 0 } }
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  // TerrainPreview 是 public 路由, 放行 (无需登录)
  const isPublic = to.name === 'Login' || to.name === 'TerrainPreview'
  if (!isPublic && !token) return next('/login')
  if (to.name === 'Login' && token) return next('/')
  // Admin role check — only enforce when role is known (not empty/fresh reload)
  if (to.meta.role) {
    const role = useAuthStore().role
    if (role && role !== 'super_admin' && to.meta.role === 'super_admin') return next('/')
    if (role && role !== 'super_admin' && role !== 'admin' && to.meta.role === 'admin') return next('/')
  }
  next()
})

export default router
