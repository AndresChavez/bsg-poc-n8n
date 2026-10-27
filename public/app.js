/* Sin respuestas simuladas: cada mensaje se envía a Vercel y de allí a n8n. */
(()=>{'use strict';
 const C=window.MESA_CONFIG,$=id=>document.getElementById(id);
 const fresh=()=>crypto.randomUUID();let session=fresh(),busy=false,pending=null,shown=new Set();
 try{session=sessionStorage.getItem('mo_consultas_session')||session;sessionStorage.setItem('mo_consultas_session',session);}catch{}
 const text=(tag,clase,value)=>{const n=document.createElement(tag);if(clase)n.className=clase;n.textContent=value;return n;};
 const status=s=>$('estado-consulta').textContent=s;
 const count=()=>$('contador').textContent=$('mensaje').value.length+' / 1000';
 function chat(rol,mensaje){$('vacio')?.remove();const n=text('div','mensaje-chat '+rol,'');const contenido=rol==='agente'&&window.MilOficiosMarkdown?window.MilOficiosMarkdown.render(mensaje):text('span','',mensaje);n.append(text('strong','mensaje-autor',rol==='cliente'?'Tú':rol==='agente'?'Agente':'Aviso'),contenido);$('conversacion').append(n);$('conversacion').scrollTop=$('conversacion').scrollHeight;}
 function nueva(){if(busy)return;session=fresh();try{sessionStorage.setItem('mo_consultas_session',session);}catch{}pending=null;shown.clear();$('conversacion').replaceChildren(text('p','ayuda','Conversación nueva. Identifica al cliente antes de consultar su historial.'));$('mensaje').value='';count();status('');$('mensaje').focus();}
 async function enviar(e){e.preventDefault();if(busy)return;const mensaje=$('mensaje').value.trim(),codigo=$('codigo').value.trim();
  let problema=mensaje.length<3||mensaje.length>1000?'Escribe entre 3 y 1000 caracteres.':!codigo?'Introduce el código de acceso de la demo.':'';
  $('error-mensaje').textContent=problema;$('error-mensaje').hidden=!problema;if(problema)return;
  if(!pending||pending.mensaje!==mensaje)pending={mensaje,session_id:session,request_id:fresh()};
  if(!shown.has(pending.request_id)){chat('cliente',mensaje);shown.add(pending.request_id);}
  busy=true;$('enviar').disabled=true;$('nueva').disabled=true;$('mensaje').disabled=true;$('enviar-texto').textContent='Consultando…';status('Esperando la respuesta del agente de n8n…');
  const control=new AbortController(),timer=setTimeout(()=>control.abort(),C.timeoutMs);
  try{const res=await fetch(C.endpoint,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json','x-access-code':codigo},body:JSON.stringify(pending),signal:control.signal,cache:'no-store'});
   let data;try{data=await res.json();}catch{throw Error('La API no devolvió una respuesta JSON.');}
   if(!res.ok||data.ok!==true)throw Error(data.error?.mensaje||'No se pudo completar la consulta.');
   if(data.meta?.session_id!==session||data.meta?.request_id!==pending.request_id||typeof data.respuesta!=='string')throw Error('La respuesta no corresponde a este mensaje.');
   chat('agente',data.respuesta);pending=null;$('mensaje').value='';count();status('Respuesta recibida desde n8n.');
  }catch(err){chat('error',err.name==='AbortError'?'La consulta tardó demasiado. Puedes reintentar el mensaje.':err.message||'No se pudo contactar con el servidor.');status('Consulta no completada.');}
  finally{clearTimeout(timer);busy=false;$('enviar').disabled=false;$('nueva').disabled=false;$('mensaje').disabled=false;$('enviar-texto').textContent='Enviar consulta';}
 }
 for(const a of C.acciones){const b=text('button','ejemplo','');b.type='button';b.append(text('span','ejemplo-titulo',a.titulo),text('span','ejemplo-tipo',a.detalle));b.addEventListener('click',()=>{if(busy)return;$('mensaje').value=a.mensaje;count();$('mensaje').focus();});const li=document.createElement('li');li.append(b);$('acciones-consulta').append(li);}
 $('formulario').addEventListener('submit',enviar);$('nueva').addEventListener('click',nueva);$('mensaje').addEventListener('input',count);$('mensaje').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();$('formulario').requestSubmit();}});
 fetch(C.health,{cache:'no-store',signal:AbortSignal.timeout(8000)}).then(r=>r.json()).then(d=>{if(d.ok!==true)throw Error();$('conexion').dataset.estado=d.configurado?'conectado':'sin-configurar';$('conexion-texto').textContent=d.configurado?'API configurada · n8n':'Falta configurar conexión';if(!d.configurado){$('aviso').textContent='Configura N8N_WEBHOOK_URL, N8N_WEBHOOK_TOKEN y ACCESS_CODE en el servidor. Las consultas no utilizan respuestas guardadas.';$('aviso').hidden=false;}}).catch(()=>{$('conexion').dataset.estado='sin-backend';$('conexion-texto').textContent='API no disponible';$('aviso').textContent='Publica el proyecto completo o inicia FastAPI para conectar con n8n.';$('aviso').hidden=false;});
})();
