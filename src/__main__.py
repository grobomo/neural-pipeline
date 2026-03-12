"""Allow running src package directly for diagnostics."""
from .config import Config

config = Config()
print(f"Neural Pipeline root: {config.root}")
print(f"Phases: {', '.join(config.phases)}")
print(f"Models: ego={config.model_for('ego')}, worker={config.model_for('worker')}")
