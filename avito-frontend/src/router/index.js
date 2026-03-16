import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  // --- Guest routes (no auth required) ---
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/RegisterView.vue'),
    meta: { guest: true },
  },
  {
    path: '/verify',
    name: 'VerifyOtp',
    component: () => import('../views/VerifyOtpView.vue'),
    meta: { guest: true },
  },

  // --- Authenticated routes (tenant panel) ---
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { title: 'Dashboard', icon: 'home', auth: true },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('../views/ProfileView.vue'),
    meta: { title: 'Profile', icon: 'user', auth: true },
  },

  // --- Legacy xapi panel routes ---
  {
    path: '/auth',
    name: 'Auth',
    component: () => import('../views/AuthView.vue'),
    meta: { title: 'Authorization', icon: 'key', panel: true },
  },
  {
    path: '/messenger',
    name: 'Messenger',
    component: () => import('../views/MessengerView.vue'),
    meta: { title: 'Messenger', icon: 'chat', panel: true },
  },
  {
    path: '/search',
    name: 'Search',
    component: () => import('../views/SearchView.vue'),
    meta: { title: 'Search', icon: 'search', panel: true },
  },
  {
    path: '/farm',
    name: 'Farm',
    component: () => import('../views/FarmView.vue'),
    meta: { title: 'Token Farm', icon: 'server', panel: true },
  },

  // --- Default redirect ---
  {
    path: '/',
    redirect: () => {
      return localStorage.getItem('access_token') ? '/dashboard' : '/login'
    },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Navigation guard
router.beforeEach((to, from, next) => {
  const hasToken = !!localStorage.getItem('access_token')

  // Auth-required routes → redirect to login
  if (to.meta.auth && !hasToken) {
    return next('/login')
  }

  // Guest-only routes → redirect to dashboard if already logged in
  if (to.meta.guest && hasToken) {
    return next('/dashboard')
  }

  next()
})

export default router
