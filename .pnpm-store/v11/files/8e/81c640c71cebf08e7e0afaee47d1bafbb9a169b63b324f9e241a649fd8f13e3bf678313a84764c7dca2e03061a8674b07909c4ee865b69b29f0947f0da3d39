import { AxiosInstance } from "axios";
import { EntitiesModule } from "./entities.types";
import { RoomsSocket } from "../utils/socket-utils.js";
/**
 * Configuration for the entities module.
 * @internal
 */
export interface EntitiesModuleConfig {
    axios: AxiosInstance;
    appId: string;
    getSocket: () => ReturnType<typeof RoomsSocket>;
}
/**
 * Creates the entities module for the Base44 SDK.
 *
 * @param config - Configuration object containing axios, appId, and getSocket
 * @returns Entities module with dynamic entity access
 * @internal
 */
export declare function createEntitiesModule(config: EntitiesModuleConfig): EntitiesModule;
