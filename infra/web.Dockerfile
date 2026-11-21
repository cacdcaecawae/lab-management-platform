# Build context: repository root. Builds the Vue app and serves it with Nginx.
FROM node:24-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM nginx:1.29-alpine
# The HTTPS-only readiness probe uses system CA verification and connects to loopback.
RUN apk add --no-cache curl
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY infra/nginx.health.inc /etc/nginx/lab/health.inc
COPY infra/nginx.site.inc /etc/nginx/lab/site.inc
COPY infra/nginx.admin.inc /etc/nginx/lab/admin.inc
COPY --from=build /src/dist /usr/share/nginx/html
