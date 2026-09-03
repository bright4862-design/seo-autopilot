const PROBE_ID = "fixlist-new-route-activation-probe-20260903-v1";
const SOURCE_SHA = "5a91dfee0a86a6c67a5ef56d56e46a1b240647e7";

export default async function (_req: Request): Promise<Response> {
  return Response.json({
    ok: true,
    probe_id: PROBE_ID,
    source_sha: SOURCE_SHA,
  });
}
