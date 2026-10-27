"""Pruebas de API con transporte simulado: no llaman a n8n ni leen .env."""
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import app as proxy
from contrato import normalizar_salida,validar_peticion,ErrorContrato
S='11111111-1111-4111-8111-111111111111';R='22222222-2222-4222-8222-222222222222'
class Tests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  proxy._visitas.clear();self.env=patch.dict(os.environ,{'ACCESS_CODE':'test-only','N8N_WEBHOOK_TOKEN':'webhook-test-only','N8N_WEBHOOK_URL':'https://n8n.invalid/webhook/mil-oficios'});self.env.start()
  self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=proxy.app),base_url='http://test')
 async def asyncTearDown(self):await self.client.aclose();self.env.stop()
 def body(self):return {'mensaje':'Consulta de políticas','session_id':S,'request_id':R}
 def reply(self):return {'ok':True,'respuesta':'Respuesta controlada del agente.','meta':{'session_id':S,'request_id':R,'execution_id':'test-001'},'raw_api':{'secret':'NO_ENVIAR'}}
 async def test_access_required(self):
  r=await self.client.post('/api/triage',json=self.body());self.assertEqual(r.status_code,401)
 async def test_access_unconfigured(self):
  os.environ['ACCESS_CODE']='';r=await self.client.post('/api/triage',json=self.body());self.assertEqual(r.status_code,503)
 async def test_live_forwarding(self):
  original=httpx.AsyncClient
  def handle(req):
   self.assertEqual(json.loads(req.content),self.body());self.assertEqual(req.headers['x-api-key'],'webhook-test-only');self.assertNotIn('x-access-code',req.headers)
   return httpx.Response(200,json=self.reply())
  def factory(**kwargs):return original(transport=httpx.MockTransport(handle),**kwargs)
  with patch.object(proxy.httpx,'AsyncClient',factory):
   r=await self.client.post('/api/triage',json=self.body(),headers={'x-access-code':'test-only'})
  self.assertEqual(r.status_code,200);self.assertEqual(r.json()['respuesta'],'Respuesta controlada del agente.');self.assertNotIn('NO_ENVIAR',r.text);self.assertEqual(r.headers['cache-control'],'no-store')
 async def test_foreign_session(self):
  async def fake(_):r=self.reply();r['meta']['session_id']='otra';return r
  with patch.object(proxy,'llamar_backend',fake):r=await self.client.post('/api/triage',json=self.body(),headers={'x-access-code':'test-only'})
  self.assertEqual(r.status_code,502)
 async def test_invalid_inputs(self):
  async def blocked(_):raise AssertionError('No debe consultar n8n')
  with patch.object(proxy,'llamar_backend',blocked):
   for body in [{}, {**self.body(),'mensaje':'x'*1001},{**self.body(),'session_id':'123'},{**self.body(),'request_id':False}]:
    r=await self.client.post('/api/triage',json=body,headers={'x-access-code':'test-only'});self.assertEqual(r.status_code,400)
 async def test_json_error(self):
  r=await self.client.post('/api/triage',content='{',headers={'x-access-code':'test-only'});self.assertEqual(r.status_code,400)
 async def test_backend_auth_failure(self):
  with self.assertRaises(ErrorContrato) as ctx:proxy.interpretar(httpx.Response(401,text='not authorized'))
  self.assertEqual(ctx.exception.codigo,'backend_acceso')
 async def test_health_config(self):
  r=await self.client.get('/api/health');self.assertTrue(r.json()['configurado']);self.assertNotIn('test-only',r.text)
  os.environ['N8N_WEBHOOK_TOKEN']='';r=await self.client.get('/api/health');self.assertFalse(r.json()['configurado'])
 async def test_static(self):
  r=await self.client.get('/');self.assertIn('Respuesta del agente',r.text);self.assertNotIn('Especialistas compatibles',r.text)
 async def test_contract_without_business_fields(self):
  r=normalizar_salida(self.reply());self.assertEqual(r['meta']['version'],'4.0');self.assertNotIn('registro',r);self.assertNotIn('raw_api',r)
 async def test_empty_answer(self):
  for d in [{},{'ok':True,'respuesta':''},{'ok':True,'output':'texto'}]:
   with self.assertRaises(ErrorContrato):normalizar_salida(d)
 async def test_backend_error(self):
  with self.assertRaises(ErrorContrato):normalizar_salida({'ok':False,'error':{'codigo':'backend','mensaje':'Error controlado'}})
if __name__=='__main__':unittest.main(verbosity=2)
