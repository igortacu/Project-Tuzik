FROM python:3.10.14-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY second_brain ./second_brain

# Drop root: /app and /vault are chowned to this user here for the ./data
# bind mount and any first-run local access. The shared `vault` named volume
# is actually seeded by whichever container starts first per depends_on
# (syncthing, per docker-compose.yml), so the real UID match across
# containers relies on both images independently running as UID 1000 --
# murzik via --uid 1000 here, syncthing via the explicit PUID/PGID=1000 set
# in docker-compose.yml -- not on this image's mount/chown order.
RUN useradd --create-home --uid 1000 murzik \
    && mkdir -p /app/data /vault \
    && chown -R murzik:murzik /app /vault
USER murzik

CMD ["python", "-m", "second_brain", "telegram"]
