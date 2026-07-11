# Frontend image for the LexPar AI React app (production deploy only — local dev keeps `npm run dev`).
# Multi-stage: build the static bundle with Node, serve it with nginx.
# Build context is ./frontend (see infra/docker-compose.prod.yml).
#
# VITE_API_BASE_URL is baked in at BUILD time (Vite inlines import.meta.env values into the
# bundle). In production it is the public HTTPS origin (Caddy serves the app and proxies /api/*
# to the backend on the same origin), e.g. https://165-245-129-142.sslip.io.

# --- Stage 1: build ---
FROM node:22-alpine AS build

WORKDIR /app

# Install deps first so source edits don't bust the dependency layer.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# --- Stage 2: serve ---
FROM nginx:1.27-alpine

# SPA config: client-side routes fall back to index.html (see nginx.conf).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
