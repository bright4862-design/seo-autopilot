/**
 * Creates the SSO module for the Base44 SDK.
 *
 * @param axios - Axios instance
 * @param appId - Application ID
 * @returns SSO module with authentication methods
 * @internal
 */
export function createSsoModule(axios, appId) {
    return {
        // Get SSO access token for a specific user
        async getAccessToken(userid) {
            const url = `/apps/${appId}/auth/sso/accesstoken/${userid}`;
            return axios.get(url);
        },
        // Get the stored SSO OIDC ID token for a specific user
        async getIdToken(userid) {
            const url = `/apps/${appId}/auth/sso/idtoken/${userid}`;
            return axios.get(url);
        },
    };
}
