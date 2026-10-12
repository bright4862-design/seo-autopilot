import { getAccessToken } from "../utils/auth-utils.js";
const PROVIDER_PATHS = {
    openai: "openai",
    typesafe: "typesafe",
};
export function createAiGatewayModule({ serverUrl, token, appId, headers = {}, }) {
    const connection = ({ provider = "openai" } = {}) => {
        var _a;
        if (!Object.prototype.hasOwnProperty.call(PROVIDER_PATHS, provider)) {
            throw new Error(`Unsupported AI Gateway provider: ${provider}`);
        }
        const providerPath = PROVIDER_PATHS[provider];
        return {
            baseURL: `${serverUrl}/api/apps/${appId}/ai/${providerPath}/v1`,
            token: (_a = token !== null && token !== void 0 ? token : getAccessToken()) !== null && _a !== void 0 ? _a : "",
            headers: { ...headers },
        };
    };
    return {
        connection,
    };
}
