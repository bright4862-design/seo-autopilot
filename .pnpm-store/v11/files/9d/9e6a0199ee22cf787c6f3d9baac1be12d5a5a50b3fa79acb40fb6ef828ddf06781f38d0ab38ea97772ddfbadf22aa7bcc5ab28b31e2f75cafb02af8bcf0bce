/**
 * Type-only base class for Actors.
 *
 * Import and extend this in your actor files:
 *   import { Actor } from "@base44/sdk";
 *   export class MyActor extends Actor { ... }
 *
 * At deploy time the bundler replaces this import with the compiled
 * Cloudflare Durable Object implementation — this file provides types only.
 */
/**
 * Base class for an Actor.
 *
 * @typeParam Incoming - messages this actor *receives* from clients
 *   (`handleMessage`'s `msg`) — the schema's `toServer` section.
 * @typeParam Outgoing - messages this actor *sends* to clients
 *   (`conn.send`/`broadcast`) — the schema's `toClient` section.
 *
 * With a generated `schema.jsonc`, wire both from the registry so they can't drift
 * from the client's types:
 * ```ts
 * type Reg = ActorRegistry["MyActor"];
 * class MyActor extends Actor<Reg["toServer"], Reg["toClient"]> { ... }
 * ```
 */
export class Actor {
    constructor() {
        /**
         * Managed ticker (opt-in). Override {@link shouldTick} and the platform runs
         * {@link handleTick} on a timer of {@link tickIntervalMs} while it returns true,
         * and stops (letting the Durable Object hibernate — no compute cost) when it
         * returns false. The platform owns scheduling, rescheduling, self-heal, and
         * error-safety.
         *
         * Re-evaluated after every connect/message/close and on every tick, so keep it
         * cheap and pure (no async, no side effects). Example: `return this.players >= 2`.
         */
        this.tickIntervalMs = 100;
    }
    /**
     * Optional wake hook: runs once when the instance starts, before any
     * connection is handled — safe to load persisted state here.
     */
    handleStart() { }
    /**
     * Optional handler for scheduled wakes. Runs when a timer armed via
     * {@link schedule} comes due, receiving the same `key` that was scheduled.
     * The schedule is one-shot: it fires once and is cleared before this runs.
     */
    handleWake(_key) { }
    /**
     * Arm a one-shot wake at `at` (epoch ms or a `Date`), identified by `key`.
     * When it comes due the platform calls {@link handleWake} with this `key`.
     * Scheduling the same `key` again reschedules it.
     */
    schedule(_key, _at) {
        throw new Error("Actor.schedule() is only available inside a deployed actor");
    }
    /** Cancel a pending wake previously armed with {@link schedule}. */
    cancelSchedule(_key) {
        throw new Error("Actor.cancelSchedule() is only available inside a deployed actor");
    }
    broadcast(_data) {
        throw new Error("Actor.broadcast() is only available inside a deployed actor");
    }
    getConnections() {
        throw new Error("Actor.getConnections() is only available inside a deployed actor");
    }
    get instanceId() {
        throw new Error("Actor.instanceId is only available inside a deployed actor");
    }
    get storage() {
        throw new Error("Actor.storage is only available inside a deployed actor");
    }
    /**
     * Anonymous Base44 client scoped to this actor instance — no user or service
     * auth, so entity access is RLS-gated (same as a logged-out visitor). Always
     * operates on production data: an actor runs server-side with no per-connection
     * identity, so a Test DB preview selected in the editor does not apply here.
     * Example: `const rows = await this.client.entities.Score.list();`
     */
    get client() {
        throw new Error("Actor.client is only available inside a deployed actor");
    }
}
