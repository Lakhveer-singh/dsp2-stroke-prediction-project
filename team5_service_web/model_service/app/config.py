import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dsp_user:change_me@localhost:5432/dsp_app")
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(os.path.dirname(__file__), "artifacts", "model_pipeline.pkl"))
