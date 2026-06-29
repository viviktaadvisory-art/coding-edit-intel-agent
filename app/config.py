import os

# Base Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")

# Create Database directory if it doesn't exist
os.makedirs(DB_DIR, exist_ok=True)

# Separate Databases Paths
IAM_PROXY_DB_PATH = os.path.join(DB_DIR, "iam_proxy.db")
ONTOLOGIES_DB_PATH = os.path.join(DB_DIR, "ontologies.db")
CLAIMS_REGISTRY_DB_PATH = os.path.join(DB_DIR, "claims_registry.db")
PROVIDER_PROFILES_DB_PATH = os.path.join(DB_DIR, "provider_profiles.db")

# Connection URIs
IAM_PROXY_DB_URI = f"sqlite:///{IAM_PROXY_DB_PATH}"
ONTOLOGIES_DB_URI = f"sqlite:///{ONTOLOGIES_DB_PATH}"
CLAIMS_REGISTRY_DB_URI = f"sqlite:///{CLAIMS_REGISTRY_DB_PATH}"
PROVIDER_PROFILES_DB_URI = f"sqlite:///{PROVIDER_PROFILES_DB_PATH}"
