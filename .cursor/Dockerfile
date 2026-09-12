# Cloud Agent base image for the One9Founders backend dev environment.
# System-level, slow-changing dependencies live here; repo/Python/Node
# dependencies are installed by .cursor/install.sh after checkout.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System packages:
#  - git/curl/ca-certificates/gnupg/sudo: agent tooling + service control
#  - build-essential/libpq-dev: building Python wheels (psycopg2, etc.)
#  - postgresql 16 + pgvector: the app's database (migrations CREATE EXTENSION vector)
#  - redis-server: cache backend
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg sudo locales \
        build-essential libpq-dev \
        postgresql postgresql-contrib postgresql-16-pgvector \
        redis-server \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 LTS (Next.js 15 frontend) via NodeSource.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# The ubuntu:24.04 image ships a non-root `ubuntu` user (uid 1000).
# Grant passwordless sudo so start.sh can manage postgres/redis.
RUN echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu \
    && chmod 0440 /etc/sudoers.d/ubuntu

USER ubuntu
WORKDIR /home/ubuntu
