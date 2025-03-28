from sqlalchemy import create_engine, Column, Integer, String, Enum, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from enum import Enum as PyEnum
import databases
import sqlalchemy

# Configuración de base de datos
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/bd-test"

# Motor de base de datos
database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# Base para modelos
Base = declarative_base()

class EstadoAdmision(PyEnum):
    EN_PROCESO = "en_proceso"
    ERROR_REGISTRO = "error_registro"
    ADMITIDO = "admitido"

class TipoCliente(PyEnum):
    PERSONA = "persona"
    EMPRESA = "empresa"

class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(Enum(TipoCliente), nullable=False)
    
    # Campos para persona
    NombrePersona = Column(String, nullable=True)
    DNI = Column(String, nullable=True, unique=True, index=True)
    
    # Campos para empresa
    NombreEmpresa = Column(String, nullable=True)
    RUC = Column(String, nullable=True, unique=True, index=True)
    
    # Campos comunes
    correo = Column(String, nullable=False, unique=True, index=True)
    EstadoAdmision = Column(Enum(EstadoAdmision), default=EstadoAdmision.EN_PROCESO)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())

# Crear motor de SQLAlchemy
engine = create_engine(DATABASE_URL)

# Crear sesión
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Crear tablas
Base.metadata.create_all(bind=engine)

def get_db():
    """Genera una sesión de base de datos"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()