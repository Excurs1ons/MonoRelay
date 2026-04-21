<template>
  <div class="app-container" :class="{ 'light': isLight }">
    <!-- Sidebar -->
    <aside class="sidebar" :class="{ 'collapsed': isCollapsed, 'mobile-open': isMobileOpen }">
      <div class="sidebar-header">
        <div class="logo">
          <div class="logo-box">PR</div>
          <span class="logo-text">MonoRelay</span>
        </div>
      </div>

      <nav class="nav-menu">
        <router-link to="/" class="nav-item">
          <LayoutDashboard :size="18" />
          <span>{{ $t('nav.dashboard') }}</span>
        </router-link>
        
        <router-link to="/keys" class="nav-item">
          <Key :size="18" />
          <span>{{ userRole === 'admin' ? '上游密钥' : '我的令牌' }}</span>
        </router-link>

        <router-link to="/logs" class="nav-item">
          <Activity :size="18" />
          <span>{{ $t('nav.logs') }}</span>
        </router-link>

        <!-- Admin Only Menu -->
        <template v-if="userRole === 'admin'">
          <div class="nav-divider">管理</div>
          <router-link to="/providers" class="nav-item">
            <Globe :size="18" />
            <span>提供商管理</span>
          </router-link>
          <router-link to="/users" class="nav-item">
            <Users :size="18" />
            <span>用户管理</span>
          </router-link>
          <router-link to="/analytics" class="nav-item">
            <BarChart3 :size="18" />
            <span>增强统计</span>
          </router-link>
          <router-link to="/settings" class="nav-item">
            <Settings :size="18" />
            <span>{{ $t('nav.settings') }}</span>
          </router-link>
        </template>
      </nav>

      <div class="sidebar-footer">
        <div class="user-info" v-if="user">
          <div class="avatar">{{ user.username[0].toUpperCase() }}</div>
          <div class="details">
            <div class="name">{{ user.username }}</div>
            <div class="role-badge">{{ userRole }}</div>
          </div>
          <button class="logout-btn" @click="logout" title="退出登录">
            <LogOut :size="16" />
          </button>
        </div>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="main-content">
      <header class="top-header">
        <div class="flex items-center gap-4">
          <button class="menu-toggle" @click="isMobileOpen = !isMobileOpen">
            <Menu :size="20" />
          </button>
          <div class="breadcrumb">
            <span class="text-dim">Prisma</span> / <span>{{ currentRouteName }}</span>
          </div>
        </div>

        <div class="header-actions">
          <div class="balance-display" v-if="user && userRole === 'user'">
            <CreditCard :size="14" />
            <span>余额: ${{ user.balance?.toFixed(2) }}</span>
          </div>
          <button class="theme-toggle" @click="toggleTheme">
            <Sun v-if="!isLight" :size="18" />
            <Moon v-else :size="18" />
          </button>
        </div>
      </header>

      <div class="page-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>
    </main>

    <div class="mobile-overlay" v-if="isMobileOpen" @click="isMobileOpen = false"></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { api } from './api'
import { 
  LayoutDashboard, Key, Activity, Globe, Settings, 
  Users, BarChart3, LogOut, Menu, Sun, Moon, CreditCard 
} from 'lucide-vue-next'

const isCollapsed = ref(false)
const isMobileOpen = ref(false)
const isLight = ref(localStorage.getItem('theme') === 'light')
const user = ref(null)
const router = useRouter()
const route = useRoute()

const userRole = computed(() => user.value?.role || (user.value?.is_admin ? 'admin' : 'user'))
const currentRouteName = computed(() => route.path === '/' ? 'Dashboard' : route.path.slice(1).charAt(0).toUpperCase() + route.path.slice(2))

async function fetchUser() {
  if (route.meta.public) return
  try {
    user.value = await api.getMe()
  } catch (e) {
    if (!route.meta.public) router.push('/login')
  }
}

function toggleTheme() {
  isLight.value = !isLight.value
  localStorage.setItem('theme', isLight.value ? 'light' : 'dark')
}

function logout() {
  localStorage.removeItem('access_token')
  router.push('/login')
}

watch(() => route.path, () => {
  isMobileOpen.value = false
  fetchUser()
})

onMounted(() => {
  fetchUser()
})
</script>

<style>
/* Style inherited from v0.5.0 but optimized for multi-tenant */
:root {
  --color-bg: #09090b;
  --color-bg-card: #121217;
  --color-bg-input: #18181b;
  --color-border: #27272a;
  --color-text: #fafafa;
  --color-text-dim: #a1a1aa;
  --color-accent: #f97316;
  --color-accent-hover: #ea580c;
  --radius: 12px;
}

.light {
  --color-bg: #f8fafc;
  --color-bg-card: #ffffff;
  --color-bg-input: #f1f5f9;
  --color-border: #e2e8f0;
  --color-text: #0f172a;
  --color-text-dim: #64748b;
}

.app-container { display: flex; min-height: 100vh; background: var(--color-bg); color: var(--color-text); font-family: 'Inter', sans-serif; }
.sidebar { width: 260px; background: var(--color-bg-card); border-right: 1px solid var(--color-border); display: flex; flex-direction: column; transition: all 0.3s; z-index: 100; }
.main-content { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.top-header { height: 64px; border-bottom: 1px solid var(--color-border); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; background: var(--color-bg); }

.nav-menu { flex: 1; padding: 12px; display: flex; flex-direction: column; gap: 4px; }
.nav-item { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 8px; color: var(--color-text-dim); text-decoration: none; transition: all 0.2s; font-size: 14px; font-weight: 500; }
.nav-item:hover, .router-link-active { background: rgba(249, 115, 22, 0.1); color: var(--color-accent); }
.nav-divider { padding: 16px 12px 8px; font-size: 11px; font-weight: 700; color: var(--color-text-dim); text-transform: uppercase; letter-spacing: 0.05em; }

.user-info { padding: 16px; border-top: 1px solid var(--color-border); display: flex; align-items: center; gap: 12px; }
.avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--color-accent); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; }
.details { flex: 1; min-width: 0; }
.name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.role-badge { font-size: 10px; background: rgba(255,255,255,0.1); padding: 1px 6px; border-radius: 4px; display: inline-block; }

.balance-display { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; color: var(--color-accent); background: rgba(249, 115, 22, 0.1); padding: 4px 10px; border-radius: 20px; }

@media (max-width: 768px) {
  .sidebar { position: fixed; left: -260px; height: 100vh; }
  .sidebar.mobile-open { left: 0; }
  .mobile-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 90; backdrop-filter: blur(2px); }
}
</style>
