/**
 * Creates the entities module for the Base44 SDK.
 *
 * @param config - Configuration object containing axios, appId, and getSocket
 * @returns Entities module with dynamic entity access
 * @internal
 */
export function createEntitiesModule(config) {
    const { axios, appId, getSocket } = config;
    // Using Proxy to dynamically handle entity names
    return new Proxy({}, {
        get(target, entityName) {
            // Don't create handlers for internal properties
            if (typeof entityName !== "string" ||
                entityName === "then" ||
                entityName.startsWith("_")) {
                return undefined;
            }
            // Create entity handler
            return createEntityHandler(axios, appId, entityName, getSocket);
        },
    });
}
/**
 * Parses the realtime message data and extracts event information.
 * @internal
 */
function parseRealtimeMessage(dataStr) {
    var _a;
    try {
        const parsed = JSON.parse(dataStr);
        return {
            type: parsed.type,
            data: parsed.data,
            id: parsed.id || ((_a = parsed.data) === null || _a === void 0 ? void 0 : _a.id),
            timestamp: parsed.timestamp || new Date().toISOString(),
        };
    }
    catch (error) {
        console.warn("[Base44 SDK] Failed to parse realtime message:", error);
        return null;
    }
}
const DEFAULT_PAGE_LIMIT = 100;
function isPageOptions(value) {
    return typeof value === "object" && value !== null;
}
/**
 * Creates a handler for a specific entity.
 *
 * @param axios - Axios instance
 * @param appId - Application ID
 * @param entityName - Entity name
 * @param getSocket - Function to get the socket instance
 * @returns Entity handler with CRUD methods
 * @internal
 */
function createEntityHandler(axios, appId, entityName, getSocket) {
    const baseURL = `/apps/${appId}/entities/${entityName}`;
    const fieldsParam = (fields) => Array.isArray(fields) ? fields.join(",") : fields;
    // GET /{entity}: the array form shared by list() and filter()
    const readArray = (sort, limit, skip, fields, query) => {
        const params = {};
        if (query)
            params.q = JSON.stringify(query);
        if (sort)
            params.sort = sort;
        if (limit)
            params.limit = limit;
        if (skip)
            params.skip = skip;
        if (fields)
            params.fields = fieldsParam(fields);
        return axios.get(baseURL, { params });
    };
    // GET /{entity}/v2/list: one cursor page of records or distinct values, shared by list(options) and filter(query, options)
    const readPage = (options, query) => {
        const params = {};
        if (query)
            params.q = JSON.stringify(query);
        params.limit = options.limit || DEFAULT_PAGE_LIMIT;
        if (options.cursor)
            params.cursor = options.cursor;
        if ("distinct" in options) {
            params.distinct = options.distinct;
        }
        else {
            if (options.sort)
                params.sort = options.sort;
            if (options.fields)
                params.fields = fieldsParam(options.fields);
        }
        return axios.get(`${baseURL}/v2/list`, { params });
    };
    return {
        // list(sort, limit, skip, fields) returns an array; list(options) returns one cursor page.
        async list(...args) {
            const [sort, limit, skip, fields] = args;
            return isPageOptions(sort) ? readPage(sort) : readArray(sort, limit, skip, fields);
        },
        // filter(query, sort, limit, skip, fields) returns an array; filter(query, options) returns one cursor page.
        async filter(query, ...args) {
            const [sort, limit, skip, fields] = args;
            return isPageOptions(sort) ? readPage(sort, query) : readArray(sort, limit, skip, fields, query);
        },
        // Get entity by ID
        async get(id) {
            return axios.get(`${baseURL}/${id}`);
        },
        // Create new entity
        async create(data) {
            return axios.post(baseURL, data);
        },
        // Update entity by ID
        async update(id, data) {
            return axios.put(`${baseURL}/${id}`, data);
        },
        // Delete entity by ID
        async delete(id) {
            return axios.delete(`${baseURL}/${id}`);
        },
        // Delete multiple entities based on query
        async deleteMany(query) {
            return axios.delete(baseURL, { data: query });
        },
        // Create multiple entities in a single request
        async bulkCreate(data) {
            return axios.post(`${baseURL}/bulk`, data);
        },
        // Update multiple entities matching a query using a MongoDB update operator
        async updateMany(query, data) {
            return axios.patch(`${baseURL}/update-many`, { query, data });
        },
        // Count entities matching a query
        async count(query) {
            const params = {};
            if (query)
                params.q = JSON.stringify(query);
            const result = await axios.get(`${baseURL}/count`, { params });
            return result.count;
        },
        // Server-side group-by aggregation
        async aggregate(spec) {
            return axios.post(`${baseURL}/aggregate`, spec);
        },
        // Create or update by a natural key
        async upsert(records, options) {
            return axios.post(`${baseURL}/upsert`, { records, key: options.key });
        },
        // Update multiple entities by ID, each with its own update data
        async bulkUpdate(data) {
            return axios.put(`${baseURL}/bulk`, data);
        },
        // Import entities from a file
        async importEntities(file) {
            const formData = new FormData();
            formData.append("file", file, file.name);
            return axios.post(`${baseURL}/import`, formData, {
                headers: {
                    "Content-Type": "multipart/form-data",
                },
            });
        },
        // Subscribe to realtime updates
        subscribe(callback) {
            const room = `entities:${appId}:${entityName}`;
            // Get the socket and subscribe to the room
            const socket = getSocket();
            const unsubscribe = socket.subscribeToRoom(room, {
                update_model: (msg) => {
                    var _a;
                    const event = parseRealtimeMessage(msg.data);
                    if (!event) {
                        return;
                    }
                    // Server signals oversize broadcasts with `_oversize: true` on
                    // `data`. The wire payload was slimmed to fit under the realtime
                    // transport cap, so big string fields arrive as empty strings (or
                    // the whole record collapses to a stub). Surface this to the
                    // developer console so they know to fetch the full record on
                    // demand (e.g. a follow-up entities.X.get(id) call) instead of
                    // rendering the slimmed payload directly. Skip on delete events
                    // — the record no longer exists.
                    if (event.type !== "delete" && ((_a = event.data) === null || _a === void 0 ? void 0 : _a._oversize)) {
                        console.error(`[Base44 SDK] Realtime broadcast for ${entityName}#${event.id} was oversize and got slimmed for transport. ` +
                            `Fields >10 KB are empty and the rest of the record may be a stub. ` +
                            `Call \`entities.${entityName}.get("${event.id}")\` to fetch the full record.`);
                    }
                    try {
                        callback(event);
                    }
                    catch (error) {
                        console.error("[Base44 SDK] Subscription callback error:", error);
                    }
                },
            });
            return unsubscribe;
        },
    };
}
