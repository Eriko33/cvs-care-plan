FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# CPU-only torch first: the default PyPI wheel pulls in several GB of unused
# NVIDIA/CUDA packages. This container has no GPU, so skip that entirely.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
