import sys
import pathlib

# Add the repo root to sys.path so that `metis_app` can be imported
# without requiring a separate install step.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import reflex as rx

config = rx.Config(app_name="metis_reflex")
