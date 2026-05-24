FROM node:24-alpine AS frontend-builder
WORKDIR /build
COPY web/frontend/package.json web/frontend/package-lock.json* ./
RUN npm install
COPY web/frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=frontend-builder /static /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
