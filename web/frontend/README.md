# Pollo Video Generator - Vue Frontend

A Vue 3 frontend for the Pollo Video Generator with client-side routing.

## URL Routes

- `/` - Home page with project grid
- `/project/:name` - Project page (defaults to gallery)
- `/project/:name/generate` - Project generation form
- `/project/:name/gallery` - Project video gallery
- `/project/:name/gallery/:videoFilename` - Gallery with specific video open
- `/project/:name/history` - Project job history

## Project Structure

```
frontend/
├── src/
│   ├── router/              # Vue Router configuration
│   │   └── index.js
│   ├── components/          # Reusable UI components
│   │   ├── form/           # Form-specific components
│   │   │   ├── RatioPicker.vue
│   │   │   ├── LengthSlider.vue
│   │   │   └── ToggleSwitch.vue
│   │   ├── AppHeader.vue
│   │   ├── ProjectCard.vue
│   │   ├── VideoCard.vue
│   │   ├── VideoModal.vue
│   │   ├── JobCard.vue
│   │   └── ToastContainer.vue
│   ├── composables/         # Reusable logic (Vue composition API)
│   │   ├── useApi.js       # API calls
│   │   ├── useToast.js     # Toast notifications
│   │   └── useProjectSettings.js  # Project settings persistence
│   ├── views/              # Page-level components
│   │   ├── HomeView.vue    # Home page with project grid
│   │   ├── ProjectView.vue # Project page with tabs
│   │   └── panels/         # Tab panels
│   │       ├── GeneratePanel.vue
│   │       ├── GalleryPanel.vue
│   │       └── HistoryPanel.vue
│   ├── App.vue             # Root component
│   ├── main.js             # Entry point
│   └── style.css           # Global styles
├── package.json
├── vite.config.js
└── index.html
```

## Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Development (with hot reload):
```bash
npm run dev
```
This starts Vite dev server on port 5173, proxying API calls to FastAPI on port 5000.

3. Build for production:
```bash
npm run build
```

## Development

**Option 1: Use the dev script (recommended)**
```bash
./dev.sh
```
This starts both the FastAPI backend and Vue frontend dev servers.

**Option 2: Run servers separately**

Run the FastAPI backend in one terminal:
```bash
python web/api.py
```

Run the Vue frontend in another terminal:
```bash
cd web/frontend
npm run dev
```

Then open http://localhost:5173 for development with hot reload.

API documentation is available at http://localhost:5000/docs

## Production

Run the FastAPI server:
```bash
python web/api.py
```

Open http://localhost:5000

## Features

- **Deep linking**: Share URLs to specific projects, tabs, or even videos
- **Browser history**: Back/forward buttons work as expected
- **Bookmarkable**: Save links to frequently used project views
- **Keyboard shortcuts**: Press Escape to close video modal
