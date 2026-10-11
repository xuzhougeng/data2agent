# Multi-stage: build the portal binary, then ship it with one package directory.
# Build context = a package directory that contains this Dockerfile (build_portal.py --target hosted copies it there),
# or the repo's portal/ directory with PKG pointing at a package.
#
#   docker build -t myportal .            # from inside the package dir
#   docker run -p 8080:8080 myportal
FROM golang:1.25-bookworm AS build
ARG PORTAL_REPO=https://github.com/xuzhougeng/data2agent.git
ARG PORTAL_REF=main
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 --branch ${PORTAL_REF} ${PORTAL_REPO} . && cd portal && CGO_ENABLED=1 go build -trimpath -ldflags="-s -w" -o /portal ./cmd/portal

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* \
 && useradd -r -u 10001 portal
COPY --from=build /portal /usr/local/bin/portal
WORKDIR /pkg
COPY --chown=portal:portal . /pkg
USER portal
EXPOSE 8080
ENTRYPOINT ["portal", "serve", "/pkg"]
CMD ["--addr", ":8080"]
