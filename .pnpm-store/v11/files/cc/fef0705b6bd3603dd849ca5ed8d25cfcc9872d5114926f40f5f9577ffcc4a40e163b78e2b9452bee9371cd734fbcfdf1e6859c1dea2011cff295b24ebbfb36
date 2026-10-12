import axios from "axios";
import { isInIFrame } from "./common.js";
import { v4 as uuidv4 } from "uuid";
import { getAnalyticsSessionId } from "../modules/analytics.js";
/**
 * Custom error class for Base44 SDK errors.
 *
 * This error is thrown when API requests fail. It extends the standard `Error` class and includes additional information about the HTTP status, error code, and response data from the server.
 *
 * @example
 * ```typescript
 * try {
 *   await client.entities.Todo.get('invalid-id');
 * } catch (error) {
 *   if (error instanceof Base44Error) {
 *     console.error('Status:', error.status);      // 404
 *     console.error('Message:', error.message);    // "Not found"
 *     console.error('Code:', error.code);          // "NOT_FOUND"
 *     console.error('Data:', error.data);          // Full response data
 *   }
 * }
 * ```
 *
 */
export class Base44Error extends Error {
    /**
     * Creates a new Base44Error instance.
     *
     * @param message - Human-readable error message
     * @param status - HTTP status code
     * @param code - Error code from the API
     * @param data - Full response data from the server
     * @param originalError - Original axios error object
     * @internal
     */
    constructor(message, status, code, data, originalError) {
        super(message);
        this.name = "Base44Error";
        this.status = status;
        this.code = code;
        this.data = data;
        this.originalError = originalError;
    }
    /**
     * Serializes the error to a JSON-safe object.
     *
     * Useful for logging or sending error information to external services
     * without circular reference issues.
     *
     * @returns JSON-safe representation of the error.
     *
     * @example
     * ```typescript
     * try {
     *   await client.entities.Todo.get('invalid-id');
     * } catch (error) {
     *   if (error instanceof Base44Error) {
     *     const json = error.toJSON();
     *     console.log(json);
     *     // {
     *     //   name: "Base44Error",
     *     //   message: "Not found",
     *     //   status: 404,
     *     //   code: "NOT_FOUND",
     *     //   data: { ... }
     *     // }
     *   }
     * }
     * ```
     */
    toJSON() {
        return {
            name: this.name,
            message: this.message,
            status: this.status,
            code: this.code,
            data: this.data,
        };
    }
}
/**
 * Safely logs error information without circular references.
 *
 * @param prefix - Prefix for the log message
 * @param error - The error to log
 * @internal
 */
function safeErrorLog(prefix, error) {
    if (error instanceof Base44Error) {
        console.error(`${prefix} ${error.status}: ${error.message}`);
        if (error.data) {
            try {
                console.error("Error data:", JSON.stringify(error.data, null, 2));
            }
            catch (e) {
                console.error("Error data: [Cannot stringify error data]");
            }
        }
    }
    else {
        console.error(`${prefix} ${error instanceof Error ? error.message : String(error)}`);
    }
}
/**
 * Creates an axios client with default configuration and interceptors.
 *
 * Sets up an axios instance with:
 * - Default headers
 * - Authentication token injection
 * - Response data unwrapping
 * - Error transformation to Base44Error
 * - iframe messaging support
 *
 * @param options - Client configuration options
 * @returns Configured axios instance
 * @internal
 */
export function createAxiosClient({ baseURL, headers = {}, token, interceptResponses = true, onError, }) {
    const client = axios.create({
        baseURL,
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            ...headers,
        },
    });
    // Add token to requests if available
    if (token) {
        client.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    }
    // Add origin URL in browser environment
    client.interceptors.request.use((config) => {
        // `window.location` is absent on React Native (where `window` still exists),
        // so guard on it before reading `.href`.
        if (typeof window !== "undefined") {
            if (window.location) {
                config.headers.set("X-Origin-URL", window.location.href);
            }
            // On unauthenticated requests, attach a stable anonymous visitor id so the
            // backend can support anonymous agent access (conversation grouping + ownership).
            // Authenticated requests are identified by their Authorization header instead.
            if (!config.headers.get("Authorization")) {
                config.headers.set("X-Base44-Anonymous-Id", getAnalyticsSessionId());
            }
        }
        const requestId = uuidv4();
        config.requestId = requestId;
        if (isInIFrame) {
            try {
                window.parent.postMessage({
                    type: "api-request-start",
                    requestId,
                    data: {
                        url: baseURL + config.url,
                        method: config.method,
                        body: config.data instanceof FormData
                            ? "[FormData object]"
                            : config.data,
                    },
                }, "*");
            }
            catch (_a) {
                /* skip the logging */
            }
        }
        return config;
    });
    // Handle responses
    if (interceptResponses) {
        client.interceptors.response.use((response) => {
            var _a;
            const requestId = (_a = response.config) === null || _a === void 0 ? void 0 : _a.requestId;
            try {
                if (isInIFrame && requestId) {
                    window.parent.postMessage({
                        type: "api-request-end",
                        requestId,
                        data: {
                            statusCode: response.status,
                            response: response.data,
                        },
                    }, "*");
                }
            }
            catch (_b) {
                /* do nothing */
            }
            return response.data;
        }, (error) => {
            var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m;
            const data = (_a = error.response) === null || _a === void 0 ? void 0 : _a.data;
            const message = ((_b = data === null || data === void 0 ? void 0 : data.error) === null || _b === void 0 ? void 0 : _b.message) || (data === null || data === void 0 ? void 0 : data.message) || (data === null || data === void 0 ? void 0 : data.detail) || error.message;
            const base44Error = new Base44Error(message, (_c = error.response) === null || _c === void 0 ? void 0 : _c.status, (_k = (_f = (_e = (_d = data === null || data === void 0 ? void 0 : data.error) === null || _d === void 0 ? void 0 : _d.code) !== null && _e !== void 0 ? _e : data === null || data === void 0 ? void 0 : data.code) !== null && _f !== void 0 ? _f : (_j = (_h = (_g = error.response) === null || _g === void 0 ? void 0 : _g.headers) === null || _h === void 0 ? void 0 : _h.get) === null || _j === void 0 ? void 0 : _j.call(_h, "x-base44-connector-error")) !== null && _k !== void 0 ? _k : (_m = (_l = error.response) === null || _l === void 0 ? void 0 : _l.headers) === null || _m === void 0 ? void 0 : _m["x-base44-connector-error"], data, error);
            // Log errors in development
            if (process.env.NODE_ENV !== "production") {
                safeErrorLog("[Base44 SDK Error]", base44Error);
            }
            onError === null || onError === void 0 ? void 0 : onError(base44Error);
            return Promise.reject(base44Error);
        });
    }
    return client;
}
