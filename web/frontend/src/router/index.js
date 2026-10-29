import { createRouter, createWebHistory } from 'vue-router'
import UsageView from '../views/UsageView.vue'
import CharactersView from '../views/CharactersView.vue'
import InstructionsView from '../views/InstructionsView.vue'
import MediaView from '../views/MediaView.vue'
const RequestLogView = () => import('../views/RequestLogView.vue')
const StudioView = () => import('../views/StudioView.vue')

const routes = [
  // The unified Studio is the app; chat + generate are folded into it.
  { path: '/', redirect: '/studio' },
  {
    path: '/studio',
    name: 'studio',
    component: StudioView,
    meta: { title: 'Studio — Pollo', fullBleed: true },
  },
  {
    path: '/studio/:id',
    name: 'studio-thread',
    component: StudioView,
    meta: { title: 'Studio — Pollo', fullBleed: true },
  },
  {
    path: '/usage',
    name: 'usage',
    component: UsageView,
    meta: { title: 'Credit Usage — Pollo' },
  },
  {
    path: '/requests',
    name: 'request-log',
    component: RequestLogView,
    meta: { title: 'Request log — Pollo' },
  },
  {
    path: '/media',
    name: 'media',
    component: MediaView,
    meta: { title: 'Media — Pollo' },
  },
  {
    path: '/characters',
    name: 'characters',
    component: CharactersView,
    meta: { title: 'Characters — Pollo' },
  },
  {
    path: '/instructions',
    name: 'instructions',
    component: InstructionsView,
    meta: { title: 'Instructions — Pollo' },
  },
  // Old chat/generate paths now live in Studio
  { path: '/chat/:pathMatch(.*)*', redirect: '/studio' },
  { path: '/project/:pathMatch(.*)*', redirect: '/studio' },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title || 'Pollo Video Generator'
  next()
})

export default router
