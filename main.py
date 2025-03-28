import re
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, validator, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import smtplib
from email.mime.text import MIMEText

from database import get_db, Cliente, EstadoAdmision, TipoCliente

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

remitente_email = "soydiegolevano@gmail.com"
remitente_pass = "jaeu jwra flrl rwcd"

class SolicitudCreate(BaseModel):
    tipo: TipoCliente
    NombrePersona: str = None
    DNI: str = None
    AliasPersona: str = None    # Campo para alias de persona
    NombreEmpresa: str = None
    RUC: str = None
    AliasEmpresa: str = None    # Campo para alias de empresa
    correo: EmailStr

    @validator('DNI', always=True)
    def validar_dni(cls, v, values):
        if values.get('tipo') == TipoCliente.PERSONA:
            if not v:
                raise ValueError('DNI es requerido para personas')
            if not re.match(r'^\d{8}$', v):
                raise ValueError('DNI debe tener 8 dígitos')
        return v

    @validator('RUC', always=True)
    def validar_ruc(cls, v, values):
        if values.get('tipo') == TipoCliente.EMPRESA:
            if not v:
                raise ValueError('RUC es requerido para empresas')
            if not re.match(r'^\d{11}$', v):
                raise ValueError('RUC debe tener 11 dígitos')
        return v

    @validator('AliasPersona', always=True)
    def validar_alias_persona(cls, v, values):
        if values.get('tipo') == TipoCliente.PERSONA:
            if not v:
                raise ValueError('AliasPersona es requerido para personas')
            if re.search(r'\s', v):
                raise ValueError('AliasPersona no puede contener espacios')
            if v != v.lower():
                raise ValueError('AliasPersona debe estar en minúsculas')
            if not re.match(r'^[a-z0-9_]+$', v):
                raise ValueError('AliasPersona solo puede contener letras minúsculas, números y guiones bajos')
        return v

    @validator('AliasEmpresa', always=True)
    def validar_alias_empresa(cls, v, values):
        if values.get('tipo') == TipoCliente.EMPRESA:
            if not v:
                raise ValueError('AliasEmpresa es requerido para empresas')
            if re.search(r'\s', v):
                raise ValueError('AliasEmpresa no puede contener espacios')
            if v != v.lower():
                raise ValueError('AliasEmpresa debe estar en minúsculas')
            if not re.match(r'^[a-z0-9_]+$', v):
                raise ValueError('AliasEmpresa solo puede contener letras minúsculas, números y guiones bajos')
        return v

def validar_identidad(identificador: str, tipo: TipoCliente) -> bool:
    """
    Simulación de validación externa de identidad.
    """
    return True

def crear_schema_por_alias(db: Session, alias: str) -> bool:
    """
    Crea un schema en PostgreSQL con el nombre indicado en alias, si no existe.
    """
    try:
        query = text(f'CREATE SCHEMA IF NOT EXISTS "{alias}"')
        db.execute(query)
        db.commit()
        return True
    except Exception as e:
        print(f"Error al crear el schema '{alias}': {e}")
        db.rollback()
        return False

def replicar_tablas(db: Session, alias: str):
    """
    Replica la estructura de las tablas existentes en el schema 'public'
    (exceptuando la tabla 'clientes') dentro del schema 'alias'. No copia datos.
    """
    sql = f"""
    DO $$
    DECLARE
        rec record;
    BEGIN
        FOR rec IN
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public' AND tablename != 'clientes'
        LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS {alias}.%I (LIKE public.%I INCLUDING ALL)',
                rec.tablename, rec.tablename
            );
        END LOOP;
    END $$;
    """
    db.execute(text(sql))
    db.commit()

def validar_creation_schema(cliente: Cliente, db: Session) -> bool:
    """
    Valida que se haya asignado un alias y crea un schema en PostgreSQL con ese alias.
    """
    if cliente.tipo == TipoCliente.PERSONA:
        if not cliente.AliasPersona:
            print("Falta AliasPersona")
            return False
        print("Persona validada")
        schema_created = crear_schema_por_alias(db, cliente.AliasPersona)
    elif cliente.tipo == TipoCliente.EMPRESA:
        if not cliente.AliasEmpresa:
            print("Falta AliasEmpresa")
            return False
        print("Empresa validada")
        schema_created = crear_schema_por_alias(db, cliente.AliasEmpresa)
    else:
        schema_created = False
    return schema_created

def enviar_email(cliente: Cliente) -> bool:
    try:
        asunto = 'Solicitud Aprobada'
        if cliente.tipo == TipoCliente.PERSONA:
            cuerpo = f'Estimado {cliente.NombrePersona}, su solicitud ha sido aprobada.'
        else:
            cuerpo = f'Estimado representante de {cliente.NombreEmpresa}, su solicitud ha sido aprobada.'

        msg = MIMEText(cuerpo)
        msg['Subject'] = asunto
        msg['From'] = remitente_email
        msg['To'] = cliente.correo

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(remitente_email, remitente_pass)
            server.send_message(msg)
        
        return True
    except Exception as e:
        print(f"Error enviando email: {e}")
        return False

@app.post("/solicitud")
@limiter.limit("5/minute")
async def crear_solicitud(
    request: Request,
    solicitud: SolicitudCreate, 
    db: Session = Depends(get_db)
):
    # Validación inicial de identidad
    identificador = solicitud.DNI if solicitud.tipo == TipoCliente.PERSONA else solicitud.RUC
    if not validar_identidad(identificador, solicitud.tipo):
        raise HTTPException(status_code=400, detail="No se ha podido comprobar su identidad")
    
    # Crear registro de cliente con los nuevos campos de alias
    nuevo_cliente = Cliente(
        tipo=solicitud.tipo,
        NombrePersona=solicitud.NombrePersona,
        DNI=solicitud.DNI,
        AliasPersona=solicitud.AliasPersona,
        NombreEmpresa=solicitud.NombreEmpresa,
        RUC=solicitud.RUC,
        AliasEmpresa=solicitud.AliasEmpresa,
        correo=solicitud.correo,
        EstadoAdmision=EstadoAdmision.EN_PROCESO
    )
    
    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)
    
    return {"id": nuevo_cliente.id, "estado": nuevo_cliente.EstadoAdmision}

@app.get("/solicitudes")
async def listar_solicitudes(db: Session = Depends(get_db)):
    solicitudes = db.query(Cliente).filter(
        Cliente.EstadoAdmision == EstadoAdmision.EN_PROCESO
    ).all()
    return solicitudes

@app.post("/aprobar")
async def aprobar_solicitud(
    id_solicitud: int,
    db: Session = Depends(get_db)
):
    cliente = db.query(Cliente).filter(Cliente.id == id_solicitud).first()
    
    if not cliente:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    if not enviar_email(cliente):
        raise HTTPException(status_code=500, detail="Error al enviar el email")
    
    # Crear el schema usando el alias correspondiente y replicar la estructura de tablas (sin datos)
    alias = cliente.AliasPersona if cliente.tipo == TipoCliente.PERSONA else cliente.AliasEmpresa
    if validar_creation_schema(cliente, db):
        replicar_tablas(db, alias)
        cliente.EstadoAdmision = EstadoAdmision.ADMITIDO
    else:
        cliente.EstadoAdmision = EstadoAdmision.ERROR_REGISTRO
    
    db.commit()
    return {"id": cliente.id, "estado": cliente.EstadoAdmision}

@app.post("/rechazar")
async def rechazar_solicitud(
    id_solicitud: int,
    db: Session = Depends(get_db)
):
    cliente = db.query(Cliente).filter(Cliente.id == id_solicitud).first()

    if not cliente:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    
    if enviar_email(cliente):
        cliente.EstadoAdmision = EstadoAdmision.RECHAZADO
    else:
        cliente.EstadoAdmision = EstadoAdmision.ERROR_REGISTRO
    
    db.commit()
    return {"id": cliente.id, "estado": cliente.EstadoAdmision}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
