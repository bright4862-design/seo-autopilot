const windowObj = typeof window !== "undefined"
    ? window
    : { base44SharedInstances: {} };
// Singleton (shared between sdk instances)//
export function getSharedInstance(name, factory) {
    if (!windowObj.base44SharedInstances) {
        windowObj.base44SharedInstances = {};
    }
    if (!windowObj.base44SharedInstances[name]) {
        windowObj.base44SharedInstances[name] = {
            instance: factory(),
        };
    }
    return windowObj.base44SharedInstances[name].instance;
}
