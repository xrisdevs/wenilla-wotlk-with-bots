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
RUN python3 scripts/setup-sources.py benilla
RUN bash client/browser.sh setup
RUN --mount=type=cache,target=/root/.cargo/registry bash client/browser.sh build
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libssl3t64 && rm -rf /var/lib/apt/lists/*
COPY --from=build /source/client/benilla-src/target/release/wenilla-host /usr/local/bin/wenilla-host
COPY --from=build /source/client/benilla-src/web/dist /www
USER 65534:65534
EXPOSE 8090
ENTRYPOINT ["wenilla-host"]
