FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv git build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /work
COPY tools/hailo_compile_yolo26x/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --upgrade pip && python3 -m pip install -r /tmp/requirements.txt
CMD ["bash", "tools/hailo_compile_yolo26x/compile_yolo26x.sh"]
