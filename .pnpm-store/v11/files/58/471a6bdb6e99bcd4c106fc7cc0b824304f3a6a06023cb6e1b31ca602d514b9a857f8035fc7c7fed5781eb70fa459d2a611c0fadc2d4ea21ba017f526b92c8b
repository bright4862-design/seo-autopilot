import { AsyncLocalStorage } from "node:async_hooks";
import { format } from "node:util";

export const REQUEST_ID_HEADER = "x-b44-request-id";

const CONSOLE_PATCHED = Symbol.for("base44.routeRequestLog.consolePatched");
const TAGGED_CONSOLE_METHODS = ["log", "info", "warn", "error", "debug"] as const;

type TaggedConsoleMethod = (typeof TAGGED_CONSOLE_METHODS)[number];
type TaggableConsole = Pick<Console, TaggedConsoleMethod> & { [CONSOLE_PATCHED]?: boolean };
type RouteEvent = { req: Request };
type CallNextHandler = () => unknown;

const currentRequestId = new AsyncLocalStorage<string>();

export const requestLogPrefix = (requestId: string, level: TaggedConsoleMethod) =>
  `[b44-req ${requestId} ${level}] `;

const prefixEveryLine = (text: string, prefix: string) =>
  text
    .split("\n")
    .map((line) => prefix + line)
    .join("\n");

function prefixWhileInsideRequest(
  level: TaggedConsoleMethod,
  originalMethod: (...args: unknown[]) => void
) {
  return (...args: unknown[]) => {
    const requestId = currentRequestId.getStore();
    if (requestId === undefined) return originalMethod(...args);
    return originalMethod(prefixEveryLine(format(...args), requestLogPrefix(requestId, level)));
  };
}

function tagConsoleWithRequestId(target: TaggableConsole) {
  if (target[CONSOLE_PATCHED]) return;
  for (const method of TAGGED_CONSOLE_METHODS) {
    target[method] = prefixWhileInsideRequest(method, target[method].bind(target));
  }
  target[CONSOLE_PATCHED] = true;
}

const routeLabel = (req: Request) => `${req.method} ${new URL(req.url).pathname}`;

const describeError = (error: unknown) =>
  error instanceof Error ? `${error.name}: ${error.message}` : String(error);

async function runRouteAndSummarize(event: RouteEvent, next: CallNextHandler, target: TaggableConsole) {
  const startedAt = Date.now();
  const elapsed = () => `${Date.now() - startedAt}ms`;
  try {
    const result = await next();
    target.info(`${routeLabel(event.req)} handled in ${elapsed()}`);
    return result;
  } catch (error) {
    target.error(`${routeLabel(event.req)} threw ${describeError(error)} after ${elapsed()}`);
    throw error;
  }
}

export function tagRouteRequests(target: TaggableConsole) {
  tagConsoleWithRequestId(target);
  return (event: RouteEvent, next: CallNextHandler) => {
    const requestId = event.req.headers.get(REQUEST_ID_HEADER);
    if (requestId === null) return next();
    return currentRequestId.run(requestId, () => runRouteAndSummarize(event, next, target));
  };
}
