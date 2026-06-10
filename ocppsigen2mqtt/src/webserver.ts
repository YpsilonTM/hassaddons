// src/webserver.ts

import express from 'express';
import path from 'path';
import { OcppServer } from './ocppServer'; // Import OcppServer

export class WebServer {
    private app: express.Application;
    private port: number;
    private ocppServer: OcppServer; // Add ocppServer property

    constructor(port: number, ocppServer: OcppServer) { // Accept ocppServer in constructor
        this.app = express();
        this.port = port;
        this.ocppServer = ocppServer; // Assign ocppServer

        this.setupRoutes();
    }

    private setupRoutes() {
        // Serve static files from the 'public' directory
        this.app.use(express.static(path.join(__dirname, '..' , 'public')));
        this.app.use(express.json()); // Enable JSON body parsing

        this.app.post('/start', async (req, res) => {
            const { chargePointId, connectorId, idTag } = req.body;
            
            // Fallback to environment variables or defaults if not provided in request
            // Ensure CHARGER_ID is treated as a string even if it looks like a number
            const targetChargePointId = chargePointId || process.env.CHARGER_ID?.toString();
            const targetConnectorId = connectorId || 1;

            console.log(`Webserver received /start request for ChargePointId: ${targetChargePointId}`);
            
            if (!targetChargePointId) {
                return res.status(400).send('Missing chargePointId and no CHARGER_ID env variable set');
            }

            try {
                await this.ocppServer.sendRemoteStartTransaction(targetChargePointId, targetConnectorId, idTag);
                res.status(200).send('RemoteStartTransaction sent');
            } catch (error: any) {
                console.error('Error in /start:', error.message);
                res.status(500).send(`Error sending RemoteStartTransaction: ${error.message}`);
            }
        });

        this.app.post('/stop', async (req, res) => {
            const { chargePointId } = req.body;
            
            // Fallback to environment variable if not provided
            const targetChargePointId = chargePointId || process.env.CHARGER_ID?.toString();

            console.log(`Webserver received /stop request for ChargePointId: ${targetChargePointId}`);
            
            if (!targetChargePointId) {
                return res.status(400).send('Missing chargePointId and no CHARGER_ID env variable set');
            }

            try {
                await this.ocppServer.sendRemoteStopTransaction(targetChargePointId);
                res.status(200).send('RemoteStopTransaction sent');
            } catch (error: any) {
                console.error('Error in /stop:', error.message);
                res.status(500).send(`Error sending RemoteStopTransaction: ${error.message}`);
            }
        });

        this.app.post('/limit', async (req, res) => {
            const { chargePointId, amperes, connectorId } = req.body;
            
            // Fallback to environment variables or defaults if not provided in request
            const targetChargePointId = chargePointId || process.env.CHARGER_ID?.toString();
            const targetConnectorId = connectorId || 1;

            console.log(`Webserver received /limit request for ChargePointId: ${targetChargePointId}, Amperes: ${amperes}`);
            
            if (!targetChargePointId) {
                return res.status(400).send('Missing chargePointId and no CHARGER_ID env variable set');
            }

            if (amperes === undefined || amperes === null) {
                return res.status(400).send('Missing amperes');
            }

            try {
                await this.ocppServer.sendSetLimitAmperes(targetChargePointId, amperes, targetConnectorId);
                res.status(200).send(`Set charging limit to ${amperes}A sent`);
            } catch (error: any) {
                console.error('Error in /limit:', error.message);
                res.status(500).send(`Error sending SetChargingProfile: ${error.message}`);
            }
        });

        this.app.post('/getconfig', async (req, res) => {
            const { chargePointId, keys } = req.body;
            
            const targetChargePointId = chargePointId || process.env.CHARGER_ID?.toString();

            console.log(`Webserver received /getconfig request for ChargePointId: ${targetChargePointId}`);
            
            if (!targetChargePointId) {
                return res.status(400).send('Missing chargePointId');
            }

            try {
                await this.ocppServer.sendGetConfiguration(targetChargePointId, keys);
                res.status(200).send(`GetConfiguration sent`);
            } catch (error: any) {
                console.error('Error in /getconfig:', error.message);
                res.status(500).send(`Error sending GetConfiguration: ${error.message}`);
            }
        });
    }

    start(): void {
        this.app.listen(this.port, () => {
            console.log(`Webserver listening on port ${this.port}`);
            console.log(`Open http://localhost:${this.port} in your browser to test.`);
        });
    }
}
