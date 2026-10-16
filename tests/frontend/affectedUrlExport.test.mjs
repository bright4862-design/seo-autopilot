import assert from "node:assert/strict";
import test from "node:test";
const output = await import("../../src/lib/affectedUrlExport.js").catch(error => {
  if (error.code === "ERR_MODULE_NOT_FOUND") return {};
  throw error;
});
const origin = "https://example.com";
const routes = ["/x", "/x/", "/X", "/a/../x", "/café", "/caf%C3%A9", "/a%2Fb", "/q?b=2&a=1&a=0", 'https://foreign.example/a,b'];
const item = { affectedPages: routes, websiteUrl: origin, title: 'Describe "these" pages', rule: 'missing_meta_description', priority: 'medium', templateFamily: 'product_page', original: { evidence_url_identity_version: 'evidence_url_identity_v2_published_route' } };

test("actual CSV serializer retains every published route and quotes fields", () => {
  assert.equal(typeof output.serializeAffectedUrlsCsv, 'function');
  const csv = output.serializeAffectedUrlsCsv(item);
  assert.equal(csv.split('\n')[0], '"affected_url","finding","rule","priority","template_family"');
  const expected = routes.map(route => `${route.startsWith('/') ? origin : ''}${route}`);
  assert.deepEqual(csv.split('\n').slice(1), expected.map(url => `"${url}","Describe ""these"" pages","missing_meta_description","medium","product_page"`));
});

test("copy serializer retains published route spellings and validates linkable evidence", () => {
  assert.equal(typeof output.serializeAffectedUrlsText, 'function');
  assert.equal(output.serializeAffectedUrlsText(item), routes.map(route => `${route.startsWith('/') ? origin : ''}${route}`).join('\n'));
  assert.equal(output.serializeAffectedUrlsText({...item, affectedPages: ['/x', 'javascript:alert(1)', '//foreign.example/x']}), origin + '/x');
  assert.equal(output.serializeAffectedUrlsText({...item, websiteUrl: '', affectedPages: ['/x']}), '');
});

test("historical copy and CSV retain the former component serialization", () => {
  assert.equal(typeof output.serializeAffectedUrlsText, 'function');
  assert.equal(output.serializeAffectedUrlsText({...item, original: {}, affectedPages: ['/a/../x', '/café', origin + '/a/../x']}), [origin + '/x', origin + '/caf%C3%A9', origin + '/a/../x'].join('\n'));
});
