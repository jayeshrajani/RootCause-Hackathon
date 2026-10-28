# RootCause API image for Cloud Run. Reference-photo retrieval (torch/FAISS) is not included.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install . && useradd --system --uid 10001 rootcause

USER rootcause
# Cloud Run injects PORT; 8080 is the local default.
ENV ROOTCAUSE_ENVIRONMENT=production PORT=8080
EXPOSE 8080
# --no-proxy-headers: trusting every proxy would take the client-supplied (leftmost)
# X-Forwarded-For entry. Per-IP limits read the header themselves, trusting only
# ROOTCAUSE_TRUSTED_PROXY_HOPS entries from the right.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-proxy-headers"]
