from astromesh.ml.model_registry import ModelRegistry, ModelFormat, ModelStatus
from astromesh.ml.serving.onnx_runtime import ONNXModelServer, ONNXServingConfig
from astromesh.ml.serving.torch_serve import TorchModelServer, TorchServingConfig
from astromesh.ml.training.classifier import ClassifierTrainer, ClassifierConfig
from astromesh.ml.training.embeddings import EmbeddingTrainer, EmbeddingTrainerConfig


def test_register_model():
    registry = ModelRegistry()
    info = registry.register("my-classifier", "1.0", ModelFormat.ONNX,
                             "/models/classifier.onnx", "classification")
    assert info.name == "my-classifier"
    assert info.status == ModelStatus.REGISTERED


def test_get_model():
    registry = ModelRegistry()
    registry.register("model", "1.0", ModelFormat.PYTORCH, "/path", "generation")
    registry.register("model", "2.0", ModelFormat.PYTORCH, "/path2", "generation")
    info = registry.get("model", "latest")
    assert info.version == "2.0"


def test_list_models_by_task():
    registry = ModelRegistry()
    registry.register("cls1", "1.0", ModelFormat.ONNX, "/p1", "classification")
    registry.register("emb1", "1.0", ModelFormat.ONNX, "/p2", "embedding")
    cls_models = registry.list_models(task="classification")
    assert len(cls_models) == 1
    assert cls_models[0].name == "cls1"


def test_unregister_model():
    registry = ModelRegistry()
    registry.register("temp", "1.0", ModelFormat.ONNX, "/p", "test")
    registry.unregister("temp", "1.0")
    assert registry.get("temp", "1.0") is None


async def test_classifier_trainer():
    config = ClassifierConfig(model_name="test-model", epochs=1)
    trainer = ClassifierTrainer(config)
    await trainer.prepare([{"text": "hello", "label": 0}])
    metrics = await trainer.train()
    assert metrics["status"] == "training_complete"


async def test_embedding_trainer():
    config = EmbeddingTrainerConfig(base_model="test-model", epochs=1)
    trainer = EmbeddingTrainer(config)
    await trainer.prepare([{"query": "q", "positive": "p"}])
    metrics = await trainer.train()
    assert metrics["status"] == "training_complete"


def test_onnx_serving_config():
    config = ONNXServingConfig(model_path="/models/test.onnx", device="cpu")
    server = ONNXModelServer(config)
    assert server._config.device == "cpu"


def test_torch_serving_config():
    config = TorchServingConfig(model_path="/models/test.pt")
    server = TorchModelServer(config)
    assert server._config.device == "cpu"
