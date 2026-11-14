import {useEffect,useRef,useState} from 'react';
import {Viewer,Cartesian3,Cartesian2,Color,EllipsoidTerrainProvider,SingleTileImageryProvider,UrlTemplateImageryProvider,GeographicTilingScheme,Rectangle,GeoJsonDataSource,BillboardCollection,ScreenSpaceEventHandler,ScreenSpaceEventType,Cartographic,Math as CMath,SplitDirection,SceneMode,BlendOption} from 'cesium';
import {Globe2,Map as MapIcon,LocateFixed,PenLine,Check,X,Plus,Minus} from 'lucide-react';
import 'cesium/Build/Cesium/Widgets/widgets.css';
import type {Geometry,Layer,Place,Point,Selection} from './types';
import {fmt} from './api';

const reduced=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const emptyGeometry={type:'FeatureCollection',features:[]};
function coordinates(geometry:Geometry){const result:number[][]=[];function walk(value:unknown){if(Array.isArray(value)){if(typeof value[0]==='number')result.push(value as number[]);else value.forEach(walk)}}walk(geometry.coordinates);return result;}
function bounds(geometry:Geometry){const points=coordinates(geometry),longitudes=[...new Set(points.map(p=>(p[0]+360)%360))].sort((a,b)=>a-b);let gap=-1,start=0,end=0;for(let i=0;i<longitudes.length;i++){const next=longitudes[(i+1)%longitudes.length]+(i===longitudes.length-1?360:0);if(next-longitudes[i]>gap){gap=next-longitudes[i];start=next%360;end=longitudes[i]}}const full=360-gap>350;return Rectangle.fromDegrees(full?-180:start>180?start-360:start,Math.min(...points.map(p=>p[1])),full?180:end>180?end-360:end,Math.max(...points.map(p=>p[1])));}
function glyph(square:boolean){const canvas=document.createElement('canvas');canvas.width=canvas.height=20;const ctx=canvas.getContext('2d')!;ctx.fillStyle=square?'#f3b968':'#80d2df';if(square)ctx.fillRect(3,3,14,14);else{ctx.beginPath();ctx.arc(10,10,7,0,Math.PI*2);ctx.fill()}return canvas.toDataURL();}

type Props={selection:Selection;layers:Layer[];compare:boolean;split:number;place:Place|null;drawing:boolean;onDrawing:(value:boolean)=>void;onGeometry:(geometry:Geometry)=>void;onInspect:(point:Point|null)=>void;flat:boolean;onFlat:(value:boolean)=>void};
export default function Globe({selection,layers,compare,split,place,drawing,onDrawing,onGeometry,onInspect,flat,onFlat}:Props){
 const element=useRef<HTMLDivElement>(null),viewer=useRef<Viewer|null>(null),collection=useRef<BillboardCollection|null>(null),aoi=useRef<GeoJsonDataSource|null>(null),vertices=useRef<number[][]>([]);
 const callbacks=useRef({onDrawing,onGeometry,onInspect});callbacks.current={onDrawing,onGeometry,onInspect};
 const drawRef=useRef(drawing),[ready,setReady]=useState(false),[error,setError]=useState(''),[n,setN]=useState(0),[liveImagery,setLiveImagery]=useState(false);
 drawRef.current=drawing;
 useEffect(()=>{
  if(!element.current)return;let disposed=false;let observer:ResizeObserver|undefined;let handler:ScreenSpaceEventHandler|undefined;
  try{
   const v=new Viewer(element.current,{baseLayer:false,baseLayerPicker:false,animation:false,timeline:false,homeButton:false,geocoder:false,sceneModePicker:false,navigationHelpButton:false,fullscreenButton:false,infoBox:false,selectionIndicator:false,terrainProvider:new EllipsoidTerrainProvider(),requestRenderMode:true,maximumRenderTimeChange:Infinity,scene3DOnly:false,shouldAnimate:false,msaaSamples:2,contextOptions:{webgl:{alpha:false,preserveDrawingBuffer:true}}});
   viewer.current=v;v.scene.backgroundColor=Color.fromCssColorString('#071820');v.scene.globe.baseColor=Color.fromCssColorString('#102b37');v.scene.globe.enableLighting=false;v.scene.globe.showGroundAtmosphere=false;if(v.scene.skyBox)v.scene.skyBox.show=false;if(v.scene.sun)v.scene.sun.show=false;if(v.scene.moon)v.scene.moon.show=false;if(v.scene.skyAtmosphere)v.scene.skyAtmosphere.show=true;v.scene.fog.enabled=false;v.resolutionScale=Math.min(window.devicePixelRatio,1.5);v.scene.screenSpaceCameraController.minimumZoomDistance=10000;v.scene.screenSpaceCameraController.maximumZoomDistance=42_000_000;
   v.scene.globe.maximumScreenSpaceError=1;
   v.camera.setView({destination:Cartesian3.fromDegrees(-65,5,18_000_000)});
   SingleTileImageryProvider.fromUrl('/assets/earth-reference.jpg',{credit:'NASA GIBS / ESDIS · Blue Marble de referencia'}).then(provider=>{if(disposed)return;v.imageryLayers.addImageryProvider(provider,0);v.scene.requestRender()}).catch(()=>{});
   const tiles=new UrlTemplateImageryProvider({url:'/api/imagery/blue-marble/{z}/{x}/{y}.jpg',tilingScheme:new GeographicTilingScheme(),maximumLevel:8,tileWidth:512,tileHeight:512,credit:'NASA GIBS · imagen de referencia, no adquirida en la fecha seleccionada'});
   const tileLayer=v.imageryLayers.addImageryProvider(tiles);tileLayer.brightness=.91;tileLayer.contrast=1.08;tiles.errorEvent.addEventListener(()=>{if(!disposed)setLiveImagery(false)});
   v.scene.globe.tileLoadProgressEvent.addEventListener((count:number)=>{if(!disposed&&count===0)setLiveImagery(true)});
   const points=new BillboardCollection({scene:v.scene,blendOption:BlendOption.TRANSLUCENT});collection.current=points;v.scene.primitives.add(points);
   handler=new ScreenSpaceEventHandler(v.scene.canvas);
   handler.setInputAction((event:{position:Cartesian2})=>{
    if(drawRef.current){const ray=v.camera.getPickRay(event.position);const cartesian=ray&&v.scene.globe.pick(ray,v.scene);if(!cartesian)return;const pos=Cartographic.fromCartesian(cartesian);vertices.current.push([CMath.toDegrees(pos.longitude),CMath.toDegrees(pos.latitude)]);setN(vertices.current.length);const line=v.entities.getById('drawing');if(line)v.entities.remove(line);if(vertices.current.length>=2)v.entities.add({id:'drawing',polyline:{positions:Cartesian3.fromDegreesArray(vertices.current.flat()),width:2,material:Color.fromCssColorString('#f3c27b')}});v.scene.requestRender();return;}
    const picked=v.scene.pick(event.position);callbacks.current.onInspect(picked?.id?.geometry?.type==='Point'?picked.id:null);
   },ScreenSpaceEventType.LEFT_CLICK);
   v.screenSpaceEventHandler.removeInputAction(ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
   observer=new ResizeObserver(()=>{if(!v.isDestroyed()){v.resize();v.scene.requestRender()}});observer.observe(element.current);
   setReady(true);
  }catch(e){setError('El visor 3D no pudo iniciarse en este dispositivo. Puedes seleccionar un territorio y usar el calendario y las coordenadas.');}
  return()=>{disposed=true;observer?.disconnect();handler?.destroy();if(viewer.current&&!viewer.current.isDestroyed())viewer.current.destroy();viewer.current=null;};
 },[]);
 useEffect(()=>{const v=viewer.current;if(!ready||!v||!collection.current)return;const points=collection.current;points.removeAll();const square=glyph(true),circle=glyph(false);for(const [index,layer] of layers.entries())for(const point of layer.points.features){const [lon,lat]=point.geometry.coordinates;points.add({position:Cartesian3.fromDegrees(lon,lat,500),image:layer.source==='modis'?square:circle,width:layer.source==='modis'?6:5,height:layer.source==='modis'?6:5,id:point,splitDirection:compare?(index===0?SplitDirection.LEFT:SplitDirection.RIGHT):SplitDirection.NONE,disableDepthTestDistance:0});}v.scene.requestRender();},[ready,layers,compare]);
 useEffect(()=>{const v=viewer.current;if(!v||!ready)return;v.scene.splitPosition=split/100;v.scene.requestRender()},[split,ready]);
 useEffect(()=>{const v=viewer.current;if(!v||!ready)return;if(flat&&v.scene.mode!==SceneMode.SCENE2D)v.scene.morphTo2D(reduced()?0:.7);else if(!flat&&v.scene.mode!==SceneMode.SCENE3D)v.scene.morphTo3D(reduced()?0:.7)},[flat,ready]);
 const areaKey=JSON.stringify([selection.scope,selection.department,selection.geometry]);
 useEffect(()=>{const v=viewer.current;if(!v||!ready)return;let active=true;
  if(aoi.current){v.dataSources.remove(aoi.current,true);aoi.current=null;}
  const geometry=selection.geometry||place?.geometry;
  if(geometry){GeoJsonDataSource.load({type:'Feature',geometry,properties:{}},{stroke:Color.fromCssColorString('#edce97'),strokeWidth:2,fill:Color.fromCssColorString('#e4be79').withAlpha(.025),clampToGround:false}).then(source=>{if(!active||v.isDestroyed())return;aoi.current=source;v.dataSources.add(source);v.scene.requestRender()}).catch(()=>{});v.camera.flyTo({destination:bounds(geometry),duration:reduced()?0:1.1});}
  else if(selection.scope==='PER')v.camera.flyTo({destination:Rectangle.fromDegrees(-83,-20,-67,2),duration:reduced()?0:1.1});
  else v.camera.flyTo({destination:Cartesian3.fromDegrees(-65,5,18_000_000),duration:reduced()?0:1.1});
  return()=>{active=false};
 },[areaKey,ready,place?.properties.id]);
 useEffect(()=>{if(!drawing){vertices.current=[];setN(0);const v=viewer.current;const entity=v?.entities.getById('drawing');if(entity)v?.entities.remove(entity);v?.scene.requestRender()}},[drawing]);
 function finish(){if(vertices.current.length<3)return;const ring=[...vertices.current,vertices.current[0]];callbacks.current.onGeometry({type:'Polygon',coordinates:[ring]});callbacks.current.onDrawing(false);}
 function center(){const v=viewer.current;if(!v)return;if(selection.geometry)v.camera.flyTo({destination:bounds(selection.geometry),duration:reduced()?0:.7});else if(selection.scope==='PER')v.camera.flyTo({destination:Rectangle.fromDegrees(-83,-20,-67,2),duration:reduced()?0:.7});else v.camera.flyTo({destination:Cartesian3.fromDegrees(-65,5,18_000_000),duration:reduced()?0:.7});}
 return <><div ref={element} className="earth-canvas" aria-label="Visor geoespacial mundial. Usa los controles de territorio como alternativa a los gestos."/>{error&&<div className="map-fallback"><img src="/assets/earth-reference.jpg" alt="Cartografía mundial de referencia NASA"/><p role="status">{error}</p></div>}<div className="map-tools" aria-label="Herramientas del mapa"><button aria-label={flat?'Cambiar a globo 3D':'Cambiar a mapa 2D'} onClick={()=>onFlat(!flat)} disabled={!ready}>{flat?<Globe2 size={17}/>:<MapIcon size={17}/>}<span>{flat?'3D':'2D'}</span></button><button aria-label="Centrar selección" onClick={center} disabled={!ready}><LocateFixed size={17}/></button><button aria-label="Acercar" onClick={()=>{viewer.current?.camera.zoomIn((viewer.current?.camera.positionCartographic.height||1e6)*.4);viewer.current?.scene.requestRender()}} disabled={!ready}><Plus size={17}/></button><button aria-label="Alejar" onClick={()=>{viewer.current?.camera.zoomOut((viewer.current?.camera.positionCartographic.height||1e6)*.5);viewer.current?.scene.requestRender()}} disabled={!ready}><Minus size={17}/></button><button aria-label="Dibujar un área" aria-pressed={drawing} onClick={()=>onDrawing(!drawing)} disabled={!ready}><PenLine size={17}/></button></div>{drawing&&<div className="draw-help" role="status"><span>Añade vértices sobre el mapa · {n} puntos</span><button onClick={finish} disabled={n<3}><Check size={15}/>Aplicar área</button><button onClick={()=>onDrawing(false)} aria-label="Cancelar dibujo"><X size={16}/></button></div>}<span className="imagery-credit">NASA GIBS · {liveImagery?'teselas de referencia':'referencia global'} · WGS84</span></>;
}
