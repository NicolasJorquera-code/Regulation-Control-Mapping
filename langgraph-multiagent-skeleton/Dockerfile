FROM python:3.11-slim

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source and config
COPY src/ src/
COPY config/ config/

# Healthcheck
HEALTHCHECK CMD python -c "import skeleton" || exit 1

# Expose Streamlit port
EXPOSE 8501

# CUSTOMIZE: Change the entrypoint if you use a different UI framework.
ENTRYPOINT ["streamlit", "run", "src/skeleton/ui/app.py", \
            "--server.port=8501", "--server.address=0.0.0.0"]
