import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api'

const routes = [
  { path: '/login', component: () => import('./views/Login.vue'), meta: { public: true } },
  { 
    path: '/', 
    component: () => import('./views/Dashboard.vue'),
    meta: { roles: ['admin', 'user'] } 
  },
  { 
    path: '/keys', 
    component: () => import('./views/Keys.vue'),
    meta: { roles: ['admin', 'user'] } 
  },
  { 
    path: '/logs', 
    component: () => import('./views/Logs.vue'),
    meta: { roles: ['admin', 'user'] } 
  },
  { 
    path: '/providers', 
    component: () => import('./views/Providers.vue'),
    meta: { roles: ['admin'] } 
  },
  { 
    path: '/settings', 
    component: () => import('./views/Settings.vue'),
    meta: { roles: ['admin'] } 
  },
  { 
    path: '/users', 
    component: () => import('./views/Users.vue'),
    meta: { roles: ['admin'] } 
  },
  { 
    path: '/analytics', 
    component: () => import('./views/Analytics.vue'),
    meta: { roles: ['admin'] } 
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  if (to.meta.public) return next()

  const token = localStorage.getItem('access_token')
  if (!token) return next('/login')

  try {
    // We cache user info in state or fetch if missing
    const user = await api.getMe()
    if (!user) throw new Error('Unauthorized')
    
    const userRole = user.role || (user.is_admin ? 'admin' : 'user')
    
    if (to.meta.roles && !to.meta.roles.includes(userRole)) {
      console.warn('Access denied for role:', userRole)
      return next('/')
    }
    next()
  } catch (e) {
    localStorage.removeItem('access_token')
    next('/login')
  }
})

export default router
