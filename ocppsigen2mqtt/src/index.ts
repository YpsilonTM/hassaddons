import { OcppServer } from './ocppServer';
import { MqttClient } from './mqttClient';

const OCPP_SERVER_PORT = parseInt(process.env.OCPP_PORT || '9200', 10);
const MQTT_HOST = process.env.MQTT_HOST || 'core-mosquitto';
const MQTT_PORT = process.env.MQTT_PORT || '1883';
const MQTT_USER = process.env.MQTT_USER || '';
const MQTT_PASS = process.env.MQTT_PASS || '';
const CHARGER_ID = process.env.CHARGER_ID || 'unknown';
const MQTT_TOPIC_PREFIX = process.env.MQTT_TOPIC_PREFIX || 'ocpp';

async function main() {
    console.log('Starting OCPP Server & MQTT Bridge...');

    const mqttBrokerUrl = `mqtt://${MQTT_HOST}:${MQTT_PORT}`;
    const mqttClient = new MqttClient(mqttBrokerUrl, MQTT_USER, MQTT_PASS);

    try {
        await mqttClient.connect();
        console.log('MQTT Client connected successfully.');
    } catch (error) {
        console.error('Failed to connect to MQTT broker:', error);
        return; // Exit if MQTT fails
    }

    const ocppServer = new OcppServer(OCPP_SERVER_PORT);
    ocppServer.start();

    // Publish Home Assistant MQTT Discovery configuration
    const deviceConfig = {
        identifiers: [CHARGER_ID],
        name: "Sigenergy EVAC",
        manufacturer: "Sigenergy"
    };

    const discoveryTopics = [
        {
            topic: `homeassistant/sensor/${CHARGER_ID}_current/config`,
            payload: {
                name: "Charging Current",
                state_topic: `${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/state`,
                value_template: "{{ value_json.current }}",
                unit_of_measurement: "A",
                device_class: "current",
                unique_id: `${CHARGER_ID}_current`,
                device: deviceConfig
            }
        },
        {
            topic: `homeassistant/sensor/${CHARGER_ID}_power/config`,
            payload: {
                name: "Charging Power",
                state_topic: `${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/state`,
                value_template: "{{ value_json.power }}",
                unit_of_measurement: "W",
                device_class: "power",
                unique_id: `${CHARGER_ID}_power`,
                device: deviceConfig
            }
        },
        {
            topic: `homeassistant/sensor/${CHARGER_ID}_energy/config`,
            payload: {
                name: "Total Energy",
                state_topic: `${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/state`,
                value_template: "{{ value_json.energy }}",
                unit_of_measurement: "Wh",
                device_class: "energy",
                state_class: "total_increasing",
                unique_id: `${CHARGER_ID}_energy`,
                device: deviceConfig
            }
        },
        {
            topic: `homeassistant/sensor/${CHARGER_ID}_status/config`,
            payload: {
                name: "Status",
                state_topic: `${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/state`,
                value_template: "{{ value_json.status }}",
                unique_id: `${CHARGER_ID}_status`,
                device: deviceConfig
            }
        },
        {
            topic: `homeassistant/button/${CHARGER_ID}_start/config`,
            payload: {
                name: "Start Charging",
                command_topic: `${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/command`,
                payload_press: "START",
                unique_id: `${CHARGER_ID}_start`,
                icon: "mdi:ev-station",
                device: deviceConfig
            }
        },
        {
            topic: `homeassistant/button/${CHARGER_ID}_stop/config`,
            payload: {
                name: "Stop Charging",
                command_topic: `${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/command`,
                payload_press: "STOP",
                unique_id: `${CHARGER_ID}_stop`,
                icon: "mdi:stop-circle-outline",
                device: deviceConfig
            }
        }
    ];

    for (const conf of discoveryTopics) {
        await mqttClient.publish(conf.topic, JSON.stringify(conf.payload), true);
    }
    console.log('Home Assistant MQTT Discovery published.');

    // State cache to avoid sending duplicate empty states
    const stateCache: any = {
        status: "Unknown",
        current: 0,
        power: 0,
        energy: 0
    };

    const publishState = () => {
        mqttClient.publish(`${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/state`, JSON.stringify(stateCache), true);
    };

    // Listen to OCPP Server Events
    ocppServer.on('status', (chargePointId, status) => {
        if (chargePointId === CHARGER_ID) {
            stateCache.status = status;
            
            // If the charger is no longer actively charging, zero out the current and power
            if (status !== 'Charging') {
                stateCache.current = 0;
                stateCache.power = 0;
            }
            
            publishState();
        }
    });

    ocppServer.on('meterValues', (chargePointId, data) => {
        if (chargePointId === CHARGER_ID) {
            if (data.current !== undefined) stateCache.current = data.current;
            if (data.power !== undefined) stateCache.power = data.power;
            if (data.energy !== undefined) stateCache.energy = data.energy;
            publishState();
        }
    });

    // Listen for incoming MQTT Commands from Home Assistant
    mqttClient.subscribe(`${MQTT_TOPIC_PREFIX}/${CHARGER_ID}/command`, (message) => {
        const cmd = message.trim().toUpperCase();
        console.log(`Received MQTT Command: ${cmd}`);
        if (cmd === 'START') {
            ocppServer.sendRemoteStartTransaction(CHARGER_ID);
        } else if (cmd === 'STOP') {
            ocppServer.sendRemoteStopTransaction(CHARGER_ID);
        }
    });
}

main();