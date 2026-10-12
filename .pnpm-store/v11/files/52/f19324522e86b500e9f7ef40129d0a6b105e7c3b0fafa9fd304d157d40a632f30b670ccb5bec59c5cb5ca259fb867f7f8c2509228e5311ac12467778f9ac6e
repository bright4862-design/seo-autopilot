import { getAccessToken } from "../utils/auth-utils.js";
export function createAgentsModule({ axios, getSocket, appId, serverUrl, token, }) {
    const baseURL = `/apps/${appId}/agents`;
    // Track active conversations
    const currentConversations = {};
    const getConversations = () => {
        return axios.get(`${baseURL}/conversations`);
    };
    const getConversation = (conversationId) => {
        return axios.get(`${baseURL}/conversations/${conversationId}`);
    };
    const listConversations = (filterParams) => {
        return axios.get(`${baseURL}/conversations`, {
            params: filterParams,
        });
    };
    const createConversation = (conversation) => {
        return axios.post(`${baseURL}/conversations`, conversation);
    };
    const addMessage = async (conversation, message) => {
        return axios.post(`${baseURL}/conversations/v2/${conversation.id}/messages`, message);
    };
    const subscribeToConversation = (conversationId, onUpdate) => {
        const room = `/agent-conversations/${conversationId}`;
        const socket = getSocket();
        // Store the promise for initial conversation state
        const conversationPromise = getConversation(conversationId).then((conv) => {
            currentConversations[conversationId] = conv;
            return conv;
        });
        return socket.subscribeToRoom(room, {
            connect: () => { },
            update_model: async ({ data: jsonStr }) => {
                const data = JSON.parse(jsonStr);
                if (data._message) {
                    // Wait for initial conversation to be loaded
                    await conversationPromise;
                    const message = data._message;
                    // Update shared conversation state
                    const currentConversation = currentConversations[conversationId];
                    if (currentConversation) {
                        const messages = currentConversation.messages || [];
                        const existingIndex = messages.findIndex((m) => m.id === message.id);
                        const updatedMessages = existingIndex !== -1
                            ? messages.map((m, i) => (i === existingIndex ? message : m))
                            : [...messages, message];
                        currentConversations[conversationId] = {
                            ...currentConversation,
                            messages: updatedMessages,
                        };
                        onUpdate === null || onUpdate === void 0 ? void 0 : onUpdate(currentConversations[conversationId]);
                    }
                }
            },
        });
    };
    const getWhatsAppConnectURL = (agentName) => {
        const baseUrl = `${serverUrl}/api/apps/${appId}/agents/${encodeURIComponent(agentName)}/whatsapp`;
        const accessToken = token !== null && token !== void 0 ? token : getAccessToken();
        if (accessToken) {
            return `${baseUrl}?token=${accessToken}`;
        }
        else {
            // No token - URL will redirect to login automatically
            return baseUrl;
        }
    };
    const getTelegramConnectURL = (agentName) => {
        const baseUrl = `${serverUrl}/api/apps/${appId}/agents/${encodeURIComponent(agentName)}/telegram`;
        const accessToken = token !== null && token !== void 0 ? token : getAccessToken();
        if (accessToken) {
            return `${baseUrl}?token=${accessToken}`;
        }
        else {
            // No token - URL will redirect to login automatically
            return baseUrl;
        }
    };
    return {
        getConversations,
        getConversation,
        listConversations,
        createConversation,
        addMessage,
        subscribeToConversation,
        getWhatsAppConnectURL,
        getTelegramConnectURL,
    };
}
