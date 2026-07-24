FROM python:3.11-slim

WORKDIR /app
# alembic's env.py imports `app.core.config`, but alembic (a console-script
# entry point, not `python script.py`) doesn't add the cwd to sys.path on
# its own - without this, `alembic -c migrations/alembic.ini upgrade head`
# fails with "ModuleNotFoundError: No module named 'app'" for every
# in-container invocation (docker compose exec, a migration Job, etc.).
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 neuroweave && chown -R neuroweave:neuroweave /app
USER neuroweave

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
