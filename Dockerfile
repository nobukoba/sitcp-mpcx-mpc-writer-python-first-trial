FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
COPY src /app/src
RUN pip install --no-cache-dir .
ENTRYPOINT ["sitcp-mpc-writer"]
