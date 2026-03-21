"""OrbitConfig — Pydantic model for orbit.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator


class ProviderSpec(BaseModel):
    name: Literal["gcp", "aws", "azure"]
    project: str = ""
    region: str = "us-central1"


class ComputeServiceSpec(BaseModel):
    min_instances: int = 1
    max_instances: int = 3
    cpu: str = "1"
    memory: str = "1Gi"


class ComputeSpec(BaseModel):
    runtime: ComputeServiceSpec = ComputeServiceSpec(cpu="2", memory="2Gi", max_instances=5)


class DatabaseSpec(BaseModel):
    tier: str = "db-f1-micro"
    version: str = "POSTGRES_16"
    storage_gb: int = 10
    high_availability: bool = False


class CacheSpec(BaseModel):
    tier: str = "basic"
    memory_gb: int = 1


class SecretsSpec(BaseModel):
    provider_keys: bool = True
    jwt_secret: bool = True


class ImagesSpec(BaseModel):
    runtime: str = "fulfarodev/astromesh:latest"


class OrbitSpec(BaseModel):
    provider: ProviderSpec
    compute: ComputeSpec = ComputeSpec()
    database: DatabaseSpec = DatabaseSpec()
    cache: CacheSpec = CacheSpec()
    secrets: SecretsSpec = SecretsSpec()
    images: ImagesSpec = ImagesSpec()


class OrbitMetadata(BaseModel):
    name: str
    environment: Literal["dev", "staging", "production"] = "dev"


class OrbitConfig(BaseModel):
    apiVersion: str
    kind: str
    metadata: OrbitMetadata
    spec: OrbitSpec

    @model_validator(mode="after")
    def validate_schema(self) -> OrbitConfig:
        if self.apiVersion != "astromesh/v1":
            raise ValueError(f"Unsupported apiVersion: {self.apiVersion}. Expected: astromesh/v1")
        if self.kind != "OrbitDeployment":
            raise ValueError(f"Unsupported kind: {self.kind}. Expected: OrbitDeployment")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> OrbitConfig:
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        data = yaml.safe_load(path.read_text())
        return cls.model_validate(data)
