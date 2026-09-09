FROM golang:1.27.0-alpine3.24 AS builder

ARG CADDY_COMMIT=8ec11a4b7e39a5fd00da2fc5cb9b543e31fd7926
RUN apk add --no-cache git \
    && git clone --filter=blob:none https://github.com/caddyserver/caddy.git /src/caddy \
    && git -C /src/caddy checkout "${CADDY_COMMIT}" \
    && cd /src/caddy \
    && go get golang.org/x/crypto@v0.55.0 golang.org/x/net@v0.57.0 \
        golang.org/x/text@v0.41.0 \
        google.golang.org/grpc@v1.83.2 \
    && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" \
        -o /out/caddy ./cmd/caddy

FROM alpine:3.24

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates libcap mailcap \
    && addgroup -g 10001 caddy \
    && adduser -D -u 10001 -G caddy caddy \
    && mkdir -p /config/caddy /data/caddy /etc/caddy \
    && chmod 1777 /config/caddy /data/caddy
COPY --from=builder /out/caddy /usr/bin/caddy
RUN setcap cap_net_bind_service=+ep /usr/bin/caddy

ENV XDG_CONFIG_HOME=/config \
    XDG_DATA_HOME=/data

WORKDIR /srv
USER 10001:10001
EXPOSE 80 443 443/udp
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
