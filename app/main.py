from fastapi import FastAPI, HTTPException
import docker
from contextlib import asynccontextmanager
import app_logging
from pydantic import BaseModel, Field
from containers_set import ContainerEnvironment, ContainersSet, UnknownContainersCountException

logger = app_logging.get_logger("main")

docker_client: docker.DockerClient
environments: dict[str, ContainerEnvironment]

@asynccontextmanager
async def lifespan(app: FastAPI):
    global docker_client, environments
    docker_client = docker.from_env()
    logger.info("Docker version: %s", docker_client.version())

    img = "registry.reset.inso-w.at/2025ws-ase-pr-group/25ws-ase-pr-qse-09/test-host:alpine"
    environments = {env.name: env for env in [
        ContainerEnvironment(name="prod", first_port=2220, container_image=img),
        ContainerEnvironment(name="test", first_port=3000, container_image=img),
    ]}

    yield

    docker_client.close()

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
        c_set = ContainersSet(env, docker_client)
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
    
    c_set = ContainersSet(env, docker_client)
    try:
        started_count = c_set.reset(request.new_count)
    except UnknownContainersCountException:
        raise HTTPException(400, "No containers are running; new_count must be set")

    return ResetResponse(started_count=started_count)
