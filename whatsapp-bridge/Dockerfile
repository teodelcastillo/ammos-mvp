FROM golang:1.25-alpine AS builder

RUN apk add --no-cache gcc musl-dev sqlite-dev

WORKDIR /app
COPY . .
# Resolve dependencies from source imports
RUN go get go.mau.fi/whatsmeow@latest && \
    go get github.com/mattn/go-sqlite3@latest && \
    go get github.com/mdp/qrterminal/v3@latest && \
    go mod tidy && \
    CGO_ENABLED=1 go build -o whatsapp-bridge .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates sqlite-libs
WORKDIR /app
COPY --from=builder /app/whatsapp-bridge .
RUN mkdir -p /data

EXPOSE 8080
CMD ["./whatsapp-bridge"]
