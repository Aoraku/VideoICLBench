FROM python:3.11

ENV DEPLOY=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .

RUN chmod +x /app/start.sh

EXPOSE 80

CMD ["/app/start.sh"]
