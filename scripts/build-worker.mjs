import {mkdir,rm,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url));
const target=path.join(root,'dist','public');
await rm(target,{recursive:true,force:true});await mkdir(target,{recursive:true});
const files=['index.html','auth.js','auth.css','storage.js','pedidos.js','manifest.webmanifest','pwa.js','service-worker.js','icons/icon-180.png','icons/icon-192.png','icons/icon-512.png'];
for(const name of files){await mkdir(path.dirname(path.join(target,name)),{recursive:true});await copyFile(path.join(root,name),path.join(target,name));}
console.log(`Cloudflare: ${files.length} arquivos públicos preparados.`);
