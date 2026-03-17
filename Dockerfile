FROM python:3.11-slim AS base

WORKDIR /app

# System dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip cache purge

# Source code and config
COPY src/ src/
COPY config/ config/

# Install package in editable mode
RUN pip install --no-cache-dir -e .

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import controlnexus; print(controlnexus.__version__)" || exit 1

# Default: launch Streamlit dashboard
ENTRYPOINT ["streamlit", "run", "src/controlnexus/ui/app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true"]
