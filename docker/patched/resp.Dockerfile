# Patched build of CAISR-App resp image.
# Upstream uses `FROM python:3.8.3` (Debian buster), whose apt repos are now
# archived, so `apt-get update` fails. We repoint apt at archive.debian.org and
# skip the non-essential `apt-get upgrade`. Everything else matches upstream.
# Build context must be the CAISR-App-main folder.
FROM python:3.8.3

SHELL ["/bin/bash", "-c"]

ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN sed -i -e 's|deb.debian.org/debian|archive.debian.org/debian|g' \
           -e 's|security.debian.org/debian-security|archive.debian.org/debian-security|g' \
           -e '/buster-updates/d' /etc/apt/sources.list && \
    apt-get -o Acquire::Check-Valid-Until=false update && \
    apt-get install -y --no-install-recommends python3-tk && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY caisr_resp.py /data/
COPY resp /data/resp/

WORKDIR /data

RUN python3 -m venv /caisr_resp && \
    source /caisr_resp/bin/activate && \
    /caisr_resp/bin/pip install --upgrade pip && \
    /caisr_resp/bin/pip install -r resp/resp_requirements.txt

ENTRYPOINT ["/bin/bash", "-c", "source /caisr_resp/bin/activate && exec python caisr_resp.py"]
