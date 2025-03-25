FROM python:3.10.11

WORKDIR /src

COPY ./requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY ./src .

EXPOSE 8000

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000"]