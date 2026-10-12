import { AsyncLocalStorage } from "node:async_hooks";
import { format } from "node:util";
export const REQUEST_ID_HEADER = "x-b44-request-id";
const CONSOLE_PATCHED = Symbol.for("base44.routeRequestLog.consolePatched");
const TAGGED_CONSOLE_METHODS = ["log", "info", "warn", "error", "debug"];
const currentRequestId = new AsyncLocalStorage();
export const requestLogPrefix = (requestId, level) => `[b44-req ${requestId} ${level}] `;
const prefixEveryLine = (text, prefix) => text
    .split("\n")
    .map((line) => prefix + line)
    .join("\n");
function prefixWhileInsideRequest(level, originalMethod) {
    return (...args) => {
        const requestId = currentRequestId.getStore();
        if (requestId === undefined)
            return originalMethod(...args);
        return originalMethod(prefixEveryLine(format(...args), requestLogPrefix(requestId, level)));
    };
}
function tagConsoleWithRequestId(target) {
    if (target[CONSOLE_PATCHED])
        return;
    for (const method of TAGGED_CONSOLE_METHODS) {
        target[method] = prefixWhileInsideRequest(method, target[method].bind(target));
    }
    target[CONSOLE_PATCHED] = true;
}
const routeLabel = (req) => `${req.method} ${new URL(req.url).pathname}`;
const describeError = (error) => error instanceof Error ? `${error.name}: ${error.message}` : String(error);
async function runRouteAndSummarize(event, next, target) {
    const startedAt = Date.now();
    const elapsed = () => `${Date.now() - startedAt}ms`;
    try {
        const result = await next();
        target.info(`${routeLabel(event.req)} handled in ${elapsed()}`);
        return result;
    }
    catch (error) {
        target.error(`${routeLabel(event.req)} threw ${describeError(error)} after ${elapsed()}`);
        throw error;
    }
}
export function tagRouteRequests(target) {
    tagConsoleWithRequestId(target);
    return (event, next) => {
        const requestId = event.req.headers.get(REQUEST_ID_HEADER);
        if (requestId === null)
            return next();
        return currentRequestId.run(requestId, () => runRouteAndSummarize(event, next, target));
    };
}
//# sourceMappingURL=route-request-tagger.js.map