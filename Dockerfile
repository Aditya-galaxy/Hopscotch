# Matches the local interpreter the lock is generated on. A 3.13 freeze does
# not necessarily resolve on 3.12, and "works on my machine" is exactly the
# failure this lock exists to prevent.
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
# Install from the LOCK, not the loose list. An unpinned resolve is what broke
# the deployment on 25 Aug: same commit, new image, different Firestore client.
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY src/ ./src/
COPY registry/ ./registry/
# Generated media is baked in. The Veo explainer is district-wide and identical
# for every family, so it ships with the image rather than being regenerated.
COPY data/media/ ./data/media/

# ONE image, two entrypoints. The default serves the coordinator dashboard;
# the Cloud Run JOB overrides the command to run the tick:
#   --command python --args=-m,hopscotch.jobs.tick
# Two Dockerfiles would drift -- the job and the dashboard share every module
# that matters, so they must share the image.
CMD exec uvicorn hopscotch.dashboard.app:app --host 0.0.0.0 --port ${PORT:-8080}
