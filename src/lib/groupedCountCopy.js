export function refreshGroupedCountEvidence(group = {}) {
  const affectedPages = Array.isArray(group?.affected_pages)
    ? group.affected_pages.filter(Boolean)
    : [];
  const declared = Number(group?.page_count);
  const pageCount = Math.max(
    affectedPages.length,
    Number.isFinite(declared) ? Math.max(0, Math.trunc(declared)) : 0,
  );
  const noun = pageCount === 1 ? "page" : "pages";

  return {
    ...group,
    page_count: pageCount,
    current_value: `${pageCount} affected ${noun} in this group.`,
  };
}
