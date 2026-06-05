# ----------------------------------------------------------------
# Frontend image — Next.js 14 (build then `next start` on :3000).
# Next's server proxies /api/* to the backend (API_PROXY_TARGET).
# ----------------------------------------------------------------

# ---- 1. Build ----
FROM node:20-alpine AS builder
WORKDIR /app

# Install deps from lockfile (cached unless package*.json changes)
COPY package.json package-lock.json ./
RUN npm ci

# Build the production bundle
COPY . .
RUN npm run build

# ---- 2. Run ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000

# Only what's needed to run `next start`
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.js ./next.config.js

EXPOSE 3000
CMD ["npm", "run", "start"]
