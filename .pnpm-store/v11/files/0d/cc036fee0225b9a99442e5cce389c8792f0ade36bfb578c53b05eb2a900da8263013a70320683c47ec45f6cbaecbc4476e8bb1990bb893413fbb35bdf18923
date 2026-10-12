import { io } from "socket.io-client";
import { getAccessToken } from "./auth-utils.js";
import { getAnalyticsSessionId } from "../modules/analytics.js";
const ROOM_LEAVE_GRACE_MS = 250;
function initializeSocket(config, handlers) {
    var _a;
    // On unauthenticated clients, send a stable anonymous visitor id on the
    // handshake so the backend can verify room access for anonymous agent
    // conversations (mirrors the X-Base44-Anonymous-Id HTTP header). Authenticated
    // clients are identified by their token instead.
    const resolvedToken = (_a = config.token) !== null && _a !== void 0 ? _a : getAccessToken();
    const query = {
        app_id: config.appId,
    };
    if (resolvedToken) {
        query.token = resolvedToken;
    }
    else {
        query.anonymous_id = getAnalyticsSessionId();
    }
    const socket = io(config.serverUrl, {
        path: config.mountPath,
        transports: config.transports,
        query,
    });
    socket.on("connect", async () => {
        var _a;
        console.log("connect", socket.id);
        return (_a = handlers.connect) === null || _a === void 0 ? void 0 : _a.call(handlers);
    });
    socket.on("update_model", async (msg) => {
        var _a;
        return (_a = handlers.update_model) === null || _a === void 0 ? void 0 : _a.call(handlers, msg);
    });
    socket.on("error", async (error) => {
        var _a;
        return (_a = handlers.error) === null || _a === void 0 ? void 0 : _a.call(handlers, error);
    });
    socket.on("connect_error", async (error) => {
        var _a;
        console.error("connect_error", error);
        return (_a = handlers.error) === null || _a === void 0 ? void 0 : _a.call(handlers, error);
    });
    return socket;
}
export function RoomsSocket({ config }) {
    let currentConfig = { ...config };
    const roomsToListeners = {};
    const pendingRoomLeaves = {};
    const handlers = {
        connect: async () => {
            const promises = [];
            Object.keys(roomsToListeners).forEach((room) => {
                const listeners = getListeners(room);
                if (listeners.length === 0) {
                    return;
                }
                joinRoom(room);
                listeners.forEach(({ connect }) => {
                    const promise = async () => connect === null || connect === void 0 ? void 0 : connect();
                    promises.push(promise());
                });
            });
            await Promise.all(promises);
        },
        update_model: async (msg) => {
            const listeners = getListeners(msg.room);
            const promises = listeners.map((listener) => { var _a; return (_a = listener.update_model) === null || _a === void 0 ? void 0 : _a.call(listener, msg); });
            await Promise.all(promises);
        },
        error: async (error) => {
            console.error("error", error);
            const promises = Object.values(roomsToListeners)
                .flat()
                .map((listener) => { var _a; return (_a = listener.error) === null || _a === void 0 ? void 0 : _a.call(listener, error); });
            await Promise.all(promises);
        },
    };
    let socket = initializeSocket(config, handlers);
    function cleanup() {
        disconnect();
    }
    function disconnect() {
        clearPendingRoomLeaves();
        if (socket) {
            socket.disconnect();
        }
    }
    function updateConfig(config) {
        cleanup();
        currentConfig = {
            ...currentConfig,
            ...config,
        };
        socket = initializeSocket(currentConfig, handlers);
    }
    function joinRoom(room) {
        socket.emit("join", room);
    }
    function leaveRoom(room) {
        socket.emit("leave", room);
    }
    async function updateModel(room, data) {
        var _a;
        const dataStr = JSON.stringify(data);
        return (_a = handlers.update_model) === null || _a === void 0 ? void 0 : _a.call(handlers, { room, data: dataStr });
    }
    function getListeners(room) {
        var _a;
        return (_a = roomsToListeners[room]) !== null && _a !== void 0 ? _a : [];
    }
    function cancelPendingRoomLeave(room) {
        const pendingLeave = pendingRoomLeaves[room];
        if (!pendingLeave) {
            return;
        }
        clearTimeout(pendingLeave);
        delete pendingRoomLeaves[room];
    }
    function clearPendingRoomLeaves() {
        Object.keys(pendingRoomLeaves).forEach((room) => {
            var _a, _b;
            clearTimeout(pendingRoomLeaves[room]);
            delete pendingRoomLeaves[room];
            if (((_b = (_a = roomsToListeners[room]) === null || _a === void 0 ? void 0 : _a.length) !== null && _b !== void 0 ? _b : 0) === 0) {
                delete roomsToListeners[room];
            }
        });
    }
    function scheduleRoomLeave(room) {
        cancelPendingRoomLeave(room);
        pendingRoomLeaves[room] = setTimeout(() => {
            var _a, _b;
            delete pendingRoomLeaves[room];
            if (((_b = (_a = roomsToListeners[room]) === null || _a === void 0 ? void 0 : _a.length) !== null && _b !== void 0 ? _b : 0) > 0) {
                return;
            }
            leaveRoom(room);
            delete roomsToListeners[room];
        }, ROOM_LEAVE_GRACE_MS);
    }
    const subscribeToRoom = (room, handlers) => {
        if (roomsToListeners[room]) {
            cancelPendingRoomLeave(room);
        }
        else {
            joinRoom(room);
            roomsToListeners[room] = [];
        }
        roomsToListeners[room].push(handlers);
        let unsubscribed = false;
        return () => {
            var _a, _b;
            if (unsubscribed) {
                return;
            }
            unsubscribed = true;
            roomsToListeners[room] =
                (_b = (_a = roomsToListeners[room]) === null || _a === void 0 ? void 0 : _a.filter((listener) => listener !== handlers)) !== null && _b !== void 0 ? _b : [];
            if (roomsToListeners[room].length === 0) {
                scheduleRoomLeave(room);
            }
        };
    };
    return {
        socket,
        subscribeToRoom,
        updateConfig,
        updateModel,
        disconnect,
    };
}
