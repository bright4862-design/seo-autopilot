import { Socket } from "socket.io-client";
export interface RoomsSocketConfig {
    serverUrl: string;
    mountPath: string;
    transports: string[];
    appId: string;
    token?: string;
}
export type TSocketRoom = string;
export type TJsonStr = string;
type RoomsSocketEventsMap = {
    listen: {
        connect: () => Promise<void> | void;
        update_model: (msg: {
            room: string;
            data: TJsonStr;
        }) => Promise<void> | void;
        error: (error: Error) => Promise<void> | void;
    };
    emit: {
        join: (room: string) => void;
        leave: (room: string) => void;
    };
};
type TEvent = keyof RoomsSocketEventsMap["listen"];
type THandler<E extends TEvent> = RoomsSocketEventsMap["listen"][E];
export type RoomsSocket = ReturnType<typeof RoomsSocket>;
export declare function RoomsSocket({ config }: {
    config: RoomsSocketConfig;
}): {
    socket: Socket<{
        connect: () => Promise<void> | void;
        update_model: (msg: {
            room: string;
            data: TJsonStr;
        }) => Promise<void> | void;
        error: (error: Error) => Promise<void> | void;
    }, {
        join: (room: string) => void;
        leave: (room: string) => void;
    }>;
    subscribeToRoom: (room: TSocketRoom, handlers: Partial<{ [k in TEvent]: THandler<k>; }>) => () => void;
    updateConfig: (config: Partial<RoomsSocketConfig>) => void;
    updateModel: (room: string, data: any) => Promise<void>;
    disconnect: () => void;
};
export {};
