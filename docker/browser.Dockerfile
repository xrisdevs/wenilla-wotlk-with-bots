# syntax=docker/dockerfile:1
FROM ubuntu:24.04 AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential clang pkg-config git curl ca-certificates python3 libssl-dev brotli && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /source
COPY sources.json ./
COPY scripts/setup-sources.py ./scripts/
COPY patches ./patches
COPY client ./client
COPY addons ./addons
RUN python3 scripts/setup-sources.py benilla
RUN bash client/browser.sh setup
RUN --mount=type=cache,target=/root/.cargo/registry --mount=type=cache,id=wenilla-client-target,target=/source/client/benilla-src/target,sharing=locked bash client/browser.sh build
COPY runtime/arena-host ./runtime/arena-host
RUN --mount=type=cache,target=/root/.cargo/registry --mount=type=cache,id=wenilla-arena-target,target=/source/runtime/arena-host/target,sharing=locked cd client/benilla-src && cargo test --locked --manifest-path ../../runtime/arena-host/Cargo.toml && cargo build --locked --release --manifest-path ../../runtime/arena-host/Cargo.toml && install -Ds ../../runtime/arena-host/target/release/wenilla-arena-host /out/wenilla-arena-host
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/wenilla-arena-host /usr/local/bin/wenilla-arena-host
COPY --from=build /source/client/benilla-src/web/dist /www
WORKDIR /app
COPY controller/lobby/builds.json ./controller/lobby/builds.json
COPY client/lobby ./client/lobby
COPY docker/scripts/browser.sh /browser.sh
RUN mkdir /state && chown 65534:65534 /state
USER 65534:65534
EXPOSE 8090
ENTRYPOINT ["bash", "/browser.sh"]
