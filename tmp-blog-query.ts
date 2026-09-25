const rows = await base44.entities.BlogPost.filter({ generation_key: 'daily:2026-09-25' });
console.log(JSON.stringify(rows.map(r => ({ id: r.id, status: r.status, slug: r.slug, title: r.title }))));
