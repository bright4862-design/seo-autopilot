/**
 * Creates the app logs module for the Base44 SDK.
 *
 * @param axios - Axios instance
 * @param appId - Application ID
 * @returns App logs module with methods for tracking and analyzing app usage
 * @internal
 */
export function createAppLogsModule(axios, appId) {
    const baseURL = `/app-logs/${appId}`;
    return {
        // Log user activity in the app
        async logUserInApp(pageName) {
            await axios.post(`${baseURL}/log-user-in-app/${pageName}`);
        },
        // Fetch app logs with optional parameters
        async fetchLogs(params = {}) {
            const response = await axios.get(baseURL, { params });
            return response;
        },
        // Get app statistics
        async getStats(params = {}) {
            const response = await axios.get(`${baseURL}/stats`, { params });
            return response;
        },
    };
}
