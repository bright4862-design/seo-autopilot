import type { Base44Client, CreateClientAnalyticsConfig, CreateClientConfig, CreateClientOptions } from "./client.types.js";
export type { Base44Client, CreateClientAnalyticsConfig, CreateClientConfig, CreateClientOptions, };
/**
 * Creates a Base44 client.
 *
 * This is the main entry point for the Base44 SDK. It creates a client that provides access to the SDK's modules, such as {@linkcode EntitiesModule | entities}, {@linkcode AuthModule | auth}, and {@linkcode FunctionsModule | functions}.
 *
 * How you get a client depends on your context:
 * - **Inside a Base44 app:** The client is automatically created and configured for you. Import it from `@/api/base44Client`.
 * - **External app using Base44 as a backend:** Call `createClient()` directly in your code to create and configure the client.
 *
 * The client supports three authentication modes:
 * - **Anonymous**: Access modules without authentication using `base44.moduleName`. Operations are scoped to public data and permissions.
 * - **User authentication**: Access modules with user-level permissions using `base44.moduleName`. Operations are scoped to the authenticated user's data and permissions. Use `base44.auth.loginViaEmailPassword()` or other auth methods to get a token.
 * - **Service role authentication**: Access modules with elevated permissions using `base44.asServiceRole.moduleName`. Operations bypass entity access rules and field-level security, giving full read and write access to all of the app's data. Only available in Base44-hosted backend functions. Create a client with service role authentication using {@linkcode createClientFromRequest | createClientFromRequest()}.
 *
 * For example, when using the {@linkcode EntitiesModule | entities} module:
 * - **Anonymous**: Can only read public data.
 * - **User authentication**: Can access the current user's data.
 * - **Service role authentication**: Can read and write any record, bypassing access rules.
 *
 * Most modules are available in all three modes, but with different permission levels. However, some modules are only available in specific authentication modes.
 *
 * @param config - Configuration object for the client.
 * @returns A configured Base44 client instance with access to all SDK modules.
 *
 * @example
 * ```typescript
 * // Create a client for your app
 * import { createClient } from '@base44/sdk';
 *
 * const base44 = createClient({
 *   appId: 'my-app-id'
 * });
 *
 * // Use the client to access your data
 * const products = await base44.entities.Products.list();
 * ```
 */
export declare function createClient(config: CreateClientConfig): Base44Client;
/**
 * Creates a Base44 client from an HTTP request.
 *
 * This function is designed for use in Base44-hosted backend functions. For frontends and external backends, use {@linkcode createClient | createClient()} instead.
 *
 * When used in a Base44-hosted backend function, `createClientFromRequest()` automatically extracts authentication tokens from the request headers that Base44 injects when forwarding requests. The returned client includes service role access using `base44.asServiceRole`, which bypasses entity access rules and field-level security.
 *
 * To learn more about the Base44 client, see {@linkcode createClient | createClient()}.
 *
 * @param request - The incoming HTTP request object containing Base44 authentication headers.
 * @returns A configured Base44 client instance with authentication from the incoming request.
 *
 * @example
 * ```typescript
 * // User authentication in backend function
 * import { createClientFromRequest } from 'npm:@base44/sdk';
 *
 * Deno.serve(async (req) => {
 *   try {
 *     const base44 = createClientFromRequest(req);
 *     const user = await base44.auth.me();
 *
 *     if (!user) {
 *       return Response.json({ error: 'Unauthorized' }, { status: 401 });
 *     }
 *
 *     // Access user's data
 *     const userOrders = await base44.entities.Orders.filter({ userId: user.id });
 *     return Response.json({ orders: userOrders });
 *   } catch (error) {
 *     return Response.json({ error: error.message }, { status: 500 });
 *   }
 * });
 * ```
 *
 * @example
 * ```typescript
 * // Service role authentication in backend function
 * import { createClientFromRequest } from 'npm:@base44/sdk';
 *
 * Deno.serve(async (req) => {
 *   try {
 *     const base44 = createClientFromRequest(req);
 *
 *     // Read across all users, bypassing the Orders entity's access rules
 *     const recentOrders = await base44.asServiceRole.entities.Orders.list('-created_at', 50);
 *
 *     return Response.json({ orders: recentOrders });
 *   } catch (error) {
 *     return Response.json({ error: error.message }, { status: 500 });
 *   }
 * });
 * ```
 *
 */
export declare function createClientFromRequest(request: Request): Base44Client;
