FROM node:22.20.0-bookworm-slim@sha256:b21fe589dfbe5cc39365d0544b9be3f1f33f55f3c86c87a76ff65a02f8f5848e
WORKDIR /opt/ralio
COPY runner/package.json runner/package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev && npm cache clean --force
COPY runner/evaluate.mjs runner/launch.mjs ./
RUN mkdir -p /work && chown 10001:10001 /work
USER 10001:10001
ENV NODE_ENV=production
ENTRYPOINT ["node", "/opt/ralio/evaluate.mjs"]
