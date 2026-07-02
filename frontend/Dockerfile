# 3D Medical CLIP frontend (P1 skeleton). Base image pinned by digest.
# Build the static bundle, then serve it with `vite preview`.
FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# vite preview recompiles vite.config.ts to a temp file at runtime, so the
# runtime user must own the working dir.
RUN chown -R node:node /app

EXPOSE 5173
USER node

HEALTHCHECK --interval=10s --timeout=5s --retries=10 --start-period=20s \
  CMD wget -qO- http://127.0.0.1:5173/ >/dev/null 2>&1 || exit 1

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
