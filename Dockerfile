FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libsndfile1 \
    ffmpeg \
    libasound2 \
    libportaudio2 \
    portaudio19-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY constraints.txt requirements.txt requirements-dev.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt -c constraints.txt \
    && python -m pip install -r requirements-dev.txt -c constraints.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY config ./config
COPY dcs_scripts ./dcs_scripts

RUN python -m pip install -e . --no-deps

CMD ["python", "-m", "pytest", "-q"]
