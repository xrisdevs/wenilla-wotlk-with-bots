# syntax=docker/dockerfile:1
FROM ubuntu:24.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends build-essential clang cmake ninja-build git ccache curl ca-certificates python3 pkg-config libmysqlclient-dev libssl-dev libbz2-dev libreadline-dev libncurses-dev zlib1g-dev libboost-filesystem-dev libboost-program-options-dev libboost-regex-dev libboost-locale-dev libboost-iostreams-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /source
COPY sources.json ./
COPY scripts/setup-sources.py scripts/apply-custom.sh ./scripts/
COPY custom ./custom
COPY patches ./patches
RUN python3 scripts/setup-sources.py server && bash scripts/apply-custom.sh
ARG JOBS=4
RUN --mount=type=cache,target=/root/.cache/ccache cmake -S server -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/trinitycore -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_C_COMPILER_LAUNCHER=ccache -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DTOOLS=0 -DSCRIPTS=static -DWITH_WARNINGS=0 -DCOPY_CONF=1 && cmake --build /build -j${JOBS} && cmake --install /build

FROM build AS gateway
RUN python3 scripts/setup-sources.py benilla
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /source/client/benilla-src
RUN --mount=type=cache,target=/root/.cargo/registry --mount=type=cache,target=/root/.cargo/git cargo build --locked --release -p wenilla-host

FROM ubuntu:24.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 ARENA_LOBBY_HOME=/persist/lobby ARENA_DB_HOST=127.0.0.1 ARENA_DB_USER=trinity ARENA_SOAP_URL=http://127.0.0.1:7878/ ARENA_SOAP_USER=ARENAOP
RUN apt-get update && apt-get install -y --no-install-recommends mysql-server mysql-client python3 python3-venv supervisor ca-certificates libssl3t64 libbz2-1.0 libreadline8t64 libncurses6 zlib1g libboost-filesystem1.83.0 libboost-program-options1.83.0 libboost-regex1.83.0 libboost-locale1.83.0 libboost-iostreams1.83.0 libmysqlclient21 libboost-chrono1.83.0 libboost-thread1.83.0 libboost-atomic1.83.0 libboost-date-time1.83.0 libboost-system1.83.0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /opt/trinitycore /opt/trinitycore
COPY --from=gateway /source/client/benilla-src/target/release/wenilla-host /usr/local/bin/wenilla-host
RUN python3 -c 'import subprocess; paths=["/opt/trinitycore/bin/authserver", "/opt/trinitycore/bin/worldserver", "/usr/local/bin/wenilla-host"]; results=[subprocess.check_output(["ldd", p], text=True) for p in paths]; print("\n".join(results)); assert all("not found" not in r for r in results)'
COPY controller ./controller
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r controller/lobby/requirements.txt
COPY client/lobby ./client/lobby
COPY artifacts/fly/www ./www
COPY artifacts/fly/seed ./seed
COPY docker/conf ./conf
COPY deploy/fly ./deploy/fly
EXPOSE 8090
ENTRYPOINT ["/opt/venv/bin/python", "/app/deploy/fly/start.py"]
