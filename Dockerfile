FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/config

EXPOSE 5000

CMD ["gunicorn", "-c", "deploy/gunicorn.conf.py", "simple_contacts.app_main:app"]
