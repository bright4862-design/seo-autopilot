const CONNECTOR_API_METHODS = new Set([
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
]);
/**
 * Creates the Connectors module for the Base44 SDK.
 *
 * @param axios - Axios instance (should be service role client)
 * @param appId - Application ID
 * @returns Connectors module with methods to retrieve OAuth tokens
 * @internal
 */
export function createConnectorsModule(axios, appId) {
    return {
        /**
         * Retrieve an OAuth access token for a specific external integration type.
         * @deprecated Use getConnection(integrationType) and use the returned accessToken (and connectionConfig when needed) instead.
         */
        // @ts-expect-error Return type mismatch with interface - implementation returns string, interface expects string but implementation is typed as ConnectorAccessTokenResponse
        async getAccessToken(integrationType) {
            if (!integrationType || typeof integrationType !== "string") {
                throw new Error("Integration type is required and must be a string");
            }
            const response = await axios.get(`/apps/${appId}/external-auth/tokens/${encodeURIComponent(integrationType)}`);
            // @ts-expect-error
            return response.access_token;
        },
        async getConnection(integrationType) {
            var _a;
            if (!integrationType || typeof integrationType !== "string") {
                throw new Error("Integration type is required and must be a string");
            }
            const response = await axios.get(`/apps/${appId}/external-auth/tokens/${encodeURIComponent(integrationType)}`);
            const data = response;
            return {
                accessToken: data.access_token,
                connectionConfig: (_a = data.connection_config) !== null && _a !== void 0 ? _a : null,
            };
        },
        async getWorkspaceConnection(connectorId) {
            var _a;
            if (!connectorId || typeof connectorId !== "string") {
                throw new Error("Connector ID is required and must be a string");
            }
            const response = await axios.get(`/apps/${appId}/external-auth/tokens/connectors/${encodeURIComponent(connectorId)}`);
            const data = response;
            return {
                accessToken: data.access_token,
                connectionConfig: (_a = data.connection_config) !== null && _a !== void 0 ? _a : null,
            };
        },
        /**
         * @deprecated Use getCurrentAppUserConnection(connectorId) and use the returned accessToken (and connectionConfig when needed) instead.
         */
        async getCurrentAppUserAccessToken(connectorId) {
            if (!connectorId || typeof connectorId !== "string") {
                throw new Error("Connector ID is required and must be a string");
            }
            const response = await axios.get(`/apps/${appId}/app-user-auth/connectors/${encodeURIComponent(connectorId)}/token`);
            const data = response;
            return data.access_token;
        },
        async getCurrentAppUserConnection(connectorId) {
            var _a;
            if (!connectorId || typeof connectorId !== "string") {
                throw new Error("Connector ID is required and must be a string");
            }
            const response = await axios.get(`/apps/${appId}/app-user-auth/connectors/${encodeURIComponent(connectorId)}/token`);
            const data = response;
            return {
                accessToken: data.access_token,
                connectionConfig: (_a = data.connection_config) !== null && _a !== void 0 ? _a : null,
            };
        },
        async callApi(integrationType, request) {
            assertNonEmptyString(integrationType, "Integration type");
            // Encoded so a runtime-built identifier can only ever select a
            // connector, never re-target another route under this token.
            return proxyCall(axios, `/apps/${appId}/connectors/${encodeURIComponent(integrationType)}/call`, request);
        },
    };
}
function assertNonEmptyString(value, label) {
    if (!value || typeof value !== "string") {
        throw new Error(`${label} is required and must be a string`);
    }
}
/**
 * POST a request to the connector proxy and normalize the response.
 *
 * The proxy reports upstream outcomes in the body rather than as HTTP status, so
 * a provider 4xx/5xx arrives here as a resolved response with `success: false` —
 * only Base44-side failures reject through the axios error interceptor.
 *
 * @internal
 */
async function proxyCall(axios, url, request) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _j;
    if (!request || typeof request !== "object") {
        throw new Error("Request is required and must be an object");
    }
    assertNonEmptyString(request.path, "Request path");
    const method = (_a = request.method) !== null && _a !== void 0 ? _a : "GET";
    if (!CONNECTOR_API_METHODS.has(method)) {
        throw new Error("Request method must be one of GET, POST, PUT, PATCH, DELETE, or HEAD");
    }
    const response = await axios.post(url, {
        method,
        // Omitted when unset (undefined or null, since untyped callers write
        // either) so the proxy applies the connector's declared default host.
        ...(request.host == null ? {} : { host: request.host }),
        path: request.path,
        query: (_b = request.query) !== null && _b !== void 0 ? _b : {},
        headers: (_c = request.headers) !== null && _c !== void 0 ? _c : {},
        body: (_d = request.body) !== null && _d !== void 0 ? _d : null,
    });
    const data = response;
    return {
        success: data.success,
        phase: data.phase,
        status: (_e = data.status_code) !== null && _e !== void 0 ? _e : null,
        data: data.data,
        dataBase64: (_f = data.data_base64) !== null && _f !== void 0 ? _f : null,
        contentType: (_g = data.content_type) !== null && _g !== void 0 ? _g : null,
        headers: (_h = data.headers) !== null && _h !== void 0 ? _h : {},
        creditsCharged: (_j = data.credits_charged) !== null && _j !== void 0 ? _j : 0,
    };
}
/**
 * Creates the user-scoped Connectors module (app-user OAuth flows).
 *
 * @param axios - Axios instance (user-scoped client)
 * @param appId - Application ID
 * @returns User connectors module with app-user OAuth methods
 * @internal
 */
export function createUserConnectorsModule(axios, appId) {
    return {
        async connectAppUser(connectorId) {
            if (!connectorId || typeof connectorId !== "string") {
                throw new Error("Connector ID is required and must be a string");
            }
            const response = await axios.post(`/apps/${appId}/app-user-auth/connectors/${encodeURIComponent(connectorId)}/initiate`);
            const data = response;
            return data.redirect_url;
        },
        async disconnectAppUser(connectorId) {
            if (!connectorId || typeof connectorId !== "string") {
                throw new Error("Connector ID is required and must be a string");
            }
            await axios.delete(`/apps/${appId}/app-user-auth/connectors/${encodeURIComponent(connectorId)}`);
        },
    };
}
