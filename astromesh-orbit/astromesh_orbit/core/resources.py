"""Typed resource specifications for Orbit deployments."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComputeSpec:
    min_instances: int = 1
    max_instances: int = 3
    cpu: str = "1"
    memory: str = "1Gi"


@dataclass(frozen=True)
class DatabaseSpec:
    tier: str = "db-f1-micro"
    version: str = "POSTGRES_16"
    storage_gb: int = 10
    high_availability: bool = False


@dataclass(frozen=True)
class CacheSpec:
    tier: str = "basic"
    memory_gb: int = 1


@dataclass(frozen=True)
class SecretsSpec:
    provider_keys: bool = True
    jwt_secret: bool = True


@dataclass(frozen=True)
class ImagesSpec:
    runtime: str = "fulfarodev/astromesh:latest"
    cloud_api: str = "fulfarodev/astromesh-cloud-api:latest"
    studio: str = "fulfarodev/astromesh-cloud-studio:latest"
