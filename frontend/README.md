# knx-sim dashboard (frontend)

React + TypeScript + Tailwind CSS, built with Vite. Talks to the backend
FastAPI app in `knx_sim/web/` over REST (`/api/...`) and a WebSocket
(`/ws`) for live telegram/state updates.

## Development

Start the backend first (from the repo root):

```
python -m knx_sim.cli examples/demo-house.yaml
```

Then, in this directory:

```
npm install
npm run dev
```

Open the printed `http://localhost:5173` URL. Vite's dev server proxies
`/api` and `/ws` to the backend at `127.0.0.1:8080` (see `vite.config.ts`),
so no CORS setup is needed and the two processes can be developed/reloaded
independently.

## Production build

```
npm run build
```

Outputs static assets to `dist/`, intended to be served directly by the
FastAPI backend (wired up in a later round -- for now, use `npm run dev`
against a running backend).

## Scripts

- `npm run dev` -- Vite dev server with hot module reload.
- `npm run build` -- type-check (`tsc -b`) then production build.
- `npm run lint` -- oxlint.
- `npm run preview` -- serve the production build locally, without the API proxy.
