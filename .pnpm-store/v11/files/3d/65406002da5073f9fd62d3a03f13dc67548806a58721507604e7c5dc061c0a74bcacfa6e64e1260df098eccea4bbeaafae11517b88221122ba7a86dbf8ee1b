/**
 * Creates the custom integrations module for the Base44 SDK.
 *
 * @param axios - Axios instance for making HTTP requests
 * @param appId - Application ID
 * @returns Custom integrations module with `call()` method
 * @internal
 */
export function createCustomIntegrationsModule(axios, appId) {
    return {
        async call(slug, operationId, params) {
            // Validate required parameters
            if (!(slug === null || slug === void 0 ? void 0 : slug.trim())) {
                throw new Error("Integration slug is required and cannot be empty");
            }
            if (!(operationId === null || operationId === void 0 ? void 0 : operationId.trim())) {
                throw new Error("Operation ID is required and cannot be empty");
            }
            // Convert camelCase to snake_case for Python backend
            const { pathParams, queryParams, ...rest } = params !== null && params !== void 0 ? params : {};
            const body = {
                ...rest,
                ...(pathParams && { path_params: pathParams }),
                ...(queryParams && { query_params: queryParams }),
            };
            // Make the API call
            const response = await axios.post(`/apps/${appId}/integrations/custom/${slug}/${operationId}`, body);
            // The axios interceptor extracts response.data, so we get the payload directly
            return response;
        },
    };
}
