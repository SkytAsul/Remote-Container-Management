from docker import DockerClient
from docker.models.containers import Container
from containers_models import (
    ContainerEnvironment,
    ContainersManager,
    ContainersSet,
    UnknownContainersCountException,
)
import app_logging

_logger = app_logging.get_logger("docker-manager")


class DockerManager(ContainersManager):
    def __enter__(self):
        self.docker_client = DockerClient.from_env()
        _logger.info("Docker version: %s", self.docker_client.version())
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.docker_client.close()

    def crete_containers_set(self, env: ContainerEnvironment) -> "DockerSet":
        return DockerSet(env, self.docker_client)


class DockerSet(ContainersSet):
    _env_label = "remotely-managed-env"
    _img_name = "registry.reset.inso-w.at/2025ws-ase-pr-group/25ws-ase-pr-qse-09/test-host:alpine"

    def __init__(
        self,
        env: ContainerEnvironment,
        docker_client: DockerClient,
    ):
        self._env = env
        self._docker_client = docker_client

    @property
    def _filter(self):
        return {"label": f"{DockerSet._env_label}={self._env.name}"}

    def get_running_count(self) -> int:
        containers = self._docker_client.containers.list(
            filters=self._filter, sparse=True
        )
        assert isinstance(containers, list)

        count = 0
        for container in containers:
            assert isinstance(container, Container)
            if container.status == "running":
                count += 1
            else:
                _logger.warning(
                    "Container %s is not running (status %s)",
                    container.name,
                    container.status,
                )

        return count

    def reset(self, count: int | None) -> int:
        containers = self._docker_client.containers.list(
            filters=self._filter,
        )
        assert isinstance(containers, list)

        if count is None:
            count = len(containers)
            if count == 0:
                raise UnknownContainersCountException()

        for container in containers:
            assert isinstance(container, Container)
            _logger.info("Stopping and removing %s", container.name)
            container.remove(force=True)

        for i in range(1, count + 1):
            port = self._env.first_port + i
            name = f"remote-{self._env.name}-{i}"
            _logger.info("Starting %s, listening on port %d", name, port)
            self._docker_client.containers.run(
                DockerSet._img_name,
                restart_policy={"Name": "always"},
                ports={"22/tcp": port},
                name=name,
                hostname=name,
                labels={DockerSet._env_label: self._env.name},
                detach=True,
            )

        return count
