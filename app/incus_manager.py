from containers_models import (
    ContainerEnvironment,
    ContainersManager,
    ContainersSet,
    UnknownContainersCountException,
)
import app_logging
import requests
import requests_unixsocket
import time

_logger = app_logging.get_logger("incus-manager")

_url_base = "http+unix://%2Fvar%2Flib%2Fincus%2Funix.socket"
requests_unixsocket.monkeypatch()


def _handle_incus_error(response: requests.Response) -> requests.Response:
    if 400 <= response.status_code < 600:
        raise requests.HTTPError(
            f"{response.status_code} error.", response.reason, str(response.content)
        )
    return response


def _get_operation(response: requests.Response) -> str:
    return response.json()["metadata"]["id"]


def _wait_for_operations(operations: list[str]) -> None:
    for operation in operations:
        response = requests.get(f"{_url_base}/1.0/operations/{operation}/wait")
        if 400 <= response.status_code < 600:
            _logger.warning(
                "An error occurred while waiting for an operation to finish: %s, %s",
                response.reason,
                str(response.content),
            )


class IncusManager(ContainersManager):
    def __enter__(self):
        _logger.info(
            "Incus server version: %s",
            _handle_incus_error(requests.get(f"{_url_base}/1.0")).json()["metadata"][
                "environment"
            ]["server_version"],
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def crete_containers_set(self, env: ContainerEnvironment) -> "IncusSet":
        return IncusSet(env)


class IncusSet(ContainersSet):
    _img_alias = "ansible-debian-host"

    def __init__(
        self,
        env: ContainerEnvironment,
    ):
        self._env = env

    @property
    def _container_name_prefix(self):
        return f"remote-{self._env.name}"

    def _get_containers(self) -> list[dict]:
        containers = _handle_incus_error(
            requests.get(f"{_url_base}/1.0/instances", params={"recursion": 1})
        ).json()["metadata"]
        assert isinstance(containers, list)

        filtered_containers = []
        for container in containers:
            container_name = container["name"]
            assert isinstance(container_name, str)

            if container_name.startswith(self._container_name_prefix):
                filtered_containers.append(container)

        return filtered_containers

    def get_running_count(self) -> int:
        containers = self._get_containers()

        count = 0
        for container in containers:
            container_status = container["status"]
            if container_status == "Running":
                count += 1
            else:
                _logger.warning(
                    "Container %s is not running (status %s)",
                    container["name"],
                    container_status,
                )

        return count

    def reset(self, count: int | None) -> int:
        containers = self._get_containers()

        if count is None:
            count = len(containers)
            if count == 0:
                raise UnknownContainersCountException()

        operations: list[str]
        if len(containers) != 0:
            operations = []
            for container in containers:
                container_name = container["name"]
                _logger.info("Stopping %s", container_name)
                response = _handle_incus_error(
                    requests.put(
                        f"{_url_base}/1.0/instances/{container_name}/state",
                        json={"action": "stop", "force": True},
                    )
                )
                operations.append(_get_operation(response))

            _logger.info("Waiting for all containers to stop...")
            _wait_for_operations(operations)

            operations = []
            for container in containers:
                container_name = container["name"]
                _logger.info("Removing %s", container_name)
                response = _handle_incus_error(
                    requests.delete(f"{_url_base}/1.0/instances/{container_name}")
                )
                operations.append(_get_operation(response))

            _logger.info("Waiting for all containers to be removed...")
            _wait_for_operations(operations)

        operations = []
        for i in range(1, count + 1):
            port = self._env.first_port + i
            name = f"{self._container_name_prefix}-{i}"
            _logger.info("Starting %s, listening on port %d", name, port)
            response = _handle_incus_error(
                requests.post(
                    f"{_url_base}/1.0/instances",
                    json={
                        "name": name,
                        "start": True,
                        "type": "container",
                        "source": {"type": "image", "alias": IncusSet._img_alias},
                        "devices": {
                            "ssh-access": {
                                "type": "proxy",
                                "connect": "tcp:127.0.0.1:22",
                                "listen": f"tcp:0.0.0.0:{port}",
                            }
                        },
                    },
                )
            )
            operations.append(_get_operation(response))

        _logger.info("Waiting for all containers to be started...")
        _wait_for_operations(operations)

        return count
