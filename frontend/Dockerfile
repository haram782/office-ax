# Office-AX frontend — Vite 빌드 후 nginx로 정적 서빙 + API 리버스 프록시
#
# 단일 origin 구성: ngrok 무료 플랜은 고정 도메인이 1개뿐이므로
# nginx 하나가 프론트/API/media를 모두 서빙한다 (결정 18).
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Google OAuth client ID는 빌드 타임에 주입된다 (Vite 정적 치환)
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
# 베타용 서버 설정은 compose에서 volume으로 주입한다 (infra/nginx/beta.conf)
