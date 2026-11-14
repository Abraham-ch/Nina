import {cpSync,existsSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
for(const name of ['Workers','Assets','ThirdParty','Widgets']) {
  const source=resolve(root,'node_modules/cesium/Build/Cesium',name);
  const destination=resolve(root,'public/cesium',name);
  mkdirSync(destination,{recursive:true});
  cpSync(source,destination,{recursive:true,force:true});
}
if(!existsSync(resolve(root,'public/assets/countries.geojson'))) throw Error('Falta la cartografía de referencia de países');
console.log('Recursos Cesium preparados localmente.');
