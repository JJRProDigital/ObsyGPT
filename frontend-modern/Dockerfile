# Stage 1: user documentation (Material for MkDocs), served at /docs/
FROM squidfunk/mkdocs-material:9 AS docs
WORKDIR /docs
COPY docs/ ./
RUN mkdocs build

# Stage 2: SPA build
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend-modern/package*.json ./
RUN npm ci
COPY frontend-modern/ ./
RUN npm run build

# Stage 3: nginx serving landing + SPA + docs from the same container
FROM nginx:alpine

COPY frontend-modern/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=docs /docs/site /usr/share/nginx/docs
# Real landing ships with the private deploy; the public snapshot gets a
# redirect stub written by scripts/publish-public.ps1.
COPY frontend-modern/landing /usr/share/nginx/landing/

EXPOSE 80
