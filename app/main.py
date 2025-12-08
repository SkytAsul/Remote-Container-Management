from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import app_logging
from pydantic import BaseModel, Field
from containers_models import ContainerEnvironment, UnknownContainersCountException, ContainersManager
import os

logger = app_logging.get_logger("main")

environments: dict[str, ContainerEnvironment]
containers_manager: ContainersManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    global environments, containers_manager

    match os.getenv("CONTAINERS_TYPE", "docker"):
        case "docker":
            import docker_manager
            containers_manager = docker_manager.DockerManager()
        case "incus":
            import incus_manager
            containers_manager = incus_manager.IncusManager()
        case x:
            raise ValueError(f"Unknown containers type {x}")

    environments = {env.name: env for env in [
        ContainerEnvironment(name="prod", first_port=2220),
        ContainerEnvironment(name="test", first_port=3000),
    ]}

    with containers_manager:
        yield

app = FastAPI(
    lifespan=lifespan,
    title="Remote Container Management"
)

class StatusResponse(BaseModel):
    containers_count: dict[str, int]

@app.get("/")
def get_status():
    containers_count: dict[str, int] = {}
    for env in environments.values():
        c_set = containers_manager.crete_containers_set(env)
        count = c_set.get_running_count()
        containers_count[env.name] = count
    
    return StatusResponse(containers_count=containers_count)

class ResetRequest(BaseModel):
    environment: str
    new_count: int | None = Field(default=None, gt=0, lt=20)
    """Amount of containers to start. If not set, will default to the current
    amount of started containers. If there are none, the request will fail.
    """

class ResetResponse(BaseModel):
    started_count: int

@app.post("/reset")
def reset(request: ResetRequest) -> ResetResponse:
    env = environments.get(request.environment)
    if env is None:
        raise HTTPException(404, "Environment not found")
    
    c_set = containers_manager.crete_containers_set(env)
    try:
        started_count = c_set.reset(request.new_count)
    except UnknownContainersCountException:
        raise HTTPException(400, "No containers are running; new_count must be set")

    return ResetResponse(started_count=started_count)
