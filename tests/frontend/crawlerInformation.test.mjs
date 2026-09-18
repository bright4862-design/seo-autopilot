import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import * as router from 'react-router-dom';

test('crawler information identifies policy limits', async () => {
  const result = await build({ entryPoints: ['src/pages/Crawler.jsx'], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react'] });
  const module = { exports: {} };
  vm.runInNewContext(result.outputFiles[0].text, { module, exports: module.exports, require: createRequire(import.meta.url) });
  const html = renderToStaticMarkup(React.createElement(module.exports.default));
  assert.match(html, /FixListBot\/1\.0/);
  assert.match(html, /robots\.txt/);
  assert.match(html, /150/);
  assert.match(html, /user.agent.*not.*authentication/i);
});

test('the actual app routes /crawler without rendering the authentication gate', async () => {
  const compile = async (entry, require) => {
    const result = await build({ entryPoints: [entry], bundle: true, write: false, platform: 'node', format: 'cjs', external: ['react', 'react-router-dom', '@/*'] });
    const module = { exports: {} };
    vm.runInNewContext(result.outputFiles[0].text, { module, exports: module.exports, require });
    return module.exports.default;
  };
  const require = createRequire(import.meta.url);
  const Crawler = await compile('src/pages/Crawler.jsx', require);
  const App = await compile('src/App.jsx', (name) => {
    if (name === 'react-router-dom') return {
      ...router,
      BrowserRouter: ({ children }) => React.createElement(router.MemoryRouter, { initialEntries: ['/crawler'] }, children),
    };
    if (name === '@/pages/Crawler') return Crawler;
    if (name === '@/components/ProtectedRoute') return () => { throw new Error('Crawler information must not require authentication'); };
    if (name.startsWith('@/')) return () => null;
    return require(name);
  });
  assert.match(renderToStaticMarkup(React.createElement(App)), /About the FixList crawler/);
});
