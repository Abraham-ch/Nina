import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {ArrowLeft,ArrowRight,X} from 'lucide-react';

// Guía de la plataforma para quien conoce poco del tema: resalta cada control y explica el concepto que hay detrás.
type Step={target?:string;title:string;body:string};
const STEPS:Step[]=[
 {title:'Bienvenida a NINA',body:'NINA reúne las detecciones de calor que los satélites de la NASA registran desde 2000. Cada detección es un píxel térmico: un área de 375 m a 1 km más caliente que su entorno. No equivale a un incendio individual; muchas detecciones pueden pertenecer al mismo fuego.'},
 {target:'.territory-field',title:'1 · ¿Dónde?',body:'Elige el territorio: el planeta, el Perú con su archivo histórico, cualquier país o una región peruana. Todo lo que ves (mapa, calendario y exportaciones) se recalcula para esa área.'},
 {target:'.sensor-field',title:'2 · ¿Con qué ojos?',body:'Cada satélite es un observador distinto. MODIS (1 km) mira desde 2000; VIIRS (375 m) desde 2012 y ve más detalle, así que detecta más focos sobre el mismo fuego. Por eso NINA nunca suma sus conteos: compara siempre dentro de un mismo observador.'},
 {target:'.coordinates-button',title:'3 · Tu propia área',body:'¿Te interesa una cuenca, un área protegida o tu distrito? Escribe coordenadas o dibuja un polígono sobre el mapa con el lápiz de la derecha.'},
 {target:'.atlas-stage',title:'4 · El mapa',body:'Cada nube roja agrupa detecciones del mes elegido. Arrastra para girar el globo y usa la rueda para acercarte. Haz clic en un punto para ver su fecha, su potencia radiativa (FRP, en megavatios) y la confianza del producto.'},
 {target:'.map-tools',title:'5 · Herramientas del mapa',body:'Cambia entre globo 3D y mapa 2D, vuelve a centrar tu selección, acércate o aléjate y dibuja un área.'},
 {target:'.month-axis',title:'6 · ¿Cuándo?',body:'Elige el mes. Una marca vacía significa que no hay datos para ese periodo, que no es lo mismo que cero focos. NINA nunca pinta un hueco como «sin actividad».'},
 {target:'.map-evidence',title:'7 · ¿Es un mes inusual?',body:'«Revisar evidencia» compara el mes con la mediana de ese mismo mes en otros años del mismo observador e indica cuántos años sustentan la comparación.'},
 {target:'.site-header nav',title:'8 · Más vistas',body:'«Calendario» muestra años por meses para descubrir la temporada de fuego de un lugar. «Laboratorio» pone dos observadores lado a lado para ver cuánto cambia la señal según el satélite.'},
 {target:'.time-export',title:'9 · Llévate los datos',body:'Exporta los focos y los agregados en CSV, con la cita de NASA FIRMS y los filtros usados. Recuerda: son datos de contexto histórico, no para decisiones tácticas o a escala local.'},
 {target:'.story-start',title:'10 · Una historia guiada',body:'«Expedición» te lleva por una pregunta real: ¿cambió el fuego o cambió el observador? Puedes volver a esta guía cuando quieras con el botón «Guía».'},
];

export default function Tour({onClose}:{onClose:()=>void}){
 const [i,setI]=useState(0),[rect,setRect]=useState<DOMRect|null>(null),card=useRef<HTMLDivElement>(null),[pos,setPos]=useState({top:0,left:0});
 const step=STEPS[i],last=i===STEPS.length-1;
 useEffect(()=>{const el=step.target?document.querySelector(step.target):null;el?.scrollIntoView({block:'center',behavior:'instant'});card.current?.focus();
  const measure=()=>setRect(el?el.getBoundingClientRect():null);measure();
  addEventListener('resize',measure);addEventListener('scroll',measure,true);return()=>{removeEventListener('resize',measure);removeEventListener('scroll',measure,true)}},[i]);
 useLayoutEffect(()=>{const c=card.current;if(!c)return;const w=c.offsetWidth,h=c.offsetHeight,m=16;
  if(!rect){setPos({top:(innerHeight-h)/2,left:(innerWidth-w)/2});return}
  // Debajo del objetivo si cabe; si no, encima; si el objetivo ocupa casi toda la pantalla, dentro de él.
  let top=rect.bottom+14;if(top+h>innerHeight-m)top=rect.top-h-14;if(top<m)top=Math.min(innerHeight-h-m,rect.top+24);
  const left=Math.min(Math.max(m,rect.left+rect.width/2-w/2),innerWidth-w-m);setPos({top,left})},[rect,i]);
 useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape')onClose();else if(e.key==='ArrowRight'&&!last)setI(i+1);else if(e.key==='ArrowLeft'&&i)setI(i-1)};addEventListener('keydown',key);return()=>removeEventListener('keydown',key)},[i,last,onClose]);
 const pad=6;
 return <div className="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
  {rect?<div className="tour-spot" style={{top:rect.top-pad,left:rect.left-pad,width:rect.width+pad*2,height:rect.height+pad*2}}/>:<div className="tour-veil"/>}
  <div ref={card} tabIndex={-1} className="tour-card" style={pos}>
   <div className="tour-top"><span>{i+1} / {STEPS.length}</span><button onClick={onClose} aria-label="Cerrar guía"><X size={16}/></button></div>
   <h2 id="tour-title">{step.title}</h2><p>{step.body}</p>
   <div className="tour-progress" aria-hidden="true">{STEPS.map((_,k)=><i key={k} className={k<=i?'on':''}/>)}</div>
   <div className="tour-actions"><button onClick={()=>setI(i-1)} disabled={!i}><ArrowLeft size={15}/>Anterior</button>{last?<button className="tour-next" onClick={onClose}>Empezar a explorar</button>:<button className="tour-next" onClick={()=>setI(i+1)}>Siguiente<ArrowRight size={15}/></button>}</div>
  </div>
 </div>;
}
