# Patched build of CAISR-App limb image.
# Upstream uses `FROM python:3.6.9` (Debian buster), whose apt repos are now
# archived, so `apt-get update` fails. We repoint apt at archive.debian.org and
# skip the non-essential `apt-get upgrade`. Everything else matches upstream.
# Build context must be the CAISR-App-main folder.
FROM python:3.6.9

SHELL ["/bin/bash", "-c"]

ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN sed -i -e 's|deb.debian.org/debian|archive.debian.org/debian|g' \
           -e 's|security.debian.org/debian-security|archive.debian.org/debian-security|g' \
           -e '/buster-updates/d' /etc/apt/sources.list && \
    apt-get -o Acquire::Check-Valid-Until=false update && \
    apt-get install -y --no-install-recommends python3-tk && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /data
COPY caisr_limb.py /data/caisr_limb.py
COPY limb /data/limb

RUN python3 -m venv /caisr_limb && \
    source /caisr_limb/bin/activate && \
    /caisr_limb/bin/pip install --upgrade pip && \
    /caisr_limb/bin/pip install -r limb/limb_requirements.txt

ENTRYPOINT ["/bin/bash", "-c", "source /caisr_limb/bin/activate && exec python caisr_limb.py"]
