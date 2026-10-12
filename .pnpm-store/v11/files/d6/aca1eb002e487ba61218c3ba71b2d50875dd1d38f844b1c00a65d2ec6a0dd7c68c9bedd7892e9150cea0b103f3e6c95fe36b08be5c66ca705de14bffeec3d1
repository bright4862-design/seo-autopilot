export declare const REQUEST_ID_HEADER = "x-b44-request-id";
declare const CONSOLE_PATCHED: unique symbol;
declare const TAGGED_CONSOLE_METHODS: readonly ["log", "info", "warn", "error", "debug"];
type TaggedConsoleMethod = (typeof TAGGED_CONSOLE_METHODS)[number];
type TaggableConsole = Pick<Console, TaggedConsoleMethod> & {
    [CONSOLE_PATCHED]?: boolean;
};
type RouteEvent = {
    req: Request;
};
type CallNextHandler = () => unknown;
export declare const requestLogPrefix: (requestId: string, level: TaggedConsoleMethod) => string;
export declare function tagRouteRequests(target: TaggableConsole): (event: RouteEvent, next: CallNextHandler) => unknown;
export {};
//# sourceMappingURL=route-request-tagger.d.ts.map