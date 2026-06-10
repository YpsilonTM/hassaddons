import { WebSocket, WebSocketServer } from 'ws';
import { v4 as uuidv4 } from 'uuid';
import { EventEmitter } from 'events';

export type OcppMessage = 
    | [2, string, string, any]                 // CALL
    | [3, string, any]                         // CALLRESULT
    | [4, string, string, string, any];        // CALLERROR

export class OcppServer extends EventEmitter {
    private wss: WebSocketServer;
    private connectedClients: Map<string, WebSocket> = new Map();
    private activeTransactions: Map<string, number> = new Map();

    constructor(port: number) {
        super();
        this.wss = new WebSocketServer({ 
            port,
            handleProtocols: (protocols) => {
                if (protocols.has('ocpp1.6')) return 'ocpp1.6';
                return false;
            }
        });
    }

    start(): void {
        this.wss.on('connection', (ws: WebSocket, req) => {
            const urlParts = req.url?.split('/');
            const chargePointId = urlParts ? urlParts[urlParts.length - 1] : 'unknown';

            if (this.connectedClients.has(chargePointId)) {
                console.warn(`[OCPP] ChargePoint ${chargePointId} is already connected. Closing new connection.`);
                ws.close(1008, 'Already connected');
                return;
            }

            console.log(`[OCPP] ChargePoint ${chargePointId} connected successfully matching subprotocol 'ocpp1.6'`);
            this.connectedClients.set(chargePointId, ws);

            ws.on('message', (message: string) => {
                this.handleOcppMessage(chargePointId, message.toString());
            });

            ws.on('close', () => {
                console.log(`[OCPP] ChargePoint ${chargePointId} disconnected`);
                this.connectedClients.delete(chargePointId);
            });

            ws.on('error', (error) => {
                console.error(`[OCPP] ChargePoint ${chargePointId} WebSocket error:`, error.message);
                this.connectedClients.delete(chargePointId);
            });
        });

        this.wss.on('listening', () => {
            console.log(`[OCPP] Server listening on port ${this.wss.options.port}`);
        });

        this.wss.on('error', (error) => {
            console.error('[OCPP] Server error:', error);
        });
    }

    private async handleOcppMessage(chargePointId: string, message: string) {
        try {
            const parsedMessage = JSON.parse(message);
            if (!Array.isArray(parsedMessage)) {
                console.error(`[OCPP] Invalid message format from ${chargePointId}. Expected JSON Array.`);
                return;
            }

            const messageTypeId = parsedMessage[0];
            const uniqueId = parsedMessage[1];

            if (typeof uniqueId !== 'string' || !uniqueId) {
                console.error(`[OCPP] Missing or invalid UniqueId in message from ${chargePointId}`);
                return;
            }

            switch (messageTypeId) {
                case 2: { // CALL (Request from Charge Point)
                    const [,, action, payload] = parsedMessage as [number, string, string, any];
                    console.log(`[OCPP] CALL from ${chargePointId} - UniqueId: ${uniqueId}, Action: ${action}, Payload:`, payload);

                    if (action === 'BootNotification') {
                        // Aligned with Sigenergy Annex B config parameters (HeartbeatInterval default: 90 seconds)
                        this.sendCallResult(chargePointId, uniqueId, { 
                            currentTime: new Date().toISOString(), 
                            interval: 90, 
                            status: 'Accepted' 
                        });
                        console.log(`[OCPP] Sent BootNotification.conf to ${chargePointId}`);

                    } else if (action === 'Authorize') {
                        this.sendCallResult(chargePointId, uniqueId, { 
                            idTagInfo: { 
                                status: 'Accepted',
                                expiryDate: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString() // 24 hour buffer
                            } 
                        });
                        console.log(`[OCPP] Sent Authorize.conf to ${chargePointId}`);

                    } else if (action === 'Heartbeat') {
                        this.sendCallResult(chargePointId, uniqueId, { 
                            currentTime: new Date().toISOString() 
                        });
                        console.log(`[OCPP] Sent Heartbeat.conf to ${chargePointId}`);

                    } else if (action === 'MeterValues') {
                        // Recover active transaction if needed
                        if (payload.transactionId && typeof payload.transactionId === 'number') {
                            if (this.activeTransactions.get(chargePointId) !== payload.transactionId) {
                                this.activeTransactions.set(chargePointId, payload.transactionId);
                            }
                        } else if (!this.activeTransactions.has(chargePointId)) {
                            this.activeTransactions.set(chargePointId, payload.connectorId || 1);
                        }

                        // Parse MeterValues for Home Assistant
                        let current: number | undefined;
                        let power: number | undefined;
                        let energy: number | undefined;

                        for (const mv of payload.meterValue || []) {
                            for (const sv of mv.sampledValue || []) {
                                if (sv.measurand === 'Current.Import') current = parseFloat(sv.value);
                                if (sv.measurand === 'Power.Active.Import') power = parseFloat(sv.value);
                                if (sv.measurand === 'Energy.Active.Import.Register') energy = parseFloat(sv.value);
                            }
                        }

                        if (current !== undefined || power !== undefined || energy !== undefined) {
                            this.emit('meterValues', chargePointId, { current, power, energy });
                        }

                        this.sendCallResult(chargePointId, uniqueId, {});

                    } else if (action === 'StatusNotification') {
                        this.emit('status', chargePointId, payload.status);
                        this.sendCallResult(chargePointId, uniqueId, {});

                    } else if (action === 'StartTransaction') {
                        const transactionId = payload.connectorId || 1;
                        this.activeTransactions.set(chargePointId, transactionId);
                        
                        this.sendCallResult(chargePointId, uniqueId, { 
                            idTagInfo: { status: 'Accepted' }, 
                            transactionId: transactionId 
                        });
                        console.log(`[OCPP] StartTransaction for ${chargePointId} (TxId: ${transactionId})`);

                    } else if (action === 'StopTransaction') {
                        this.activeTransactions.delete(chargePointId);
                        
                        // Emit 0 for current/power and update final energy from meterStop
                        if (payload.meterStop !== undefined) {
                            this.emit('meterValues', chargePointId, { 
                                current: 0, 
                                power: 0, 
                                energy: payload.meterStop 
                            });
                        }

                        this.sendCallResult(chargePointId, uniqueId, { 
                            idTagInfo: { status: 'Accepted' } 
                        });
                        console.log(`[OCPP] StopTransaction for ${chargePointId}`);

                    } else {
                        console.warn(`[OCPP] Unhandled OCPP action from ${chargePointId}: ${action}`);
                        this.sendCallError(chargePointId, uniqueId, 'NotImplemented', `Action '${action}' is not supported.`, {});
                    }
                    break;
                }

                case 3: { // CALLRESULT (Response from Charge Point to our Remote commands)
                    const [,, payload] = parsedMessage as [number, string, any];
                    console.log(`[OCPP] CALLRESULT from ${chargePointId} - UniqueId: ${uniqueId}, Payload:`, payload);
                    
                    if (payload.status === 'Accepted' || payload.status === 'Rejected') {
                        console.log(`[OCPP] Command outcome for ${chargePointId}: ${payload.status}`);
                    }
                    break;
                }

                case 4: { // CALLERROR (Error response from Charge Point)
                    const [,, errorCode, errorDescription, errorDetails] = parsedMessage as [number, string, string, string, any];
                    console.error(`[OCPP] CALLERROR from ${chargePointId} - UniqueId: ${uniqueId}`, {
                        errorCode,
                        errorDescription,
                        errorDetails
                    });
                    break;
                }

                default:
                    console.warn(`[OCPP] Unknown OCPP message type from ${chargePointId}: ${messageTypeId}`);
            }
        } catch (error) {
            console.error(`[OCPP] Error parsing message from ${chargePointId}:`, error);
        }
    }

    /**
     * Core transmission engine. Encapsulates standard payload stringifying.
     */
    private sendRaw(chargePointId: string, messageArray: OcppMessage) {
        const ws = this.connectedClients.get(chargePointId);
        if (ws && ws.readyState === WebSocket.OPEN) {
            const message = JSON.stringify(messageArray);
            ws.send(message);
            console.log(`[OCPP] Message sent to ${chargePointId}:`, message);
        } else {
            console.warn(`[OCPP] ChargePoint ${chargePointId} WebSocket not open. Message dropped.`);
        }
    }

    /**
     * Sends a CALL (Server-to-ChargePoint Action Request)
     */
    public sendCall(chargePointId: string, uniqueId: string, action: string, payload: object) {
        this.sendRaw(chargePointId, [2, uniqueId, action, payload]);
    }

    /**
     * Sends a CALLRESULT (Successful Response to a ChargePoint Request)
     */
    public sendCallResult(chargePointId: string, uniqueId: string, payload: object) {
        this.sendRaw(chargePointId, [3, uniqueId, payload]);
    }

    /**
     * Sends a CALLERROR (Error Response to a ChargePoint Request)
     */
    public sendCallError(chargePointId: string, uniqueId: string, errorCode: string, errorDescription: string, errorDetails: object = {}) {
        this.sendRaw(chargePointId, [4, uniqueId, errorCode, errorDescription, errorDetails]);
    }

    public sendRemoteStartTransaction(chargePointId: string, connectorId: number = 1, idTag?: string): string {
        const uniqueId = uuidv4();
        const payload: any = { connectorId };
        payload.idTag = idTag || process.env.OCPP_RFID_TAG || 'HomeAssistant';
        this.sendCall(chargePointId, uniqueId, 'RemoteStartTransaction', payload);
        return uniqueId;
    }

    public sendRemoteStopTransaction(chargePointId: string): string {
        const uniqueId = uuidv4();
        const targetTransactionId = this.activeTransactions.get(chargePointId) || 1;
        const payload = { transactionId: targetTransactionId };
        this.sendCall(chargePointId, uniqueId, 'RemoteStopTransaction', payload);
        return uniqueId;
    }

    public sendChangeAvailability(chargePointId: string, type: 'Operative' | 'Inoperative', connectorId: number = 1): string {
        const uniqueId = uuidv4();
        this.sendCall(chargePointId, uniqueId, 'ChangeAvailability', { connectorId, type });
        return uniqueId;
    }
}