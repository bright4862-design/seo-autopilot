import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

export async function renderComponent(path, props) {
  const result = await build({
    entryPoints:[path], bundle:true, write:false, platform:'node', format:'cjs', external:['react','react/*','react-dom','react-dom/*'], mainFields:['module','main'],
    alias:{'@':resolve('src')},
    plugins:[{name:'inert-analytics',setup(build) {
      build.onResolve({filter:/[\/]lib[\/]analytics(?:\.js)?$/},()=>({path:'analytics',namespace:'test-service'}));
      build.onLoad({filter:/.*/,namespace:'test-service'},()=>({contents:'export function trackEvent() {}'}));
    }}],
  });
  const module = {exports:{}};
  new Function('require','module','exports','window',result.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports,{self:null,top:null});
  return renderToStaticMarkup(React.createElement(module.exports.default, props));
}
