"""astromeshd — Astromesh Agent Runtime Daemon (platform-agnostic)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

from astromesh_node.daemon.config import DaemonConfig, detect_config_dir
from astromesh_node.installer.detect import get_installer
from astromesh_node.platform.detect import get_service_manager

logger = logging.getLogger("astromeshd")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="astromeshd",
        description="Astromesh Agent Runtime Daemon",
    )
    parser.add_argument("--config", type=str, default=None, help="Config directory")
    parser.add_argument("--host", type=str, default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["debug", "info", "warning", "error"],
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in foreground mode (no init system integration)",
    )
    parser.add_argument("--pid-file", type=str, default=None, help="PID file path")
    return parser.parse_args(argv)


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _default_pid_file() -> str:
    """Return the default PID file path for the current platform."""
    try:
        installer = get_installer()
        return str(installer.data_dir() / "astromeshd.pid")
    except Exception:
        return "/var/lib/astromesh/data/astromeshd.pid"


def write_pid_file(pid_file: str) -> None:
    Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
    Path(pid_file).write_text(str(os.getpid()))


def remove_pid_file(pid_file: str) -> None:
    path = Path(pid_file)
    if path.exists():
        path.unlink()


async def run_daemon(args: argparse.Namespace) -> None:
    import uvicorn

    from astromesh.api.main import app
    from astromesh.api.routes import agents, system
    from astromesh.runtime.engine import AgentRuntime
    from astromesh.runtime.peers import PeerClient
    from astromesh.runtime.services import ServiceManager

    config_dir = detect_config_dir(args.config)
    daemon_config = DaemonConfig.from_config_dir(config_dir)

    host = args.host or daemon_config.host
    port = args.port or daemon_config.port
    pid_file = args.pid_file or _default_pid_file()

    # Platform service manager
    service_mgr = get_service_manager(foreground=args.foreground)

    # Create service manager and peer client
    service_manager = ServiceManager(daemon_config.services)
    peer_client = PeerClient(daemon_config.peers)

    # Create mesh if enabled
    mesh_manager = None
    elector = None
    from astromesh.mesh.config import MeshConfig

    mesh_config = MeshConfig.from_dict(daemon_config.mesh)
    if mesh_config.enabled:
        from astromesh.mesh.leader import LeaderElector
        from astromesh.mesh.manager import MeshManager

        mesh_manager = MeshManager(mesh_config, service_manager)
        elector = LeaderElector(mesh_manager)
        peer_client = PeerClient.from_mesh(mesh_manager)
        logger.info("Mesh enabled, node: %s", mesh_config.node_name)
        if daemon_config.peers:
            logger.warning("spec.peers ignored when mesh is enabled")

    enabled = service_manager.enabled_services()
    logger.info("Enabled services: %s", ", ".join(enabled))
    for warning in service_manager.validate():
        logger.warning("Config warning: %s", warning)
    if daemon_config.peers:
        logger.info("Peers: %s", ", ".join(p["name"] for p in daemon_config.peers))

    installer = get_installer()
    system_dir = str(installer.config_dir())
    mode = "system" if config_dir == system_dir else "dev"
    logger.info("Starting astromeshd in %s mode", mode)
    logger.info("Config directory: %s", config_dir)

    write_pid_file(pid_file)

    runtime = AgentRuntime(
        config_dir=config_dir,
        service_manager=service_manager,
        peer_client=peer_client,
    )
    await runtime.bootstrap()

    agents.set_runtime(runtime)
    system.set_runtime(runtime)

    from astromesh.api.routes import memory as memory_routes
    from astromesh.api.routes import templates as templates_route

    memory_routes.set_runtime(runtime)

    templates_path = Path(config_dir) / "templates"
    if templates_path.is_dir():
        templates_route.set_templates_dir(str(templates_path))

    from astromesh.api.routes import mesh as mesh_routes

    mesh_routes.set_mesh(mesh_manager, elector)

    agent_count = len(runtime.list_agents())
    logger.info("Loaded %d agent(s)", agent_count)

    if mesh_manager:
        mesh_manager.update_agents([a["name"] for a in runtime.list_agents()])
        await mesh_manager.join()
        elector.elect()
        logger.info("Mesh joined, cluster size: %d", len(mesh_manager.cluster_state().nodes))

    runtime.mesh_manager = mesh_manager

    await service_mgr.notify_ready()

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=args.log_level,
        access_log=True,
    )
    server = uvicorn.Server(config)

    loop = asyncio.get_event_loop()

    def handle_shutdown(sig, frame):
        logger.info("Received %s, shutting down...", signal.Signals(sig).name)
        server.should_exit = True

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, lambda: handle_shutdown(signal.SIGTERM, None))
        loop.add_signal_handler(signal.SIGINT, lambda: handle_shutdown(signal.SIGINT, None))
    else:
        signal.signal(signal.SIGTERM, handle_shutdown)
        signal.signal(signal.SIGINT, handle_shutdown)

    def _reload_config():
        logger.info("Config reload triggered")

    service_mgr.register_reload_handler(_reload_config)

    mesh_tasks = []
    if mesh_manager:

        async def _gossip_loop():
            while not server.should_exit:
                try:
                    await mesh_manager.gossip_once()
                except Exception as e:
                    logger.debug("Gossip error: %s", e)
                await asyncio.sleep(mesh_config.gossip_interval)

        async def _heartbeat_loop():
            while not server.should_exit:
                try:
                    await mesh_manager.heartbeat_once()
                except Exception as e:
                    logger.debug("Heartbeat error: %s", e)
                await asyncio.sleep(mesh_config.heartbeat_interval)

        mesh_tasks.append(asyncio.create_task(_gossip_loop()))
        mesh_tasks.append(asyncio.create_task(_heartbeat_loop()))

    try:
        await server.serve()
    finally:
        await service_mgr.notify_stopping()
        for task in mesh_tasks:
            task.cancel()
        if mesh_manager:
            await mesh_manager.leave()
            await mesh_manager.close()
        remove_pid_file(pid_file)
        logger.info("astromeshd stopped")


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)
    asyncio.run(run_daemon(args))


if __name__ == "__main__":
    main()
