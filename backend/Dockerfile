FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml README.md ./
COPY citylab ./citylab
RUN pip install --no-cache-dir ".[postgres]" && useradd --create-home city
USER city
EXPOSE 8000
CMD ["uvicorn", "citylab.main:app", "--host", "0.0.0.0", "--port", "8000"]
