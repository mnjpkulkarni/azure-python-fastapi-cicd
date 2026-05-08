import uuid
from typing import Dict

jobs: Dict[str, dict] = {}

def create_job():
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running", "logs": []}
    return job_id

def update_job(job_id, status=None, log=None):
    if status:
        jobs[job_id]["status"] = status
    if log:
        jobs[job_id]["logs"].append(log)

def get_job(job_id):
    return jobs.get(job_id, {"error": "Job not found"})