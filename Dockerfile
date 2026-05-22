FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m pip install --upgrade pip

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY fixlog ./fixlog
COPY fixlog_harness ./fixlog_harness
COPY scripts ./scripts

RUN pip install .

CMD ["sh", "scripts/railway-start.sh"]
