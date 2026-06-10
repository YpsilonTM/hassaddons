// src/mqttClient.ts

import * as mqtt from 'mqtt';

export class MqttClient {
    private client: mqtt.MqttClient | null = null;
    private mqttBrokerUrl: string;
    private mqttUsername?: string;
    private mqttPassword?: string;

    constructor(mqttBrokerUrl: string, mqttUsername?: string, mqttPassword?: string) {
        this.mqttBrokerUrl = mqttBrokerUrl;
        this.mqttUsername = mqttUsername;
        this.mqttPassword = mqttPassword;
    }

    connect(): Promise<void> {
        return new Promise((resolve, reject) => {
            const options: mqtt.IClientOptions = {
                keepalive: 60,
                reconnectPeriod: 1000,
                protocolId: 'MQTT',
                protocolVersion: 4,
                clean: true,
                resubscribe: true,
            };

            if (this.mqttUsername) {
                options.username = this.mqttUsername;
            }
            if (this.mqttPassword) {
                options.password = this.mqttPassword;
            }

            this.client = mqtt.connect(this.mqttBrokerUrl, options);

            this.client.on('connect', () => {
                console.log('MQTT client connected');
                resolve();
            });

            this.client.on('error', (err) => {
                console.error('MQTT client error:', err);
                this.client?.end();
                reject(err);
            });

            this.client.on('close', () => {
                console.log('MQTT client disconnected');
                // Implement reconnection logic here if not handled by mqtt.js
            });
        });
    }

    subscribe(topic: string, callback: (message: string) => void): void {
        if (!this.client) return;
        this.client.subscribe(topic, (err) => {
            if (err) console.error(`Failed to subscribe to ${topic}`, err);
            else console.log(`Subscribed to MQTT topic: ${topic}`);
        });

        this.client.on('message', (t, msg) => {
            if (t === topic) {
                callback(msg.toString());
            }
        });
    }

    publish(topic: string, message: string, retain: boolean = false): Promise<void> {
        return new Promise((resolve, reject) => {
            if (this.client && this.client.connected) {
                this.client.publish(topic, message, { qos: 0, retain }, (err) => {
                    if (err) {
                        console.error('Failed to publish MQTT message:', err);
                        return reject(err);
                    }
                    console.log(`MQTT message published to topic '${topic}': ${message}`);
                    resolve();
                });
            } else {
                const errorMessage = 'MQTT client not connected. Message not published.';
                console.warn(errorMessage);
                reject(new Error(errorMessage));
            }
        });
    }

    close(): void {
        if (this.client) {
            this.client.end();
            console.log('MQTT client closed');
        }
    }
}
