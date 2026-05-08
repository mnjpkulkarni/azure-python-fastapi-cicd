from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from services.cicd_pipeline import ACRCIManager, RepoManager, AzureDeployer, CICDPipeline
from services.job_manager import create_job, update_job, get_job

router = APIRouter()


class DeployRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    image_name: str
    acr_name: str
    app_name: str
    resource_group: str


def run_pipeline(job_id, req: DeployRequest):
    try:
        update_job(job_id, log="Pipeline execution started")
        
        repo = RepoManager(req.repo_url, req.branch, f"./repos/{job_id}")
        update_job(job_id, log="RepoManager created")

        acr = ACRCIManager(
            registry=req.acr_name,
            image_name=req.image_name,
            tag=job_id
        )
        update_job(job_id, log="ACRCIManager created")

        deployer = AzureDeployer(
            app_name=req.app_name,
            resource_group=req.resource_group,
            image=""  # Will be set by pipeline
        )
        update_job(job_id, log="AzureDeployer created")

        pipeline = CICDPipeline(repo, acr, deployer)
        update_job(job_id, log="CICDPipeline created, starting execution...")
        
        pipeline.run()
        
        update_job(job_id, status="completed", log="Pipeline completed successfully")
        print(f"Job {job_id} completed successfully")

    except Exception as e:
        error_msg = f"Pipeline failed: {str(e)}"
        print(f"Job {job_id} failed with error: {error_msg}")
        update_job(job_id, status="failed", log=error_msg)


@router.post("/deploy")
def trigger_deploy(req: DeployRequest, background_tasks: BackgroundTasks):
    job_id = create_job()

    background_tasks.add_task(run_pipeline, job_id, req)

    return {
        "message": "Deployment started",
        "job_id": job_id
    }


@router.get("/status/{job_id}")
def check_status(job_id: str):
    return get_job(job_id)