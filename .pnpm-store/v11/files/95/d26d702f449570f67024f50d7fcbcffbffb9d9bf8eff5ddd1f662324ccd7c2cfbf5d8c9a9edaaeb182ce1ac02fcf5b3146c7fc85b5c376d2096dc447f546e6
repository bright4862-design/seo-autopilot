import { AxiosInstance } from "axios";
import { ConnectorsModule, UserConnectorsModule } from "./connectors.types.js";
/**
 * Creates the Connectors module for the Base44 SDK.
 *
 * @param axios - Axios instance (should be service role client)
 * @param appId - Application ID
 * @returns Connectors module with methods to retrieve OAuth tokens
 * @internal
 */
export declare function createConnectorsModule(axios: AxiosInstance, appId: string): ConnectorsModule;
/**
 * Creates the user-scoped Connectors module (app-user OAuth flows).
 *
 * @param axios - Axios instance (user-scoped client)
 * @param appId - Application ID
 * @returns User connectors module with app-user OAuth methods
 * @internal
 */
export declare function createUserConnectorsModule(axios: AxiosInstance, appId: string): UserConnectorsModule;
