FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Production image: no --reload (that's a docker-compose dev-only override,
# see docker-compose.yml). Render/other hosts run this CMD as-is.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
