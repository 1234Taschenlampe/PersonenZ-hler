# YOLO26x to Hailo-10H HEF

This folder contains the offline compilation workflow for systems where the Hailo Dataflow Compiler is not available on the Raspberry Pi.

Run on a compatible x86-64 Ubuntu host with the Hailo Dataflow Compiler and Model Zoo installed:

```bash
python3 -m venv .venv-hailo
. .venv-hailo/bin/activate
pip install -r tools/hailo_compile_yolo26x/requirements.txt
cp /path/to/yolo26x.pt models/yolo26x.pt
tools/hailo_compile_yolo26x/compile_yolo26x.sh data/calibration
```

The expected output is:

```text
models/yolo26x_hailo10h_640.hef
```

The YAML and ALLS files are intentionally small starting points based on the YOLO26m-style Hailo Model Zoo flow. Validate parser end nodes against the official YOLO26x export before production compilation.
