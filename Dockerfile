FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY registry/ ./registry/
# Generated media is baked in. The Veo explainer is district-wide and identical
# for every family, so it ships with the image rather than being regenerated.
COPY data/media/ ./data/media/

# ONE image, two entrypoints. The default serves the coordinator dashboard;
# the Cloud Run JOB overrides the command to run the tick:
#   --command python --args=-m,agentx.jobs.tick
# Two Dockerfiles would drift -- the job and the dashboard share every module
# that matters, so they must share the image.
CMD exec uvicorn agentx.dashboard.app:app --host 0.0.0.0 --port ${PORT:-8080}
