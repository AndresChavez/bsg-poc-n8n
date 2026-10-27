/* Markdown del agente: convertir y sanear antes de insertar en la conversación. */
(()=>{'use strict';
 const tags=['p','br','strong','em','del','ul','ol','li','blockquote','code','pre','h1','h2','h3','h4','h5','h6','hr','table','thead','tbody','tr','th','td','a'];
 function render(mensaje){
  const contenido=document.createElement('div');contenido.className='mensaje-contenido';
  const original=String(mensaje??'');
  // Si una dependencia no está disponible, conservar una respuesta legible como texto.
  if(!window.marked?.parse||!window.DOMPurify?.isSupported){contenido.classList.add('texto-plano');contenido.textContent=original;return contenido;}
  try{
   const html=window.marked.parse(original,{gfm:true,breaks:true,async:false});
   const limpio=window.DOMPurify.sanitize(html,{
    ALLOWED_TAGS:tags,ALLOWED_ATTR:['href','title','start','align'],
    ALLOW_DATA_ATTR:false,ALLOW_ARIA_ATTR:false,
    ALLOWED_URI_REGEXP:/^(?:https?:|mailto:)/i,RETURN_DOM_FRAGMENT:true
   });
   for(const enlace of limpio.querySelectorAll('a[href]')){enlace.setAttribute('target','_blank');enlace.setAttribute('rel','noopener noreferrer');}
   contenido.append(limpio);
  }catch{contenido.classList.add('texto-plano');contenido.textContent=original;}
  return contenido;
 }
 window.MilOficiosMarkdown=Object.freeze({render});
})();
