ARG  CODE_VERSION=latest
FROM python:3.12.3-bookworm

WORKDIR /cl-dashboard-firestore

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/curiouslearning/cl-dashboard-firestore.git .

RUN pip3 install -r requirements.txt

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8501

CMD ["./entrypoint.sh"]