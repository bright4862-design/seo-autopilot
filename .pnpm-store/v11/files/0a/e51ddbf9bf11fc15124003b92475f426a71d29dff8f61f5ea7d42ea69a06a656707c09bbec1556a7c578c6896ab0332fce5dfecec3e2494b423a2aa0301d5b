import type { Base44ErrorJSON } from "./axios-client.types.js";
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
export declare class Base44Error extends Error {
    /**
     * HTTP status code of the error.
     */
    status: number;
    /**
     * Error code from the API.
     */
    code: string;
    /**
     * Full response data from the server containing error details.
     */
    data: any;
    /**
     * The original error object from Axios.
     */
    originalError: unknown;
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
    constructor(message: string, status: number, code: string, data: any, originalError: unknown);
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
    toJSON(): Base44ErrorJSON;
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
export declare function createAxiosClient({ baseURL, headers, token, interceptResponses, onError, }: {
    baseURL: string;
    headers?: Record<string, string>;
    token?: string;
    interceptResponses?: boolean;
    onError?: (error: Error) => void;
}): import("axios").AxiosInstance;
export type { Base44ErrorJSON } from "./axios-client.types.js";
