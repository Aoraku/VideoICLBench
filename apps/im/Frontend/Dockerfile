# TODO Start: [Student] Complete Dockerfile
FROM node:22 AS builder

WORKDIR /app

ARG VIC_BACKEND_URL=http://im-backend:8000
ENV VIC_BACKEND_URL=$VIC_BACKEND_URL

# Set pnpm registry
RUN npm install -g pnpm@10.4.1

# Copy package files
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source code
COPY . .

# Build the application
RUN pnpm build


# Production stage
FROM node:22

WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME="0.0.0.0"
ENV PORT=80

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 80

# Start the server
CMD ["node", "server.js"]
# TODO End
