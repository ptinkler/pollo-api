import { createRouter, createWebHistory } from 'vue-router'
const StudioView = () => import('../views/StudioView.vue')

// Studio IS the app and lives at the root. Its center panes are real paths so
// the browser back button returns you where you were. Static pane paths are
// matched ahead of the catch-all `/:id` thread route (vue-router ranks static
// segments above params), and thread ids are uuid hex so they never collide
// with a pane name. Every route renders StudioView, which reads the route to
// pick the pane. The backend serves index.html for any non-/api path, so these
// deep links survive a reload.
const page = (path, name, title, extra = {}) => ({
  path,
  name,
  component: StudioView,
  meta: { title, fullBleed: true },
  ...extra,
})

const routes = [
  page('/', 'studio', 'Pollo Studio'),
  page('/settings', 'studio-settings', 'Settings — Pollo'),
  page('/tools', 'studio-tools', 'Tools & library — Pollo'),
  page('/media', 'studio-media', 'Media — Pollo'),
  page('/favourites', 'studio-favourites', 'Favourites — Pollo'),
  page('/usage', 'studio-usage', 'Credit usage — Pollo'),
  page('/characters', 'studio-characters', 'Characters — Pollo'),
  page('/instructions', 'studio-instructions', 'Instructions — Pollo'),
  page('/requests', 'studio-requests', 'Request log — Pollo'),
  page('/space/:spaceId', 'studio-space', 'Space — Pollo'),
  page('/:id/:view(chat|gallery)?', 'studio-thread', 'Pollo Studio'),
  // Any stray old/unknown URL goes to Studio home.
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title || 'Pollo Studio'
  next()
})

export default router
