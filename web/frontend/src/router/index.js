import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ProjectView from '../views/ProjectView.vue'
import UsageView from '../views/UsageView.vue'
import CharactersView from '../views/CharactersView.vue'
import InstructionsView from '../views/InstructionsView.vue'
import MediaView from '../views/MediaView.vue'
// Lazy: chat pulls in the markdown renderer, which the video pages don't need
const ChatView = () => import('../views/ChatView.vue')
const RequestLogView = () => import('../views/RequestLogView.vue')
const StudioView = () => import('../views/StudioView.vue')

// Empty component for child routes - ProjectView handles tab rendering via v-show
const EmptyRouteComponent = { render: () => null }

const routes = [
  {
    // Cutover: the unified Studio is the default landing
    path: '/',
    redirect: '/studio',
  },
  {
    // The classic Generate landing, still reachable
    path: '/classic',
    name: 'home',
    component: HomeView,
    meta: { title: 'Pollo Video Generator' },
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
  {
    // Unified Studio shell (overhaul, in progress — runs alongside the old UI)
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
    path: '/chat',
    name: 'chat',
    component: ChatView,
    meta: { title: 'Chat — Pollo', fullBleed: true },
  },
  {
    // The old chat Library is now part of Media
    path: '/chat/library',
    redirect: { name: 'media', query: { origin: 'chat' } },
  },
  {
    path: '/chat/:id',
    name: 'chat-conversation',
    component: ChatView,
    meta: { title: 'Chat — Pollo', fullBleed: true },
  },
  {
    path: '/project/:project',
    component: ProjectView,
    props: true,
    meta: { title: 'Project' },
    children: [
      {
        path: '',
        redirect: to => ({ name: 'project-gallery', params: { project: to.params.project } }),
      },
      {
        path: 'generate',
        name: 'project-generate',
        component: EmptyRouteComponent,
        meta: { tab: 'generate' },
      },
      {
        path: 'gallery',
        name: 'project-gallery',
        component: EmptyRouteComponent,
        meta: { tab: 'gallery' },
      },
      {
        path: 'gallery/:videoFilename',
        name: 'project-video',
        component: EmptyRouteComponent,
        meta: { tab: 'gallery' },
      },
      {
        path: 'history',
        name: 'project-history',
        component: EmptyRouteComponent,
        meta: { tab: 'history' },
      },
      {
        path: 'archive',
        name: 'project-archive',
        component: EmptyRouteComponent,
        meta: { tab: 'archive' },
      },
    ],
  },
  {
    // Catch-all redirect to home
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

// Update page title on navigation (only for non-project pages)
// Project pages handle their own title with the display name
router.beforeEach((to, from, next) => {
  if (!to.params.project) {
    document.title = to.meta.title || 'Pollo Video Generator'
  }
  next()
})

export default router
