"""Contrato 4.0: mensaje del operador y respuesta textual del agente n8n."""
from __future__ import annotations
import re
import uuid

VERSION='4.0'
CODIGOS_ERROR=('validacion','acceso','limite','sin_configurar','backend_acceso','backend_url','cuota_ia','backend','timeout','respuesta_invalida')
class ErrorContrato(Exception):
 def __init__(self,codigo,mensaje,status=400,detalle='',reintentable=False):
  super().__init__(mensaje);self.codigo,self.mensaje,self.status=codigo,mensaje,status;self.detalle,self.reintentable=detalle,reintentable
def limpiar_texto(valor,maximo):
 return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]','',valor).strip()[:maximo] if isinstance(valor,str) else ''
def validar_peticion(cuerpo):
 if not isinstance(cuerpo,dict) or not isinstance(cuerpo.get('mensaje'),str):raise ErrorContrato('validacion','Escribe tu consulta.')
 bruto=cuerpo['mensaje']
 if len(bruto)>4000:raise ErrorContrato('validacion','El mensaje supera los 1000 caracteres.')
 mensaje=limpiar_texto(bruto,4000)
 if not 3<=len(mensaje)<=1000:raise ErrorContrato('validacion','Escribe entre 3 y 1000 caracteres.')
 out={'mensaje':mensaje}
 for k in ('session_id','request_id'):
  try:out[k]=str(uuid.UUID(cuerpo[k]))
  except (KeyError,ValueError,AttributeError,TypeError):raise ErrorContrato('validacion',k+' debe ser un UUID válido.') from None
 return out
def normalizar_salida(crudo,*,backend='n8n',ruta='C'):
 if not isinstance(crudo,dict):raise ErrorContrato('respuesta_invalida','n8n no devolvió un objeto JSON.',502)
 if crudo.get('ok') is False:
  e=crudo.get('error') if isinstance(crudo.get('error'),dict) else {};codigo=e.get('codigo') if e.get('codigo') in CODIGOS_ERROR else 'backend'
  raise ErrorContrato(codigo,limpiar_texto(e.get('mensaje'),300) or 'No fue posible completar la consulta.',502,reintentable=e.get('reintentable') is True)
 if crudo.get('ok') is not True or not isinstance(crudo.get('respuesta'),str) or not crudo['respuesta'].strip():raise ErrorContrato('respuesta_invalida','n8n no devolvió una respuesta del agente.',502)
 m=crudo.get('meta') if isinstance(crudo.get('meta'),dict) else {}
 return {'ok':True,'respuesta':limpiar_texto(crudo['respuesta'],12000),'meta':{'version':VERSION,'backend':backend,'ruta':ruta,'session_id':limpiar_texto(m.get('session_id'),80),'request_id':limpiar_texto(m.get('request_id'),80),'execution_id':limpiar_texto(m.get('execution_id'),80)}}
def respuesta_error(e,id_solicitud,backend='n8n'):
 return {'ok':False,'error':{'codigo':e.codigo if e.codigo in CODIGOS_ERROR else 'backend','mensaje':limpiar_texto(e.mensaje,300),'reintentable':bool(e.reintentable)},'meta':{'version':VERSION,'backend':backend,'id':id_solicitud}}
