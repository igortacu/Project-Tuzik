FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY second_brain ./second_brain

# Drop root: the persisted mount points are created and chowned here so a
# fresh named volume (Docker copies a volume's initial ownership from the
# image directory it overlays) comes up owned by this user too. Bind mounts
# (./data on the VPS) still need matching host-side ownership -- handled in
# the deploy runbook.
RUN useradd --create-home --uid 1000 murzik \
    && mkdir -p /app/data /vault \
    && chown -R murzik:murzik /app /vault
USER murzik

CMD ["python", "-m", "second_brain", "telegram"]
