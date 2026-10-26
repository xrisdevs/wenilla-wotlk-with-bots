# Build + runtime image for TrinityCore 3.3.5 with NPCBots (arm64/amd64)
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential clang cmake ninja-build git ccache gdb \
      libmysqlclient-dev mysql-client libssl-dev libbz2-dev libreadline-dev libncurses-dev zlib1g-dev \
      libboost-filesystem-dev libboost-program-options-dev libboost-regex-dev libboost-locale-dev libboost-iostreams-dev \
      p7zip-full ca-certificates curl python3 \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global --add safe.directory '*'

ENV CCACHE_DIR=/build/.ccache
COPY scripts/ /scripts/
RUN chmod +x /scripts/*.sh
WORKDIR /opt/trinitycore
