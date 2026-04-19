import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores'

const routes = [
  { path: '/', redirect: '/dashboard' },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
  },
  {
    path: '/providers',
    name: 'Providers',
    component: () => import('@/views/Providers.vue'),
  },
  {
    path: '/keys',
    name: 'Keys',
    component: () => import('@/views/Keys.vue'),
  },
  {
    path: '/models',
    name: 'Models',
    component: () => import('@/views/Models.vue'),
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('@/views/Logs.vue'),
  },
  {
    path: '/config',
    name: 'Config',
    component: () => import('@/views/Config.vue'),
  },
  {
    path: '/analytics',
    name: 'Analytics',
    component: () => import('@/views/Analytics.vue'),
  },
  {
    path: '/help',
    name: 'Help',
    component: () => import('@/views/Help.vue'),
  },
  {
    path: '/about',
    name: 'About',
    component: () => import('@/views/About.vue'),
  },
  {
    path: '/users',
    name: 'Users',
    component: () => import('@/views/Users.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
  },
  {
    path: '/account',
    name: 'Account',
    component: () => import('@/views/Account.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (!authStore.token && to.path !== '/') {
    window.location.href = '/'
  } else {
    next()
  }
})

export default router
