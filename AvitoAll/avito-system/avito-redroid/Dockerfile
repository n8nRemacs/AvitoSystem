# Dockerfile for Avito Redroid with Device Masking
# Builds a custom Redroid image that masks as a random real device from GSMArena DB

FROM redroid/redroid:13.0.0-latest

LABEL maintainer="avito-redroid"
LABEL description="Redroid with random device masking for Avito"
LABEL version="1.0.0"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Python dependencies for masking scripts
COPY scripts/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Create directories
RUN mkdir -p /opt/masking \
    /opt/output/tokens \
    /opt/output/profiles \
    /system/etc/init.d

# Copy masking scripts
COPY scripts/device_profile_gen.py /opt/masking/
COPY scripts/build_prop_gen.py /opt/masking/
COPY scripts/fingerprint_gen.py /opt/masking/
RUN chmod +x /opt/masking/*.py

# Copy init scripts
COPY init.d/01_apply_mask.sh /system/etc/init.d/
COPY init.d/02_cleanup_emu.sh /system/etc/init.d/
COPY init.d/03_start_services.sh /system/etc/init.d/
RUN chmod +x /system/etc/init.d/*.sh

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose ports
# 5555 - ADB
# 8000 - ws-scrcpy web interface (if installed separately)
EXPOSE 5555 8000

# Volume for persistent data (device profile, Avito tokens, etc.)
VOLUME ["/data"]

# Environment variables with defaults
ENV REDROID_WIDTH=1080 \
    REDROID_HEIGHT=2400 \
    REDROID_DPI=420 \
    REDROID_GPU_MODE=auto \
    GSMARENA_DB_HOST=85.198.98.104 \
    GSMARENA_DB_PORT=5433 \
    GSMARENA_DB_USER=postgres \
    GSMARENA_DB_NAME=postgres

# Entrypoint handles masking before starting Android
ENTRYPOINT ["/entrypoint.sh"]
