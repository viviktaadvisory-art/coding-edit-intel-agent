from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import (
    IAM_PROXY_DB_URI,
    ONTOLOGIES_DB_URI,
    CLAIMS_REGISTRY_DB_URI,
    PROVIDER_PROFILES_DB_URI
)

# 1. Database Engine Mappings (Check Same Thread is False for SQLite multi-thread FastAPI support)
iam_engine = create_engine(IAM_PROXY_DB_URI, connect_args={"check_same_thread": False})
ontology_engine = create_engine(ONTOLOGIES_DB_URI, connect_args={"check_same_thread": False})
claims_engine = create_engine(CLAIMS_REGISTRY_DB_URI, connect_args={"check_same_thread": False})
provider_engine = create_engine(PROVIDER_PROFILES_DB_URI, connect_args={"check_same_thread": False})

# 2. Session Factories
SessionIAM = sessionmaker(autocommit=False, autoflush=False, bind=iam_engine)
SessionOntology = sessionmaker(autocommit=False, autoflush=False, bind=ontology_engine)
SessionClaims = sessionmaker(autocommit=False, autoflush=False, bind=claims_engine)
SessionProvider = sessionmaker(autocommit=False, autoflush=False, bind=provider_engine)

# 3. Segregated Declarative Bases
IAMBase = declarative_base()
OntologyBase = declarative_base()
ClaimsBase = declarative_base()
ProviderBase = declarative_base()

# 4. Dependency Injection Session Providers
def get_iam_db():
    db = SessionIAM()
    try:
        yield db
    finally:
        db.close()

def get_ontology_db():
    db = SessionOntology()
    try:
        yield db
    finally:
        db.close()

def get_claims_db():
    db = SessionClaims()
    try:
        yield db
    finally:
        db.close()

def get_provider_db():
    db = SessionProvider()
    try:
        yield db
    finally:
        db.close()
