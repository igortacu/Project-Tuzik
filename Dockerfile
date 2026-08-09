FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY second_brain ./second_brain

CMD ["python", "-m", "second_brain", "telegram"]
