import { GetAccessTokenOptions, SaveAccessTokenOptions, RemoveAccessTokenOptions, GetLoginUrlOptions } from "./auth-utils.types.js";
/**
 * Retrieves an access token from URL parameters or local storage.
 *
 * Low-level utility for manually retrieving tokens. In most cases, the Base44 client handles
 * token management automatically. This function is useful for custom authentication flows or when you need direct access to stored tokens. Requires a browser environment and can't be used in the backend.
 *
 * @internal
 *
 * @param options - Configuration options for token retrieval.
 * @returns The access token string if found, null otherwise.
 *
 * @example
 * ```typescript
 * // Get access token from URL or local storage
 * const token = getAccessToken();
 *
 * if (token) {
 *   console.log('User is authenticated');
 * } else {
 *   console.log('No token found, redirect to login');
 * }
 * ```
 * @example
 * ```typescript
 * // Get access token from custom local storage key
 * const token = getAccessToken({ storageKey: 'my_app_token' });
 * ```
 * @example
 * ```typescript
 * // Get access token from URL but don't save or remove it
 * const token = getAccessToken({
 *   saveToStorage: false,
 *   removeFromUrl: false
 * });
 * ```
 */
export declare function getAccessToken(options?: GetAccessTokenOptions): string | null;
/**
 * Saves an access token to local storage.
 *
 * Low-level utility for manually saving tokens. In most cases, the Base44 client handles token management automatically. This function is useful for custom authentication flows or managing custom tokens. Requires a browser environment and can't be used in the backend.
 *
 * @internal
 *
 * @param token - The access token string to save.
 * @param options - Configuration options for saving the token.
 * @returns Returns`true` if the token was saved successfully, `false` otherwise.
 *
 * @example
 * ```typescript
 * // Save access token after login
 * const response = await base44.auth.loginViaEmailPassword(email, password);
 * const success = saveAccessToken(response.access_token, {});
 *
 * if (success) {
 *   console.log('User is now authenticated');
 *   // Token is now available for future page loads
 * }
 * ```
 * @example
 * ```typescript
 * // Save access token to local storage using custom key
 * const success = saveAccessToken(token, {
 *   storageKey: `my_custom_token_key`
 * });
 * ```
 */
export declare function saveAccessToken(token: string, options: SaveAccessTokenOptions): boolean;
/**
 * Removes the access token from local storage.
 *
 * Low-level utility for manually removing tokens from the browser's local storage. In most cases, the Base44 client handles token management automatically. For standard logout flows, use {@linkcode AuthModule.logout | base44.auth.logout()} instead, which handles token removal and redirects automatically. This function is useful for custom authentication flows or when you need to manually remove tokens. Requires a browser environment and can't be used in the backend.
 *
 * @internal
 *
 * @param options - Configuration options for token removal.
 * @returns Returns `true` if the token was removed successfully, `false` otherwise.
 *
 * @example
 * ```typescript
 * // Remove custom token key
 * const success = removeAccessToken({
 *   storageKey: 'my_custom_token_key'
 * });
 * ```
 *
 * @example
 * ```typescript
 * // Standard logout flow with token removal and redirect
 * base44.auth.logout('/login');
 * ```
 */
export declare function removeAccessToken(options: RemoveAccessTokenOptions): boolean;
/**
 * Constructs the absolute URL for the login page with a redirect parameter.
 *
 * Low-level utility for building login URLs. For standard login redirects, use {@linkcode AuthModule.redirectToLogin | base44.auth.redirectToLogin()} instead, which handles this automatically. This function is useful when you need to construct login URLs without a client instance or for custom authentication flows.
 *
 * @internal
 *
 * @param nextUrl - The URL to redirect to after successful login.
 * @param options - Configuration options.
 * @returns The complete login URL with encoded redirect parameters.
 *
 * @example
 * ```typescript
 * // Redirect to login page
 * const loginUrl = getLoginUrl('/dashboard', {
 *   serverUrl: 'https://base44.app',
 *   appId: 'my-app-123'
 * });
 * window.location.href = loginUrl;
 * // User will be redirected back to /dashboard after login
 * ```
 */
export declare function getLoginUrl(nextUrl: string, options: GetLoginUrlOptions): string;
