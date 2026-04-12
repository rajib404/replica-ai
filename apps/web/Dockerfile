# syntax=docker/dockerfile:1.6
# ─── deps stage ────────────────────────────────────────────
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /repo

# Copy workspace manifests for cached install
COPY package.json package-lock.json turbo.json tsconfig.json ./
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
COPY packages/db/package.json packages/db/

RUN npm ci --include=dev --prefer-offline --no-audit --no-fund

# ─── builder stage ─────────────────────────────────────────
FROM node:20-alpine AS builder
WORKDIR /repo
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /repo/node_modules ./node_modules
COPY package.json package-lock.json turbo.json tsconfig.json ./
COPY packages ./packages
COPY apps/web ./apps/web

# NEXT_PUBLIC_API_URL is baked at build time; pass via build-arg
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npx turbo run build --filter=@replica-ai/web

# ─── runner stage ──────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -g 1001 -S nodejs && adduser -S -u 1001 -G nodejs nextjs

# Pull in built workspace + node_modules + manifests
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/.next ./apps/web/.next
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/public ./apps/web/public
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/package.json ./apps/web/
COPY --from=builder --chown=nextjs:nodejs /repo/apps/web/next.config.js ./apps/web/
COPY --from=builder --chown=nextjs:nodejs /repo/packages ./packages
COPY --from=builder --chown=nextjs:nodejs /repo/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /repo/package.json /repo/package-lock.json ./

USER nextjs
EXPOSE 3000
CMD ["npm", "run", "start", "--workspace", "@replica-ai/web"]
