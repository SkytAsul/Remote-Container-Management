from containers_models import ContainerEnvironment, ContainersManager, ContainersSet, UnknownContainersCountException
import app_logging
import requests, requests_unixsocket
import time

_logger = app_logging.get_logger("incus-manager")

_url_base = "http+unix://%2Fvar%2Flib%2Fincus%2Funix.socket"
requests_unixsocket.monkeypatch()

class IncusManager(ContainersManager):
    def __enter__(self):
        _logger.info("Incus server version: %s", requests.get(
            f"{_url_base}/1.0"
        ).json()["metadata"]["environment"]["server_version"])
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def crete_containers_set(self, env: ContainerEnvironment) -> 'IncusSet':
        return IncusSet(env)

class IncusSet(ContainersSet):
    _img_name = "local:ansible-debian-host"
    _img_fingerprint = "aa97635bd0c3966293412f15a9e650166a2a19a63d60f335ee3753461343a1bf"
    
    def __init__(
            self,
            env: ContainerEnvironment,
    ):
        self._env = env
    
    @property
    def _container_name_prefix(self):
        return f"remote-{self._env.name}"

    def _get_containers(self) -> list[dict]:
        containers = requests.get(
            f"{_url_base}/1.0/instances",
            params={"recursion": 1}
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
                _logger.warning("Container %s is not running (status %s)", container["name"], container_status)
        
        return count
    
    def reset(self, count: int | None) -> int:
        containers = self._get_containers()

        if count is None:
            count = len(containers)
            if count == 0:
                raise UnknownContainersCountException()

        if len(containers) != 0:
            for container in containers:
                container_name = container["name"]
                _logger.info("Stopping %s", container_name)
                requests.put(
                    f"{_url_base}/1.0/instances/{container_name}/state",
                    json={
                        "action": "stop",
                        "force": True
                    }
                ).raise_for_status()
            
            _logger.info("Waiting 10s for all containers to stop...")
            time.sleep(10)

            for container in containers:
                container_name = container["name"]
                _logger.info("Removing %s", container_name)
                requests.delete(
                    f"{_url_base}/1.0/instances/{container_name}"
                ).raise_for_status()
        
        for i in range(1, count+1):
            port = self._env.first_port + i
            name = f"{self._container_name_prefix}-{i}"
            _logger.info("Starting %s, listening on port %d", name, port)
            response = requests.post(
                f"{_url_base}/1.0/instances",
                json={
                    "name": name,
                    "start": True,
                    "type": "container",
                    "source": {
                        "type": "image",
                        "fingerprint": IncusSet._img_fingerprint
                    },
                    "devices": {
                        "ssh-access": {
                            "type": "proxy",
                            "connect": "tcp:127.0.0.1:22",
                            "listen": f"tcp:0.0.0.0:{port}"
                        }
                    }
                }
            ).raise_for_status()

        return count