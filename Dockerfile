FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
# Cloud Run Job entrypoint. Scales to zero between ticks: ten days of
# unattended operation costs approximately nothing.
CMD ["python", "-m", "agentx.jobs.tick"]
