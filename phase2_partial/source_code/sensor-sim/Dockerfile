FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sensor_sim.py .
COPY enroll.py .
COPY wait_for.py .

CMD ["python", "-u", "wait_for.py"]