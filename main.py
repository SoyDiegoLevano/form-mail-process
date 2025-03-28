from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware  # Importa CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, validator, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import random
import re
import smtplib
from email.mime.text import MIMEText

from database import get_db, Cliente, EstadoAdmision, TipoCliente

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # O especifica los orígenes permitidos
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
    NombreEmpresa: str = None
    RUC: str = None
    correo: EmailStr

    @validator('DNI', always=True)
    def validar_dni(cls, v, values):
        if values.get('tipo') == TipoCliente.PERSONA and not v:
            raise ValueError('DNI es requerido para personas')
        if v and not re.match(r'^\d{8}$', v):
            raise ValueError('DNI debe tener 8 dígitos')
        return v

    @validator('RUC', always=True)
    def validar_ruc(cls, v, values):
        if values.get('tipo') == TipoCliente.EMPRESA and not v:
            raise ValueError('RUC es requerido para empresas')
        if v and not re.match(r'^\d{11}$', v):
            raise ValueError('RUC debe tener 11 dígitos')
        return v

def validar_identidad_inicial(identificador: str, tipo: TipoCliente) -> bool:
    """
    Simulación de validación externa de identidad
    En un escenario real, esto sería una llamada a un servicio externo
    """
    return True

def validar_identidad_secundaria(nombre: str, tipo: TipoCliente) -> bool:
    """
    Simulación de segunda validación externa
    En un escenario real, esto sería una llamada a un servicio externo
    """
    return True

def enviar_email(cliente: Cliente) -> bool:
    try:
        # Configurar el asunto y cuerpo del mensaje
        asunto = 'Solicitud Aprobada'
        if cliente.tipo == TipoCliente.PERSONA:
            cuerpo = f'Estimado {cliente.NombrePersona}, su solicitud ha sido aprobada.'
        else:
            cuerpo = f'Estimado representante de {cliente.NombreEmpresa}, su solicitud ha sido aprobada.'

        # Crear el mensaje
        msg = MIMEText(cuerpo)
        msg['Subject'] = asunto
        msg['From'] = remitente_email
        msg['To'] = cliente.correo

        # Configurar conexión SMTP con Gmail
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            # Autenticar con las credenciales de Gmail
            server.login(remitente_email, remitente_pass)
            
            # Enviar el mensaje
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
    if not validar_identidad_inicial(identificador, solicitud.tipo):
        raise HTTPException(status_code=400, detail="No se ha podido comprobar su identidad")
    
    # Crear registro de cliente
    nuevo_cliente = Cliente(
        tipo=solicitud.tipo,
        NombrePersona=solicitud.NombrePersona,
        DNI=solicitud.DNI,
        NombreEmpresa=solicitud.NombreEmpresa,
        RUC=solicitud.RUC,
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
    
    # Validación secundaria
    nombre = cliente.NombrePersona if cliente.tipo == TipoCliente.PERSONA else cliente.NombreEmpresa
    if validar_identidad_secundaria(nombre, cliente.tipo):
        cliente.EstadoAdmision = EstadoAdmision.ADMITIDO
        enviar_email(cliente)
    else:
        cliente.EstadoAdmision = EstadoAdmision.ERROR_REGISTRO
    
    db.commit()
    return {"id": cliente.id, "estado": cliente.EstadoAdmision}
