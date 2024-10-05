import subprocess

# subprocess.run("uvicorn app:app --host 0.0.0.0 --reload", shell=True)
subprocess.run("uvicorn app:app --host 0.0.0.0", shell=True)
